from __future__ import print_function, absolute_import, division, unicode_literals

from datetime import datetime as dtime
from glob import glob
import os
from subprocess import CalledProcessError

from .. import common_utils, wrf_date_fmt, _pretty_n_col
from ..configuration import autowrf_classlib as awclib, config_utils
from . import ensembles

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


def _run_wrf(wrf_dir, ntasks, dry_run=False, config_obj=None):
    if ntasks > 0:
        # when WRF runs under MPI it automatically saves terminal from each task to an rsl.{out,error}.NNNN file so
        # we don't need to make a log file ourselves
        common_utils.run_external_mpi('./wrf.exe', ntasks=ntasks, cwd=wrf_dir, config_obj=config_obj, dry_run=dry_run)
    else:
        with open(os.path.join(wrf_dir, 'wrfrun.log'), 'w') as logfile:
            common_utils.run_external('./wrf.exe', config_obj, cwd=wrf_dir, logfile_handle=logfile,
                                      dry_run=dry_run)


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
                        dry_run=False):
    config_obj = config_utils.AutoWRFChemConfig()
    if wrf_dir is None:
        wrf_dir = config_utils.get_wrf_run_dir(config_obj)

    try:
        _check_for_missing_files(wrf_dir, config_obj)
        if not no_sync_namelist:
            awclib.NamelistContainer.clear_temp_changes(config_obj=config_obj)
        _set_model_run_time(wrf_dir, rst, require_rst_file, run_for=run_for)
        _run_wrf(wrf_dir, ntasks, dry_run=dry_run, config_obj=config_obj)
    except (MissingInputFileError, InputDataError) as err:
        common_utils.eprint(str(err), max_columns=_pretty_n_col)
        return 1
    except CalledProcessError as err:
        common_utils.eprint('WRF exited with error code {ecode}. Check the output logs (rsl.error.* if running in MPI, '
                            'wrfrun.log if not).'.format(ecode=err.args[0]))

    return 0


def drive_ens_execution(create_config=None, submit=None, dry_run=False):
    import pdb

    if create_config is not None:
        ensembles.create_new_ens_cfg_file(create_config)
    elif submit is not None:
        pdb.set_trace()
        ensembles.build_ens_dirs(submit)
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
    parser.set_defaults(exec_func=drive_wrf_execution)


def setup_ens_clargs(enspar):
    enspar.description = 'Set up or run an ensemble with different settings'

    ensgrp = enspar.add_mutually_exclusive_group(required=True)
    ensgrp.add_argument('-c', '--create-config', help='Create a template config file with the given name')
    ensgrp.add_argument('-s', '--submit', help='Submit the ensemble to run using the given config file')

    enspar.add_argument('--dry-run', action='store_true', help='For --submit, do not actually submit the jobs, just'
                                                               'create the directories and the submit scripts.')

    enspar.set_defaults(exec_func=drive_ens_execution)
