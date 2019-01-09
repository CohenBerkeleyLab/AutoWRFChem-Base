from __future__ import print_function, absolute_import, division, unicode_literals

from collections import OrderedDict
import copy
import datetime as dt
import f90nml
from glob import glob
import math
import os
import re
from string import whitespace

from textui import uielements as uiel, uibuilder as uib

import pdb
from . import autowrf_consts as awc, config_utils, ENVIRONMENT, WRF_TOP_DIR, WPS_TOP_DIR, _pretty_n_col
from .. import _config_dir, _config_defaults_dir

# Python 2/3 compatibility: "input()" in Python 3 is like "raw_input()" in Python 2
try:
    input = raw_input
except NameError:
    pass

#TODO: check number of domains when loading WRF namelist
#TODO: figure out domains for WPS namelist


DEBUG_LEVEL = 1


class NamelistError(Exception):
    """
    Parent class for any namelist-related errors
    """
    pass


class NamelistReadingError(NamelistError):
    """
    Exception to use if there's an issue reading a namelist file.
    """
    pass


class NamelistFormatError(NamelistError):
    """
    Exception to use when there is an issue formatting inputs to the namelist
    """
    pass


class NamelistValueError(NamelistError):
    """
    Error if an invalid value is given for a namelist option
    """
    pass


class RegistryError(Exception):
    """
    Base class for all registry related errors
    """
    pass


class RegistryParsingError(RegistryError):
    """
    Exception to use when there is a problem parsing a registry file
    """
    pass


class RegistryIOError(RegistryError):
    """
    Exception to use when cannot find the registry file to load
    """
    pass


def msg_print(msg):
    if DEBUG_LEVEL > 0:
        print(msg)


###########################################
# FUNCTIONS TO CHECK NAMELIST INPUT TYPES #
###########################################

def _is_bool(val):
    return re.match(r'\.(true|false)\.', val) is not None


def _is_int(val):
    try:
        int(val)
    except ValueError:
        return False
    else:
        return True


def _is_real(val):
    try:
        float(val)
    except ValueError:
        return False
    else:
        return '.' in val


def _is_char(val):
    return re.match(r"'.*'$", val) is not None


_type_checks = {'logical': _is_bool, 'integer': _is_int, 'real': _is_real, 'character': _is_char}


####################
# NAMELIST CLASSES #
####################

class Namelist(object):
    # These are used to format the output so that the domains are aligned
    opt_field_width = 36
    opt_val_width = 8
    # options will be stored as an ordered dictionary of ordered dictionaries
    # the child dictionaries correspond to namelist sections (which are the key
    # names in the main dictionary). Ordering it keeps the sections in order so
    # the output namelist looks like the namelist.
    #
    # mets (= meteorologies) is just a list of allows meteorologies. It's used by
    # the NamelistContainer class to print the list of allowable meteorogies. Make
    # sure that each entry in this list has a corresponding if or elif branch in
    # SetMetOpts for each child namelist
    #
    # TODO: replace with those defined in the config file
    mets = ["NARR"]

    # functions that will be called whenever an option (given by the key) is set. The function will receive the namelist
    # instance as the only argument
    callbacks = dict()

    # extra registry rconfig entries. This dictionary will be used to update the registry dictionary with additional
    # namelist options. Each value should be a dictionary itself that would result from Registry parsing an rconfig
    # line. Currently that would have the following key/value pairs:
    #   'default' - the default value, as a string no matter what type it is. Booleans should be Fortran style, i.e.
    #     ".true." or ".false."
    #   'how_set' - a dictionary {'how': 'namelist', 'section': <section>} where <section> is the namelist section the
    #     option should be found in
    #   'num_entries' - either '1' or 'max_domains', specifying whether this option is only specified once or per-domain
    #   'symbol' - the name of the option. Should be the same as the key in the rconfig dict.
    #   'type' - what (fortran) type this value is. One of "character", "integer", "logical", "real".
    _extra_registry_entries = {}

    @property
    def max_domains(self):
        return int(self.GetOptValNoSect('max_dom')[0])

    def __init__(self, namelist_file, registry):
        self._registry = copy.deepcopy(registry)
        self._registry.registry['rconfig'].update(self._extra_registry_entries)
        self.opts = OrderedDict()
        self.ReadNamelist(namelist_file)

    def IterOpts(self):
        for sect_name, sect_dict in self.opts.items():
            for opt_name, opt_val in sect_dict.items():
                yield opt_val, opt_name, sect_name

    def ReadNamelist(self, namelist_file):
        sectname=""
        with open(namelist_file, 'r') as f:
            for line in f:
                line = line.strip()
                if len(line) == 0 or line[0] == "/":
                    continue
                elif line[0] == "&":
                    # This is a section definition line
                    # All following options are added to this
                    # section
                    sectname = line[1:]
                    self.opts[sectname] = OrderedDict()
                else:
                    # Read the line into the appropriate dictionary
                    lsplit = line.split("=")
                    optname = lsplit[0].strip()
                    # This will import multiple options for multiple domains,
                    # but things like setting the start and end date will
                    # assume that they are all the same.
                    optvals = [s.strip() for s in lsplit[1].split(",")]
                    try:
                        optvals.remove("")
                    except ValueError:
                        # Try to remove any empty strings, but don't error if there isn't one
                        pass

                    self.opts[sectname][optname] = optvals

    def WriteNamelist(self, out_filename):
        with open(out_filename, 'w') as f:
            for sect, optlist in self.opts.items():
                f.write("&"+sect+"\n")
                for optname, optvals in optlist.items():
                    padding = " " * (self.opt_field_width - len(optname) - 1)
                    f.write(" "+optname+padding+"= ")
                    for val in optvals:
                        padding = " " * (self.opt_val_width - len(val) - 1)
                        f.write(val + "," + padding)
                    f.write("\n")

                f.write(" /\n\n")

    def TimedeltaHMS(self, td):
        seconds = td.seconds
        hour = int(math.floor(seconds/3600))
        seconds = seconds % 3600
        minutes = int(math.floor(seconds/60))
        seconds = int(seconds % 60)
        return hour, minutes, seconds

    def IsOptInNamelist(self, optname):
        # Loops through all the options in the namelist and
        # checks if the specified one is there.
        for sect in self.opts:
            for k in self.opts[sect]:
                # Only need the key values, since those are the option names
                if k == optname:
                    return True

        return False

    def IsOptInSection(self, sectname, optname):
        # Much simpler check function that returns true if the option is
        # in the specified section, false otherwise. However, we will check
        # that a valid section is specified first.
        try:
            sect = self.opts[sectname]
        except KeyError:
            raise KeyError("{0} is not a valid namelist section".format(sectname))

        for k in sect:
            if k == optname:
                return True

        return False

    def IsSectionInNamelist(self, sectname):
        # Checks if the given section name exists in the namelist
        for sect in self.opts:
            if sect == sectname:
                return True

        return False

    def is_option_per_domain(self, optname):
        reg_opt = self.lookup_opt_in_registry(optname)
        return reg_opt['num_entries'] == 'max_domains'

    def FindOptSection(self, optname):
        # Returns which section the option is in, or None if not an option
        for sect in self.opts:
            if self.IsOptInSection(sect, optname):
                return sect

        return None

    def match_option_length_to_domains(self, optval, error_if_too_long=False):
        n_dom = self.max_domains
        if not isinstance(optval, list):
            optval = [optval]

        if len(optval) < n_dom:
            optval += optval[-1:] * (n_dom - len(optval))
        else:
            if error_if_too_long and len(optval) > n_dom:
                raise NamelistValueError('More values given ({}) than domains ({})'.format(len(optval), n_dom))
            else:
                optval = optval[:n_dom]

        return optval

    def check_value_type(self, optname, optval):
        """
        Check that the values given for a namelist option are of the correct format.

        :param optname: the option name
        :type optname: str

        :param optval: the option value
        :type optval: str or list of str

        :return: True if the type is correct, False otherwise. If optval is a list, a list of bools is returned.
        :rtype: bool or list of bools
        """

        reg_entry_type = self.lookup_opt_in_registry(optname)['type']
        try:
            check_fxn = _type_checks[reg_entry_type]
        except KeyError:
            raise NotImplementedError('No check function implemented for registry entry type {}'.format(reg_entry_type))

        if isinstance(optval, list):
            return [check_fxn(x) for x in optval]
        else:
            return check_fxn(optval)

    def SetOptVal(self, sectname, optname, vals_in):
        # Currently just assigns the given value to all
        # domains if more than one and not given a list
        # as vals. Will need to be changed if running nests
        # It's probably that everything actually is a list in the
        # options dict, but this will check anyway.
        # Also convert vals to strings
        if isinstance(vals_in, list):
            vals = [str(v) for v in vals_in]
        else:
            vals = str(vals_in)

        # we'll make sure that we set the right number of options for the maximum number of domains
        n_domains = self.max_domains if self.is_option_per_domain(optname) else 1

        if isinstance(vals, list):
            if len(vals) < n_domains:
                raise NamelistFormatError('Too few values given for "{opt}" in "{sect}". {n} values given; '
                                          '{n_dom} domains requested.'.format(opt=optname, sect=sectname, n=len(vals),
                                                                              n_dom=n_domains))

            self.opts[sectname][optname] = vals
        else:
            vals = self.match_option_length_to_domains(vals)
            if isinstance(self.opts[sectname][optname], list):
                self.opts[sectname][optname] = vals
            else:
                raise NotImplementedError('Option value stored in the namelist is not a list!')

        if optname in self.callbacks:
            self.callbacks[optname](self)

    def MatchOptionQuoting(self, sectname, optname, new_vals):
        # Make sure that, if the previous value of the option is quoted, that the new value is as well
        curr_val = self.GetOptVal(sectname, optname, domainnum=1)
        if curr_val[0] == "'" or curr_val[-1] == "'":
            if type(new_vals) is list:
                out_val = []
                for v in new_vals:
                    if not v.startswith("'"):
                        v = "'" + v
                    if not v.endswith("'"):
                        v += "'"
                    out_val.append(v)
            else:
                out_val = new_vals
                if not out_val.startswith("'"):
                    out_val = "'" + out_val
                if not out_val.endswith("'"):
                    out_val += "'"
        else:
            out_val = new_vals

        return out_val

    def SetOptValNoSect(self, optname, vals_in):
        # Allows you to specify just the option name without knowing its section name
        for sect in self.opts:
            if self.IsOptInSection(sect, optname):
                self.SetOptVal(sect, optname, vals_in)
                return

        raise KeyError("Could not find the option {0}".format(optname))

    def GetOptVal(self, sectname, optname, domainnum=None, match_n_domains=False):
        # Finds an option by name in "sectname". The optional argument domainnum allows the user to request a single
        # domain's value (1 based)
        if not self.IsOptInSection(sectname, optname):
            raise KeyError("Could not find the option {0}".format(optname))

        val = self.opts[sectname][optname]
        if not isinstance(val, list):
            raise NotImplementedError('All namelist values are expected to be lists')

        if match_n_domains and self.is_option_per_domain(optname):
            val = self.match_option_length_to_domains(val)
            n_dom = self.max_domains

        if domainnum is not None and self.is_option_per_domain(optname):
            if domainnum >= len(val):
                raise NamelistError('Option "{}" in section "{}" ')
            return self.opts[sectname][optname][domainnum-1]
        else:
            return self.opts[sectname][optname]

    def GetOptValNoSect(self, optname, domainnum=None, noquotes=False, match_n_domains=False):
        # Finds an option by name in any section. The optional argument domainnum allows the user to request a single
        # domain's value (1 based). noquotes removes any leading or trailing '
        val = None
        for sect in self.opts:
            if self.IsOptInSection(sect, optname):
                val = self.GetOptVal(sect, optname, domainnum=domainnum, match_n_domains=match_n_domains)
                if domainnum is not None and type(self.opts[sect][optname]) is list:
                    val = self.opts[sect][optname][domainnum-1]
                else:
                    val = self.opts[sect][optname]

        if val is None:
            raise KeyError("Could not find the option {0}".format(optname))

        if noquotes and type(val) is str:
            if val[0] == "'":
                val = val[1:]
            if val[-1] == "'":
                val = val[:-1]

        return val

    def IsOptBool(self, sectname, optname):
        opt = self.opts[sectname][optname]
        if type(opt) is list:
            opt = opt[0]

        return opt.strip() == ".true." or opt.strip() == ".false."

    def lookup_opt_in_registry(self, optname):
        return self._registry.lookup_reg_entry('rconfig', optname)


