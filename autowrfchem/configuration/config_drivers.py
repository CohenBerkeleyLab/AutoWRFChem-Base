from __future__ import print_function, absolute_import, division
from collections import OrderedDict
import copy
import os
import subprocess

from textui import uibuilder as uib, uielements as uiel

from . import config_utils as cu, ENVIRONMENT, AUTOMATION
from .. import ui

import pdb

_pretty_n_col = 72

_preset_fxns = {'get_netcdf_dir()': cu.get_ncdf_dir,
                'get_yacc_exec()': cu.get_yacc_exec,
                'get_flexlib_dir()': cu.get_flexlib_dir}


def setup_envvars(config_obj):
    # Things to check
    presets = cu.get_envvar_presets()
    menu_opts = OrderedDict()
    menu_opts['Keep current configuration'] = _keep_config_envvars
    menu_opts['Merge shell environmental variables'] = _merge_environment
    for name, preset in presets.items():
        menu_opts['Preset: {}'.format(name)] = lambda cobj: _set_envvar_preset(cobj, preset)

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

#####################
# CONFIG MENU HOOKS #
#####################


def _check_config_state_hook(pgrm_data):
    """
    Check the state of the AutoWRFChem config and print any issues to alert the user.

    This is intended to be an entry hook to the main configuration menu.

    :param pgrm_data: the data dictionary for the main configuration program.
    :type pgrm_data: dict

    :return: None
    """
    fixes_needed = False
    config_obj = pgrm_data[_pgrm_cfg_key]

    uiel.user_message('\nChecking configuration...')
    try:
        config_obj.check_env_vars()
    except cu.ConfigurationSettingsError:
        uiel.user_message('  * One or more environmental variables need fixed')
        fixes_needed = True

    try:
        config_obj.check_auto_vars()
    except cu.ConfigurationSettingsError:
        uiel.user_message('  * One or more automation variables need fixed')
        fixes_needed = True

    if fixes_needed:
        uiel.user_message('\nYou will want to address the above issues before running the WRF/WPS configuration '
                          'scripts.\nYou could also go ahead and save the current config an modify the config file '
                          'manually ({})'.format(config_obj._config_file),
                          pause=True, max_columns=_pretty_n_col)
    else:
        uiel.user_message('\nNo issues detected.')


##################################
# ENVIRONMENTAL VARIABLE CONTROL #
##################################

def _merge_environment(config_obj, interactive=False):
    """
    Merge the shell environment with the environmental variables defined in the AutoWRFChem configuration.

    This will take any relevant environmental variables defined in the shell and store their values in the
    configuration, overwriting the existing value.

    :param config_obj: the object storing the environmental variables configuration
    :type config_obj: `AutoWRFChemConfig`

    :param interactive: optional, if ``True``, will tell the user what variables are going to be set from the shell and
     ask if it is okay to do so. Default is ``False``.
    :type interactive: bool

    :return: None, modifies ``config_obj`` in-place.
    """
    if interactive:
        ask_permission = False
        for opt, val in config_obj[ENVIRONMENT].items():
            env_val = os.getenv(opt)
            if env_val is not None:
                ask_permission = True
                print('{opt} will be set to "{val}"'.format(opt=opt, val=val))
        if ask_permission:
            if not uiel.user_input_yn('Is this okay to set?'):
                return
        else:
            uiel.user_message('No relevant env. vars defined in the shell', pause=True)
            return

    for opt in config_obj[ENVIRONMENT]:
        env_val = os.getenv(opt)
        if env_val is not None:
            config_obj[ENVIRONMENT][opt] = env_val


