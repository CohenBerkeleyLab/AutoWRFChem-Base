from __future__ import print_function
import datetime as dt
import math
from collections import OrderedDict
import pickle
import os
from glob import glob
import pdb

class Namelist:
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
            for sect, optlist in self.opts.iteritems():
                f.write("&"+sect+"\n")
                for optname, optvals in optlist.iteritems():
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

        if type(vals) is list:
            self.opts[sectname][optname] = vals
        else:
            if type(self.opts[sectname][optname]) is list:
                for i in range(len(self.opts[sectname][optname])):
                    self.opts[sectname][optname][i] = vals
            else:
                self.opts[sectname][optname]

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

    def SetMetOpts(self, met_type):
        if met_type == "NARR":
            self.SetOptVal("time_control", "interval_seconds", 10800)
            self.SetOptVal("domains", "p_top_requested", 10000)
            self.SetOptVal("domains", "e_vert", 30)
            self.SetOptVal("domains", "num_metgrid_levels", 30)
            self.SetOptVal("domains", "num_metgrid_soil_levels", 4)
        else:
            raise RuntimeError("{0} is not a recognized meteorology".format(met_type))

    def GetTimePeriod(self):
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


class WpsNamelist(Namelist):
    allowed_proj = ("lambert", "mercator", "polar", "lat-lon")

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

    def SetMetOpts(self, met_type):
        if met_type == "NARR":
            self.SetOptVal("share", "interval_seconds", 10800)
        else:
            raise RuntimeError("{0} is not a recognized meteorology".format(met_type))

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
            print("{0} is not a recognized map projection".format(map_proj))
            proj_opts = None

        return proj_opts, all_opts

    def AdjustMapProjOpts(self, map_proj):
        # Returns true if adjustment succeeded, false otherwise
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

        if opt_added:
            print("New domain options added to WPS geogrid section for {0} projection - you will need to set them".format(map_proj))
        if opt_removed:
            print("Domain options unecessary for {0} projection removed".format(map_proj))
        if opt_added or opt_removed:
            junk = raw_input("Press ENTER to continue.")