class WrfNamelist(Namelist):

    # Define extra namelist options that don't exist in the registry and whether they need to expand and contract
    # with the number of domains.
    # The NIO options (in &namelist_quilt) are read in by external/RSL_LITE/module_dm.F.
    _extra_registry_entries = {'nio_tasks_per_group':
                                {'default': '0',
                                 'how_set': {'how': 'namelist', 'section': 'namelist_quilt'},
                                 'num_entries': 'max_domains',
                                 'symbol': 'nio_tasks_per_group',
                                 'type': 'integer'
                                 },
                               'nio_groups':
                                {'default': '1',
                                 'how_set': {'how': 'namelist', 'section': 'namelist_quilt'},
                                 'num_entries': '1',
                                 'symbol': 'nio_groups',
                                 'type': 'integer'
                                }
                               }

    # Define additional callback functions in this section, then add them to the following callbacks attribute
    def UpdateOptDomains(self, trim_extra=False):
        n_dom = self.max_domains
        for optval, optname, _ in self.IterOpts():
            try:
                reg_opt = self.lookup_opt_in_registry(optname)
            except KeyError:
                print('{} not in registry!'.format(optname))
                continue
            else:
                do_expand_with_domains = reg_opt['num_entries'] == 'max_domains'

            if do_expand_with_domains:
                if len(optval) < n_dom:
                    self.SetOptValNoSect(optname, optval + optval[-1:] * (n_dom - len(optval)))
                elif len(optval) > n_dom and trim_extra:
                    self.SetOptValNoSect(optname, optval[:n_dom])

    # This must come after the callback functions are defined.
    callbacks = {'max_dom': UpdateOptDomains}

    def __init__(self, namelist_file, registry):
        super(WrfNamelist, self).__init__(namelist_file, registry)
        # Is gfdda_end_h an option in the namelist? If not, we don't need to see if it should be updated with the run
        # time
        self.update_fdda_end = False
        if self.IsOptInNamelist("gfdda_end_h"):
            # Compare the end time to the run time. If they are close (within 1 hr) then it is likely that the FDDA end
            # time was meant to be the same as the run time (i.e. use FDDA for the entire run).
            rtime = self.GetRunTime(runtime_unit="hours")
            gfdda_end = float(self.GetOptVal("fdda", "gfdda_end_h", domainnum=1))
            if abs(rtime - gfdda_end) < 1.0:
                self.update_fdda_end = True
                msg_print("Keeping gfdda_end equal to run time. To stop this, set its value manually")
                msg_print("(do not choose 'y' when asked whether to use it for the entire run)")

    def SetTimePeriod(self, startdate, enddate):
        curr_start, curr_end = self.GetTimePeriod()
        if startdate is None:
            startdate = curr_start
        elif type(startdate) is dt.timedelta:
            startdate = curr_start + startdate
        elif type(startdate) is not dt.date and type(startdate) is not dt.datetime:
            raise TypeError("startdate must be a datetime date or datetime")

        if enddate is None:
            enddate = curr_end
        elif type(enddate) is dt.timedelta:
            enddate = curr_end + enddate
        elif type(enddate) is not dt.date and type(enddate) is not dt.datetime:
            raise TypeError("enddate must be a datetime date or datetime")

        if type(startdate) is dt.date:
            startdate = dt.datetime(startdate.year, startdate.month, startdate.day)
        if type(enddate) is dt.date:
            enddate = dt.datetime(enddate.year, enddate.month, enddate.day)

        self.SetOptVal("time_control", "start_year", startdate.year)
        self.SetOptVal("time_control", "start_month", startdate.month)
        self.SetOptVal("time_control", "start_day", startdate.day)
        self.SetOptVal("time_control", "start_hour", startdate.hour)
        self.SetOptVal("time_control", "start_minute", startdate.minute)
        self.SetOptVal("time_control", "start_second", startdate.second)

        self.SetOptVal("time_control", "end_year", enddate.year)
        self.SetOptVal("time_control", "end_month", enddate.month)
        self.SetOptVal("time_control", "end_day", enddate.day)
        self.SetOptVal("time_control", "end_hour", enddate.hour)
        self.SetOptVal("time_control", "end_minute", enddate.minute)
        self.SetOptVal("time_control", "end_second", enddate.second)

        run_td = enddate - startdate
        self.SetOptVal("time_control", "run_days", run_td.days)
        hms = self.TimedeltaHMS(run_td)
        self.SetOptVal("time_control", "run_hours", hms[0])
        self.SetOptVal("time_control", "run_minutes", hms[1])
        self.SetOptVal("time_control", "run_seconds", hms[2])

        # Keep the FDDA end time the same as the run time (if desired) so that FDDA nudging is used through the whole
        # model run
        if self.update_fdda_end:
            run_time = int(math.ceil(self.GetRunTime(runtime_unit="hours")))
            self.SetOptVal("fdda", "gfdda_end_h", run_time)

    def GetTimePeriod(self, runtime_unit="days"):
        # Returns start and end dates as datetime objects and the runtime
        # in days as a float. Can override the runtime unit to be "days",
        # "hours", "minutes", or "seconds"
        sy = int(self.GetOptVal("time_control", "start_year", domainnum=1))
        sm = int(self.GetOptVal("time_control", "start_month", domainnum=1))
        sd = int(self.GetOptVal("time_control", "start_day", domainnum=1))
        shr = int(self.GetOptVal("time_control", "start_hour", domainnum=1))
        smin = int(self.GetOptVal("time_control", "start_minute", domainnum=1))
        ssec = int(self.GetOptVal("time_control", "start_second", domainnum=1))

        ey = int(self.GetOptVal("time_control", "end_year", domainnum=1))
        em = int(self.GetOptVal("time_control", "end_month", domainnum=1))
        ed = int(self.GetOptVal("time_control", "end_day", domainnum=1))
        ehr = int(self.GetOptVal("time_control", "end_hour", domainnum=1))
        emin = int(self.GetOptVal("time_control", "end_minute", domainnum=1))
        esec = int(self.GetOptVal("time_control", "end_second", domainnum=1))

        start_date = dt.datetime(sy, sm, sd, shr, smin, ssec)
        end_date = dt.datetime(ey, em, ed, ehr, emin, esec)

        return start_date, end_date

    def GetRunTime(self, runtime_unit="days"):
        rdays = float(self.GetOptVal("time_control", "run_days", domainnum=1))
        rhrs = float(self.GetOptVal("time_control", "run_hours", domainnum=1))
        rmins = float(self.GetOptVal("time_control", "run_minutes", domainnum=1))
        rsecs = float(self.GetOptVal("time_control", "run_seconds", domainnum=1))

        runtime = rdays + rhrs/24.0 + rmins/(24.0*60.0) + rsecs/(24.0*60.0*60.0)
        if runtime_unit == "days":
            pass # no calculation necessary
        elif runtime_unit == "hours":
            runtime *= 24.0
        elif runtime_unit == "minutes":
            runtime_unit *= 24.0*60.0
        elif runtime_unit == "seconds":
            runtime *= 24.0*60.0*60.0
        else:
            raise ValueError("runtime_unit '{0}' is invalid.".format(runtime_unit))

        return runtime


