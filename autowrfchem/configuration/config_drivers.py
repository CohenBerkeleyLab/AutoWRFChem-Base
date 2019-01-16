from __future__ import print_function, absolute_import, division
import os
import subprocess

from textui import uibuilder as uib, uielements as uiel

from .. import _pretty_n_col
from ..common_utils import run_external, eprint
from . import  _pgrm_main_check_key, _pgrm_cfg_key, _pgrm_clargs_key, _pgrm_warn_to_choose_env, _pgrm_nl_key, \
    ENVIRONMENT, AUTOMATION, AUTOMATION_PATHS
from . import config_utils as cu, autowrf_classlib as awclib, autowrf_namelist_main as awnlmain

_preset_fxns = {'get_netcdf_dir()': cu.get_ncdf_dir,
                'get_yacc_exec()': cu.get_yacc_exec,
                'get_flexlib_dir()': cu.get_flexlib_dir}


############################
# ALTERNATE MAIN FUNCTIONS #
############################

def _update_std_config():
    cfg = cu.AutoWRFChemConfig(ignore_differences_with_defaults=True)
    new_cfg = cfg.update_from_defaults()
    new_cfg.write()
    uiel.user_message('Your config file has been updated. A backup of the original was created.',
                      max_columns=_pretty_n_col)

#####################
# CONFIG MENU HOOKS #
#####################


def _check_config_state_hook(pgrm_data, force_check=False, is_exit=False):
    """
    Check the state of the AutoWRFChem config and print any issues to alert the user.

    This is intended to be an entry hook to the main configuration menu.

    :param pgrm_data: the data dictionary for the main configuration program.
    :type pgrm_data: dict

    :return: None
    """

    if not pgrm_data[_pgrm_main_check_key] and not force_check:
        return

    pgrm_data[_pgrm_main_check_key] = False

    fixes_needed = False
    config_obj = pgrm_data[_pgrm_cfg_key]

    uiel.user_message('\nChecking configuration...')
    try:
        config_obj.check_env_vars()
    except cu.ConfigurationSettingsError:
        uiel.user_message('  * One or more environmental variables need fixed')
        fixes_needed = True

    try:
        config_obj.check_auto_paths()
    except cu.ConfigurationSettingsError:
        uiel.user_message('  * One or more automation variables need fixed')
        fixes_needed = True

    if fixes_needed:
        msg = '\nYou will want to address the above issues before running the WRF/WPS configuration ' \
              'scripts.\nYou could also go ahead and save the current config and modify the config file ' \
              'manually ({})'.format(config_obj._config_file)
        if not is_exit:
            msg += '\n\nEach submenu has its own diagnostic option for more help\n' \
                   'Choose "Check configuration" from the main menu to see this again'
        uiel.user_message(msg, pause=not is_exit, max_columns=_pretty_n_col)
    else:
        uiel.user_message('\nNo issues detected.')

    if is_exit and fixes_needed:
        return uiel.user_input_yn('\nThere are remaining issues with the configuration.\n'
                                      'Return to the menu to correct them?', currentvalue="n")
    else:
        return None


def _save_config_exit_hook(pgrm_data):
    if _check_config_state_hook(pgrm_data, force_check=True, is_exit=True):
        return False

    config_obj = pgrm_data[_pgrm_cfg_key]
    if config_obj.has_changed or config_obj.read_from_defaults:
        if uiel.user_input_yn('Configuration has been changed. Save changes?'):
            config_obj.write()


#########################
# COMMON MENU FUNCTIONS #
#########################

def _diagnose_env_problem(pgrm_data):
    config_obj = pgrm_data[_pgrm_cfg_key]
    try:
        config_obj.check_env_vars()
    except cu.ConfigurationSettingsError as err:
        failures = err.args[1]
        uiel.user_message('Problems with environmental variables that must be corrected:')

        undef_vars = failures['undefined_vars']
        if len(undef_vars) > 0:
            uiel.user_message('\n* The following variables must be given a real value: {}'.format(', '.join(undef_vars)))

        if failures['bad_netcdf_dir']:
            is_not_dir = failures['netcdf_causes']['ncdf_dir_nonexistant']
            ncdf_missing_files = failures['netcdf_causes']['missing_files']
            if is_not_dir:
                uiel.user_message('\n* The path given for the netCDF directory is not a directory')
            else:
                uiel.user_message('\n* The netCDF directory is invalid. The following files were not found:\n'
                                  '    {}\n'
                                  '(Note that these files are not all that are needed for the netCDF library, just the '
                                  'ones that this programs tests for.)'.format('\n    '.join(ncdf_missing_files)),
                                  max_columns=_pretty_n_col)

        if failures['bad_yacc_path']:
            uiel.user_message('The YACC path is invalid (no yacc executable found)')

        if failures['bad_flex_path']:
            uiel.user_message('The FLEX library path is invalid (no libfl.a file found)')

        uiel.user_message('', pause=True)


def _diagnose_auto_problem(pgrm_data):
    config_obj = pgrm_data[_pgrm_cfg_key]
    try:
        config_obj.check_auto_paths()
    except cu.ConfigurationSettingsError as err:
        failures = err.args[1]
        bad_vars = '\n    * '.join([opt for opt, chk in failures.items() if chk])
        uiel.user_message('The following automation component paths are not directories:\n    * {}'
                          .format(bad_vars), max_columns=_pretty_n_col, pause=True)


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


