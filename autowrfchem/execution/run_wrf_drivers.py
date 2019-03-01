from __future__ import print_function, absolute_import, division, unicode_literals

from datetime import datetime as dtime
from glob import glob
import os
import shutil
from subprocess import CalledProcessError

from .. import common_utils, wrf_date_fmt, _pretty_n_col, config_dir
from ..configuration import autowrf_classlib as awclib, config_utils, RUNTIME, DO_REINIT, REINIT_FREQ, REINIT_RUN_TIME
from . import ensembles

import pdb

class WRFRunError(Exception):
    """
    Superclass for errors that occur while running WRF
    """
    pass


class MissingInputFileError(WRFRunError):
    """
    Error to throw if required input files are missing
    """
    pass


class InputDataError(WRFRunError):
    """
    Error to use if there is something incorrect about the input data
    """
    pass


def _check_for_missing_files(wrf_dir, config_obj):

    missing_files = []

    def check_helper(file_pattern, domain):
        filename = file_pattern.format(domain)
        if not os.path.isfile(os.path.join(wrf_dir, filename)):
            missing_files.append(filename)

    nlc = awclib.NamelistContainer.load_namelists()

    # only need wrfbdy for the first domain
    check_helper('wrfbdy_d{:02d}', 1)

    max_dom = nlc.wrf_namelist.max_domains
    for dom in range(1, max_dom+1):
        # Always need wrfinput_dXX and wrfbdy_dXX files
        check_helper('wrfinput_d{:02d}', dom)

        # Only need these if running chemistry
        if config_utils.get_is_chem(config_obj):
            check_helper('wrfchemi_00z_d{:02d}', dom)
            check_helper('wrfchemi_12z_d{:02d}', dom)
            check_helper('wrfbiochemi_d{:02d}', dom)

    if len(missing_files) > 0:
        file_list = '\n  * '.join(sorted(missing_files))
        msg = '{} required input files are missing:\n  * {}\nAborting run'.format(len(missing_files), file_list)
        raise MissingInputFileError(msg)


def _date_of_rst_file(rst_files, namelist_container):
    n_dom = namelist_container.wrf_namelist.max_domains

    restart_dates = []

    for dom in range(1, n_dom+1):
        dom_str = 'd{:02d}'.format(dom)
        domain_rst_files = sorted([f for f in rst_files if dom_str in f])
        last_file_date_str = common_utils.wrf_date_re.search(domain_rst_files[-1]).group()
        last_file_datetime = dtime.strptime(last_file_date_str, wrf_date_fmt)
        restart_dates.append(last_file_datetime)

    # require that all the domains have a restart file for the same time.
    if not all([d == restart_dates[0] for d in restart_dates]):
        raise InputDataError('The last restart files for the domains have different dates ({})'
                             .format(', '.join([str(d) for d in restart_dates])))

    return restart_dates[0]


def _run_wrf_once(wrf_dir, ntasks, dry_run=False, config_obj=None):
    
    _check_for_missing_files(wrf_dir, config_obj)

    if ntasks > 0:
        # when WRF runs under MPI it automatically saves terminal from each task to an rsl.{out,error}.NNNN file so
        # we don't need to make a log file ourselves
        common_utils.run_external_mpi('./wrf.exe', ntasks=ntasks, cwd=wrf_dir, config_obj=config_obj, dry_run=dry_run)
    else:
        with open(os.path.join(wrf_dir, 'wrfrun.log'), 'w') as logfile:
            common_utils.run_external('./wrf.exe', config_obj, cwd=wrf_dir, logfile_handle=logfile,
                                      dry_run=dry_run)