class WpsNamelist(Namelist):
    # allowed_proj lists valid map projections that WPS will recognize
    allowed_proj = ("lambert", "mercator", "polar", "lat-lon")
    # nei_proj must be a subset of allowed_proj, these are the projections
    # that work with the emiss_v0x.F tool used to grid NEI emissions
    nei_proj = ("lambert", "polar")

    def SetTimePeriod(self, startdate, enddate):
        curr_start, curr_end = self.GetTimePeriod()
        if startdate is None:
            startdate = curr_start
        elif type(startdate) is dt.timedelta:
            startdate = curr_start + startdate
        elif type(startdate) is not dt.date and type(startdate) is not dt.datetime:
            raise TypeError("startdate must be a datetime date, datetime, timedelta, or None (to keep current start date)")

        if enddate is None:
            enddate = curr_end
        elif type(enddate) is dt.timedelta:
            enddate = curr_end + enddate
        elif type(enddate) is not dt.date and type(enddate) is not dt.datetime:
            raise TypeError("enddate must be a datetime date, datetime, timedelta, or None (to keep current end date)")

        if type(startdate) is dt.date:
            startdate = dt.datetime(startdate.year, startdate.month, startdate.day)
        if type(enddate) is dt.date:
            enddate = dt.datetime(enddate.year, enddate.month, enddate.day)

        start_string = "{:04}-{:02}-{:02}_{:02}:{:02}:{:02}".format(startdate.year, startdate.month, startdate.day, startdate.hour, startdate.minute, startdate.second)
        self.SetOptVal("share", "start_date", start_string)
        end_string = "{:04}-{:02}-{:02}_{:02}:{:02}:{:02}".format(enddate.year, enddate.month, enddate.day, enddate.hour, enddate.minute, enddate.second)
        self.SetOptVal("share", "end_date", end_string)


    def GetTimePeriod(self):
        # Returns the start and end dates as datetime objects. Currently just returns the first domain time period
        # since this has been set up really for a single domain run.
        start_string = self.GetOptValNoSect("start_date", 1)
        end_string = self.GetOptValNoSect("end_date", 1)

        start_date = WpsNamelist.ConvertDate(start_string)
        end_date = WpsNamelist.ConvertDate(end_string)

        return start_date, end_date

    @staticmethod
    def ConvertDate(date_in):
        in_split = date_in.split("_")
        date_parts = [int(p.replace("'", "")) for p in in_split[0].split("-")]
        if len(in_split) > 1:
            time_parts = [int(p.replace("'", "")) for p in in_split[1].split(":")]
        else:
            time_parts = [0, 0, 0]
        return dt.datetime(date_parts[0], date_parts[1], date_parts[2], time_parts[0], time_parts[1], time_parts[2])

    def SetMapProj(self, map_proj, neiproj=False):
        # Special method to set map projection; needed since changing the projection
        # alters what other options should be present in geogrid
        # Setting neiproj to true will alter the messages printed if options are changed.
        self.SetOptVal("geogrid", "map_proj", map_proj)
        self.AdjustMapProjOpts(map_proj, neiproj)

    def MapProjOptions(self, map_proj):
        # Returns the necessary lat/lon settings for a given map projection as the first tuple
        # Returns all options specific to different projections as the second.
        all_opts = ("truelat1", "truelat2", "stand_lon", "pole_lat", "pole_lon")
        if map_proj == "lambert":
            proj_opts = ("truelat1", "truelat2", "stand_lon")
        elif map_proj == "mercator":
            proj_opts = ("truelat1")
        elif map_proj == "polar":
            proj_opts = ("truelat1", "stand_lon")
        elif map_proj == "lat-lon":
            proj_opts = ("pole_lat", "pole_lon", "stand_lon")
        else:
            msg_print("{0} is not a recognized map projection".format(map_proj))
            proj_opts = None

        return proj_opts, all_opts

    def AdjustMapProjOpts(self, map_proj, neiproj=False):
        # Returns true if adjustment succeeded, false otherwise
        # Setting neiproj to true will alter the messages printed if options are changed.
        proj_opts, all_opts = self.MapProjOptions(map_proj)
        # All these options are in the "geogrid" section
        curr_opts = self.opts["geogrid"].keys()
        opt_added = False
        opt_removed = False
        for opt in all_opts:
            if opt in proj_opts and opt not in curr_opts:
                # Needed option does not exist, add it.
                self.opts["geogrid"][opt] = ["0"]
                self.SetOptVal("geogrid", opt, 0)
                opt_added = True
            elif opt not in proj_opts and opt in curr_opts:
                # Unecessary option exists, remove it
                junk = self.opts["geogrid"].pop(opt)
                opt_removed = True

        if opt_added or opt_removed:
            # Shift geog_data_path around to the end
            gdp_temp = self.opts["geogrid"].pop("geog_data_path", None)
            self.opts["geogrid"]["geog_data_path"] = gdp_temp

        if opt_added and not neiproj:
            msg_print("New domain options added to WPS geogrid section for {0} projection - you will need to set them".format(map_proj))
        if opt_removed and not neiproj:
            msg_print("Domain options unecessary for {0} projection removed".format(map_proj))
        if opt_added or opt_removed:
            if neiproj:
                msg_print("geogrid options have changed with the map projection.")
                msg_print("The NEI compatibility checker will help you set them.")

            junk = input("Press ENTER to continue.")


