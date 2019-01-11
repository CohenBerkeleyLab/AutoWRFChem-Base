#!/usr/bin/env python
from __future__ import print_function
import argparse
import calendar
import datetime as dt
from glob import glob
import os
import re
import sys

from .. import MetFilesMissingError
from . import MixedTarredUntarredFilesError

import pdb
__author__ = 'Josh'

# This program generates a list of expected met GRIB files for a given time period
# The time period should be specified in YYYY-MM-DD format from the command line.


def _narr_end_of_range_date(curr_date, ndays):
    # NARR date ranges are such that they do not cross months; if a range of days would
    # straddle two months, it is cut off at the end of that month.
    tdel = dt.timedelta(days=ndays-1)
    eor_date = curr_date + tdel
    eom_day = calendar.monthrange(curr_date.year, curr_date.month)[1]
    #pdb.set_trace()
    if eor_date.month != curr_date.month:
        # month range returns two values; the second is the number of days
        # in the given month
        eor_date = dt.date(curr_date.year, curr_date.month, eom_day)
    elif eom_day - eor_date.day <= 1 and eor_date.month != 2:
        # At the the 3D NARR files have an extra day if it would otherwise be the
        # day before the end of the month, except in February. (The algorithm NARR
        # seems to use to generate filenames/ranges is very obtuse. It seems like
        # they must've hand-specified ranges.)
        eor_date = eor_date.replace(day=eom_day)

    return eor_date


def _narr_next_sfc_date(curr_date):
    #pdb.set_trace()
    if curr_date.day >= 1 and curr_date.day <= 9:
        tdel = dt.timedelta(days=10-curr_date.day)
    elif curr_date.day >= 10 and curr_date.day <= 19:
        tdel = dt.timedelta(days=20-curr_date.day)
    else:
        eom_day = calendar.monthrange(curr_date.year, curr_date.month)[1]
        tdel = dt.timedelta(days=eom_day+1-curr_date.day)

    return curr_date + tdel


def _make_narr_grib_list(start_date, end_date):
    if (type(start_date) is not dt.datetime and type(start_date) is not dt.date or
            type(end_date) is not dt.datetime and type(end_date) is not dt.date):
        raise TypeError("start_date and end_date must be datetime or date objects")

    narr_files = []
    narr_files += _list_narr_grib_files(start_date, end_date, '3D')
    narr_files += _list_narr_grib_files(start_date, end_date, 'RS.flx')
    narr_files += _list_narr_grib_files(start_date, end_date, 'RS.sfc')

    return narr_files


def _list_narr_grib_files(start_date, end_date, suffix):
    # NARR files are every 3 hours, so make sure the start date is at the beginning of a three
    # hour block
    start_date = start_date.replace(minute=0, second=0, microsecond=0)
    start_hour = start_date.hour
    if start_hour % 3 != 0:
        start_date = start_date.replace(start_hour - (start_hour % 3))

    file_pattern = 'merged_AWIP32.{date}.{suffix}'
    files = []
    curr_date = start_date
    while curr_date <= end_date:
        files.append(file_pattern.format(date=curr_date.strftime('%Y%m%d%H'), suffix=suffix))
        curr_date += dt.timedelta(hours=3)

    return files


def _make_narr_tar_list(start_date, end_date):
    if (type(start_date) is not dt.datetime and type(start_date) is not dt.date or
            type(end_date) is not dt.datetime and type(end_date) is not dt.date):
        raise TypeError("start_date and end_date must be datetime or date objects")

    narr_files = []
    _list_narr_tar_files(narr_files, start_date, end_date, "NARR3D_", 3)
    _list_narr_tar_files(narr_files, start_date, end_date, "NARRflx_", 8)
    _list_narr_sfc_tar_files(narr_files, start_date, end_date)

    return narr_files


def _list_narr_tar_files(narr_files, start_date, end_date, stem, ndays, extension="tar"):
    # NARR files come in multi day groups, the file names are of the format
    # NARRxxx_YYYYMM_SSEE.tar, where YYYY is the year, MM the month, SS the first
    # day of the three day group and EE the last. xxx varies depending on the file type,
    #
    # narr_files is the list to append to; start_ and end_ date are (of course) the
    # first and last day of the WRF run. stem is the file name up to the year. ndays
    # is how many days per group. extension is the file extension, defaults to tar.

    dom = start_date.day
    # Day of month must be a multiple of ndays plus 1
    while dom % ndays != 1:
        dom -= 1

    if stem == "NARR3D_" and dom == 31:
        # This kludge fixes a bug that occurs if the time period requested
        # starts on the 31st - 31 to 31 fits the rules that work for everything
        # else, but NARR3D files are produced for 28 to 31, not 28 to 30 and 31 to 31.
        dom = 28

    curr_date = dt.date(start_date.year, start_date.month, dom)
    while curr_date <= end_date:
        eor_date = _narr_end_of_range_date(curr_date, ndays)
        fname = "{namestem}{year:04}{month:02}_{sday:02}{eday:02}.{ext}".format(
            namestem = stem, year = curr_date.year, month=curr_date.month, sday=curr_date.day, eday=eor_date.day,
            ext=extension
        )
        narr_files.append(fname)
        curr_date = eor_date + dt.timedelta(days=1)
        if curr_date.day <= ndays:
            curr_date = curr_date.replace(day=1)


