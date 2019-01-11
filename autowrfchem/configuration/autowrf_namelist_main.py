from __future__ import print_function
import sys
import os
import datetime as dt

from textui import uibuilder as uib, uielements as uiel, uierrors

from . import _pgrm_cfg_key, _pgrm_nl_key, config_utils, AUTOMATION, AUTOMATION_PATHS, MET_TYPE
from . import autowrf_classlib as WRF
from .. import namelists_dir, _pretty_n_col
import pdb


def MyPath():
    return os.path.dirname(os.path.abspath(__file__))


wrf_namelist_template_file = os.path.join(MyPath(), "namelist.input.template.chem")
wps_namelist_template_file = os.path.join(MyPath(), "namelist.wps.template")


def Startup():
    # Check if the NAMELISTS subfolder exists already,
    # create it if not
    if not os.path.isdir(namelists_dir):
        os.mkdir(namelists_dir)


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def select_preexisting_namelists(config_obj):
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


def load_menu(pgrm_data, loadmethod):
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


def PrintHelp(markstring):
    # Find the DOC section in this file and print it
    pline = False
    with open(__file__, 'r') as f:
        for line in f:
            if not pline:
                if "# BEGIN{0}".format(markstring) in line:# and "#notthis" not in line:
                    pline = True
            else:
                if "# END{0}".format(markstring) in line:# and "#notthis" not in line:
                    pline = False
                else:
                    l = line.strip()
                    # Remove the leading #
                    if l.startswith("#"):
                        l = l[1:]
                    # Replace $MYDIR with the directory of this file
                    l = l.replace("$MYDIR", MyPath())
                    print(l)

def SaveMenu(nlc):
    # Decide how to save the namelists. Pass it the namelist container
    opts = ["Write namelist regularly (namelist files and pickle)",
            "Write just the namelist files (not pickle - i.e. temporary namelists)",
            "Save namelists to NAMELISTS folder for later",
            "Do not save"]
    sel = UI.user_input_list("Save the namelists?", opts, returntype="index")

    if sel == 0:
        nlc.save_namelists('both')
    elif sel == 1:
        nlc.save_namelists('temporary')
    elif sel == 2:
        while True:
            suffix = UI.user_input_value("suffix", noempty=True)
            if os.path.isfile(os.path.join(namelists_dir, "namelist.input.{0}".format(suffix))) or os.path.isfile(os.path.join(namelists_dir, "namelist.wps.{0}".format(suffix))):
                if UI.user_input_yn("{0} is already used. Overwrite?".format(suffix), default="n"):
                    break
            else:
                break

        nlc.write_namelists(namelist_dir=namelists_dir, suffix=suffix)

        userans = input("Do you also write to make these the current namelist? y/[n]: ")
        if userans.lower() == "y":
            print("Writing out namelists.")
            nlc.save_namelists('both')
        else:
            print("Not writing out namelists.")
    elif sel == 3:
        pass

def StartMenu():
    opts = ["Create or modify namelists",
            "Show help",
            "Quit"]
    while True:
        sel = UI.user_input_list("What would you like to do?", opts, returntype="index", emptycancel=False)
        if sel == 0:
            return load_menu()
        elif sel == 1:
            PrintHelp("HELP")
        elif sel == 2:
            exit(0)

def ParseDateTime(dt_in):
    if dt_in[0] == "+" or dt_in[0] == "-":
        # Convert into timedelta
        return ParseTimeDelta(dt_in)
    elif "_" not in dt_in and "-" not in dt_in and ":" in dt_in:
        # Only a time component given: convert to a datetime.time object
        # and use that.
        dt_in = dt_in.strip()
        if len(dt_in) != 8:
            raise RuntimeError("If entering only a time (not date) component, the format must be HH:MM:SS")
        # Don't forget that python indices are [inclusive, exclusive] because, well, who knows
        hr = int(dt_in[0:2])
        mn = int(dt_in[3:5])
        sec = int(dt_in[6:8])

        return dt.time(hr, mn, sec)
    else:
        # Parse it as a WPS type date string: yyyy-mm-dd_HH:MM:SS
        return WRF.WpsNamelist.ConvertDate(dt_in)

