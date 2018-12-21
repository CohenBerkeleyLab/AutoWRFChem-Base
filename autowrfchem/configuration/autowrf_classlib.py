from __future__ import print_function, absolute_import, division, unicode_literals

from collections import OrderedDict
import datetime as dt
from glob import glob
import math
import os
import pickle
import re

import pdb
from . import autowrf_consts as awc

# Python 2/3 compatibility: "input()" in Python 3 is like "raw_input()" in Python 2
try:
    input = raw_input
except NameError:
    pass

DEBUG_LEVEL=1


class NamelistFormatError(Exception):
    """
    Exception to use when there is an issue formatting inputs to the namelist
    """
    pass


class RegistryParsingError(Exception):
    """
    Exception to use when there is a problem parsing a registry file
    """


def msg_print(msg):
    if DEBUG_LEVEL > 0:
        print(msg)


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
    mets = ["NARR"]

    def __init__(self, namelist_file):
        self.opts = OrderedDict()
        self.ReadNamelist(namelist_file)

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

    def FindOptSection(self, optname):
        # Returns which section the option is in, or None if not an option
        for sect in self.opts:
            if self.IsOptInSection(sect, optname):
                return sect

        return None

    def SetOptVal(self, sectname, optname, vals_in):
        # Currently just assigns the given value to all
        # domains if more than one and not given a list
        # as vals. Will need to be changed if running nests
        # It's probably that everything actually is a list in the
        # options dict, but this will check anyway.
        # Also convert vals to strings
        if type(vals_in) is list:
            vals = [str(v) for v in vals_in]
        else:
            vals = str(vals_in)

        vals = self.MatchOptionQuoting(sectname, optname, vals)

        # we'll make sure that we set the right number of options for the maximum number of domains
        n_domains = int(self.GetOptValNoSect('max_dom')[0])

        if type(vals) is list:
            if len(vals) < n_domains:
                raise NamelistFormatError('Too few values given for "{opt}" in "{sect}". {n} values given; '
                                          '{n_dom} domains requested.'.format(opt=optname, sect=sectname, n=len(vals),
                                                                              n_dom=n_domains))

            self.opts[sectname][optname] = vals
        else:
            vals = [vals] * n_domains
            if type(self.opts[sectname][optname]) is list:
                for i in range(len(self.opts[sectname][optname])):
                    self.opts[sectname][optname][i] = vals
            else:
                raise NotImplementedError('Option value stored in the namelist is not a list!')

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

    def GetOptVal(self, sectname, optname, domainnum=None):
        # Finds an option by name in "sectname". The optional argument domainnum allows the user to request a single
        # domain's value (1 based)
        if not self.IsOptInSection(sectname, optname):
            raise KeyError("Could not find the option {0}".format(optname))

        if domainnum is not None and type(self.opts[sectname][optname]) is list:
            return self.opts[sectname][optname][domainnum-1]
        else:
            return self.opts[sectname][optname]

    def GetOptValNoSect(self, optname, domainnum=None, noquotes=False):
        # Finds an option by name in any section. The optional argument domainnum allows the user to request a single
        # domain's value (1 based). noquotes removes any leading or trailing '
        val = None
        for sect in self.opts:
            if self.IsOptInSection(sect, optname):
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