def _run_wrf(wrf_dir, ntasks, dry_run=False, config_obj=None, alt_namelist=None):
    if config_obj is None:
        config_obj = config_utils.AutoWRFChemConfig()

    if not config_obj[RUNTIME].as_bool(DO_REINIT):
        return _run_wrf_once(wrf_dir, ntasks, dry_run=dry_run, config_obj=config_obj)

    reinit_freq = config_utils.get_reinit_freq(config_obj)
    reinit_run_time = config_utils.get_reinit_runtime(config_obj)

    if alt_namelist is None:
        # If not alternate persistent namelist specified, then we use the namelist container to load the default one.
        # The WrfNamelist class has no method to load the default file defined.
        nlc = awclib.NamelistContainer.load_namelists()

    else:
        # If there is an alternate namelist file specified, create a namelist container with it. This loads the standard
        # registry, which is simpler, but means that if wrf_dir points to a WRF copy using a different registry, it will
        # be inconsistent. But right now, that problem affects all runs.
        nlc = awclib.NamelistContainer(wrffile=alt_namelist,
                                       wpsfile=os.path.join(config_dir, awclib.NamelistContainer.wps_namelist_outfile))

    wrf_nl = nlc.wrf_namelist
    model_start_time, model_end_time = wrf_nl.get_time_period()

    exec_start_time = dtime.now()

    for reinit_dir, start_time in common_utils._iter_reinit_dirs(wrf_dir, model_start_time, model_end_time, reinit_freq):
        # Reset the WRF namelist so we only run this time period
        wrf_nl.set_run_time(reinit_run_time, start_time)
        wrf_nl.write_namelist(os.path.join(wrf_dir, 'namelist.input'))

        if not dry_run:
            print('Deleting previous wrfout files in {}'.format(reinit_dir))
            common_utils.rmfiles(os.path.join(reinit_dir, 'wrfout*'))

        # Link all the previously prepared input files for this time period to the main run directory
        input_files = glob(os.path.join(reinit_dir, 'wrf*'))
        for input_file in input_files:
            if input_file.startswith('wrfout'):
                # Just in case there are somehow wrf output in the input directory, don't relink them
                continue

            input_file_basename = os.path.basename(input_file)
            input_file_link = os.path.join(wrf_dir, input_file_basename)

            if not dry_run:
                if os.path.exists(input_file_link):
                    os.remove(input_file_link)

                # input_file should be an absolute path, so this shouldn't pose a problem
                print('Linking {} -> {}'.format(input_file, input_file_link))
                os.symlink(input_file, input_file_link)
            else:
                print('Would link {0} -> {1}, overwriting the first if needed'.format(input_file_link, input_file))

        # TODO: make this flexible enough to submit separate jobs for each run segment, rather than all as one
        _run_wrf_once(wrf_dir, ntasks, dry_run=dry_run, config_obj=config_obj)

        # Move all newly created WRF output files to the reinit dir. Don't move files older than when this started,
        # that would get confusing if the user left old wrfout files in the run directory
        output_files = glob(os.path.join(wrf_dir, 'wrfout*'))
        for out_file in output_files:
            ctime = dtime.fromtimestamp(os.path.getctime(out_file))
            if ctime >= exec_start_time:
                if dry_run:
                    print('Would move {} -> {}'.format(out_file, reinit_dir))
                else:
                    shutil.move(out_file, reinit_dir)


def _fmt_namelist_path(nl_path, wrf_dir=None, config_obj=None):
    if wrf_dir is None:
        wrf_dir = config_utils.get_wrf_run_dir(config_obj)

    return nl_path.format(WRF_DIR=wrf_dir, CFG_DIR=config_dir)


def _set_model_run_time(wrf_dir, do_restart, require_rst_file, run_for=None):
    nlc = awclib.NamelistContainer.load_namelists()
    start_date = None
    if do_restart:
        rst_files = glob(os.path.join(wrf_dir, 'wrfrst*'))

        if len(rst_files) == 0:
            if require_rst_file:
                raise MissingInputFileError('No wrfrst file found, and require_rst_file is True')
        else:
            start_date = _date_of_rst_file(rst_files, nlc)

    if run_for is None:
        nlc.set_time_period(start_date, None)
    else:
        nlc.set_run_time(run_for, start_date)