def ParseTimeDelta(td_in):
    # These must be given in the form [+/-]xxx[s/m/h/d]
    if td_in[-1] == "s":
        scale = 1
    elif td_in[-1] == "m":
        scale = 60
    elif td_in[-1] == "h":
        scale = 3600
    elif td_in[-1] == "d":
        scale = 3600*24
    else:
        eprint("If trying to change start or end time by a relative amount (--start-time=+1d, --start-time=-3h), the")
        eprint("value MUST end in one of d, h, m, s (days, hours, minutes, seconds, respectively)")
        exit(1)

    try:
        x = float(td_in[:-1])
    except ValueError:
        eprint("Could not parse one of the relative changes to start-date or end-date, or the value of run-time")
        exit(1)

    return dt.timedelta(seconds=x*scale)

def SplitOpt(opt):
    opt = opt.strip().split("=")
    sopt = [o.strip() for o in opt]
    if len(sopt) != 2:
        raise RuntimeError("All options must be specified as --optname=value")
    else:
        return sopt[0], sopt[1]

def CheckNamelists(wrf_nl, wps_nl):
    a_ok = True
    if not os.path.isfile(wrf_nl):
        eprint("namelist.input does not exist in {0}".format(MyPath()))
        a_ok = False
    if not os.path.isfile(wps_nl):
        eprint("namelist.wps does not exist in {0}".format(MyPath()))
        a_ok = False

    if not a_ok:
        exit(1)
    else:
        return

#### MAIN PROGRAM ####
# Call startup regardless of if we are running as the main program or as a module
Startup()


#############################
# HIDING AND HOOK FUNCTIONS #
#############################


def _registry_not_ready(pgrm_data):
    try:
        WRF.Registry.load_standard_registry()
    except WRF.RegistryError:
        uiel.user_message('The registry is not ready yet - some final setup happens during compilation. Come back to '
                          'setup your namelists after compiling.', max_columns=_pretty_n_col, pause=True)
        return False


def _save_namelists(pgrm_data):
    nlc = pgrm_data[_pgrm_nl_key]
    save_regular = 'Save namelists'
    save_temp = 'Save temporary changes to namelists'
    save_later = 'Save namelists for later'
    discard = 'Discard changes'
    cancel = 'Make further changes'
    action = uiel.user_input_list('Save changes to namelists', [save_regular, save_temp, save_later, discard, cancel],
                                  printcols=False, emptycancel=False)

    if action == save_regular:
        nlc.save_namelists(save_mode='both')
    elif action == save_temp:
        nlc.save_namelists(save_mode='temp')
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
loading_menu.attach_custom_fxn('Load/reload existing namelists', lambda pgrm_data: load_menu(pgrm_data, 'current'))
loading_menu.attach_custom_fxn('Load previously saved namelists', lambda pgrm_data: load_menu(pgrm_data, 'preexisting'))
loading_menu.attach_custom_fxn('Load the standard templates', lambda pgrm_data: load_menu(pgrm_data, 'templates'))

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


# Documentation section that will be printed as help text from the command line