def _env_var_presets_help(pgrm_data):
    presets = cu.get_envvar_presets()
    for sect_name, sect in presets.items():
        # assuming EM_CORE is the first config setting, it will have the section comment
        help_text = ' '.join([c.lstrip('# ') for c in sect.comments['EM_CORE']])
        uiel.user_message('{}: {}\n'.format(sect_name, help_text), max_columns=_pretty_n_col)


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
        user_dir = cu.rel_dir_to_abs(user_dir)
        return os.path.isdir(user_dir)

    # If all the components are currently expected in the same directory, make that the default value
    curr_top_dir = 'INIT'
    auto_paths = pgrm_data[_pgrm_cfg_key][AUTOMATION_PATHS]
    for opt, val in auto_paths.items():
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
        for opt, val in auto_paths.items():
            base_dir = os.path.basename(val.rstrip('/\\'))
            config_obj[AUTOMATION_PATHS][opt] = os.path.join(top_dir, base_dir)


####################################
# EXTERNAL CONFIGURATION FUNCTIONS #
####################################


def _run_wrf_config(config_obj, cl_args):
    """
    Run the WRF 'configure' script.

    :param config_obj: the AutoWRFChem configuration object
    :type config_obj: `AutoWRFChemConfig`

    :param cl_args: a dictionary containing the names and values of any command line arguments; should be the result
     of ``vars(parser._parse_args())`` where ``parser`` is an `argparse.ArgumentParser` instance.
    :type cl_args: dict

    :return: None
    """
    config_wrf_dir = cu.get_wrf_top_dir(config_obj)

    uiel.user_message('First you will need to choose the compiler options and nesting for WRF itself.',
                      max_columns=_pretty_n_col, pause=True)

    run_external(['./configure'], config_obj, cwd=config_wrf_dir)


def _run_wps_config(config_obj, cl_args):
    """
    Run the WPS 'configure' script.

    :param config_obj: the AutoWRFChem configuration object
    :type config_obj: `AutoWRFChemConfig`

    :param cl_args: a dictionary containing the names and values of any command line arguments; should be the result
     of ``vars(parser._parse_args())`` where ``parser`` is an `argparse.ArgumentParser` instance.
    :type cl_args: dict

    :return: None
    """
    config_wps_dir = cu.get_wps_top_dir(config_obj)

    uiel.user_message('Now you will need to choose the compiler options for WPS. '
                      'Remember that WPS can usually be built in serial, and that '
                      'you can build without GRIB2 if the met data you wish to use '
                      'is not in GRIB2 format (i.e. is in GRIB1 format).', max_columns=_pretty_n_col, pause=True)
    run_external(['./configure'], config_obj, cwd=config_wps_dir)


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

config_menu = uib.Menu('AutoWRFChem - Configuration', enter_hook=_check_config_state_hook, exit_hook=_save_config_exit_hook)

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
env_var_preset_menu.attach_custom_fxn('Help', _env_var_presets_help)

env_var_menu.attach_custom_fxn('Diagnose problems with env. vars', _diagnose_env_problem)

auto_setup_menu = config_menu.add_submenu('Setup automation config')
component_parent_path_menu = auto_setup_menu.attach_custom_fxn('Set parent path', _set_component_paths)
auto_setup_menu.attach_custom_fxn('Diagnose problems with automation config', _diagnose_auto_problem)

config_menu.attach_custom_fxn('Check configuration', lambda pgrm_data: _check_config_state_hook(pgrm_data, force_check=True))

run_config_menu = config_menu.attach_custom_fxn('Run WRF/WPS config scripts', _run_all_config)

config_menu.attach_submenu(awnlmain.namelist_main, 'Edit namelists and related config options')


def _quick_sync_namelists():
    try:
        nlc = awclib.NamelistContainer.load_namelists(sync_priority='user')
        nlc.save_namelists()
    except awclib.NamelistReadingError as err:
        eprint(err.args[0])
        return 1
    else:
        return 0


def drive_configuration(update_cfg=False, quick_sync_namelists=False, **cl_args):
    """
    Driver function to start the interactive configuration menu

    :param cl_args: command line arguments as keyword value pairs

    :return: exit code
    :rtype: int
    """
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

    if update_cfg:
        _update_std_config()
        return 0
    elif quick_sync_namelists:
        return _quick_sync_namelists()

    config_obj = cu.AutoWRFChemConfig()
    config_pgrm = uib.Program(config_menu)

    config_pgrm.data[_pgrm_main_check_key] = True
    config_pgrm.data[_pgrm_cfg_key] = config_obj
    config_pgrm.data[_pgrm_clargs_key] = cl_args
    config_pgrm.data[_pgrm_warn_to_choose_env] = True
    try:
        # Try reading the standard namelists if they exist. If not then the user will have to choose how to load the
        # namelists in the menu
        config_pgrm.data[_pgrm_nl_key] = awclib.NamelistContainer.load_namelists(sync_priority='user')
    except awclib.NamelistReadingError:
        pass

    config_pgrm.main_loop()

    return 0


def setup_config_clargs(parser):
    parser.description = 'Configure all aspects of AutoWRFChem interactively, including environmental variables, ' \
                         'automation config, and namelists.'
    parser.add_argument('--update-cfg', action='store_true', help='Update the standard config file with any new '
                                                                  'options added to the default config file. Should '
                                                                  'only be needed after an update.')
    parser.add_argument('-s', '--quick-sync-namelists', action='store_true',
                        help='Quickly sync manual changes to the namelists. This will interactively prompt you to '
                             'resolve conflicts in common options between the WRF and WPS namelists, then copy the '
                             'persistent namelists to the run directories.')

    # TODO: add --namelist option to go straight to namelists and namelist subcommand

    parser.set_defaults(exec_func=drive_configuration)
