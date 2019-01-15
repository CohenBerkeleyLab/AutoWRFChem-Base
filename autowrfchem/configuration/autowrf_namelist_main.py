from __future__ import print_function
import sys
import os
import datetime as dt

from textui import uibuilder as uib, uielements as uiel, uierrors

from . import _pgrm_cfg_key, _pgrm_nl_key, config_utils, AUTOMATION, AUTOMATION_PATHS, MET_TYPE
from . import autowrf_classlib as WRF
from .. import namelists_dir, _pretty_n_col
import pdb


def select_preexisting_namelists(config_obj):
    """
    Present the user a list of previously saved namelists to choose from to load

    :param config_obj: an AutoWRFChemConfig instance that gives the current environmental variables; used to choose
     whether to use the chemistry or non-chemistry namelist templates if loading the templates.
    :type config_obj: `AutoWRFChemConfig`

    :return: the WRF and WRF namelist files to load
    :rtype: str and str
    """
    files = os.listdir(namelists_dir)
    template_name = "Standard template"
    wrffiles = [template_name]
    wpsfiles = [template_name]
    for f in files:
        if f.startswith("namelist.input"):
            wrffiles.append(f)
        elif f.startswith("namelist.wps"):
            wpsfiles.append(f)

    wrffile = uiel.user_input_list("Choose the WRF namelist: ", wrffiles)
    if wrffile == template_name:
        wrffile = WRF.NamelistContainer.wrf_namelist_template(config_obj)
    elif wrffile is not None:
        wrffile = os.path.join(namelists_dir, wrffile)

    wpsfile = uiel.user_input_list("Choose the WPS namelist: ", wpsfiles)
    if wpsfile == template_name:
        wpsfile = WRF.NamelistContainer.wps_namelist_template()
    elif wpsfile is not None:
        wpsfile = os.path.join(namelists_dir, wpsfile)

    return wrffile, wpsfile


def load_namelists(pgrm_data, loadmethod):
    """
    Load the WRF and WPS namelists from the interactive menu

    :param pgrm_data: the program data dictionary
    :type pgrm_data: dict

    :param loadmethod: how to load the namelists. "templates" will load the standard templates, "preexisting" will bring
     up a submenu to choose previously saved namelists, and "current" will load the current persistent namelists.
    :type loadmethod: str

    :return: None, stores the namelists container in the program data.
    """
    config_obj = pgrm_data[_pgrm_cfg_key]
    nlcon = None

    try:
        if loadmethod == 'templates':
            nlcon = WRF.NamelistContainer.load_templates(config_obj=config_obj)
        elif loadmethod == 'preexisting':
            wrffile, wpsfile = select_preexisting_namelists(config_obj)
            if wrffile is not None and wpsfile is not None:
                nlcon = WRF.NamelistContainer(wrffile=wrffile, wpsfile=wpsfile, sync_priority='user')
            else:
                raise WRF.NamelistReadingError('')
        elif loadmethod == 'current':
            if _pgrm_nl_key in pgrm_data:
                if not uiel.user_input_yn('This will revert to the previous saved version. Continue?'):
                    return

            nlcon = WRF.NamelistContainer.load_namelists(sync_priority='user')
    except WRF.NamelistReadingError as err:
        uiel.user_message('Problem reading namelist file: {}.\nTry another method of loading'.format(err.args[0]),
                          max_columns=_pretty_n_col, pause=True)
        return

    if nlcon is not None:
        pgrm_data[_pgrm_nl_key] = nlcon
    else:
        uiel.user_message('Failed to load namelist', pause=True)


#############################
# HIDING AND HOOK FUNCTIONS #
#############################


def _registry_not_ready(pgrm_data):
    """
    Hook that checks if the registry is ready

    The namelist program relies on the registry to know what type each setting is and whether it is per domain or one
    option for the whole model. Since some final setup of the registry happens during compilation, we need to check that
    the registry is ready before allowing the user to modify the namelist.

    :param pgrm_data: the program data dictionary
    :type pgrm_data: dict

    :return: ``False`` if the registry is not ready yet, ``None`` otherwise.
    """
    try:
        WRF.Registry.load_standard_registry()
    except WRF.RegistryError:
        uiel.user_message('The registry is not ready yet - some final setup happens during compilation. Come back to '
                          'setup your namelists after compiling.', max_columns=_pretty_n_col, pause=True)
        return False


def _save_namelists(pgrm_data):
    """
    Menu hook to save the namelist files

    :param pgrm_data: the program data dictionary
    :type pgrm_data: dict

    :return: ``True``if the user indicates to discard changes to the namelist, False if the user chooses to return to
     the namelist menu, None otherwise.
    """
    nlc = pgrm_data[_pgrm_nl_key]
    save_regular = 'Save namelists'
    save_later = 'Save namelists for later'
    discard = 'Discard changes'
    cancel = 'Make further changes'
    action = uiel.user_input_list('Save changes to namelists', [save_regular, save_later, discard, cancel],
                                  printcols=False, emptycancel=False)

    if action == save_regular:
        nlc.save_namelists(save_mode='both')
    elif action == save_later:
        _save_namelists_for_later(nlc)
    elif action == discard:
        return True
    elif action == cancel:
        return False


def _namelist_not_loaded(pgrm_data):
    """
    Checks if a namelist has been loaded yet

    :param pgrm_data: the program data dictionary
    :type pgrm_data: dict

    :return: ``True`` if no namelists have been loaded yet, ``False`` otherwise
    """
    return _pgrm_nl_key not in pgrm_data


def _is_not_wrf_chem(pgrm_data):
    return not config_utils.get_is_chem(pgrm_data[_pgrm_cfg_key])