class NamelistContainer:
    # Class used to store both the WRF and WPS namelists and interact with them. This way we can ensure that any options
    # common to both are kept in sync
    my_dir = os.path.dirname(__file__)
    wrf_namelist_outfile = "namelist.input"
    wrf_namelist_template_base = os.path.join(_config_defaults_dir, wrf_namelist_outfile + ".template")
    wps_namelist_outfile = "namelist.wps"
    wps_namelist_template_base = os.path.join(_config_defaults_dir, wps_namelist_outfile + ".template")
    pickle_file = os.path.join(my_dir, "namelist_pickle.pkl")
    cfg_fname = os.path.join(my_dir,"..","wrfbuild.cfg")
    envvar_fname = os.path.join(my_dir,"..","envvar_wrfchem.cfg")
    met_fname = os.path.join(my_dir, "metlist.txt")
    chem_fname = os.path.join(my_dir, "chemlist.txt")

    # List of options (besides the dates) duplicated in WRF and WPS
    domain_opts = ["e_we", "e_sn", "dx", "dy", "parent_id", "parent_grid_ratio", "i_parent_start", "j_parent_start"]
    met_opts = ["interval_seconds", "p_top_requested", "e_vert", "num_metgrid_levels", "num_metgrid_soil_levels", "gfdda_interval_m"]
    date_opts = ["run_days", "run_hours", "run_minutes", "run_seconds", "start_year", "start_month", "start_day",
                 "start_hour", "start_minute", "start_second", "end_year", "end_month", "end_day", "end_hour",
                 "end_minute", "end_second", "start_date", "end_date"]

    # Options that may not be set directly
    # TODO: make it so that changing a domain or date opt manually just keeps WRF and WPS in sync, and a met opt issues
    #  a warning
    _restricted_opt = domain_opts + date_opts

    @property
    def wrf_setopt_menu(self):
        return self._wrf_setopt_menu

    def __init__(self, met=None, wrffile=None, wpsfile=None, wrf_registry=None, wps_registry=None):

        # Require both namelist files to be given. Will provide separate method to load templates
        if wrffile is None or wpsfile is None:
            raise NamelistReadingError('Must give both a WRF and WPS namelist file')
        if wrf_registry is None:
            wrf_registry = Registry.load_standard_registry()
        if wps_registry is None:
            wps_registry = WPSPseudoRegistry.load_standard_registry()

        self.wrf_namelist = WrfNamelist(wrffile, registry=wrf_registry)
        self.wps_namelist = WpsNamelist(wpsfile, registry=wps_registry)

        # Ensure that the options common to both WRF and WPS are synchronized
        start_date, end_date = self.get_time_period()
        self.wrf_namelist.SetTimePeriod(start_date, end_date)
        for opt in self.domain_opts:
            self.wrf_namelist.SetOptValNoSect(opt, self.wps_namelist.GetOptValNoSect(opt))

        # Met option will have to be given on the command line
        if met is not None:
            self.set_met(met)

        self._wrf_setopt_menu = self._build_setopt_menu(self.wrf_namelist)
        self._wps_setopt_menu = self._build_setopt_menu(self.wps_namelist)

    def write_namelists(self, namelist_dir=None, wps_namelist_dir=None, suffix=None):
        """
        Write the WRF and WPS namelists out as files.

        :param namelist_dir: the directory to write the namelist files to. If not given, will write to the standard
         CONFIG directory.
        :type namelist_dir: str

        :param wps_namelist_dir: the directory to write the WPS namelist to. If not given, both WRF and WPS namelists
         will be written to the same directory. If given, the WRF namelists is written to ``namelist_dir`` and the
         WPS namelist to this one. Note that ``namelist_dir`` must be given if this one is.
        :type wps_namelist_dir: str

        :param suffix: a suffix to append to the WRF and WPS namelist file. The form of the file names will be
         ``namelist.{input,wps}.{suffix}``.
        :type suffix: str

        :return: None
        """
        if namelist_dir is None:
            if wps_namelist_dir is not None:
                TypeError('If the WPS namelist dir is given, the WRF namelist dir must also be given')
            namelist_dir = _config_dir

        if wps_namelist_dir is None:
            wps_namelist_dir = namelist_dir

        wrffile = os.path.join(namelist_dir, self.wrf_namelist_outfile)
        wpsfile = os.path.join(wps_namelist_dir, self.wps_namelist_outfile)

        if suffix is not None:
            wrffile += "." + suffix
            wpsfile += "." + suffix

        self.wrf_namelist.WriteNamelist(wrffile)
        self.wps_namelist.WriteNamelist(wpsfile)

    def save_namelists(self, save_mode='both', awc_config=None):
        """
        High level function to write the namelists out to the standard locations.

        AutoWRFChem uses two copies of the namelists. The first is the "permanent" namelists that represent the full
        model run that you want to execute. These are typically saved in the CONFIG directory. The second are the
        "temporary" namelists that describe the piece of the run that is actually being executed. These are written
        in the respective run directories for WRF and WPS.

        This method writes the namelist files to one or both of these locations. Which ones depends on the ``save_mode``
        input. It is to be one of the following strings:

            'both' - save to both the permanent and temporary locations.
            'perm', 'permanent' - only save the permanent namelists
            'temp', 'temporary' - only save the temporary namelists

        If you are looking for a lower level function to write the namelists to an arbitrary location, see
        `write_namelists`.

        :param save_mode: controls which namelists (temporary or permanent) are saved, see above. Default is 'both'.
        :type save_mode: str

        :param awc_config: an alternate `AutoWRFChemConfig` instance to specify where the WRF and WPS run directories
         are. If not given, the standard config file is loaded automatically.
        :type awc_config: AutoWRFChemConfig

        :return: None
        """

        if awc_config is None:
            awc_config = config_utils.AutoWRFChemConfig()

        save_perm = False
        save_temp = False

        if save_mode.lower() == 'both':
            save_perm = True
            save_temp = True
        elif save_mode.lower() in ['perm', 'permanent']:
            save_perm = True
        elif save_mode.lower() in ['temp', 'temporary']:
            save_temp = True
        else:
            raise ValueError('Allowed values for save_mode are "both", "perm", "permanent", "temp", or "temporary"')

        try:
            awc_config.check_auto_vars([WRF_TOP_DIR, WPS_TOP_DIR])
        except config_utils.ConfigurationSettingsError:
            if save_temp:
                print('Cannot write namelists to WRF/WPS directories, those directories are not set up correctly')
            save_temp = False

        if save_perm:
            self.write_namelists()

        if save_temp:
            wrf_dir = config_utils.get_wrf_run_dir(awc_config)
            wps_dir = config_utils.get_wps_run_dir(awc_config)
            self.write_namelists(namelist_dir=wrf_dir, wps_namelist_dir=wps_dir)

    @classmethod
    def load_namelists(cls):
        """
        Loads the static namelists from the standard place

        :return: new instance of this class
        """
        wrffile = os.path.join(_config_dir, cls.wrf_namelist_outfile)
        wpsfile = os.path.join(_config_dir, cls.wps_namelist_outfile)
        return cls(wrffile=wrffile, wpsfile=wpsfile)

    @classmethod
    def load_templates(cls, config_obj=None):
        """
        Load the standard namelist template files.

        :return: new instance of this class
        """
        return cls(wrffile=cls.wrf_namelist_template(config_obj), wpsfile=cls.wps_namelist_template())

    @classmethod
    def wrf_namelist_template(cls, config_obj=None):
        if config_utils.get_is_chem(config_obj):
            return cls.wrf_namelist_template_base + '.chem'
        else:
            return cls.wrf_namelist_template_base + '.nochem'

    @classmethod
    def wps_namelist_template(cls):
        return cls.wps_namelist_template_base

    def set_time_period(self, start_time, end_time):
        """
        Set the time period for the WRF and WPS namelists.

        Setting via this method ensures that the WRF and WPS namelist time periods stay in sync and that the WRF
        start/end date and run time settings are consistent.

        :param start_time: the beginning of the model run. If given as a `datetime.time` object, only the hour/minute/
         second of the start time will be changed; the year/month/day will be kept at their current values.
        :type start_time: `datetime.datetime` or `datetime.time`

        :param end_time: the end of the model run.  If given as a `datetime.time` object, only the hour/minute/
         second of the start time will be changed; the year/month/day will be kept at their current values.
        :type end_time: `datetime.datetime` or `datetime.time`

        :return: None
        """
        # If given datetime.time objects, it will assume that you want to set the start or end time but leave the date
        # component alone
        curr_start, curr_end = self.wps_namelist.GetTimePeriod()
        if type(start_time) is dt.time:
            start_time = dt.datetime(curr_start.year, curr_start.month, curr_start.day, start_time.hour, start_time.minute, start_time.second)

        if type(end_time) is dt.time:
            end_time = dt.datetime(curr_end.year, curr_end.month, curr_end.day, end_time.hour, end_time.minute, end_time.second)

        self.wrf_namelist.SetTimePeriod(start_time, end_time)
        self.wps_namelist.SetTimePeriod(start_time, end_time)

    def get_time_period(self):
        """
        Get the time period that each domain of the model will run for.

        :return: list of start/end date tuples, one per domain.
        :rtype: list of tuples of `datetime.datetime`s
        """
        # Basically a shortcut method to the WRF method of the same name. Switch from WPS to WRF for nesting: commonly,
        # inner nested domains only run the first time step for WPS since boundary conditions are then provided by the
        # outer domain. So getting the time from the WPS namelists doesn't really make sense.
        return self.wrf_namelist.GetTimePeriod()

    def user_set_time_period(self):
        """
        Interactively set the start and end dates for all domains.

        Currently, it assumes that all domains will run for the same time period.

        :return: None
        """

        # TODO: update for multiple domains
        # TODO: replace UI calls with textui
        curr_start, curr_end = self.wps_namelist.GetTimePeriod()
        start_time = UI.user_input_date("Enter the starting date", currentvalue=curr_start)
        if start_time is None:
            start_time = curr_start

        end_time = UI.user_input_date("Enter the ending date", currentvalue=curr_end)
        if end_time is None:
            end_time = curr_end

        self.set_time_period(start_time, end_time)

        msg_print("Having modified the time period, verify that the correct MOZBC data file has been selected.")
        NamelistContainer.UserSetMozFile()

    def user_set_domain(self):
        """
        Set the domain options interactively.

        :return: None
        """

        # TODO: update for multiple domains?
        # TODO: replace UI calls with textui
        for opt in self.domain_opts:
            optval = UI.user_input_value(opt, currval=self.wps_namelist.GetOptValNoSect(opt, 1))
            if optval is not None:
                self.wrf_namelist.SetOptValNoSect(opt, optval)
                self.wps_namelist.SetOptValNoSect(opt, optval)
        msg_print("Having modified the domain, verify that the correct MOZBC data file has been selected.")
        NamelistContainer.UserSetMozFile()

    def user_set_met(self):
        """
        Set the meteorology interactively

        :return: None
        """

        # TODO: should this be moved out of the namelist container?
        # TODO: replace UI with textui

        met_type = UI.user_input_list("Choose your meteorology: ", self.GetTypeList(self.met_fname))
        self.set_met(met_type)

    def set_met(self, met_type):
        """
        Set all namelist options relevant for the given meteorology

        :param met_type: the meteorology type
        :type met_type: str

        :return: None
        """
        if met_type not in self.GetTypeList(self.met_fname):
            raise RuntimeError("{0} is not a valid meteorology. Allowed meteorologies are {1}".
                               format(met_type, ', '.join(self.GetTypeList(self.met_fname))))

        met_opts = self.GetMetTypeOpts(met_type)
        missing_opts = []
        if met_opts is not None:
            for opt in met_opts:
                nl = opt["namelist"]
                if nl.IsOptInNamelist(opt["name"]):
                    nl.SetOptVal(opt["section"], opt["name"], opt["value"])
                else:
                    missing_opts.append(opt)

        if len(missing_opts) > 0:
            msg_print("The following options were not in the namelist:")
            for opt in missing_opts:
                msg_print("    {0}/{1}".format(opt["section"], format(opt["name"])))
            msg_print("This may not be a problem, if these are optional settings")

        # Also make sure that the met choice is reflected in the wrfbuild.cfg file which *should* be one level up

        if os.path.isfile(self.cfg_fname):
            with open(self.cfg_fname, 'r') as cfgr:
                cfg_lines = cfgr.readlines()

            with open(self.cfg_fname, 'w') as cfgw:
                for l in cfg_lines:
                    if "metType=" in l:
                        cfgw.write("metType={0}\n".format(met_type))
                    else:
                        cfgw.write(l)
        else:
            msg_print("Warning: could not find the wrfbuild.cfg file to ensure the meteorology is consistent.")
            msg_print("Check that the meteorology is correct in that file before running WPS.")

    def user_set_chem(self):
        """
        Choose chemical mechanism interactively

        :return: None
        """
        self.CheckTypeListFormat(self.chem_fname)
        chem_types = self.GetTypeList(self.chem_fname)
        if len(chem_types) == 0:
            msg_print("No chem types defined in {0}".format(self.chem_fname))
            return

        chem_type = UI.user_input_list("Choose a chemistry type: ", chem_types)
        if chem_type is not None:
            self.set_chem(chem_type)

    def set_chem(self, chem_type):
        """
        Set namelist options relevant for the specified chemical mechanism

        :param chem_type: the name of the chemical mechanism
        :type chem_type: str

        :return: None
        """
        chem_opts = self.GetChemTypeOpts(chem_type)
        if chem_opts is not None:
            for opt in chem_opts:
                nl = opt["namelist"]
                nl.SetOptVal(opt["section"], opt["name"], opt["value"])

    def user_set_map_proj(self, neionly=False):
        """
        Interactively set the map project WPS uses to map lat/lon to model grid

        :param neionly: optional, if ``True``, restrict the available options to those compatible with the NEI emissions
         preparation tool. Default is ``False``.
        :type neionly: bool

        :return: None
        """
        # Special method to set the WPS map projection that will present a list of options and
        # tell the namelist to adjust the other options accordingly (some are not needed to certain
        # projections)

        if neionly:
            proj_list = self.wps_namelist.nei_proj
        else:
            proj_list = self.wps_namelist.allowed_proj

        optval = uiel.user_input_list("Choose a map projection: ", proj_list, printcols=False,
                                      currentvalue=self.wps_namelist.GetOptValNoSect("map_proj", 1, noquotes=True))
        if optval is not None:
            self.wps_namelist.SetMapProj(optval, neionly)

    def GetTypeList(self, list_file):
        # TODO: unneeded? or update to work with config files?
        types = []
        with open(list_file, 'r') as f:
            for line in f:
                if line[0] == "#":
                    continue
                elif "BEGIN" in line:
                    this_type = line.replace("BEGIN", "").strip()
                    types.append(this_type)

        return types

    def GetMetTypeOpts(self, met_type):
        # TODO: convert to using the config files
        met_opts = []
        found_met = False
        reading_met = False
        with open(self.met_fname, 'r') as f:
            for line in f:
                if len(line.strip()) == 0 or line.strip()[0] == "#":
                    continue
                if "BEGIN" in line and met_type in line:
                    found_met = True
                    reading_met = True
                elif reading_met and "END" in line:
                    reading_met = False
                elif reading_met:
                    if "=" in line:
                        opt_dict = self.ParseOptionLine(line)
                        met_opts.append(opt_dict)

        if not found_met:
            raise IOError("Could not find {0} in {1}".format(met_type, self.met_fname))
        else:
            return met_opts

    def GetChemTypeOpts(self, chem_type):
        # TODO: convert to using the config files
        chem_opts = []
        found_chem = False
        reading_chem = False
        check_kpp = False
        with open(self.chem_fname, 'r') as f:
            for line in f:
                if len(line.strip()) == 0 or line.strip()[0] == "#":
                    continue
                if "BEGIN" in line and chem_type in line:
                    found_chem = True
                    reading_chem = True
                elif reading_chem and "END" in line:
                    reading_chem = False
                elif reading_chem:
                    if "=" in line:
                        opt_dict = self.ParseOptionLine(line)
                        chem_opts.append(opt_dict)

                    if "@ISKPP" in line:
                        check_kpp = True

        if check_kpp:
            found_kpp = False
            if os.path.isfile(self.envvar_fname):
                with open(self.envvar_fname, 'r') as f:
                    for line in f:
                        if "WRF_KPP" in line and "=1" in line:
                            found_kpp = True
                if not found_kpp:
                    msg_print("** Note: {0} requires WRF to be compiled with KPP enabled but WRF_KPP is not set to 1 in".format(chem_type))
                    msg_print(self.envvar_fname)
                    if not UI.user_input_yn("Do you still wish to choose this chemistry?", default="n"):
                        return None
            else:
                msg_print("** Note: {0} requires WRF to be compiled with KPP enabled. Could not find\n"
                      "{1}\n"
                      "to ensure that the env. variable WRF_KPP is set.\n"
                      "Be sure KPP is enabled when you configure WRF.".format(chem_type, self.envvar_fname))

        if not found_chem:
            raise IOError("Could not find {0} in {1}".format(chem_type, self.chem_fname))
        else:
            return chem_opts

    def ParseOptionLine(self, line):
        # probably not needed
        lsplit = line.split("=")
        optid = lsplit[0].strip().split(":")
        if len(optid) != 3:
            raise IOError("Problem reading a list file: line does not have namelist, section, and "
                          "option name specified: {0}".format(line))

        if optid[0] == "wrf":
            nl = self.wrf_namelist
        elif optid[0] == "wps":
            nl = self.wps_namelist
        else:
            raise IOError("{0} is not a valid namelist (reading metlist.txt)".format(optid[0]))


        optsect = optid[1]
        optname = optid[2]
        optval = lsplit[1].strip()
        return {"namelist":nl, "section":optsect, "name": optname, "value":optval}

    def CheckTypeListFormat(self, list_file):
        # probably not needed
        list_shortfile = os.path.basename(list_file)

        line_num = 0
        looking_for_end = False
        begin_lnum = 0
        begin_chem = ""
        found_chem_opt = False
        with open(list_file, 'r') as f:
            for line in f:
                line_num += 1
                if len(line.strip()) == 0 or line.strip()[0] == "#":
                    continue

                if "BEGIN" in line and not looking_for_end:
                    looking_for_end = True
                    begin_lnum = line_num
                    begin_chem = line.replace("BEGIN","").strip()
                    found_chem_opt = False
                elif "BEGIN" in line and looking_for_end:
                    msg_print("   Warning reading {1}: BEGIN at line {0} has no matching END".format(begin_lnum, list_shortfile))
                    found_chem_opt = False

                if "END" in line and looking_for_end:
                    if begin_chem != line.replace("END","").strip():
                        msg_print("   Warning reading {4}: BEGIN {0} at line {1} matches {2} at line {3}"
                              " (label mismatch)".format(begin_chem, begin_lnum, line.strip(), line_num, list_shortfile))
                    looking_for_end = False
                elif "END" in line and not looking_for_end:
                    msg_print("   Warning reading {1}: END at line {0} has no matching BEGIN".format(line_num, list_shortfile))

                if "END" in line and list_shortfile == "chemlist.txt" and not found_chem_opt:
                    msg_print("   Warning reading {1}: No value for chem_opt found for {0}".format(begin_chem, list_shortfile))

                if "=" in line:
                    lsplit = line.split("=")
                    optid = [v for v in lsplit[0].strip().split(":") if v != ""]

                    if len(optid) != 3:
                        msg_print("   Warning reading {0}: any option must specify namelist, section, and option name"
                              " separated by colons. Line {1} does not.".format(list_shortfile, line_num))

                    if optid[0] == "wrf":
                        nl = self.wrf_namelist
                    elif optid[0] == "wps":
                        nl = self.wps_namelist
                    else:
                        msg_print("   Warning reading {0}: '{1}' is not a recognized namelist (line {2})".
                              format(list_shortfile, optid[0], line_num))
                        continue

                    optsect = optid[1]
                    optname = optid[2]

                    if len(optname) == 0:
                        msg_print("   Warning reading {1}: no option name before the = in line {0}".format(line_num, list_shortfile))
                    elif not nl.IsSectionInNamelist(optsect):
                        msg_print("   Warning reading {0}: {1} is not a valid {2} namelist section (line {3})".
                              format(list_shortfile, optsect, optid[0], line_num))
                    elif not nl.IsOptInSection(optsect, optname):
                        msg_print("   Warning reading {0}: {1}:{2} is an unknown {3} namelist section/option pair (line {4})".
                              format(list_shortfile, optsect, optname, optid[0], line_num, ))
                    elif optname == "chem_opt":
                        found_chem_opt = True

                    optvals = [v for v in lsplit[1].strip().split(" ") if v != ""]
                    if len(optvals) == 0:
                        msg_print("   Warning reading {1}: no option value after the = in line {0}".format(line_num, list_shortfile))
                    elif len(optvals) > 1:
                        msg_print("   Warning reading {1}: multiple option values given in line {0}".format(line_num, list_shortfile))

    @staticmethod
    def UserSetMozFile():
        # TODO: massive rework

        # This function should be called any time the domain or time period is changed. It will ask the user to verify
        # that the current Mozart boundary condition file is the correct one, or set one if none exists.
        # First we need two pieces of information: one, if there is a current file, what it is. Two, what files are
        # available.

        if not os.path.isfile(NamelistContainer.cfg_fname):
            msg_print("wrfbuild.cfg does not exist. You need to run AUTOWRFCHEM CONFIG")
            msg_print("at least once to generate this file before you can set a MOZBC file.")
            return None

        with open(NamelistContainer.cfg_fname, 'r') as cfgr:
            cfg_lines = cfgr.readlines()

        mozFilename=None
        for l in cfg_lines:
            if "mozbcFile" in l:
                tmp = l.split("=")
                mozFilename=tmp[1]
                break

        mozDataDir = os.path.join(NamelistContainer.my_dir,"..","..","MOZBC","data")
        if not os.path.exists(mozDataDir):
            msg_print("You have not created the 'data' link or folder in MOZBC!")
            msg_print("This must be created and contain your MOZBC files. Both")
            msg_print("this program and the MOZBC component of the automatic WRF")
            msg_print("program rely on this.")
            input("Press ENTER to continue")
            return None

        tmp = glob(os.path.join(mozDataDir, "*.nc"))
        mozFiles = [os.path.basename(f) for f in tmp]
        if len(mozFiles) < 1:
            msg_print("No MOZBC data files present! You need to download some.")
            msg_print("As of 20 Jul 2016, they can be obtained at")
            msg_print("http://www.acom.ucar.edu/wrf-chem/mozart.shtml")
            input("Press ENTER to continue")
            return None

        newMozFilename = UI.user_input_list("Choose the MOZBC file to use: ", mozFiles, currentvalue=mozFilename)
        if newMozFilename is None and mozFilename is not None:
            newMozFilename = mozFilename
        elif newMozFilename is None:
            msg_print("No MOZART file selected! You will need to select one before running")
            msg_print("the input preparation step. Rerunning 'autowrfchem config namelist'")
            msg_print("and modifying the current namelist will allow you to select a file")
            msg_print("later.")
            input("Press ENTER to continue")
            return None
        
        wroteMoz=False
        with open(NamelistContainer.cfg_fname, 'w') as cfgw:
            for l in cfg_lines:
                if "mozbcFile" in l:
                    cfgw.write("mozbcFile=\"{0}\"\n".format(newMozFilename))
                    wroteMoz=True
                else:
                    cfgw.write(l)
            if not wroteMoz:
                cfgw.write("mozbcFile=\"{0}\"\n".format(newMozFilename))

    def user_set_opt(self, namelist_name):
        if namelist_name == 'wrf':
            uib.Program(self.wrf_setopt_menu, autostart=True)
        elif namelist_name == 'wps':
            uib.Program(self.wps_setopt_menu, autostart=True)
        else:
            raise NotImplementedError('No set opt menu defined for namelist_name == "{}"'.format(namelist_name))

    def _user_set_other_opt(self, pgrm_data, namelist, option_name):
        """

        :type pgrm_data: dict
        :type namelist: `Namelist`
        :type option_name: str
        :return:
        """
        opt_type = namelist.lookup_opt_in_registry(option_name)['type']
        is_per_domain = namelist.is_option_per_domain(option_name)

        def print_help():
            if opt_type == 'integer':
                type_help = '{opt} is an integer. Values must be entered as numbers only, no non-numeric characters.'
                four_dom_ex = ['1', '2', '3', '4']
            elif opt_type == 'real':
                type_help = '{opt} is a real number. Values entered must include a decimal point, e.g. "1." or "1.0",' \
                            ' not just "1".'
                four_dom_ex = ['1.0', '2.0', '3.0', '4.0']
            elif opt_type == 'logical':
                type_help = '{opt} is a logical value. Values must be ".true.", "t", or "T" for true and ".false.", ' \
                            '"f" or "F" for false.'
                four_dom_ex = ['.true.', '.true.', '.true.', '.true.']
            elif opt_type == 'character':
                type_help = '{opt} is a character value. Values must each be enclosed in single quotes.'
                four_dom_ex = ["'alpha'", "'beta'", "'gamma'", "'delta'"]
            else:
                raise NotImplementedError('type_help not defined for opt type = {}'.format(opt_type))

            help_str = 'All examples assume 4 domains.\n' \
                       '* Enter values for each domain separated by commas, e.g. "{ex1}".\n' \
                       '* If you enter fewer values than there are domains, then the last value ' \
                       'will be repeated (e.g. "{ex2in}" -> "{ex2out}"\n' \
                       '* You may specify which domains to edit with an @ command at the beginning ' \
                       'of the value.\n' \
                       '  - "@1 {ex3a}" would set the first domain only to {ex3a}\n' \
                       '  - "@1:2 {ex3b}" and "@:2 {ex3b}" would set the first two domains to {ex3b}\n' \
                       '  - "@3: {ex3c}" and "@3:4 {ex3c}" would set domains 3 and 4 to {ex3c}\n\n'
            help_str += type_help
            help_str = help_str.format(opt=option_name, ex1=', '.join(four_dom_ex), ex2in=', '.join(four_dom_ex[:2]),
                                       ex2out=', '.join(four_dom_ex[:2] + four_dom_ex[1:2]*2),
                                       ex3a=', '.join(four_dom_ex[:1]), ex3b=', '.join(four_dom_ex[:2]),
                                       ex3c=', '.join(four_dom_ex[2:]))
            uiel.user_message(help_str, max_columns=_pretty_n_col, pause=True)

        def check_fxn(user_input):
            if re.match(r'\s*\?\s*$', user_input):
                print_help()
                return False

            try:
                self._parse_option_input(namelist, option_name, user_input)
            except NamelistValueError as err:
                print('Improper value: {}'.format(err.args[0]))
                return False
            else:
                return True

        if option_name in self.date_opts:
            uiel.user_message('This option must be set through the "Start/end date" option in the main namelist '
                              'menu', max_columns=_pretty_n_col, pause=True)
            return
        elif option_name == 'map_proj':
            self.user_set_map_proj()
        # TODO: met opts. Needs to check current config (can use pgrm_data) and if that option has already been changed

        nval = '1 value per domain' if is_per_domain else 'exactly 1 value'
        prompt = 'Enter value(s) for {opt}, in {type} format. {opt} accepts {nval}. (? for help)'.format(
            opt=option_name, type=opt_type, nval=nval
        )

        curr_val = ', '.join(namelist.GetOptValNoSect(option_name))
        user_val = uiel.user_input_value(prompt, testfxn=check_fxn, testmsg='', currentvalue=curr_val)
        if user_val is not None:
            namelist.SetOptValNoSect(option_name, self._parse_option_input(namelist, option_name, user_val))

    def _build_setopt_menu(self, namelist):
        if isinstance(namelist, WrfNamelist):
            component = 'WRF'
        elif isinstance(namelist, WpsNamelist):
            component = 'WPS'
        else:
            component = ''

        def get_namelist_value():
            pass

        def build_section_menu(section, menu):
            """

            :type section: dict
            :type menu: `uibuilder.Menu`
            :return:
            """
            for opt in section:
                menu.attach_custom_fxn(opt, lambda pgrm_data, nl=namelist, optname=opt: self._user_set_other_opt(pgrm_data, nl, optname))

        setopt_main = uib.Menu('Set {} options: choose namelist section'.format(component),
                               last_item_name_override='Back')

        for sect_name, sect in namelist.opts.items():
            new_menu = setopt_main.add_submenu(sect_name)
            build_section_menu(sect, new_menu)

        return setopt_main

    def _parse_option_input(self, namelist, optname, input_str):

        # To handle multiple domains we need fairly complex logic. The rules are:
        #   1.  The user enters a comma separated list of values for each domain.
        #   1a. If the option is not a per domain option, do not allow multiple values to be entered.
        #   1b. If the option is a per domain option and the user enters fewer values than required, repeat the last
        #       value to fill out the necessary domains.
        #   1c. If the option is a per domain option and the user enters too many, do not accept it
        #
        #   2.  To change a subset of domains, the user can begin with a "@" value
        #   2a. The @ gets followed by python slice notation (e.g. 1, 1:, :2, 1:2, :) are all valid. However, the
        #       indexing is 1-based
        #   2b. This is ignored if the option is not per-domain
        #
        #   3.  Each value gets checked to make sure it is the right format for the type defined in the registry.
        #   3a. 'logical's must be either .true. or .false.
        #   3b. 'integer's must be parsable by int()
        #   3c. 'real's must be parsable by float() and contain a decimal point
        #   3d. 'character's must be enclosed in single quotes

        ###########################
        # First get any @ command #
        ###########################

        at_command = re.compile(r'\s*@\d*:?\d*')
        at_cmd_match = at_command.match(input_str)
        if at_cmd_match is not None:
            # Don't know why, but if I don't include the look-behind for the @, this returns an empty string
            indices = re.search(r'(?<=@)\d*:?\d*', input_str).group()
            # A slice object is a programmatic version of the "start:end" notation. Giving it None for the start or
            # end is like omitting that side of the colon, e.g. slice(None,5) === :5. This list converts the string
            # representation into arguments for slice.
            indices = [None if x == '' else int(x)-1 for x in indices.split(':')]
            if len(indices) == 1:
                # special case: if no colon, we need to make the slice a one-element one which means the equivalent of
                # 5:6, since 5:5 is zero-length. Convert from 1-based to 0-based index.
                xx = slice(indices[0], indices[0]+1)
            else:
                if indices[1] is not None:
                    # Also make the end index inclusive
                    indices[1] += 1
                xx = slice(indices[0], indices[1])
        else:
            xx = None

        input_str = at_command.sub('', input_str)

        # We'll need to know if this is a per-domain option
        is_per_domain = namelist.is_option_per_domain(optname)

        # Now split the input into a comma separated list. Ignore leading or trailing commas as well
        input_str = input_str.strip(whitespace + ',')
        input_vals = [s.strip() for s in input_str.split(',')]

        #################
        # Handle slices #
        #################

        if not is_per_domain and (len(input_vals) != 1 or input_vals[0] == ''):
            # Check that a single-value option gets exactly one value
            raise NamelistValueError('{} requires exactly 1 value'.format(optname))
        elif is_per_domain:
            if xx is None:
                # If no "@" command given, then we expand the input values to fill the right number of domains
                # Still error if too many given
                input_vals = namelist.match_option_length_to_domains(input_vals, error_if_too_long=True)
            else:
                inds = xx.indices(namelist.max_domains)
                slice_length = len(range(*inds))
                if len(input_vals) != slice_length:
                    raise NamelistValueError('{} domain(s) specified to change, but {} values provided'.format(
                        slice_length, len(input_vals)
                    ))

        #########################
        # Check type formatting #
        #########################

        reg_opt = namelist._registry.lookup_reg_entry('rconfig', optname)
        # Allow T or F (case insensitive) for logical values.
        if reg_opt['type'] == 'logical':
            for i, v in enumerate(input_vals):
                if v.lower() == 't':
                    input_vals[i] = '.true.'
                elif v.lower() == 'f':
                    input_vals[i] = '.false.'

        good_opts = namelist.check_value_type(optname, input_vals)
        if not all(good_opts):
            # Find which domains options were incorrectly formatted
            slice_start = xx.start if xx is not None else 0
            bad_inds = [str(i + 1 + slice_start) for i, x in enumerate(good_opts) if not x]
            raise NamelistValueError('The values for domain(s) {} are the incorrect format for the "{}" type'.format(
                ', '.join(bad_inds), reg_opt['type']
            ))

        if xx is None:
            return input_vals
        else:
            new_vals = copy.copy(namelist.GetOptValNoSect(optname, match_n_domains=True))
            new_vals[xx] = input_vals
            return new_vals

    def display_options(self, namelist):
        """
        Interactively display current values for options in a section of the namelist

        :param namelist: the namelist object to modify
        :type namelist: `Namelist`

        :return: None
        """
        sectnames = list(namelist.opts.keys())
        sectnames.append("All")
        sect = UI.user_input_list("Which namelist section to display?", sectnames)
        if sect == "All":
            for s in namelist.opts.keys():
                msg_print("{0}:".format(s))
                for k,v in namelist.opts[s].items():
                    msg_print("  {0} = {1}".format(k,v))
        elif sect is not None:
            for k,v in namelist.opts[sect].items():
                msg_print("  {0} = {1}".format(k,v))

    def user_nei_compat_check(self):
        """
        Interactively verify that the WPS settings are compatible with the NEI emissions prep tool

        :return: None
        """
        # This will go through the WPS options and make sure that they are compatible with the NEI gridding program
        # which only handles lambert and polar map projections and requires stand_lon == ref_lon

        # Check map proj
        curr_proj = self.wps_namelist.GetOptValNoSect("map_proj",1)
        if curr_proj not in ["'lambert'", "lambert", "'polar'", "polar"]:
            if UI.user_input_yn("map_proj must be 'lambert' or 'polar' for NEI emissions. Change it?"):
                self.user_set_map_proj(neionly=True)

        wps_expect_opt = ["stand_lon", "ref_lon", "ref_lat", "truelat1", "truelat2", "dx", "dy"]
        wrf_expect_opt = ["io_form_auxinput5", "io_style_emissions", "emiss_inpt_opt", "kemit"]
        missing_opts = False
        for opt in wps_expect_opt:
            if not self.wps_namelist.IsOptInNamelist(opt):
                msg_print("Option {0} not found in WPS namelist".format(opt))
                missing_opts = True
        for opt in wrf_expect_opt:
            if not self.wrf_namelist.IsOptInNamelist(opt):
                msg_print("Option {0} not found in WRF namelist".format(opt))
                missing_opts = True

        if missing_opts:
            msg_print("")
            msg_print("************************************************************************")
            msg_print("One or more expected options are missing from namelists")
            msg_print("This may be because an incompatible map projection was chosen")
            msg_print("Correct the map projection and try again.")
            msg_print("Note that polar projections have not been tested; if you are having")
            msg_print("issues with a polar projection, please open an issue at the GitHub repo:")
            msg_print(awc.repo)
            msg_print("************************************************************************")
            return

        stand_lon = float(self.wps_namelist.GetOptValNoSect("stand_lon",1))
        ref_lon = float(self.wps_namelist.GetOptValNoSect("ref_lon",1))
        if stand_lon != ref_lon:
            msg_print("NEI expects stand_lon ({0}) to be the same as ref_lon {1}".format(stand_lon, ref_lon))
            if UI.user_input_yn("Make stand_lon the same as ref_lon? "):
                self.wps_namelist.SetOptValNoSect("stand_lon", ref_lon)

        ref_lat = float(self.wps_namelist.GetOptValNoSect("ref_lat", 1))
        truelat1 = float(self.wps_namelist.GetOptValNoSect("truelat1", 1))
        truelat2 = float(self.wps_namelist.GetOptValNoSect("truelat2", 1))
        if truelat1 != ref_lat or truelat2 != ref_lat:
            msg_print("NEI gridding should be able to accept truelats different from ref_lat, but I have not tested it.")
            msg_print("(currently ref_lat = {0}, truelat1 = {1}, truelat2 = {2}".format(ref_lat, truelat1, truelat2))
            if UI.user_input_yn("Make the truelats the same as ref_lat?"):
                self.wps_namelist.SetOptValNoSect("truelat1", ref_lat)
                self.wps_namelist.SetOptValNoSect("truelat2", ref_lat)

        dx = int(self.wps_namelist.GetOptValNoSect("dx", 1))
        dy = int(self.wps_namelist.GetOptValNoSect("dy", 1))
        if dx < 10000:
            msg_print("NEI regridding is very simple and may behave strangely for dx < 10000 m")
            if UI.user_input_yn("Change it?"):
                optval = UI.user_input_value("dx", currval=dx)
                if optval is not None:
                    self.wps_namelist.SetOptValNoSect("dx", optval)
                    self.wps_namelist.SetOptValNoSect("dy", optval)
                    if dx != dy:
                        msg_print("dy has been changed as well (dx == dy req. for NEI")

        dy = int(self.wps_namelist.GetOptValNoSect("dy", 1))
        if dx != dy:
            msg_print("NEI expects dx == dy ({0} != {1})".format(dx, dy))
            if UI.user_input_yn("Make dy the same as dx?"):
                self.wps_namelist.SetOptValNoSect("dy", dx)

        ioform5 = int(self.wrf_namelist.GetOptValNoSect("io_form_auxinput5",1))
        if ioform5 != 2 and ioform5 != 11:
            msg_print("io_form_auxinput5 should be 2 or 11 to use NEI, (currently {0})".format(ioform5))
            if UI.user_input_yn("Set it to 2?"):
                self.wrf_namelist.SetOptValNoSect("io_form_auxinput5",2)

        iostyleemis = int(self.wrf_namelist.GetOptValNoSect("io_style_emissions",1))
        if iostyleemis != 1:
            msg_print("NEI expects io_style_emissions = 1 (currently {0})".format(iostyleemis))
            if UI.user_input_yn("Set it to 1?"):
                self.wrf_namelist.SetOptValNoSect("io_style_emissions", 1)

        emissinpt = int(self.wrf_namelist.GetOptValNoSect("emiss_inpt_opt",1))
        if emissinpt != 1:
            msg_print("NEI expects emiss_inpt_opt = 1 (currently {0})".format(iostyleemis))
            if UI.user_input_yn("Set it to 1?"):
                self.wrf_namelist.SetOptValNoSect("emiss_inpt_opt", 1)

        kemit = int(self.wrf_namelist.GetOptValNoSect("kemit", 1))
        if kemit != 19:
            msg_print("NEI has 19 emission levels. kemit is currently {0}".format(kemit))
            if UI.user_input_yn("Set kemit to 19?"):
                self.wrf_namelist.SetOptValNoSect("kemit", 19)

    def cmd_set_other_opt(self, optname, optval, force_wrf_only=False):
        """
        Set a namelist option non-interactively

        :param optname: the option name to change
        :type optname: str

        :param optval: the value to give the option

        :param force_wrf_only: optional, if ``True`` only the WRF namelist will be changed even if the option also
         exists in the WPS namelist.
        :type force_wrf_only: bool

        :return: None
        """
        # This one will be fairly complicated. First, we need to see if the option is one that is shared (domain opts)
        # or one that should not be set directly. After that, we need to figure out which namelist it belongs to, then
        # set it for that namelist. Will also need to check if the setting is a boolean before setting it.
        if optname in self.date_opts:
            raise RuntimeError("Do not set {0} directly, it must be set using the date/run time options.".format(optname))
        elif optname in self.domain_opts:
            # TODO: seems like this would raise a KeyError a lot of the time...
            if not force_wrf_only:
                self.wps_namelist.SetOptValNoSect(optname, optval)
            self.wrf_namelist.SetOptValNoSect(optname, optval)
        else:
            if optname in self.met_opts:
                msg_print("Warning: {0} is typically set by changing the meteorology type, rather than directly.".format(optname))
            sect = self.wps_namelist.FindOptSection(optname)
            if sect is not None:
                namelist = self.wps_namelist
            else:
                sect = self.wrf_namelist.FindOptSection(optname)
                if sect is None:
                    raise RuntimeError("{0} is not an option in either the WRF or WPS namelist".format(optname))
                else:
                    namelist = self.wrf_namelist
            if namelist.IsOptBool(sect, optname) and optval != ".true." and optval != ".false.":
                raise RuntimeError("{0} is a boolean value and so can only be give the value .true. or .false.".format(optname))
            namelist.SetOptVal(sect, optname, optval)


