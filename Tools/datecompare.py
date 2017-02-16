#!/usr/bin/env python
#
# datecompare.py - python script that can be used to compare two dates given as strings
#   Gives exit status of 0 if comparison is true, 1 if false, so can be used in shell if
#   statements.
from __future__ import print_function
import argparse
import datetime as dt
import re
import sys

def shell_error(msg, exitcode=2): # use 2 because 1 is used to indicate the comparison was false, not an error
    print(msg,file=sys.stderr);
    exit(exitcode)

def parse_args():
    parser = argparse.ArgumentParser(description='compare two dates', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-f', '--datefmt', default='%Y-%m-%d', help='The format that Python\'s datetime module should interprete the dates as.\n'
                                                                    'Defaults to %(default)s, i.e. yyyy-mm-dd. Most common symbols are:\n'
                                                                    '  %%Y - four digit year \n'
                                                                    '  %%m - two digit month \n'
                                                                    '  %%d - two digit day of month \n'
                                                                    '  %%H - 24 hr clock (00-23) hour \n'
                                                                    '  %%M - minute (00-59) \n'
                                                                    '  %%S - second (00-59) \n'
                                                                    'See the datetime.strptime documentation for the full list.')
    parser.add_argument('dates_ops', nargs=argparse.REMAINDER, help='The first date to compare. The format of the string is determined by the --datefmt option.\n'
                                    'Exactly one comparison operator is require, which can be:\n  =, ==, eq (equality) \n  !=, ne (not equal)'
                                    '\n  <, lt (less than) \n  <=, le (less than or equal to) \n  >, gt (greater than),'
                                    '\n  >=, ge (greater than or equal to) \n'
                                    '        Note: most of the symbolic operations (e.g. <, >) will need to be quoted when presented as arguments \n'
                                    '        to avoid the shell interpreting them as special symbols for, e.g. redirection.'
                                    'Dates may be modified with + or - operators. Examples:'
                                    '\n  +2d (add two days to the preceding date)'
                                    '\n  -12h (subtract two hours from the preceding datetime'
                                    '\n  +30m (add 30 minutes)'
                                    '\n  -40s (subtract 40 seconds)'
                                    '\n  +1d12h (add 1 day and 12 hours)')
    return parser.parse_args()

def parse_timedelta(td):
    if td[0] == '+':
        f = 1
    elif td[0] == '-':
        f = -1
    else:
        raise ValueError('The first character of td must be + or -')

    days = 0
    hours = 0
    minutes = 0
    seconds = 0

    match = re.finditer('\d+', td)
    for m in match:
        val = int(m.group())
        timeseg = td[m.end()]
        if timeseg == 'd':
            days += f * val
        elif timeseg == 'h':
            hours += f * val
        elif timeseg == 'm':
            minutes += f * val
        elif timeseg == 's':
            seconds += f * val
        else:
            shell_error('Modification operators only recognize d, h, m, s as valid time segments (days, hours, minutes, seconds')

    return dt.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

def process_dates_opts(dates_ops, date_fmt):
    comp_op = ''
    comparison_ops = ['=','==','eq','!=','ne','<','lt','<=','le','>','gt','>=','ge']
    mod_ops = ['+','-']
    dates = []
    for d in dates_ops:
        if d in comparison_ops:
            if len(comp_op) == 0:
                comp_op = d
            else:
                shell_error('Cannot specify multiply comparison operators ({0})'.format(', '.join(comparison_ops)))
        elif d[0] in mod_ops:
            if len(dates) == 0:
                shell_error('Modification operators (starting with {0}) must come after a date'.format(', '.join(mod_ops)))
            else:
                # Modify the most recent date to be read
                td = parse_timedelta(d)
                dates[-1] += td
        else:
            # Must be a date
            if len(dates) < 2:
                dates.append(convert_date(d, date_fmt))
            else:
                shell_error('Only 2 dates can be input. Already found two: {0}'.format(', '.join(dates)))

    if comp_op == '':
        shell_error('No comparison operator given')
    elif len(dates) < 2:
        shell_error('Two dates must be given for comparison')

    return dates[0], dates[1], comp_op

def convert_date(datestr,datefmt):
    dateval = dt.datetime.strptime(datestr, datefmt)
    return dateval

def compare_dates(d1, d2, op):
    if op == '=' or op == '==' or op == 'eq':
        return d1 == d2
    elif op == '!=' or op == 'ne':
        return d1 != d2
    elif op == '<' or op == 'lt':
        return d1 < d2
    elif op == '<=' or op == 'le':
        return d1 <= d2
    elif op == '>' or op == 'gt':
        return d1 > d2
    elif op == '>=' or op == 'ge':
        return d1 >= d2
    else:
        exit(2)

def main():
    args=parse_args()
    d1, d2, op = process_dates_opts(args.dates_ops, args.datefmt)
    result = compare_dates(d1, d2, op)
    if result:
        exit(0)
    else:
        exit(1)

if __name__ == '__main__':
    main()
