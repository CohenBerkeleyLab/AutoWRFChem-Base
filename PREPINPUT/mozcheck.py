# check that the given Mozart file covers the time range and the domain plus a 10 degree buffer

import argparse
import datetime as dt
import os
import re
import sys
from netCDF4 import Dataset as ncdat

wrf_dt_fmt = '%Y-%m-%d_%H:%M:%S'

def shell_error(msg, exitcode=1):
    print('{0}:\n\t{1}'.format(__file__, msg), file=sys.stderr)
    exit(exitcode)

def shell_warning(msg):
    print('{0}:\n\t{1}'.format(__file__, msg), file=sys.stderr)

def get_args():
    parser = argparse.ArgumentParser(description='Check the chosen MOZBC file satisfies the necessary conditions for the run')
    parser.add_argument('moz_file',help='MOZBC netCDF file')
    parser.add_argument('wrfin_file',help='wrfinput_dxx file')
    parser.add_argument('startdate',help='Start date for the whole WRF run')
    parser.add_argument('enddate',help='End date for the whole WRF run')

    args = parser.parse_args()


    wrfin_re = 'wrfinput_d\d+'
    date_re = '\d\d\d\d-\d\d-\d\d_\d\d:\d\d:\d\d'

    if not os.path.isfile(args.wrfin_file):
        shell_error('{0} does not exist'.format(args.wrfin_file))
    elif not re.match(wrfin_re, os.path.basename(args.wrfin_file)):
        shell_error('{0} does not appear to be a wrfinput file (base name did not match regular expression {1})'.format(wrfin_file, wrfin_re))

    if not re.match(date_re, args.startdate):
        shell_error('Start date is not in yyyy-mm-dd_HH:MM:SS format')
    if not re.match(date_re, args.enddate):
        shell_error('End date is not in yyyy-mm-dd_HH:MM:SS format')

    return args

def get_run_info(wrfin, stime_str, etime_str):
    in_rgrp = ncdat(wrfin)
    xlon = in_rgrp.variables['XLONG'][:]
    xlat = in_rgrp.variables['XLAT'][:]
    in_rgrp.close()

    sdate = dt.datetime.strptime(stime_str, wrf_dt_fmt)
    edate = dt.datetime.strptime(etime_str, wrf_dt_fmt)
    
    return (xlon.min(), xlon.max()), (xlat.min(), xlat.max()), (sdate, edate)

def convert_moz_date(dateint, datesec):
    # MOZ dates are given as an integer with 8 digits. The first four are year, then two month, then two for day
    # Some arithmetic sneakiness to break it apart
    yr = dateint//10000
    mn = (dateint % 10000)//100
    dy = dateint % 100

    hour = datesec // 3600
    minute = (datesec % 3600)//60
    sec = datesec % 60
    return dt.datetime(year=yr, month=mn, day=dy, hour=hour, minute=minute, second=sec)

def get_moz_info(mozfile):
    m_rgrp = ncdat(mozfile)
    lon = m_rgrp.variables['lon'][:]
    lon[lon>180] -= 360 # MOZBC files give longitude as degrees east (so 200 in MOZ = -160 in WRF)
    lat = m_rgrp.variables['lat'][:]
    mdate = m_rgrp.variables['date'][:]
    mdatesec = m_rgrp.variables['datesec'][:]

    moz_st_dt = convert_moz_date(mdate[0], mdatesec[0])
    moz_end_dt = convert_moz_date(mdate[-1], mdatesec[-1])
    return (lon.min(), lon.max()), (lat.min(), lat.max()), (moz_st_dt, moz_end_dt)

def moz_validation(mozfile, wrfin, wrf_startdate, wrf_enddate):
    latlon_buffer = 10

    wrf_lonlim, wrf_latlim, wrf_timelim = get_run_info(wrfin, wrf_startdate, wrf_enddate)
    moz_lonlim, moz_latlim, moz_timelim = get_moz_info(mozfile)

    exitcode = 0
    
    geo_msg = 'Warning: {0} MOZ border does not have a {1} degree buffer from the nearest WRF border\n\t{2}'
    if moz_lonlim[0] - wrf_lonlim[0] > -latlon_buffer:
        line2 = '(MOZ min lon = {0}, WRF min lon = {1})'.format(moz_lonlim[0], wrf_lonlim[0])
        shell_warning(geo_msg.format('West', latlon_buffer, line2))
        exitcode = 1
    if moz_lonlim[1] - wrf_lonlim[1] < latlon_buffer:
        line2 = '(MOZ max lon = {0}, WRF max lon = {1})'.format(moz_lonlim[1], wrf_lonlim[1])
        shell_warning(geo_msg.format('East', latlon_buffer, line2))
        exitcode = 1
    if moz_latlim[0] - wrf_latlim[0] > -latlon_buffer:
        line2 = '(MOZ min lat = {0}, WRF min lat = {1})'.format(moz_latlim[0], wrf_latlim[0])
        shell_warning(geo_msg.format('South', latlon_buffer, line2))
        exitcode = 1
    if moz_latlim[1] - wrf_latlim[1] < latlon_buffer:
        line2 = '(MOZ max lat = {0}, WRF max lat = {1})'.format(moz_latlim[1], wrf_latlim[1])
        shell_warning(geo_msg.format('North', latlon_buffer, line2))
        exitcode = 1
    if moz_timelim[0] > wrf_timelim[0]:
        line2 = '(MOZ first time = {0}, WRF first time = {1})'.format(moz_timelim[0], wrf_timelim[0])
        shell_warning('First time in MOZ file is after start time of WRF run\n\t{0}'.format(line2))
        exitcode = 1
    if moz_timelim[1] < wrf_timelim[1]:
        line2 = '(MOZ last time = {0}, WRF last time = {1})'.format(moz_timelim[1], wrf_timelim[1])
        shell_warning('Last time in MOZ file is before end time of WRF run\n\t{0}'.format(line2))

    return exitcode

def main():
    args = get_args()
    ecode = moz_validation(args.moz_file, args.wrfin_file, args.startdate, args.enddate)
    exit(ecode)

if __name__ == '__main__':
    main()