def _set_envvar_preset(config_obj, preset_dict, interactive=False):
    """
    Set the environmental variables to a predefined preset.

    If the value of an environmental variable in the preset is just defined as a constant, that value is copied to the
    active config. However, if the preset value ends in "()", it must be one of the predefined functions (in the
    `_preset_fxns` dictionary in this module) that when called return a best guess value for that config. This function
    takes care of calling those functions and copying the static values.

    :param config_obj: the object storing the environmental variables configuration
    :type config_obj: `AutoWRFChemConfig`

    :param preset_dict: the dictionary or dictionary-like object defining the values or value-returning functions to
     use to set the active config.
    :type preset_dict: dict or dict-like

    :param interactive: optional, if ``True``, then errors raised when calling a preset function are caught and printed
     without crashing Python. If ``False`` (default), errors are raised normally. Setting this to ``True`` is intended
     for using this as part of an interactive menu- or GUI- driven program.
    :type interactive: bool

    :return: None, modifies ``config_obj`` in-place.
    """
    for opt in config_obj[ENVIRONMENT]:
        preset_val = preset_dict[opt]
        if preset_val.strip().endswith('()'):
            try:
                preset_val = _preset_fxns[preset_val]()
            except Exception as err:
                if not interactive:
                    raise
                else:
                    uiel.user_message('\nThere was a problem setting the "{}" environmental variable:\n'.format(opt))
                    uiel.user_message(err.args[0] + '\n\n' + err.args[1] + '\n\n', max_columns=72, pause=True)
                    continue

        config_obj[ENVIRONMENT][opt] = preset_val


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


###############################
# AUTOMATION VARIABLE CONTROL #
###############################

def _set_component_paths(pgrm_data):
    """
    Set the initial part of all the component (WRF, WPS, etc.) paths.

    This is intended to be used as part of a menu- or GUI- driven program. AutoWRFChem stores the paths to all the
    individual components in its configuration file. The most commonly expected use is that all these components will
    be siblings in the same directory, so this function allows the user to set that containing directory.

    :param pgrm_data: the data dictionary for the main configuration program.
    :type pgrm_data: dict

    :return: None
    """
    def check_dir(user_dir):
        user_dir = cu._rel_dir_to_abs(user_dir)
        return os.path.isdir(user_dir)

    # If all the components are currently expected in the same directory, make that the default value
    curr_top_dir = 'INIT'
    auto_vars = pgrm_data[_pgrm_cfg_key][AUTOMATION]
    for opt, val in auto_vars.items():
        component_top = os.path.dirname(val.rstrip('/\\'))
        if curr_top_dir == 'INIT':
            curr_top_dir = component_top
        elif curr_top_dir != component_top:
            curr_top_dir = None
            break

    config_obj = pgrm_data[_pgrm_cfg_key]
    top_dir = uiel.user_input_value('Enter the directory that contains the directories of '
                                    'WRF and its preprocessors (e.g. WRFV3, WPS).\nMay be relative '
                                    'to the top automation directory or absolute.', testfxn=check_dir,
                                    testmsg='That is not a directory.', currentvalue=curr_top_dir)

    if top_dir is not None:
        for opt, val in auto_vars.items():
            base_dir = os.path.basename(val.rstrip('/\\'))
            config_obj[AUTOMATION][opt] = os.path.join(top_dir, base_dir)


####################################
# EXTERNAL CONFIGURATION FUNCTIONS #
####################################


def _run_wrf_config(config_obj, cl_args):
    """
    Run the WRF 'configure' script.

    :param config_obj: the AutoWRFChem configuration object
    :type config_obj: `AutoWRFChemConfig`

    :param cl_args: a dictionary containing the names and values of any command line arguments; should be the result
     of ``vars(parser.parse_args())`` where ``parser`` is an `argparse.ArgumentParser` instance.
    :type cl_args: dict

    :return: None
    """
    config_wrf_dir = cu.get_wrf_top_dir(config_obj)

    uiel.user_message('First you will need to choose the compiler options and nesting for WRF itself.',
                      max_columns=_pretty_n_col, pause=True)
    # Could try using the
    subprocess.check_call(['./configure'], cwd=config_wrf_dir, env=_create_env_dict(config_obj))