def _list_narr_sfc_tar_files(narr_files, start_date, end_date, extension="tar"):
    # The sfc files are annoying because they use the date ranges 1-9, 10-19, and 20-eom, rather than being consistent.
    # So of course they need special handling
    curr_date = start_date
    while curr_date <= end_date:
        if curr_date.day >= 1 and curr_date.day <= 9:
            drange = "0109"
        elif curr_date.day >= 10 and curr_date.day <= 19:
            drange = "1019"
        else:
            eom_day = calendar.monthrange(curr_date.year, curr_date.month)[1]
            drange = "20{:02}".format(eom_day)

        fname = "NARRsfc_{year:04}{month:02}_{days}.{ext}".format(
            year=curr_date.year, month=curr_date.month, days=drange, ext=extension
        )
        narr_files.append(fname)
        curr_date = _narr_next_sfc_date(curr_date)


def requires_untarring(met_dir, start_date, end_date):
    untarred_files = _make_narr_grib_list(start_date, end_date)
    tarred_files = _make_narr_tar_list(start_date, end_date)

    found_untarred = any([os.path.isfile(f) for f in untarred_files])
    found_tarred = any([os.path.isfile(f) for f in tarred_files])

    if found_untarred:
        return False
    elif found_tarred:
        return True
    else:
        raise MetFilesMissingError('No NARR met files found for the time period {start} to {end} in {dir}'
                                   .format(start=start_date, end=end_date, dir=met_dir))


def get_required_met_files(met_dir, start_date, end_date):
    if requires_untarring(met_dir, start_date, end_date):
        met_files = _make_narr_tar_list(start_date, end_date)
        req_untar = True
    else:
        met_files = _make_narr_grib_list(start_date, end_date)
        req_untar = False

    met_files = [os.path.join(met_dir, f) for f in met_files]

    # TODO: here's where I'd make the function smarter about file hierarchies
    missing_files = [f for f in met_files if not os.path.isfile(f)]
    n_missing_files = len(missing_files)
    if n_missing_files > 0:
        raise MetFilesMissingError('{n} met files missing:\n  * {files}'.format(
            n=n_missing_files, files='\n  * '.join(missing_files)
        ))
    else:
        return met_files, req_untar


def _parse_args():
    # TODO: move this functionality up to a driver function
    allowed_mets = ["narr"]
    parser = argparse.ArgumentParser(description='Generate the list of meteorology files expected by WPS for a given '
                                                 'date range (either the .tar archives or the actual GRIB files)',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("mettype", help="Which type of meteorology to generate file names for. Allowed values (case insensitive): {0}".
                        format(", ".join(allowed_mets)))
    parser.add_argument("startdate", help="The first date of the WRF run, in yyyy-mm-dd_HH:MM:SS format")
    parser.add_argument("enddate", help="The last date of the WRF run, in yyyy-mm-dd_HH:MM:SS format")
    parser.add_argument("-l", action="store_const", const="\n", default=" ",
                        help="Print the files one per line (rather than space delimited)")
    parser.add_argument("--grib", action="store_true", help="List the GRIB files, rather than the default .tar files")

    inputs = parser.parse_args()
    if inputs.mettype.lower() not in allowed_mets:
        print("{0} is not one of the allowed meteorologies (allowed mets: {1})".format(
            inputs.mettype, ", ".join(allowed_mets)), file=sys.stderr)
        exit(1)

    regex = "\d\d\d\d-\d\d-\d\d_\d\d:\d\d:\d\d"
    doexit = False
    if not re.match(regex, inputs.startdate):
        print("startdate '{0}' is not in yyyy-mm-dd_HH:MM:SS format".format(inputs.startdate), file=sys.stderr)
        doexit = True
    if not re.match(regex, inputs.enddate):
        print("enddate '{0}' is not in yyyy-mm-dd_HH:MM:SS format".format(inputs.enddate), file=sys.stderr)
        doexit = True

    if doexit:
        exit(1)

    start_datetime = dt.datetime.strptime(inputs.startdate, "%Y-%m-%d_%H:%M:%S")
    end_datetime = dt.datetime.strptime(inputs.enddate, "%Y-%m-%d_%H:%M:%S")
    return inputs.mettype.lower(), start_datetime, end_datetime, inputs.l, inputs.grib

#### MAIN FUNCTION #####
if __name__ == "__main__":
    met, start_datetime, end_datetime, delim, do_grib = _parse_args()
    if met == "narr":
        if do_grib:
            files = _make_narr_grib_list(start_datetime, end_datetime)
        else:
            files = _make_narr_tar_list(start_datetime.date(), end_datetime.date())
        print(delim.join(files))
    else:
        raise RuntimeError("No action specified for met type {0}".format(met))

    exit(0)