# BEGINDOC
#
# autowrf_namelist_main.py has 3 modes of usage:
#   python autowrf_namelist_main.py: with no other options, this enters an interactive mode that allows the user to
#       interactively set or modify the WRF and WPS namelists. (The main advantage of using this mode over directly
#       editing the namelists is that this program keeps common options between WRF and WPS in sync.)
#
#   python autowrf_namelist_main.py load --met=<mettype> --suffix=<suffix>: this mode will immediately make the
#       namelists contained in the NAMELIST folder with the suffix defined by the --suffix option the active namelists.
#       A meteorology must be specified with the --met option to be sure that those settings are syncronized between
#       the WRF and WPS namelists. If the --suffix option is omitted, then the template files will be used.
#
#   python autowrf_namelist_main.py mod: this mode will allow you to modify the current namelist. Most settings in
#       either the WPS or WRF namelist can be set directly by specifying their name as the option flag, e.g
#       --history_interval=60 will set the history_interval option in the WRF namelist to 60. Note that settings that
#       are boolean values must be given the value of .true. or .false. or it will be rejected. Further, at present,
#       all domains will be set to this value (there is no way to modify nested domains separately with this version of
#       this program).
#           Several options are reserved: any options associated with meteorology cannot be changed directly and can
#       only be changed by giving the flag --met=<mettype>, where <mettype> is one of the allowed meteorologies (see
#       below).
#           Further, to change the time period, the flags --start-date, --end-date, and --run-time must be used.
#       --state-date and --end-date can be one of two forms. First, they can be given as yyyy-mm-dd or
#       yyyy-mm-dd_HH:MM:SS to set either as an absolute value. Second, a relative change can be given as
#       --start-date=[+/-]nnn[d/h/m/s], that is, the option must start with either a + or - (indicating positive or
#       negative change respectively) and end in d, h, m, s (indicating days, hours, minutes, seconds). Thus,
#       --start-date=+12h will make the start date 12 hours later, while --end-date=-7d would make the run end 7 days
#       sooner.
#           Finally, --run-time can be used to set the end time relative to the start time. The syntax is the same as a
#       relative change to start or end date except a + sign is not needed at the beginning (so --run-time=12h will
#       set the end time to be 12 hours after the start time). Negative values will be rejected. Note that the run time
#       option is applied after the start date one, regardless of what order the options are on the command line.
#           Running this command without any options restores the namelists to the values stored in the pickle (useful
#       in conjunction with the "tempmod" mode below).
#
#   python autowrf_namelist_main.py modify: same behavior as "mod"
#
#   python autowrf_namelist_main.py tempmod: similar behaviour to "mod," except that in this case the pickle is not
#       changed. Since that is what is used to load the current namelist when executing the "mod" option, this means
#       that the next time you run this with the mod or similar option, you will be starting from the state BEFORE
#       running the "tempmod" command. This is very useful when preparing NEI emissions, as that requires you to
#       set a 12 hour run time briefly to prepare the emissions. This way, you could run
#       python autowrf_namelist_main.py tempmod --run-time=12h to generate the proper namelist, then
#       python autowrf_namelist_main.py mod to restore the current settings. (Of course you'd need to generate the other
#       12 hr NEI file, but this is just an example).
#
#   python autowrf_namelist_main.py check-wrf-opt: allows you to pass namelist options using the same flags as the "mod"
#       method (except that the special flags --start-date, --end-date, and --run-time cannot be used). If all the
#       options specified on the command line are correct as stored in the current permanent namelist (so temporary
#       changes made with "tempmod" cannot be checked), this will exit with 0. If any do not match, it exits with 1. If
#       you wish to allow the option to be one of several values, separate each with a comma, i.e
#       --io_form_auxinput5=2,11 will return 0 if io_form_auxinput5 is 2 or 11. If it cannot find an option, it exits
#       with exit code 2
#
#   python autowrf_namelist_main.py check-wps-opt: same as check-wrf-opt but for WPS.
#
#   python autowrf_namelist_main.py get-wrf-opt: will return the value of the WRF namelist option specified using the
#       same syntax as check-wrf-opt. Additionally, the flag --no-quotes will strip any ' characters from the string
#       first. Like check-wrf-opt, if it cannot find the option, it exits with exit code 2.
#
#   python autowrf_namelist_main.py get-wps-opt: same as get-wrf-opt but for WPS.
#
# ENDDOC
#
#
# Help section printed for the interactive help
# BEGINHELP
#
#   This help will focus on the interactive mode of operation.
#   For help on the command line options, run "python autowrf_namelist_main.py --help" from the command line.
#
#   This program allows you to interactively modify WRF/WPS namelists. The primary advantage of doing it this way rather
#   than manually editing them is that this program will ensure any options that should be synchronized between the two
#   namelists are kept synchronized (e.g. e_we and e_sn). It also handles settings that relate to the choice of met data
#   through your choice of met data.
#
#   When loading namelists, you are given three options:
#       1) Load standard templates: this reads the namelist.input.template.chem and namelist.wps.template files in
#       $MYDIR.
#       These are configured to support NEI, MEGAN, and MOZBC immediately and use RADM2 chemistry.
#
#       2) Load a pair of WPS/WRF namelists: Namelists go in
#       $MYDIR/NAMELISTS
#       either manually or from within the program. Note that WRF namelists must begin with "namelist.input" and WPS
#       namelists must begin with "namelist.wps" to be recognized by the program. The program will
#       then ask you to choose, both a WPS and WRF namelist file. You can use this feature to quickly
#       switch between chemistry or domain choices.  If the domain or time settings in the WPS and WRF namelist differ,
#       the WPS namelist takes precedence.
#
#       3) Modify the current namelists: This will load the current namelists without any temporary changes. (More on
#       those below).
#
#   Once you have loaded your namelists, you will be presented with a list of options to check or change. These are
#   fairly self explanatory. One note: whenever you change the start/end date or the domain, it will ask you to
#   choose a MOZBC input file. This expects the MOZBC files to be in a very specific place (../../MOZBC/data, relative
#   to the autowrf_classlib.py file).  If it cannot find any, it will print an error message.  It also expects
#   wrfbuild.cfg to be present one level above $MYDIR
#   as that file will be where the MOZBC file is specified.  If you are not using this as part of the larger AutoWRFChem
#   program, you can ignore this warnings, so long as you recognize that the MOZBC data file will not be specified
#   automatically.
#
#   When saving, you are again given four options. To understand these, you should know that this program has the
#   ability to temporarily modify the namelists while retaining a copy of the original. It does so by storing the
#   current namelists in two ways. First, it writes out the namelist files namelist.input and namelist.wps in its
#   directory:
#
#   $MYDIR
#
#   Second, it saves Python objects representing the namelists in the "namelist_pickle.pkl" file in the same directory.
#   (A "pickle" is how Python can save data for it to read again later.) This does NOT contain any temporary changes,
#   and is what is loaded when you choose "Modify the current namelists" when loading a file.
#
#   Temporary changes can be used when, for instance, you need to set the run time to 12 hours to generate NEI input
#   files. You probably don't want to only run WRF for 12 hours when you do the actual run, but you do need it to only
#   run that long to generate wrfchemi_00z_d01 and wrfchemi_12z_d01. By setting the 12 hour run time as a temporary
#   change, this means that the next time this program is run, it can easily restore your settings for the full run. In
#   fact, it does not support loading a namelist such that the temporary changes are maintained currently. (The full
#   AutoWRFChem program uses the command line implementation of this to automate preparing NEI emissions.)
#
#   Now we can understand the options available for saving the namelists:
#       1) Write namelist regularly: saves the namelists to both the actual namelist files and the pickle. Thus, if you
#       ran this program again and chose "Modify current namelists" you would get the namelists you just saved.
#
#       2) Write just the namelist files: does not write the pickle. Thus, if you run this program again and chose
#       "Modify current namelists" you would NOT get the namelist you just saved, but rather the last one you saved
#       using option 1 or possibly 3.
#
#       3) Save namelits to NAMELISTS folder: this will ask for a suffix to append to the namelist names to identify
#       them, then write the namelists to the NAMELIST folder, where it can load them later. It will also ask if you
#       want to also set them to be the current namelist, if you answer yes, it saves both the regular files and the
#       pickle.
#
#       4) Do not save: Self explanatory. Does not save anything.
#
#
# ENDHELP