def _run_wps_config(config_obj, cl_args):
    """
    Run the WPS 'configure' script.

    :param config_obj: the AutoWRFChem configuration object
    :type config_obj: `AutoWRFChemConfig`

    :param cl_args: a dictionary containing the names and values of any command line arguments; should be the result
     of ``vars(parser.parse_args())`` where ``parser`` is an `argparse.ArgumentParser` instance.
    :type cl_args: dict

    :return: None
    """
    config_wps_dir = cu.get_wps_top_dir(config_obj)

    uiel.user_message('Now you will need to choose the compiler options for WPS. '
                      'Remember that WPS can usually be built in serial, and that '
                      'you can build without GRIB2 if the met data you wish to use '
                      'is not in GRIB2 format (i.e. is in GRIB1 format).', max_columns=_pretty_n_col, pause=True)
    subprocess.check_call(['./configure'], cwd=config_wps_dir, env=_create_env_dict(config_obj))


def _run_all_config(pgrm_data):
    """
    Run all external configuration scripts.

    :param pgrm_data: the data dictionary for the main configuration program.
    :type pgrm_data: dict

    :return: None
    """
    # This list should contain python functions that run external config programs, like the WRF and WPS configure
    # scripts each function must accept two inputs: config_obj, which will be the configuration object, and cl_args,
    # which will be a dictionary of command line arguemnts. It will be the individual functions' job to determine if
    # they should run based on the environment or command line args
    _extern_config_fxns = [_run_wrf_config, _run_wps_config]

    config_obj = pgrm_data[_pgrm_cfg_key]
    cl_args = pgrm_data[_pgrm_clargs_key]
    for config_fxn in _extern_config_fxns:
        config_fxn(config_obj, cl_args)

#####################
# MENU CONSTRUCTION #
#####################
_pgrm_cfg_key = 'configuration'
_pgrm_clargs_key = 'command_line_args'
_pgrm_warn_to_choose_env = 'default_env_var_warn'

config_menu = uib.Menu('AutoWRFChem - Configuration', enter_hook=_check_config_state_hook)

env_var_menu = config_menu.add_submenu('Setup environmental variables')
env_var_menu.attach_custom_fxn('Merge shell environmental vars',
                               lambda pgrm_data: _merge_environment(pgrm_data[_pgrm_cfg_key], interactive=True))

env_var_preset_menu = env_var_menu.add_submenu('Choose env. var. preset', menu_item_name='Choose preset')
env_var_preset_menu._auto_exit = True
_presets = cu.get_envvar_presets()
for _preset_name, _preset_section in _presets.items():
    # We have to define the preset section for each loop as a default value to "store" it in the lambda
    # https://stackoverflow.com/a/19837683
    env_var_preset_menu.attach_custom_fxn(_preset_name,
                                          lambda pgrm_data, preset=_preset_section:
                                            _set_envvar_preset(pgrm_data[_pgrm_cfg_key], preset, interactive=True))

auto_setup_menu = config_menu.attach_custom_fxn('Setup automation config', _set_component_paths)

run_config_menu = config_menu.attach_custom_fxn('Run WRF/WPS config scripts', _run_all_config)


def drive_configuration(**cl_args):
    # Steps:
    #   1. Setup environmental variables and other parts of the config file
    #   2. Run any external configure scripts
    #   3. Choose the meteorology type; this will set some defaults in the namelist, link the right VTable for WPS
    #      and request the directory where the met data is stored.
    #   4. Setup namelists
    #
    #   It would be nice if the met data dir could eventually include year, month, etc. - my idea is to pass it through
    #   strftime and let that fill in the formatted bits, which would probably require looping over all dates in the
    #   run and linking the met files, keeping track of whether or not we've linked a particular directory yet.

    config_obj = cu.AutoWRFChemConfig()
    config_pgrm = uib.Program(config_menu)
    config_pgrm.data[_pgrm_cfg_key] = config_obj
    config_pgrm.data[_pgrm_clargs_key] = cl_args
    config_pgrm.data[_pgrm_warn_to_choose_env] = True
    #pdb.set_trace()
    config_pgrm.main_loop()

    return config_pgrm.data[_pgrm_cfg_key]

    for config_fxn in _extern_config_fxns:
        config_fxn(config_obj, cl_args)