class WrfNamelist(Namelist):
    def __init__(self, namelist_file):
        Namelist.__init__(self, namelist_file)
        #pdb.set_trace()
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
    wps_namelist_outfile = "namelist.wps"
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

    def __init__(self, met=None, wrffile=None, wpsfile=None):
        # There will be two main modes of operation: "new" will read the existing template files and generate new
        # namelists. "mod" will load the pickled current namelist - which can be used if the program needs to make
        # temporary changes to the namelist to produce part of the input without losing the user defined settings
        if wrffile is None:
            raise TypeError("A wrffile must be specified")
        else:
            self.wrf_namelist = WrfNamelist(wrffile)

        if wpsfile is None:
            raise TypeError("A wpsfile must be specified")
        else:
            self.wps_namelist = WpsNamelist(wpsfile)

        # Ensure that the options common to both WRF and WPS are synchronized
        start_date, end_date = self.wps_namelist.GetTimePeriod()
        self.wrf_namelist.SetTimePeriod(start_date, end_date)
        for opt in self.domain_opts:
            self.wrf_namelist.SetOptValNoSect(opt, self.wps_namelist.GetOptValNoSect(opt))

        # Met option will have to be given on the command line
        if met is not None:
            self.SetMet(met)

    def WriteNamelists(self, dir=None, suffix=None):
        if dir is None:
            wrffile = os.path.join(self.my_dir, self.wrf_namelist_outfile)
            wpsfile = os.path.join(self.my_dir, self.wps_namelist_outfile)
        else:
            wrffile = os.path.join(dir, self.wrf_namelist_outfile)
            wpsfile = os.path.join(dir, self.wps_namelist_outfile)

        if suffix is not None:
            wrffile += "." + suffix
            wpsfile += "." + suffix

        self.wrf_namelist.WriteNamelist(wrffile)
        self.wps_namelist.WriteNamelist(wpsfile)

    def SavePickle(self):
        with open(self.pickle_file, 'wb') as pf:
            pickle.dump(self, pf)

    @staticmethod
    def LoadPickle():
        if os.path.isfile(NamelistContainer.pickle_file):
            with open(NamelistContainer.pickle_file, 'rb') as pf:
                return pickle.load(pf)
        else:
            msg_print("No existing namelist found, loading standard template")
            return NamelistContainer()

    def SetTimePeriod(self, starttime, endtime):
        # If given datetime.time objects, it will assume that you want to set the start or end time but leave the date
        # component alone
        curr_start, curr_end = self.wps_namelist.GetTimePeriod()
        if type(starttime) is dt.time:
            starttime = dt.datetime(curr_start.year, curr_start.month, curr_start.day, starttime.hour, starttime.minute, starttime.second)

        if type(endtime) is dt.time:
            endtime = dt.datetime(curr_end.year, curr_end.month, curr_end.day, endtime.hour, endtime.minute, endtime.second)

        self.wrf_namelist.SetTimePeriod(starttime, endtime)
        self.wps_namelist.SetTimePeriod(starttime, endtime)

    def GetTimePeriod(self):
        # Basically a shortcut method to the WPS method of the same name
        return self.wps_namelist.GetTimePeriod()

    def UserSetTimePeriod(self):
        curr_start, curr_end = self.wps_namelist.GetTimePeriod()
        start_time = UI.user_input_date("Enter the starting date", currentvalue=curr_start)
        if start_time is None:
            start_time = curr_start

        end_time = UI.user_input_date("Enter the ending date", currentvalue=curr_end)
        if end_time is None:
            end_time = curr_end

        self.SetTimePeriod(start_time, end_time)

        msg_print("Having modified the time period, verify that the correct MOZBC data file has been selected.")
        NamelistContainer.UserSetMozFile()

    def UserSetDomain(self):
        for opt in self.domain_opts:
            optval = UI.user_input_value(opt, currval=self.wps_namelist.GetOptValNoSect(opt, 1))
            if optval is not None:
                self.wrf_namelist.SetOptValNoSect(opt, optval)
                self.wps_namelist.SetOptValNoSect(opt, optval)
        msg_print("Having modified the domain, verify that the correct MOZBC data file has been selected.")
        NamelistContainer.UserSetMozFile()

    def UserSetMet(self):
        met_type = UI.user_input_list("Choose your meteorology: ", self.GetTypeList(self.met_fname))
        self.SetMet(met_type)

    def SetMet(self, met_type):
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

    def UserSetChem(self):
        self.CheckTypeListFormat(self.chem_fname)
        chem_types = self.GetTypeList(self.chem_fname)
        if len(chem_types) == 0:
            msg_print("No chem types defined in {0}".format(self.chem_fname))
            return

        chem_type = UI.user_input_list("Choose a chemistry type: ", chem_types)
        if chem_type is not None:
            self.SetChem(chem_type)

    def UserSetMapProj(self, neionly=False):
        # Special method to set the WPS map projection that will present a list of options and
        # tell the namelist to adjust the other options accordingly (some are not needed to certain
        # projections)

        if neionly:
            proj_list = self.wps_namelist.nei_proj
        else:
            proj_list = self.wps_namelist.allowed_proj


        optval = UI.user_input_list("Choose a map projection: ", proj_list,
                                    currentvalue=self.wps_namelist.GetOptValNoSect("map_proj", 1, noquotes=True))
        if optval is not None:
            self.wps_namelist.SetMapProj(optval, neionly)

    def UserSetFDDAEnd(self):

        whole_run = UI.user_input_yn("Use FDDA nudging for the entire run?")
        if whole_run:
            run_hours = self.wrf_namelist.GetRunTime(runtime_unit="hours")
            run_hours = int(math.ceil(run_hours))
            self.wrf_namelist.SetOptVal("fdda", "gfdda_end_h", run_hours)
            self.wrf_namelist.update_fdda_end = True
            msg_print("gfdda_end_h set to {0}".format(run_hours))
        else:
            self.wrf_namelist.update_fdda_end = False
            optval = UI.user_input_value("gfdda_end_h", currval=self.wrf_namelist.GetOptValNoSect("gfdda_end_h", 1))

            if optval is not None:
                self.wrf_namelist.SetOptVal("fdda", "gfdda_end_h", optval)


    def SetChem(self, chem_type):
        chem_opts = self.GetChemTypeOpts(chem_type)
        if chem_opts is not None:
            for opt in chem_opts:
                nl = opt["namelist"]
                nl.SetOptVal(opt["section"], opt["name"], opt["value"])

    def GetTypeList(self, list_file):
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

    def UserSetOtherOpt(self, namelist):
        sect = UI.user_input_list("Choose the namelist section: ", namelist.opts.keys())
        if sect is None:
            return

        k = namelist.opts[sect].keys()
        if len(k) == 0:
            msg_print("{0} has no options".format(sect))
            return

        optslist = [o for o in k if o not in self.domain_opts and o not in self.date_opts]
        opt = UI.user_input_list("Choose the option to modify: ", optslist)
        if opt is None:
            return

        if opt in self.met_opts:
            msg_print("Note: {0} is usually set by choosing a meteorology type, not directly".format(opt))

        if opt == "map_proj":
            self.UserSetMapProj()
        elif opt == "gfdda_end_h":
            self.UserSetFDDAEnd()
        else:
            optval = UI.user_input_value(opt, isbool=namelist.IsOptBool(sect, opt), currval=namelist.GetOptValNoSect(opt, 1))

            if optval is not None:
                namelist.SetOptVal(sect, opt, optval)

    def DisplayOptions(self, namelist):
        sectnames = namelist.opts.keys()
        sectnames.append("All")
        sect = UI.user_input_list("Which namelist section to display?", sectnames)
        if sect == "All":
            for s in namelist.opts.keys():
                msg_print("{0}:".format(s))
                for k,v in namelist.opts[s].iteritems():
                    msg_print("  {0} = {1}".format(k,v))
        elif sect is not None:
            for k,v in namelist.opts[sect].iteritems():
                msg_print("  {0} = {1}".format(k,v))

    def UserNEICompatCheck(self):
        # This will go through the WPS options and make sure that they are compatible with the NEI gridding program
        # which only handles lambert and polar map projections and requires stand_lon == ref_lon

        # Check map proj
        curr_proj = self.wps_namelist.GetOptValNoSect("map_proj",1)
        if curr_proj not in ["'lambert'", "lambert", "'polar'", "polar"]:
            if UI.user_input_yn("map_proj must be 'lambert' or 'polar' for NEI emissions. Change it?"):
                self.UserSetMapProj(neionly=True)

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

    def CmdSetOtherOpt(self, optname, optval, forceWrfOnly=False):
        # This one will be fairly complicated. First, we need to see if the option is one that is shared (domain opts)
        # or one that should not be set directly. After that, we need to figure out which namelist it belongs to, then
        # set it for that namelist. Will also need to check if the setting is a boolean before setting it.
        if optname in self.date_opts:
            raise RuntimeError("Do not set {0} directly, it must be set using the date/run time options.".format(optname))
        elif optname in self.domain_opts:
            if not forceWrfOnly:
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

    def UserMenu(self):
        # Present a menu to let the user modify the namelist once. So this should be called from a while loop to allow
        # user to modify mulitple options. Returns True or False, False if the user has requested to exit.
        prmpt = "Choose what to modify or do:"
        opts = ["Start/end date", "Domain (common opts only)", "Meterology", "Chemistry", "Other WRF options",
                "Other WPS options", "Check for NEI compatibility", "Select MOZBC file", "Display WRF options",
                "Display WPS options", "Save and exit"]
        sel = UI.user_input_list(prmpt, opts, returntype="index", emptycancel=False)
        if sel == 0:
            self.UserSetTimePeriod()
        elif sel == 1:
            self.UserSetDomain() # Note that this only sets the options SHARED between WRF and WPS
        elif sel == 2:
            self.UserSetMet()
        elif sel == 3:
            self.UserSetChem()
        elif sel == 4:
            self.UserSetOtherOpt(self.wrf_namelist)
        elif sel == 5:
            self.UserSetOtherOpt(self.wps_namelist)
        elif sel == 6:
            self.UserNEICompatCheck()
        elif sel == 7:
            NamelistContainer.UserSetMozFile()
        elif sel == 8:
            self.DisplayOptions(self.wrf_namelist)
        elif sel == 9:
            self.DisplayOptions(self.wps_namelist)
        elif sel == 10:
            return False

        return True
  

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
            # TODO: actually check state.
            #  if state is '1', then we need to check that the variable is in the config and set to 1. If '0' then need
            #  to check that it is either missing from the config or in the config and set to 0.
            return False

        reg_dict = {k: dict() for k in self._entry_types}

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
                    skipping = not check_envvar(line.split()[1])
                elif entry == "endif":
                    skipping = False
                elif not skipping:
                    # If not skipping due to env. var., then actually parse the line. If it's an include, we end up
                    # calling this function recursively to parse the included registry file. Otherwise, if it's an entry
                    # type that we are keeping, parse the line.
                    if entry == 'include':
                        self._add_reg_include(reg_dict, reg_file, line)
                        if len(self._file_stack) == 1:
                            print(len(reg_dict['rconfig']))
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
        if len(self._file_stack) == 1:
            print('new:', len(new_dict['rconfig']))
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
            elif len(val) == 2 and val[1] == 'namelist':
                return {'how', val[0], 'section', val[1]}

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


