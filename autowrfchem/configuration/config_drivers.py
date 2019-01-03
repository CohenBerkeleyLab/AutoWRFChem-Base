from __future__ import print_function, absolute_import, division
from collections import OrderedDict
import copy
import os
import subprocess

from . import config_utils as cu, ENVIRONMENT
from .. import ui


_preset_fxns = {'get_netcdf_dir()': cu.get_ncdf_dir,
                'get_yacc_exec()': cu.get_yacc_exec,
                'get_flexlib_dir()': cu.get_flexlib_dir}


def setup_envvars(config_obj):
    presets = cu.get_envvar_presets()
    menu_opts = OrderedDict()
    menu_opts['Keep current configuration'] = _keep_config_envvars
    menu_opts['Merge shell environmental variables'] = _merge_environment
    for name, preset in presets.items():
        menu_opts['Preset: {}'.format(name)] = lambda cobj: _set_preset(cobj, preset)

    ui.user_input_menu('How would you like to set the necessary environmental variables?',
                       menu_opts, fxn_args=[config_obj])


def _keep_config_envvars(config_obj):
    if config_obj.read_from_defaults:
        prompt = \
"""The default configuration variables are set.
It is recommended that you choose a preset rather than use the defaults,
as the defaults are only placeholders.
Go back and select a preset?
"""
        if ui.user_input_yn(prompt, default='y'):
            setup_envvars(config_obj)
        else:
            return
    else:
        return


def _merge_environment(config_obj):
    for opt in config_obj.options(ENVIRONMENT):
        env_val = os.getenv(opt)
        if env_val is not None:
            config_obj.set(ENVIRONMENT, opt, env_val)


def _set_preset(config_obj, preset_dict):
    for opt in config_obj.options(ENVIRONMENT):
        preset_val = preset_dict[opt]
        if preset_val.strip().endswith('()'):
            preset_val = _preset_fxns[preset_val]()
        config_obj.set(ENVIRONMENT, opt, preset_val)


def _create_env_dict(config_obj):
    """
    Creates a dictionary that contains all existing environmental variables overwritten by those defined in the config
    :param config_obj: the object containing the AutoWRFChem configuration data

    :return: the dictionary that can be given to a subprocess function's ``env`` keyword to set the environment
    :rtype: dict
    """
    extant_env = copy.copy(os.environ)
    extant_env.update(config_obj[ENVIRONMENT])
    return extant_env


####################################
# EXTERNAL CONFIGURATION FUNCTIONS #
####################################


def _run_wrf_config(config_obj, cl_args):
    config_wrf_dir = cu.get_wrf_top_dir(config_obj)

    cu.printwait('First you will need to choose the compiler options and nesting for WRF itself.')
    # Could try using the
    subprocess.check_call(['./configure'], cwd=config_wrf_dir, env=_create_env_dict(config_obj))


def _run_wps_config(config_obj, cl_args):
    config_wps_dir = cu.get_wps_top_dir(config_obj)

    cu.printwait('Now you will need to choose the compiler options for WPS. '
                 'Remember that WPS can usually be built in serial, and that '
                 'you can build without GRIB2 if the met data you wish to use '
                 'is not in GRIB2 format (i.e. is in GRIB1 format).')
    subprocess.check_call(['./configure'], cwd=config_wps_dir, env=_create_env_dict(config_obj))


# This list should contain python functions that run external config programs, like the WRF and WPS configure scripts.
# each function must accept two inputs: config_obj, which will be the configuration object, and cl_args, which will be
# a dictionary of command line arguemnts. It will be the individual functions' job to determine if they should run based
# on the environment or command line args
_extern_config_fxns = [_run_wrf_config, _run_wps_config]


def drive_configuration(**cl_args):
    # Steps:
    #   1. Setup environmental variables
    #   2. Run any external configure scripts
    #   3. Choose the meteorology type; this will set some defaults in the namelist, link the right VTable for WPS
    #      and request the directory where the met data is stored.
    #   4. Setup namelists
    #
    #   It would be nice if the met data dir could eventually include year, month, etc. - my idea is to pass it through
    #   strftime and let that fill in the formatted bits, which would probably require looping over all dates in the
    #   run and linking the met files, keeping track of whether or not we've linked a particular directory yet.

    config_obj = cu.AutoWRFChemConfig()

    for config_fxn in _extern_config_fxns:
        config_fxn(config_obj, cl_args)