def drive_wrf_execution(ntasks=1, wrf_dir=None, rst=False, require_rst_file=False, run_for=None, no_sync_namelist=False,
                        dry_run=False, alt_namelist=None):
    config_obj = config_utils.AutoWRFChemConfig()
    if wrf_dir is None:
        # Right now, we don't do anything to make this path relative to the automation directory
        wrf_dir = config_utils.get_wrf_run_dir(config_obj)

    try:
        if not no_sync_namelist:
            awclib.NamelistContainer.clear_temp_changes(config_obj=config_obj, wrf_dir=wrf_dir)
        _set_model_run_time(wrf_dir, rst, require_rst_file, run_for=run_for)
        _run_wrf(wrf_dir, ntasks, dry_run=dry_run, config_obj=config_obj, alt_namelist=alt_namelist)
    except (MissingInputFileError, InputDataError) as err:
        common_utils.eprint(str(err), max_columns=_pretty_n_col)
        return 1
    except CalledProcessError as err:
        common_utils.eprint('WRF exited with error code {ecode}. Check the output logs (rsl.error.* if running in MPI, '
                            'wrfrun.log if not).'.format(ecode=err.args[0]))

    return 0


def drive_ens_execution(create_config=None, submit=None, ignore_if_done=False, dry_run=False, overwrite_dirs=False):

    if create_config is not None:
        ensembles.create_new_ens_cfg_file(create_config)
    elif submit is not None:
        ensembles.build_ens_dirs(submit, overwrite=overwrite_dirs)
        ensembles.submit_ens_runs(submit, config_utils.AutoWRFChemConfig(), dry_run=dry_run)

    return 0


def setup_clargs(parser):
    mpigrp = parser.add_mutually_exclusive_group(required=True)
    mpigrp.add_argument('-n', '--ntasks', type=int, help='How many tasks to use to run WRF')
    mpigrp.add_argument('--nompi', action='store_const', const=0, dest='ntasks', help='Run WRF without MPI')

    rstgrp = parser.add_argument_group('Restart options')
    rstgrp.add_argument('-r', '--rst', action='store_true', help='Start WRF from the last restart file. If not restart '
                                                                 'file found, starts from the beginning of the run.')
    rstgrp.add_argument('--require-rst-file', action='store_true', help='Change behavior of --rst to error if there '
                                                                        'is no restart file.')

    gengrp = parser.add_argument_group('General options')
    gengrp.add_argument('-t', '--run-for', type=common_utils.parse_time_string,
                        help='Set a maximum time for WRF to run for. Useful with --rst to break a long run up into '
                             'smaller runs. For more information on time formats, call "autowrfchem help timefmt".')
    gengrp.add_argument('--dry-run', action='store_true', help='Do every but actually start WRF. Instead, it '
                                                               'will print the command it would have used.')
    gengrp.add_argument('--no-sync-namelist', action='store_true', help='Do not sync the namelist in the run '
                                                                        'directory with the persistent one.')
    gengrp.add_argument('--wrf-dir', help='The WRF run directory to execute in. Generally you will set this in the '
                                          'config and can omit this option, but this is here if you need to change '
                                          'the run directory for a single run.')
    gengrp.add_argument('--alt-namelist', help='An different namelist.input file to use as the persistent namelist '
                                               'for this run. {WRF_DIR} will be replaced with the WRF run directory '
                                               'and {CFG_DIR} with the AutoWRFChem CONFIG directory. This option is '
                                               'mainly intended for use by the ensemble runner.')
    parser.set_defaults(exec_func=drive_wrf_execution)


def setup_ens_clargs(enspar):
    enspar.description = 'Set up or run an ensemble with different settings'

    # TODO: make these into subcommands
    ensgrp = enspar.add_mutually_exclusive_group(required=True)
    ensgrp.add_argument('-c', '--create-config', help='Create a template config file with the given name')
    ensgrp.add_argument('-s', '--submit', help='Submit the ensemble to run using the given config file')

    enspar.add_argument('-o', '--overwrite-dirs', action='store_true', 
                        help='Overwrite existing directories when creating ensemble run directories')
    enspar.add_argument('-i', '--ignore-if-done', action='store_true', help='Do not submit a job to run an ensemble '
                                                                            'member that has finished.')
    enspar.add_argument('--dry-run', action='store_true', help='For --submit, do not actually submit the jobs, just '
                                                               'create the directories and the submit scripts.')

    enspar.set_defaults(exec_func=drive_ens_execution)