class UI:
    def __init__(self):
        pass

    @staticmethod
    def user_input_list(prompt, options, returntype="value", currentvalue=None, emptycancel=True):
        # Method will give the user their list of options, sequentially numbered, and ask them to chose one. It will
        # ensure that the selection is in the permissible range and return, by default, the value selected. The keyword
        # argument "returntype" can be set to "index" to have this function return the index within the list options
        # rather than the value. The keyword currentvalue can be used to mark which option is currently selected
        # Returns None if the user enters an empty value to abort

        # Input checking
        if type(prompt) is not str:
            raise TypeError("PROMPT must be a string")
        if type(options) is not list and type(options) is not tuple:
            raise TypeError("OPTIONS must be a list or tuple")
        if type(returntype) is not str or returntype.lower() not in ["value", "index"]:
            raise TypeError("RETURNTYPE must be one of the strings 'value' or 'index'")

        print(prompt)
        if emptycancel:
            print("A empty answer will cancel.")
        if currentvalue is not None:
            print("The current value is marked with a *")
        for i in range(1, len(options)+1):
            if currentvalue is not None and options[i-1] == currentvalue:
                currstr = "*"
            else:
                currstr = " "
            print("  {2}{0}: {1}".format(i, options[i-1], currstr))

        while True:
            userans = input("Enter 1-{0}: ".format(len(options)))
            if len(userans) == 0:
                return None

            try:
                userans = int(userans)
            except ValueError:
                print("Input invalid")
            else:
                if userans > 0 and userans <= len(options):
                    break

        if returntype.lower() == "value":
            return options[userans-1]
        elif returntype.lower() == "index":
            return userans - 1
        else:
            raise ValueError("Value '{0}' for keyword 'returntype' is not recognized".format(returntype))

    @staticmethod
    def user_input_date(prompt, currentvalue=None):
        # Prompts the user for a date in yyyy-mm-dd or yyyy-mm-dd HH:MM:SS format. Only input is a prompt describing
        # what the date is. Returns a datetime object. The currentvalue keyword can be used to display the current
        # setting, but it must be a datetime object as well. Returns none if user ever enters an empty string.
        if currentvalue is not None and type(currentvalue) is not dt.datetime:
            raise TypeError("If given, currentvalue must be a datetime object")

        print(prompt)
        print("Enter in the format yyyy-mm-dd or yyyy-dd-mm HH:MM:SS")
        print("i.e. both 2016-04-01 and 2016-04-01 00:00:00 represent midnight on April 1st, 2016")
        print("Entering nothing will cancel")
        if currentvalue is not None:
            print("Current value is {0}".format(currentvalue))

        while True:
            userdate = input("--> ")
            userdate = userdate.strip()
            if len(userdate) == 0:
                return None

            date_and_time = userdate.split(" ")
            date_and_time = [s.strip() for s in date_and_time]
            if len(date_and_time) == 1:
                # No time passed, set to midnight
                hour = 0
                min = 0
                sec = 0
            else:
                time = date_and_time[1].split(':')
                if len(time) != 3:
                    print('Time component must be of form HH:MM:SS (three 2-digit numbers separated by colons')
                    continue

                try:
                    hour = int(time[0])
                    min = int(time[1])
                    sec = int(time[2])
                except ValueError:
                    print("Error parsing time. Be sure only numbers 0-9 are used to define HH, MM, and SS")
                    continue

            date = date_and_time[0].split("-")
            if len(date) != 3:
                print("Date component must be of form yyyy-mm-dd (4-, 2-, and 2- digits separated by dashed")
                continue

            try:
                yr = int(date[0])
                mn = int(date[1])
                dy = int(date[2])
            except ValueError:
                print("Error parsing date. Be sure only numbers 0-9 are used to define yyyy, mm, and dd.")
                continue

            # Take advantage of datetime's built in checking to be sure we have a valid date
            try:
                dateout = dt.datetime(yr,mn,dy,hour,min,sec)
            except ValueError as e:
                print("Problem with date/time entered: {0}".format(str(e)))
                continue

            # If we get here, nothing went wrong
            return dateout

    @staticmethod
    def user_input_value(optname, isbool=False, currval=None, noempty=False):
        # Allows user to input a value simply. The isbool keyword input allows this function to behave differently if
        # the option is a boolean, since those options must be given as .true. or .false.
        # As with others, a value for currval will print the current value
        # Returns None if no value given
        print("Enter a new value for {0}".format(optname))
        if currval is not None:
            print("The current value is {0}".format(currval))

        while True:
            if isbool:
                userans = input("T/F: ").lower().strip()
                if userans == "t":
                    return ".true."
                elif userans == "f":
                    return ".false."
                elif len(userans) == 0:
                    return None
                else:
                    print("Option is a boolean. Must enter T or F.")
            else:
                userans = input("--> ").strip()
                if len(userans) == 0 and not noempty:
                    return None
                elif len(userans) == 0 and noempty:
                    print("Cannot enter an empty value.")
                else:
                    return userans

    @staticmethod
    def user_input_yn(prompt, default="y"):
        while True:
            if default in "Yy":
                defstr = " [y]/n"
                defaultans = True
            else:
                defstr = " y/[n]"
                defaultans = False
            userans = input(prompt + defstr + ": ")

            if userans == "":
                return defaultans
            elif userans.lower() == "y":
                return True
            elif userans.lower() == "n":
                return False
            else:
                print("Enter y or n only. ", end="")
