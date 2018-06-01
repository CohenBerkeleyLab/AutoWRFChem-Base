# Given start and end dates for the run, figures out which year
# best represents the emissions for it and prints out a start
# date which can be used by the namelist program to set the
# start date for convert_emiss.F

import datetime as dt
import argparse
import re
import sys

def shell_error(msg, exitcode=1):
    print('{0}: {1}'.format(__file__, msg), file=sys.stderr)
    exit(exitcode)

def shell_warning(msg):
    print('{0}: {1}'.format(__file__, msg), file=sys.stderr)

def get_args():
    parser = argparse.ArgumentParser(description='Generate start dates for convert_emiss based on run start and end dates')
    parser.add_argument('zhr', help='String 00z or 12z, indicates which start time should be returned')
    parser.add_argument('startdate', help='Start date for model run in yyyy-mm-dd_HH:MM:SS format')
    parser.add_argument('enddate', help='End date for model run in yyyy-mm-dd_HH:MM:SS format')

    inputs = parser.parse_args()

    if inputs.zhr not in ['00z', '12z']:
        shell_error('zhr must be 00z or 12z')

    regex = "\d\d\d\d-\d\d-\d\d_\d\d:\d\d:\d\d"
    if not re.match(regex, inputs.startdate):
        shell_error("startdate '{0}' is not in yyyy-mm-dd_HH:MM:SS format".format(inputs.startdate))
    if not re.match(regex, inputs.enddate):
        shell_error("enddate '{0}' is not in yyyy-mm-dd_HH:MM:SS format".format(inputs.enddate))

    return inputs

def str2datetime(s):
    return dt.datetime.strptime(s, '%Y-%m-%d_%H:%M:%S');

def calc_year(startdate, enddate, hr):
    sdate = str2datetime(startdate)
    edate = str2datetime(enddate)

    if edate < sdate:
        shell_error('enddate cannot be before startdate')

    if edate.year == sdate.year:
        return dt.datetime(year=sdate.year, month=sdate.month, day=sdate.day, hour=hr)
    elif edate.year - sdate.year == 1:
        # Choose the year that makes up the majority of the run.
        sdays = dt.datetime(sdate.year+1,1,1) - sdate
        edays = edate - dt.datetime(edate.year,1,1)
        if sdays > edays:
            em_date = sdate
        else:
            em_date = dt.datetime(year=edate.year, month=1, day=1)

        shell_warning('Start and end dates are 1 year apart, calculating emissions for majority year')
        return dt.datetime(year=em_date.year, month=em_date.month, day=em_date.day, hour=hr)
    else:
        tdel = edate - sdate
        tdel /= 2
        tmpdate = sdate + tdel
        yr = tmpdate.year
        
        shell_warning('Start and end dates are >= 2 years apart, calculating emissions for mean year')
        return dt.datetime(year=yr, month=1, day=1, hour=hr)

def main():
    args = get_args()
    hrdict = {'00z':0, '12z':12}
    em_date = calc_year(args.startdate, args.enddate, hrdict[args.zhr])
    shell_warning('Emissions will use year {0}'.format(em_date.year))
    print(em_date.strftime('%Y-%m-%d_%H:%M:%S'))

if __name__ == '__main__':
    main()