def _save_namelists_for_later(nlc):
    while True:
        suffix = uiel.user_input_value("Enter an identifying suffix", emptycancel=False)
        if os.path.isfile(os.path.join(namelists_dir, "namelist.input.{0}".format(suffix))) or os.path.isfile(
                os.path.join(namelists_dir, "namelist.wps.{0}".format(suffix))):
            if uiel.user_input_yn("{0} is already used. Overwrite?".format(suffix), currentvalue="n"):
                break
        else:
            break

    nlc.write_namelists(namelist_dir=namelists_dir, suffix=suffix)


###########################
# NAMELIST EDIT FUNCTIONS #
###########################

def _set_start_end_dates(pgrm_data):
    nlc = pgrm_data[_pgrm_nl_key]
    nlc.user_set_time_period()


def _set_shared_domain(pgrm_data):
    nlc = pgrm_data[_pgrm_nl_key]
    nlc.user_set_domain()


def _restore_met_opts(pgrm_data):
    cfg_obj = pgrm_data[_pgrm_cfg_key]
    curr_met = cfg_obj[AUTOMATION][MET_TYPE]

    if curr_met == '':
        raise config_utils.ConfigurationSettingsError('MET_TYPE not set')

    nlc = pgrm_data[_pgrm_nl_key]
    nlc.set_met(curr_met)


def _set_other_opt(pgrm_data, namelist_name):
    nlc = pgrm_data[_pgrm_nl_key]
    nlc.user_set_opt(namelist_name, pgrm_data=pgrm_data)


def _display_opts(pgrm_data, namelist_name):
    nlc = pgrm_data[_pgrm_nl_key]
    if namelist_name == 'wrf':
        nlc.display_options(nlc.wrf_namelist)
    elif namelist_name == 'wps':
        nlc.display_options(nlc.wps_namelist)
    else:
        raise NotImplementedError('namelist_name == "{}"'.format(namelist_name))


def _check_nei_compat(pgrm_data):
    nlc = pgrm_data[_pgrm_nl_key]
    nlc.user_nei_compat_check()


def _choose_met_type(pgrm_data):
    avail_mets = config_utils.get_met_presets()
    met_names = list(avail_mets.keys())

    config_obj = pgrm_data[_pgrm_cfg_key]
    current_met = config_obj[AUTOMATION][MET_TYPE]
    if current_met == '':
        current_met = None

    selected_met = uiel.user_input_list('Choose a met type', met_names, currentvalue=current_met)
    if selected_met is not None:
        nlc = pgrm_data[_pgrm_nl_key]
        nlc.set_met(selected_met, config_obj=config_obj, update_config=True)


def _set_chem_mechanism(pgrm_data):
    avail_chems = config_utils.get_chem_presets()
    chem_names = list(avail_chems.keys())

    nlc = pgrm_data[_pgrm_nl_key]
    curr_chem_opt = nlc.wrf_namelist.get_opt_val_no_sect('chem_opt')
    curr_chem_name = None
    for name, sect in avail_chems:
        if curr_chem_opt == sect['WRF']['CHEM']['CHEM_OPT']:
            curr_chem_name = name
            break

    selected_chem = uiel.user_input_list('Choose a chemistry mechanism', chem_names, currentvalue=curr_chem_name)
    if selected_chem is not None:
        nlc.set_chem(selected_chem)


def _choose_mozbc_file(pgrm_data):
    raise NotImplementedError('Choosing MOZBC file not updated to AWC v2.0.0 ')


##############################
# NAMELIST MENU CONSTRUCTION #
##############################
namelist_main = uib.Menu('Namelists', enter_hook=_registry_not_ready, exit_hook=_save_namelists,
                         last_item_name_override='{} & save namelists')

loading_menu = namelist_main.add_submenu('Load different namelists', auto_exit=True)
loading_menu.attach_custom_fxn('Load/reload existing namelists', lambda pgrm_data: load_namelists(pgrm_data, 'current'))
loading_menu.attach_custom_fxn('Load previously saved namelists', lambda pgrm_data: load_namelists(pgrm_data, 'preexisting'))
loading_menu.attach_custom_fxn('Load the standard templates', lambda pgrm_data: load_namelists(pgrm_data, 'templates'))

edit_menu_top = namelist_main.add_submenu('Edit namelist options', hide_if=_namelist_not_loaded)
edit_menu_top.attach_custom_fxn('Set start/end date', _set_start_end_dates)
edit_menu_top.attach_custom_fxn('Set shared domain options', _set_shared_domain)
edit_menu_top.attach_custom_fxn('Revert met-relevant options to recommended', _restore_met_opts)
edit_menu_top.attach_custom_fxn('Choose chemical mechanism', _set_chem_mechanism, hide_if=_is_not_wrf_chem)
edit_menu_top.attach_custom_fxn('Set other WRF options', lambda pgrm_data: _set_other_opt(pgrm_data, 'wrf'))
edit_menu_top.attach_custom_fxn('Set other WPS options', lambda pgrm_data: _set_other_opt(pgrm_data, 'wps'))
edit_menu_top.attach_custom_fxn('Display WRF options', lambda pgrm_data: _display_opts(pgrm_data, 'wrf'))
edit_menu_top.attach_custom_fxn('Display WPS options', lambda pgrm_data: _display_opts(pgrm_data, 'wps'))
edit_menu_top.attach_custom_fxn('Check NEI compatibility', _check_nei_compat, hide_if=_is_not_wrf_chem)

namelist_main.attach_custom_fxn('Select meteorology', _choose_met_type, hide_if=_namelist_not_loaded)
namelist_main.attach_custom_fxn('Select MOZBC data file', _choose_mozbc_file,
                                hide_if=lambda pgrm_data: _is_not_wrf_chem(pgrm_data) or _namelist_not_loaded(pgrm_data))

