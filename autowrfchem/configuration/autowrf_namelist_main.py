from __future__ import print_function
import sys
import os
import datetime as dt

from textui import uibuilder as uib, uielements as uiel, uierrors

from . import _pretty_n_col, _pgrm_cfg_key, config_utils, AUTOMATION, MET_TYPE, autowrf_classlib as WRF
from .autowrf_classlib import UI
import pdb

def MyPath():
    return os.path.dirname(os.path.abspath(__file__))


def NamelistsPath():
    return os.path.join(MyPath(), "NAMELISTS")


wrf_namelist_template_file = os.path.join(MyPath(), "namelist.input.template")
wps_namelist_template_file = os.path.join(MyPath(), "namelist.wps.template")


def Startup():
    # Check if the NAMELISTS subfolder exists already,
    # create it if not
    if not os.path.isdir(NamelistsPath()):
        os.mkdir(NamelistsPath())


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def SelectPreexistingNamelists():
    files = os.listdir(NamelistsPath())
    template_name = "Standard template"
    wrffiles = [template_name]
    wpsfiles = [template_name]
    for f in files:
        if f.startswith("namelist.input"):
            wrffiles.append(f)
        elif f.startswith("namelist.wps"):
            wpsfiles.append(f)

    # If the namelist container is given a None for the file, it will load the standard template

    print("Select the namelist files to use. If there is a discrepancy in the domain, the WPS file")
    print("takes precedence.")
    wrffile = UI.user_input_list("Choose the WRF namelist: ", wrffiles)
    if wrffile == template_name:
        wrffile = wrf_namelist_template_file
    elif wrffile is not None:
        wrffile = os.path.join(NamelistsPath(), wrffile)

    wpsfile = UI.user_input_list("Choose the WPS namelist: ", wpsfiles)
    if wpsfile == template_name:
        wpsfile = wps_namelist_template_file
    elif wpsfile is not None:
        wpsfile = os.path.join(NamelistsPath(), wpsfile)

    return wrffile, wpsfile

def load_menu(pgrm_data, loadmethod):
    nlcon = None
    if loadmethod == 'templates':
        nlcon = WRF.NamelistContainer.load_templates()
    elif loadmethod == 'preexisting':
        wrffile, wpsfile = SelectPreexistingNamelists()
        if wrffile is not None and wpsfile is not None:
            nlcon = WRF.NamelistContainer(wrffile=wrffile, wpsfile=wpsfile)
    elif loadmethod == 'current':
        if _pgrm_nl_key in pgrm_data:
            if not uiel.user_input_yn('This will revert to the previous saved version. Continue?'):
                return
        nlcon = WRF.NamelistContainer.load_namelists()

    if nlcon is not None:
        pgrm_data[_pgrm_nl_key] = nlcon


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
            if os.path.isfile(os.path.join(NamelistsPath(),"namelist.input.{0}".format(suffix))) or os.path.isfile(os.path.join(NamelistsPath(),"namelist.wps.{0}".format(suffix))):
                if UI.user_input_yn("{0} is already used. Overwrite?".format(suffix), default="n"):
                    break
            else:
                break

        nlc.write_namelists(namelist_dir=NamelistsPath(), suffix=suffix)

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
    if namelist_name == 'wrf':
        nlc.user_set_other_opt(nlc.wrf_namelist)
    elif namelist_name == 'wps':
        nlc.user_set_other_opt(nlc.wps_namelist)
    else:
        raise NotImplementedError('namelist_name == "{}"'.format(namelist_name))


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
        config_obj[AUTOMATION][MET_TYPE] = selected_met
        nlc = pgrm_data[_pgrm_nl_key]
        nlc.set_met(selected_met)


def _set_chem_mechanism(pgrm_data):
    avail_chems = config_utils.get_chem_presets()
    chem_names = list(avail_chems.keys())

    nlc = pgrm_data[_pgrm_nl_key]
    curr_chem_opt = nlc.wrf_namelist.GetOptValNoSect('chem_opt')
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
_pgrm_nl_key = 'namelists'
namelist_main = uib.Menu('Namelists', enter_hook=_registry_not_ready)

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