class Registry(object):
    """
    Parse and represent the WRF registry

    The entries in the registry will be stored in the `registry` attribute as a dictionary, where each key is an entry
    type e.g. 'state', 'rconfig' etc. Each value will be another dictionary storing the individual entries by name.

    :param registry_file: the top registry file to read. Any subfiles `include`d will be read as well.
    :type registry_file: str

    :param envvar_config: the configuration object that stores the environmental variables used when compiling WRF.
     This is needed to choose which parts of the registry to include/not include since some parts are disabled based
     on the core chosen or other configuration options for the model.

    :param entry_types: a tuple of strings that will be used to filter what entries in the registry should be included.
     Examples are 'state', 'rconfig', i.e. the first value on a registry line. Default is just `('rconfig',)`.
    :type entry_types: tuple of str
    """

    @property
    def registry(self):
        """
        A dictionary representation of the WRF registry
        :return:
        """
        return self._registry

    # WRF registry description:
    # http://www2.mmm.ucar.edu/wrf/users/tutorial/201201/WRF%20Registry%20and%20Examples.ppt.pdf
    def __init__(self, registry_file, envvar_config, entry_types=('rconfig',)):
        """
        See class help.
        """
        # used to keep track of the include stack of registry files in case we need to print a warning/error message
        self._file_stack = []

        self._envvar_config = envvar_config
        self._entry_types = entry_types
        self._registry = self._parse_reg_file(registry_file)

    @classmethod
    def load_standard_registry(cls, **kwargs):
        """
        Load the standard registry file from the WRF directory defined in the configuration.

        This looks for $WRF_TOP_DIR/Registry/Registry.

        :param kwargs: Additional keyword arguments to pass through to the class __init__ function.

        :return: new instance of the Registry class.
        :rtype: `Registry`.
        :raises RegistryIOError: if the registry file does not exist
        """
        config_obj = config_utils.AutoWRFChemConfig()
        wrf_reg_dir = os.path.join(config_utils.get_wrf_top_dir(config_obj), 'Registry')

        std_reg_file = os.path.join(wrf_reg_dir, 'Registry')

        if not os.path.isfile(std_reg_file):
            raise RegistryIOError('Cannot find standard registry file ({})'.format(std_reg_file))

        return cls(std_reg_file, config_obj, **kwargs)

    def _parse_reg_file(self, reg_file):
        """
        Parse a single registry file.

        :param reg_file: the registry file to parse
        :type reg_file: str

        :return: the registry dictionary.
        :rtype: dict
        """
        def check_envvar(vardef):
            varname, state = vardef.split('=')
            try:
                env_state = self._envvar_config['ENVIRONMENT'][varname]
            except KeyError:
                # variable not defined in the config, so not set
                env_state = '0'

            return env_state.strip() == state.strip()

        reg_dict = {k: dict() for k in self._entry_types}

        if not os.path.isfile(reg_file):
            raise RegistryIOError('Registry file "{}" does not exist'.format(reg_file))

        with open(reg_file, 'r') as rfile:
            # opened a new registry file: add it to the stack. allows recursive calls to this function to keep track
            # of the chain of include directives followed to get to this file.
            self._file_stack.append([0, reg_file])
            skipping = False

            for line in rfile:
                # increment current line number (1-based for readability)
                self._file_stack[-1][0] += 1

                # Remove comments, skip to next line if nothing left
                line = re.sub(r'#.*', '', line).strip()
                if len(line) == 0:
                    continue

                entry = line.split()[0].strip()
                # The registry seems to use c-preprocessor ifdef lines to turn on or off parts of it based on e.g. which
                # model core is active (which is why we need the environmental variable configuration). So far, "ifdef"
                # is the only c-preprocessor directive that's used. If more get added later, we might be able to use
                # something like PLY (https://github.com/dabeaz/ply) to call the cpp, but it might not work since the
                # registry uses "ifdef" and not "#ifdef".
                #
                # For now, when we hit an "ifdef" we check if the condition is met; if not, we start skipping lines
                # until the next "endif".
                if not skipping and entry == 'ifdef':
                    # TODO: check that the registry ifdef lines actually require the env var to be 1, not just defined
                    # TODO: check that the registry ifdef = 0 should be True if the environmental variable is not defined
                    skipping = not check_envvar(line.split()[1])
                elif entry == "endif":
                    skipping = False
                elif not skipping:
                    # If not skipping due to env. var., then actually parse the line. If it's an include, we end up
                    # calling this function recursively to parse the included registry file. Otherwise, if it's an entry
                    # type that we are keeping, parse the line.
                    if entry == 'include':
                        self._add_reg_include(reg_dict, reg_file, line)
                    elif entry in self._entry_types:
                        if entry == 'rconfig':
                            self._add_rconfig(reg_dict['rconfig'], line)
                        else:
                            # Only error if we're supposed to be parsing this entry type but don't have a method to
                            # do so
                            raise NotImplementedError('No method to parse a registry entry of type "{entry}"'.format(entry=entry))

        self._file_stack.pop()
        return reg_dict

    def _add_reg_include(self, reg_dict, base_reg_file, line):
        """
        Add a registry file included in a parent file.

        :param reg_dict: the registry dictionary to update with entries from the included registry.
        :type reg_dict: dict

        :param base_reg_file: the path to registry file that contained the include directive that we're following. We
         assume that any included registry files' paths are given relative to the base file.
        :type base_reg_file: str

        :param line: the line containing the include directive.
        :type line: str

        :return: None, modifies reg_dict in place.
        """
        incl_file = re.search(r'(?<=include)\s+.+$', line).group()
        incl_file = incl_file.strip()
        incl_dir = os.path.dirname(base_reg_file)
        new_reg_file = os.path.join(incl_dir, incl_file)
        new_dict = self._parse_reg_file(new_reg_file)
        for key, val in new_dict.items():
            reg_dict[key].update(new_dict[key])

    def _add_rconfig(self, rconfig_dict, reg_line):
        """
        Parse an rconfig entry in the registry and add it to the rconfig dictionary.

        :param rconfig_dict: the dictionary containing all rconfig entries.
        :type rconfig_dict: dict

        :param reg_line: the line in the registry
        :type reg_line: str

        :return: None, modifies rconfig_dict in place
        """

        # The column that defines how an rconfig option is set has two possible forms:
        #   1) "namelist,<section>" e.g. "namelist,physics"
        #   2) "derived"
        # In the former case, we'll likely want to readily access which namelist section an option belongs in in case we
        # need to add it, so we split this column up into a dictionary to make that easier.
        def parse_how_set(val):
            val = val.split(',')
            if len(val) == 1 and val[0] == 'derived':
                return {'how', val[0], 'section', None}
            elif len(val) == 2 and val[0] == 'namelist':
                return {'how', val[0], 'section', val[1]}
            else:
                raise NotImplementedError('No parsing method defined for length {} and first part = "{}"'.format(
                    len(val), val[0]
                ))

        # Just need to set up the parsing functions, we'll rely on _parse_reg_line to do the heavy lifting
        names_and_parsers = [(None, None), ('type', str), ('symbol', str), ('how_set', parse_how_set),
                             ('num_entries', str), ('default', str)]
        self._parse_reg_line(rconfig_dict, reg_line, 2, names_and_parsers)

    def _parse_reg_line(self, entry_dict, reg_line, key_ind, names_and_parsers):
        """
        Parse a single registry line

        :param entry_dict: the dictionary containing individual entries; this will be updated in place.
        :type entry_dict: dict

        :param reg_line: the registry line to parse
        :type reg_line: str

        :param key_ind: which column to use as the key in the entry dict (0-based).
        :type key_ind: int

        :param names_and_parsers: a list of 2-element tuples where the first element is the key to use in the individual
         entry's dictionary to hold the value in the corresponding column, and the second is a function to call on the
         value in the column to parse it. Set both elements to ``None`` to ignore this column. An example for 'rconfig'
         entries is::

             [(None, None), ('type', str), ('symbol', str), ('how_set', parse_how_set),
              ('num_entries', str), ('default', str)]

         which will ignore the first column (which is 'rconfig') and create a dictionary with keys 'type', 'symbol',
         'how_set', 'num_entries', and 'default'. The values for each is the function in the tuple called on the string
         in that column, e.g. ``'type' = str(val)``.
        :type names_and_parsers: list of (str, function) tuples

        :return: None, modifies entry_dict in place.
        """
        reg_line = reg_line.split()
        key = reg_line[key_ind]
        line_dict = dict()
        for i, (name, parser) in enumerate(names_and_parsers):
            if name is not None:
                line_dict[name] = parser(reg_line[i])

        if key in entry_dict:
            # If a registry entry shows up more than once, we only care about the first instance. I'm basing this on
            # registry.io_boilerplate for WRF v3.9.1.1. In it, it defines 'auxinput1_inname' and 'io_form_auxinput1'
            # before it includes io_boilerplate_temporary.inc. The comments say that the above rconfig opts override
            # those in io_boilerplate_temporary.inc, hence I assume that the first occurrence of an entry is the one
            # that gets used.
            msg_print('Entry already exists in registry dictionary: "{key}" {stack}'.format(key=key,
                                                                                            stack=self._format_file_stack()))
        else:
            entry_dict[key] = line_dict

    def _format_file_stack(self):
        """
        Create a message describing the current stack of registry files being read.

        This is useful for errors when parsing a registry file that may be several ``include``s deep so that the
        error message can reflect exactly the path through the registry that the parser took.

        :return: the message
        :rtype: str
        """

        # print from the file in backwards
        msg = "in {file} at line {line_no}".format(file=self._file_stack[-1][1], line_no=self._file_stack[-1][0])
        for level in reversed(self._file_stack[:-1]):
            msg += ",\n  included at line {line_no} in {file}".format(line_no=level[0], file=level[1])
        return msg

    def lookup_reg_entry(self, entry_type, entry_name, match_case=False):
        """
        Return a given entry.

        :param entry_type: The type of entry (e.g. "state", "rconfig") to get.
        :type entry_type: str

        :param entry_name: The specific entry to get.
        :type entry_name: str

        :param match_case: optional, specifies whether the entry_name should match the letter case of the stored
         entry_names. Default is False, i.e. matching will be case-insensitive.
        :type match_case: bool

        :return: the dictionary representing the registry entry
        :rtype: dict

        :raises KeyError: if cannot find a unique entry with name ``entry_name``
        """

        if not match_case:
            return self._find_entry_case_insensitive(entry_type, entry_name)
        else:
            type_dict = self.registry[entry_type]
            return type_dict[entry_name]

    def _find_entry_case_insensitive(self, reg_type, entry_name, error_if_multiple=True):
        """
        Find a registry entry ignoring case of both the type and name

        :param reg_type: the registry entry type (e.g. "state", "rconfig").
        :type reg_type: str

        :param entry_name: the name of the registry entry to search for
        :type entry_name: str

        :param error_if_multiple: optional, controls what happens if multiple entries match the given entry name. If
         ``True`` (default), a `KeyError` will be raised if more than one entry matching the ``reg_type`` and
         ``entry_name`` are found. If ``False``, a list of matching entries is returned.
        :type error_if_multiple: bool

        :return: a single entry dictionary if ``error_if_multiple`` is ``True``, a list of such dicts if it is ``False``
        :rtype: dict or list of dicts

        :raises KeyError: if no matching entry is found, or if >1 found and ``error_if_multiple`` is ``True``.
        """
        def find_key_case_insensitive(dict_in, dict_key):
            keys = []
            for key, val in dict_in.items():
                if key.lower() == dict_key.lower():
                    keys.append(val)
            return keys

        entry_type_dicts = find_key_case_insensitive(self.registry, reg_type)
        entries = []
        for etype_dict in entry_type_dicts:
            entries += find_key_case_insensitive(etype_dict, entry_name)

        if error_if_multiple and len(entries) > 1:
            raise KeyError('Multiple entries found matching "{}/{}" (case insensitive)'.format(reg_type, entry_name))
        elif len(entries) < 1:
            raise KeyError('Entry "{}/{}" not found'.format(reg_type, entry_name))

        if error_if_multiple:
            return entries[0]
        else:
            return entries


