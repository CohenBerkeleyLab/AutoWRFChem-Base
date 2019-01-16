from __future__ import print_function, absolute_import, division, unicode_literals

from configobj import ConfigObj
import os
import re
import sys

from .. import _pkg_dir, common_utils
from ..configuration import config_utils, autowrf_classlib as awclib
from ..configuration import HPC, SUBMIT_CMD

import pdb

_ens_top_dir_key = 'ensemble_top_dir'
_ens_sub_file_key = 'submit_file'
_ens_sub_opt_key = 'submit_run_opts'
_ens_cfg_init_comment = \
"""# Use this config file to specify an ensemble of WRF runs
# to carry out.
#
# Each section (RUN1, RUN2, ...) specifies its own run. Within
# each section, give values for options in the WRF namelist
# for that run. Each run will use the persistent namelist 
# defined for AutoWRFChem when the ensemble directories are
# created as a base, then set the options specified in these
# sections to override the original options. Specify them just
# as you would in the namelist itself.
#
# Note that changing domain options that require re-running 
# WPS or real.exe are not currently supported."""


class EnsembleError(Exception):
    pass


class BadEnsConfigError(EnsembleError):
    """
    Error to use if there's a problem with the ensemble configuration
    """
    pass


def create_new_ens_cfg_file(filename):
    cfg = ConfigObj()
    cfg.filename = filename
    cfg.initial_comment = _ens_cfg_init_comment.split('\n')

    run1 = {'sf_sfclay_physics': [2, 2, 2, 2], 'bl_pbl_physics': [2, 2, 2, 2]}
    run2 = {'sf_sfclay_physics': [5, 5, 5, 5], 'bl_pbl_physics': [6, 6, 6, 6]}

    cfg[_ens_top_dir_key] = ''
    cfg.comments[_ens_top_dir_key] = """\n# This is the directory where all the ensemble
# run directories will be created.""".split('\n')

    cfg[_ens_sub_file_key] = ''
    cfg.comments[_ens_sub_file_key] = """\n# This is a template submit script that will be
# used to submit the ensemble members. {jobname} will be
# replaced with a custom job name and {exec} (required) 
# will be replaced with the execute command""".split('\n')

    cfg[_ens_sub_opt_key] = '--ntasks=1'
    cfg.comments[_ens_sub_opt_key] = """\n# This specifies extra command line arguments for
# autowrfchem run that will be used for each ensemble member""".split('\n')

    cfg['MYJ'] = run1
    cfg['MYNN2'] = run2
    cfg.comments['MYJ'] = """\n# These two sections would create a 2-member ensemble
# that would test the MYJ vs. MYNN2 PBL scheme.""".split('\n')
    cfg.comments['MYNN2'] = """\n# Just add more sections to add members to the ensemble.
# The section name will be used as the run directory name
# for that member.""".split('\n')

    cfg.write()


def _iter_ens_members(cfg):
    ens_top_dir = cfg[_ens_top_dir_key]
    for sect_name in cfg.sections:
        sect = cfg[sect_name]
        ens_dir = os.path.join(ens_top_dir, sect_name)
        yield sect_name, ens_dir, sect


def _create_ens_run_dir(dir_path, template_wrf_dir, excludes=(r'met_em.*', r'wrfout.*', r'namelist\.input.*')):
    os.mkdir(dir_path)
    template_files = os.listdir(template_wrf_dir)
    for f in template_files:
        if any([re.match(pat, f) for pat in excludes]):
            continue

        src = os.path.abspath(os.path.join(template_wrf_dir, f))
        dst = os.path.join(dir_path, f)
        os.symlink(src, dst)


def _ens_namelist_file(ens_dir, ens_name):
    return os.path.join(ens_dir, 'namelist.input.{}'.format(ens_name))


def build_ens_dirs(cfg_file):
    cfg = ConfigObj(cfg_file)
    template_wrf_dir = config_utils.get_wrf_run_dir()

    ens_top_dir = config_utils.rel_dir_to_abs(cfg[_ens_top_dir_key])

    if not os.path.isdir(ens_top_dir):
        raise BadEnsConfigError('The ensemble top directory ({}) does not exist'.format(ens_top_dir))

    for ens_name, ens_dir, section in _iter_ens_members(cfg):

        _create_ens_run_dir(ens_dir, template_wrf_dir)

        nlc = awclib.NamelistContainer.load_namelists()
        for optname, optval in section.items():
            nlc.wrf_namelist.set_opt_val_no_sect(optname, optval, convert_type_if_needed=True)
        nlc.wrf_namelist.write_namelist(_ens_namelist_file(ens_dir, ens_name))


def submit_ens_runs(cfg_file, awc_config, ignore_if_done=True, dry_run=False):
    submit_cmd = awc_config[HPC][SUBMIT_CMD]
    cfg = ConfigObj(cfg_file)

    submit_template = config_utils.rel_dir_to_abs(cfg[_ens_sub_file_key])
    run_args = cfg[_ens_sub_opt_key]

    # write the submit scripts to the directory containing the autowrfchem package. this way it can be found
    write_dir = os.path.abspath(os.path.join(_pkg_dir, '..'))

    with open(submit_template, 'r') as template_obj:
        for idx, (ens_name, ens_dir, _) in enumerate(_iter_ens_members(cfg)):
            ens_namelist = _ens_namelist_file(ens_dir, ens_name)
            if ignore_if_done and run_utils.is_wrf_run_complete(ens_dir, ens_namelist):
                print('{name} in {dir} finished; not submitting'.format(name=ens_name, dir=ens_dir))
                continue

            jobname = '{}-wrf_ens-{}'.format(idx+1, ens_name)
            submit_filename = os.path.join(write_dir, 'submit_' + jobname)
            # put wrf-dir last so it overrides any earlier instances and tells autowrfchem to run that particular
            # ensemble member. Also tell it not to sync the namelist in that ensemble directory with the persistent ones
            # because that would wipe out the ensemble specific settings. We use the Python executable that was used to
            # run this program so that the submit script doesn't need to worry about activating the virtual environment.
            exec_str = '{py} autowrfchem_main.py run {args} --wrf-dir={dir} --alt-namelist={nlfile}'.format(
                py=sys.executable, args=run_args, dir=ens_dir, nlfile=ens_namelist
            )

            template_obj.seek(0)
            with open(submit_filename, 'w') as submit_obj:
                for line in template_obj:
                    submit_obj.write(line.format(jobname=jobname, exec=exec_str))

            common_utils.run_external([submit_cmd, submit_filename], config_obj=awc_config, cwd=write_dir,
                                      dry_run=dry_run)