if __name__ == "__main__":

    # Namelist generation has 3 modes:
    #  1) Allow the user to interactively set the options
    #  2) Use specified existing namelists, ensuring that common options are matched
    #  3) Make a temporary namelist. This will write out the namelist file, but not overwrite the existing pickle file.
    #
    # If option 1 is chosen, it will need to load the template namelists and start the interactive menu. Upon finishing,
    # the user can choose to save the namelist files in another location to use with option 2 later, in addition to
    # saving the actual files to be linked. This can also load a different preexisting
    #
    # If option 2 is chosen, meteorology will need to be specified on the command line and optionally the namelist
    # files. (If the files are not specified, it will use the usual template files).
    #
    # Option 3 needs the values to be modified temporarily specified on the command line. Start and end dates are
    # are special and must be specified using --start-date=yyyy-mm-dd_HH:MM:SS and --end-date=yyyy-mm-dd_HH:MM:SS. All
    # other options can be modified by using their name as the flag, e.g. --bio_emiss_opt=3 will set bio_emiss_opt to 3
    # in the WRF namelist.
    #
    # This program will create the NAMELIST folder in its directory the first time it runs.
    # NAMELISTS is where you can save WPS/WRF namelist pairs for future use.  This can take two forms. First, you could
    # just save a WPS namelist there after playing with it in the WPS directory using the plotgrids utility to fine-
    # tune your domain, then load that namelist with any WRF namelist (including the standard template) to use the
    # domain with any preexisting settings. Alternately, you can save a pair of WPS/WRF namelist from within the program
    # and load them later. The domain information in the WPS namelist always takes precedence.

    arg = sys.argv

    if len(arg) == 1: # should have just this function name
        # Option 1: interactive
        while True:
            nlc = StartMenu()
            if nlc is not None:
                break

        while nlc.UserMenu():
            pass
        SaveMenu(nlc)
    if len(arg) > 1:
        WRF.DEBUG_LEVEL=0 #turn off normal messages from the classlib interface to prevent sending erroneous strings into the shell
        if arg[1] == "-h" or arg[1] == "--help":
            PrintHelp("DOC")
            print("Allowed met types are: ", end="")
            for m in WRF.Namelist.mets:
                print(m, end=" ")
            print("")
        elif arg[1] == "load":
            argopts = arg[2:]
            metopt = None
            suffix = None
            for opt in argopts:
                optname, optval = SplitOpt(opt)
                if optname == "--met":
                    metopt = optval
                elif optname == "--suffix":
                    suffix = optval

                if metopt is None:
                    eprint("Error: requesting to load an existing namelist requires meteorology to be specified with")
                    eprint("       --met=<met option> in order to ensure that both namelists use the same meteorology")
                    eprint("       settings. <met option> can be one of {0}".format(WRF.Namelist.mets))
                    exit(1)
                else:
                    if suffix is not None:
                        wrffname = WRF.NamelistContainer.wrf_namelist_outfile + "." + suffix
                        wpsfname = WRF.NamelistContainer.wps_namelist_outfile + "." + suffix
                        wrffile = os.path.join(NamelistsPath(), wrffname)
                        wpsfile = os.path.join(NamelistsPath(), wpsfname)
                        nlc = WRF.NamelistContainer(met=metopt, wrffile=wrffile, wpsfile=wpsfile)
                    else:
                        nlc = WRF.NamelistContainer(met=metopt, wrffile=wrf_namelist_template_file,
                                                    wpsfile=wps_namelist_template_file)

                    nlc.write_namelists()
                    nlc.SavePickle()

        elif arg[1] == "mod" or arg[1] == "modify" or arg[1] == "tempmod":
            # So this needs to parse the options looking for a couple things:
            #   1) start-date and end-date need to be handled specially, to use the set_time_period method
            #   2) run-time also needs to be handled specially as well
            #   3) Also add the capability to do relative changes to start and end time with the syntax
            #       --start-date=+12h
            #   4) start-date, end-date and run-time need to be processed at the end once we are sure which ones we
            #       have
            nlc = WRF.NamelistContainer.LoadPickle()
            start_date = None
            end_date = None
            run_time = None
            force_wrf_only = False
            for a in arg[2:]:
                if a == "--force-wrf-only":
                    force_wrf_only = True
                    continue

                optname, optval = SplitOpt(a)
                if optname == "--start-date":
                    start_date = ParseDateTime(optval)
                elif optname == "--end-date":
                    end_date = ParseDateTime(optval)
                elif optname == "--run-time":
                    run_time = ParseTimeDelta(optval)
                elif optname == "--met":
                    nlc.set_met(optval)
                else:
                    optname = optname.replace("-", "")
                    nlc.cmd_set_other_opt(optname, optval, force_wrf_only=force_wrf_only)

            if start_date is not None or end_date is not None:
                nlc.set_time_period(start_date, end_date)

            if run_time is not None:
                if run_time < dt.timedelta(0):
                    eprint("Negative values of run time are not permitted")
                    exit(1)

                # both are returned to ensure it is not stored as a tuple
                start_date, end_date = nlc.get_time_period()
                end_date = start_date + run_time
                nlc.set_time_period(start_date, end_date)

            nlc.write_namelists()
            # Only write the pickle if the change is not temporary
            if arg[1] == "mod" or arg[1] == "modify":
                nlc.SavePickle()

        elif "check" in arg[1]:
            wrf_namelist = os.path.join(MyPath(), "namelist.input")
            wps_namelist = os.path.join(MyPath(), "namelist.wps")

            # Verify that the namelists exist
            CheckNamelists(wrf_namelist, wps_namelist)

            nlc = WRF.NamelistContainer(wrffile=wrf_namelist, wpsfile=wps_namelist)
            if "wrf" in arg[1]:
                namelist = nlc.wrf_namelist
            elif "wps" in arg[1]:
                namelist = nlc.wps_namelist
            else:
                eprint("If trying to check an argument, must use check-wrf-opt or check-wps-opt")
                eprint("(neither 'wrf' nor 'wps' found in the flag)")
                exit(1)

            for a in arg[2:]:
                optname, optval = SplitOpt(a)
                optname = optname.replace("-", "")
                if not namelist.IsOptInNamelist(optname):
                    eprint("Could not find '{0}' in specified namelist".format(optname))
                    exit(2)
                nlopt = namelist.GetOptValNoSect(optname, domainnum=1)
                optval = optval.split(",")
                optbool = []
                # Any option should be in a string format. However, some may include single quotes.
                # So we try comparing with and without single quotes
                for i in range(len(optval)):
                    optbool.append(False)
                    if optval[i] == nlopt:
                        optbool[i] = True
                        break
                    else:
                        if nlopt.startswith("'"):
                            nlopt = nlopt[1:]
                        if nlopt.endswith("'"):
                            nlopt = nlopt[:-1]
                        if optval[i] == nlopt:
                            optbool[i] = True
                            break

                if all([not b for b in optbool]):
                    exit(1)
            exit(0)
        elif "get" in arg[1]:
            wrf_namelist = os.path.join(MyPath(), "namelist.input")
            wps_namelist = os.path.join(MyPath(), "namelist.wps")

            # Verify that the namelists exist
            CheckNamelists(wrf_namelist, wps_namelist)
            
            nlc = WRF.NamelistContainer(wrffile=wrf_namelist, wpsfile=wps_namelist)
            if "wrf" in arg[1]:
                namelist = nlc.wrf_namelist
            elif "wps" in arg[1]:
                namelist = nlc.wps_namelist
            else:
                eprint("If trying to get an argument, must use get-wrf-opt or get-wps-opt")
                eprint("(neither 'wrf' nor 'wps' was found in the flag)")
                exit(1)

            if "--no-quotes" in arg:
                noquote=True
                arg.remove("--no-quotes")
            else:
                noquote=False

            optname = arg[2].replace("-", "")
            if optname == "startdate":
                start_date, end_date = nlc.get_time_period()
                print(start_date.strftime("%Y-%m-%d_%H:%M:%S"))
            elif optname == "enddate":
                start_date, end_date = nlc.get_time_period()
                print(end_date.strftime("%Y-%m-%d_%H:%M:%S"))
            elif not namelist.IsOptInNamelist(optname):
                eprint("Could not find '{0}' in specified namelist".format(optname))
                exit(2)
            else:
                val = namelist.GetOptValNoSect(optname, domainnum=1, noquotes=noquote)
                print(val)
        else:
            eprint("Command '{0}' not recognized".format(arg[1]))
            exit(1)

    if len(arg) == 1:
        print("Goodbye")
    exit(0)
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
#       1) Load standard templates: this reads the namelist.input.template and namelist.wps.template files in
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