class NamelistContainer:
    # Class used to store both the WRF and WPS namelists and interact with them. This way we can ensure that any options
    # common to both are kept in sync
    my_dir = os.path.dirname(__file__)
    wrf_namelist_outfile = "namelist.input"
    wrf_namelist_template_file = os.path.join(my_dir, "namelist.input.template")
    wps_namelist_outfile = "namelist.wps"
    wps_namelist_template_file = os.path.join(my_dir, "namelist.wps.template")
    pickle_file = os.path.join(my_dir, "namelist_pickle.pkl")
    cfg_fname = os.path.join(my_dir,"..","wrfbuild.cfg")
    envvar_fname = os.path.join(my_dir,"..","envvar_wrfchem.cfg")
    chem_fname = os.path.join(my_dir, "chemlist.txt")

    # List of options (besides the dates) duplicated in WRF and WPS
    domain_opts = ["e_we", "e_sn", "dx", "dy", "parent_id", "parent_grid_ratio", "i_parent_start", "j_parent_start"]
    met_opts = ["interval_seconds", "p_top_requested", "e_vert", "num_metgrid_levels", "num_metgrid_soil_levels"]
    date_opts = ["run_days", "run_hours", "run_minutes", "run_seconds", "start_year", "start_month", "start_day",
                 "start_hour", "start_minute", "start_second", "end_year", "end_month", "end_day", "end_hour",
                 "end_minute", "end_second", "start_date", "end_date"]

    def __init__(self, met=None, wrffile=None, wpsfile=None):
        # There will be two main modes of operation: "new" will read the existing template files and generate new
        # namelists. "mod" will load the pickled current namelist - which can be used if the program needs to make
        # temporary changes to the namelist to produce part of the input without losing the user defined settings
        if wrffile is None:
            self.wrf_namelist = WrfNamelist(self.wrf_namelist_template_file)
        else:
            self.wrf_namelist = WrfNamelist(wrffile)

        if wpsfile is None:
            self.wps_namelist = WpsNamelist(self.wps_namelist_template_file)
        else:
            self.wps_namelist = WpsNamelist(wpsfile)

        # Ensure that the options common to both WRF and WPS are synchronized
        start_date, end_date = self.wps_namelist.GetTimePeriod()
        self.wrf_namelist.SetTimePeriod(start_date, end_date)
        for opt in self.domain_opts:
            self.wrf_namelist.SetOptValNoSect(opt, self.wps_namelist.GetOptValNoSect(opt))

        # Met option will have to be given on the command line
        if met is not None:
            self.wrf_namelist.SetMetOpts(met)
            self.wps_namelist.SetMetOpts(met)

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
            print("No existing namelist found, loading standard template")
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
        start_time = UI.UserInputDate("Enter the starting date", currentvalue=curr_start)
        if start_time is None:
            start_time = curr_start

        end_time = UI.UserInputDate("Enter the ending date", currentvalue=curr_end)
        if end_time is None:
            end_time = curr_end

        self.SetTimePeriod(start_time, end_time)

        print("Having modified the time period, verify that the correct MOZBC data file has been selected.")
        NamelistContainer.UserSetMozFile()

    def UserSetDomain(self):
        for opt in self.domain_opts:
            optval = UI.UserInputValue(opt, currval=self.wps_namelist.GetOptValNoSect(opt, 1))
            if optval is not None:
                self.wrf_namelist.SetOptValNoSect(opt, optval)
                self.wps_namelist.SetOptValNoSect(opt, optval)
        print("Having modified the domain, verify that the correct MOZBC data file has been selected.")
        NamelistContainer.UserSetMozFile()

    def UserSetMet(self):
        met_type = UI.UserInputList("Choose your meteorology: ", Namelist.mets)
        self.SetMet(met_type)

    def SetMet(self, met_type):
        if met_type not in Namelist.mets:
            raise RuntimeError("{0} is not a valid meteorology. Allowed meteorologies are {1}".format(met_type, Namelist.mets))

        self.wrf_namelist.SetMetOpts(met_type)
        self.wps_namelist.SetMetOpts(met_type)

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
            print("Warning: could not find the wrfbuild.cfg file to ensure the meteorology is consistent.")
            print("Check that the meteorology is correct in that file before running WPS.")

    def UserSetChem(self):
        self.CheckChemTypeListFormat()
        chem_types = self.GetChemTypeList()
        if len(chem_types) == 0:
            print("No chem types defined in {0}".format(self.chem_fname))
            return

        chem_type = UI.UserInputList("Choose a chemistry type: ", chem_types)
        if chem_type is not None:
            self.SetChem(chem_type)

    def SetChem(self, chem_type):
        chem_opts = self.GetChemTypeOpts(chem_type)
        if chem_opts is not None:
            for optname, optval in chem_opts.iteritems():
                self.wrf_namelist.SetOptVal("chem",optname,optval)

    def GetChemTypeList(self):
        chem_types = []
        with open(self.chem_fname, 'r') as f:
            for line in f:
                if line[0] == "#":
                    continue
                elif "BEGIN" in line:
                    this_type = line.replace("BEGIN", "").strip()
                    chem_types.append(this_type)

        return chem_types

    def GetChemTypeOpts(self, chem_type):
        chem_opts = {}
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
                        lsplit = line.split("=")
                        optname = lsplit[0].strip()
                        optval = lsplit[1].strip()
                        chem_opts[optname] = optval

                    if "@ISKPP" in line:
                        check_kpp = True

        if check_kpp:
            found_kpp = False
            with open(self.envvar_fname, 'r') as f:
                for line in f:
                    if "WRF_KPP" in line and "=1" in line:
                        found_kpp = True
            if not found_kpp:
                print("** Note: {0} requires WRF to be compiled with KPP enabled but WRF_KPP is not set to 1 in".format(chem_type))
                print(self.envvar_fname)
                if not UI.UserInputYN("Do you still wish to choose this chemistry?", default="n"):
                    return None

        if not found_chem:
            raise IOError("Could not find {0} in {1}".format(chem_type, self.chem_fname))
        else:
            return chem_opts

    def CheckChemTypeListFormat(self):
        line_num = 0
        looking_for_end = False
        begin_lnum = 0
        begin_chem = ""
        found_chem_opt = False
        with open(self.chem_fname, 'r') as f:
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
                    print("   Warning reading chemlist.txt: BEGIN at line {0} has no matching END".format(begin_lnum))
                    found_chem_opt = False

                if "END" in line and looking_for_end:
                    if begin_chem != line.replace("END","").strip():
                        print("   Warning reading chemlist.txt: BEGIN {0} at line {1} matches {2} at line {3}"
                              " (chemistry label mismatch)".format(begin_chem, begin_lnum, line.strip(), line_num))
                    looking_for_end = False
                elif "END" in line and not looking_for_end:
                    print("   Warning reading chemlist.txt: END at line {0} has no matching BEGIN".format(line_num))

                if "END" in line and not found_chem_opt:
                    print("   Warning reading chemlist.txt: No value for chem_opt found for {0}".format(begin_chem))

                if "=" in line:
                    lsplit = line.split("=")
                    optname = lsplit[0].strip()
                    if len(optname) == 0:
                        print("   Warning reading chemlist.txt: no option name before the = in line {0}".format(line_num))
                    elif not self.wrf_namelist.IsOptInSection("chem", optname):
                        print("   Warning reading chemlist.txt: {0} is an unknown chemistry namelist option (line {1})".format(optname, line_num))
                    elif optname == "chem_opt":
                        found_chem_opt = True
                    optvals = [v for v in lsplit[1].strip().split(" ") if v != ""]
                    if len(optvals) == 0:
                        print("   Warning reading chemlist.txt: no option value after the = in line {0}".format(line_num))
                    elif len(optvals) > 1:
                        print("   Warning reading chemlist.txt: multiple option values given in line {0}".format(line_num))

    @staticmethod
    def UserSetMozFile():
        # This function should be called any time the domain or time period is changed. It will ask the user to verify
        # that the current Mozart boundary condition file is the correct one, or set one if none exists.
        # First we need two pieces of information: one, if there is a current file, what it is. Two, what files are
        # available.

        if not os.path.isfile(NamelistContainer.cfg_fname):
            print("wrfbuild.cfg does not exist. You need to run AUTOWRFCHEM CONFIG")
            print("at least once to generate this file before you can set a MOZBC file.")
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
            print("You have not created the 'data' link or folder in MOZBC!")
            print("This must be created and contain your MOZBC files. Both")
            print("this program and the MOZBC component of the automatic WRF")
            print("program rely on this.")
            raw_input("Press ENTER to continue")
            return None

        tmp = glob(os.path.join(mozDataDir, "*.nc"))
        mozFiles = [os.path.basename(f) for f in tmp]
        if len(mozFiles) < 1:
            print("No MOZBC data files present! You need to download some.")
            print("As of 20 Jul 2016, they can be obtained at")
            print("http://www.acom.ucar.edu/wrf-chem/mozart.shtml")
            raw_input("Press ENTER to continue")
            return None

        newMozFilename = UI.UserInputList("Choose the MOZBC file to use: ", mozFiles,currentvalue=mozFilename)
        if newMozFilename is None and mozFilename is not None:
            newMozFilename = mozFilename
        elif newMozFilename is None:
            print("No MOZART file selected! You will need to select one before running")
            print("the input preparation step. Rerunning 'autowrfchem config namelist'")
            print("and modifying the current namelist will allow you to select a file")
            print("later.")
            raw_input("Press ENTER to continue")
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
        sect = UI.UserInputList("Choose the namelist section: ", namelist.opts.keys())
        if sect is None:
            return

        k = namelist.opts[sect].keys()
        if len(k) == 0:
            print("{0} has no options".format(sect))
            return

        optslist = [o for o in k if o not in self.domain_opts and o not in self.met_opts and o not in self.date_opts]
        opt = UI.UserInputList("Choose the option to modify: ", optslist)
        if opt is None:
            return

        if opt == "map_proj":
            optval = UI.UserInputList("Choose a map projection: ", namelist.allowed_proj,
                                      currentvalue=namelist.GetOptValNoSect(opt, 1, noquotes=True))
        else:
            optval = UI.UserInputValue(opt, isbool=namelist.IsOptBool(sect, opt), currval=namelist.GetOptValNoSect(opt, 1))

        if optval is not None:
            namelist.SetOptVal(sect, opt, optval)
            if opt == "map_proj":
                namelist.AdjustMapProjOpts(optval)

    def DisplayOptions(self, namelist):
        sectnames = namelist.opts.keys()
        sectnames.append("All")
        sect = UI.UserInputList("Which namelist section to display?", sectnames)
        if sect == "All":
            for s in namelist.opts.keys():
                print("{0}:".format(s))
                for k,v in namelist.opts[s].iteritems():
                    print("  {0} = {1}".format(k,v))
        elif sect is not None:
            for k,v in namelist.opts[sect].iteritems():
                print("  {0} = {1}".format(k,v))

    def UserNEICompatCheck(self):
        # This will go through the WPS options and make sure that they are compatible with the NEI gridding program
        # which only handles lambert and polar map projections and requires stand_lon == ref_lon

        # Check map proj
        curr_proj = self.wps_namelist.GetOptValNoSect("map_proj",1)
        if curr_proj not in ["'lambert'", "lambert", "'polar'", "polar"]:
            if UI.UserInputYN("map_proj must be 'lambert' or 'polar' for NEI emissions. Change it?"):
                optval = UI.UserInputValue("map_proj", currval=curr_proj)
                if optval is not None:
                    self.wps_namelist.SetOptValNoSect("map_proj", optval)

        stand_lon = float(self.wps_namelist.GetOptValNoSect("stand_lon",1))
        ref_lon = float(self.wps_namelist.GetOptValNoSect("ref_lon",1))
        if stand_lon != ref_lon:
            print("NEI expects stand_lon ({0}) to be the same as ref_lon {1}".format(stand_lon, ref_lon))
            if UI.UserInputYN("Make stand_lon the same as ref_lon? "):
                self.wps_namelist.SetOptValNoSect("stand_lon", ref_lon)

        ref_lat = float(self.wps_namelist.GetOptValNoSect("ref_lat", 1))
        truelat1 = float(self.wps_namelist.GetOptValNoSect("truelat1", 1))
        truelat2 = float(self.wps_namelist.GetOptValNoSect("truelat2", 1))
        if truelat1 != ref_lat or truelat2 != ref_lat:
            print("NEI gridding should be able to accept truelats different from ref_lat, but I have not tested it.")
            print("(currently ref_lat = {0}, truelat1 = {1}, truelat2 = {2}".format(ref_lat, truelat1, truelat2))
            if UI.UserInputYN("Make the truelats the same as ref_lat?"):
                self.wps_namelist.SetOptValNoSect("truelat1", ref_lat)
                self.wps_namelist.SetOptValNoSect("truelat2", ref_lat)

        dx = int(self.wps_namelist.GetOptValNoSect("dx", 1))
        dy = int(self.wps_namelist.GetOptValNoSect("dy", 1))
        if dx < 10000:
            print("NEI regridding is very simple and may behave strangely for dx < 10000 m")
            if UI.UserInputYN("Change it?"):
                optval = UI.UserInputValue("dx", currval=dx)
                if optval is not None:
                    self.wps_namelist.SetOptValNoSect("dx", optval)
                    self.wps_namelist.SetOptValNoSect("dy", optval)
                    if dx != dy:
                        print("dy has been changed as well (dx == dy req. for NEI")

        dy = int(self.wps_namelist.GetOptValNoSect("dy", 1))
        if dx != dy:
            print("NEI expects dx == dy ({0} != {1})".format(dx, dy))
            if UI.UserInputYN("Make dy the same as dx?"):
                self.wps_namelist.SetOptValNoSect("dy", dx)

        ioform5 = int(self.wrf_namelist.GetOptValNoSect("io_form_auxinput5",1))
        if ioform5 != 2 and ioform5 != 11:
            print("io_form_auxinput5 should be 2 or 11 to use NEI, (currently {0})".format(ioform5))
            if UI.UserInputYN("Set it to 2?"):
                self.wrf_namelist.SetOptValNoSect("io_form_auxinput5",2)

        iostyleemis = int(self.wrf_namelist.GetOptValNoSect("io_style_emissions",1))
        if iostyleemis != 1:
            print("NEI expects io_style_emissions = 1 (currently {0})".format(iostyleemis))
            if UI.UserInputYN("Set it to 1?"):
                self.wrf_namelist.SetOptValNoSect("io_style_emissions", 1)

        emissinpt = int(self.wrf_namelist.GetOptValNoSect("emiss_inpt_opt",1))
        if emissinpt != 1:
            print("NEI expects emiss_inpt_opt = 1 (currently {0})".format(iostyleemis))
            if UI.UserInputYN("Set it to 1?"):
                self.wrf_namelist.SetOptValNoSect("emiss_inpt_opt", 1)

        kemit = int(self.wrf_namelist.GetOptValNoSect("kemit", 1))
        if kemit != 19:
            print("NEI has 19 emission levels. kemit is currently {0}".format(kemit))
            if UI.UserInputYN("Set kemit to 19?"):
                self.wrf_namelist.SetOptValNoSect("kemit", 19)

    def CmdSetOtherOpt(self, optname, optval, forceWrfOnly=False):
        # This one will be fairly complicated. First, we need to see if the option is one that is shared (domain opts)
        # or one that should not be set directly. After that, we need to figure out which namelist it belongs to, then
        # set it for that namelist. Will also need to check if the setting is a boolean before setting it.
        if optname in self.date_opts:
            raise RuntimeError("Do not set {0} directly, it must be set using the date/run time options.".format(optname))
        elif optname in self.met_opts:
            raise RuntimeError("Do not set {0} directly, it must be set using the --met option".format(optname))
        elif optname in self.domain_opts:
            if not forceWrfOnly:
                self.wps_namelist.SetOptValNoSect(optname, optval)
            self.wrf_namelist.SetOptValNoSect(optname, optval)
        else:
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
        sel = UI.UserInputList(prmpt, opts, returntype="index", emptycancel=False)
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
  
    
class UI:
    def __init__(self):
        pass

    @staticmethod
    def UserInputList( prompt, options, returntype="value", currentvalue=None, emptycancel=True):
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
            userans = raw_input("Enter 1-{0}: ".format(len(options)))
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
    def UserInputDate( prompt, currentvalue=None):
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
            userdate = raw_input("--> ")
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
            except ValueError, e:
                print("Problem with date/time entered: {0}".format(str(e)))
                continue

            # If we get here, nothing went wrong
            return dateout

    @staticmethod
    def UserInputValue( optname, isbool=False, currval=None, noempty=False):
        # Allows user to input a value simply. The isbool keyword input allows this function to behave differently if
        # the option is a boolean, since those options must be given as .true. or .false.
        # As with others, a value for currval will print the current value
        # Returns None if no value given
        print("Enter a new value for {0}".format(optname))
        if currval is not None:
            print("The current value is {0}".format(currval))

        while True:
            if isbool:
                userans = raw_input("T/F: ").lower().strip()
                if userans == "t":
                    return ".true."
                elif userans == "f":
                    return ".false."
                elif len(userans) == 0:
                    return None
                else:
                    print("Option is a boolean. Must enter T or F.")
            else:
                userans = raw_input("--> ").strip()
                if len(userans) == 0 and not noempty:
                    return None
                elif len(userans) == 0 and noempty:
                    print("Cannot enter an empty value.")
                else:
                    return userans

    @staticmethod
    def UserInputYN(prompt, default="y"):
        while True:
            if default in "Yy":
                defstr = " [y]/n"
                defaultans = True
            else:
                defstr = " y/[n]"
                defaultans = False
            userans = raw_input(prompt + defstr + ": ")

            if userans == "":
                return defaultans
            elif userans.lower() == "y":
                return True
            elif userans.lower() == "n":
                return False
            else:
                print("Enter y or n only. ", end="")