class WPSPseudoRegistry(Registry):
    def _parse_reg_file(self, reg_file):
        """
        Parse the WPS "all_options" namelist as a pseudo registry

        :param reg_file: the path to the namelist.wps.all_options file
        :type reg_file: str

        :return: a dictionary with the 'rconfig' entry type section containing the WPS entry types
        """
        all_opts_nl = f90nml.read(reg_file)
        default_n_dom = all_opts_nl['share']['max_dom']
        nl_dict = dict()
        for sect_name, section in all_opts_nl.items():
            for opt_name, opt_val in section.items():
                default_val = opt_val[0] if isinstance(opt_val, list) else opt_val
                opt_dict = dict()
                opt_dict['default'] = default_val
                opt_dict['how_set'] = {'how': 'namelist', 'section': sect_name}
                if isinstance(opt_val, list):
                    if len(opt_val) == default_n_dom:
                        opt_dict['num_entries'] = 'max_domains'
                    else:
                        opt_dict['num_entries'] = 'multiple'
                else:
                    opt_dict['num_entries'] = '1'
                opt_dict['symbol'] = opt_name
                if isinstance(default_val, bool):
                    opt_dict['type'] = 'logical'
                elif isinstance(default_val, int):
                    opt_dict['type'] = 'integer'
                elif isinstance(default_val, float):
                    opt_dict['type'] = 'real'
                elif isinstance(default_val, str):
                    opt_dict['type'] = 'character'
                else:
                    raise NotImplementedError('No fortran type defined for WPS value of type {}'.format(
                        type(default_val).__name__
                    ))
                nl_dict[opt_name] = opt_dict

        return {'rconfig': nl_dict}

    @classmethod
    def load_standard_registry(cls, **kwargs):
        """
        Load the standard namelist.wps.all_options file form the WPS directory defined in the configuration

        This looks for $WPS_TOP_DIR/namelist.wps.all_options

        :param kwargs: Additional keyword arguments to pass through to the class __init__ function.

        :return: new instance of the WPSPseudoRegistry class
        :rtype: `WPSPseudoRegistry`
        :raises RegistryIOError: if the namelist.wps.all_options file does not exist
        """
        config_obj = config_utils.AutoWRFChemConfig()
        std_reg_file = os.path.join(config_utils.get_wps_top_dir(config_obj), 'namelist.wps.all_options')
        if not os.path.isfile(std_reg_file):
            raise RegistryIOError('Cannot find standard all options WPS namelist ({})'.format(std_reg_file))

        return cls(std_reg_file, config_obj, **kwargs)