#!/usr/bin/env python
#
# datecompare.py - python script that can be used to compare two dates given as strings
#   Gives exit status of 0 if comparison is true, 1 if false, so can be used in shell if
#   statements.
from __future__ import print_function
import argparse
import datetime as dt
import sys

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
    parser.add_argument('date1', help='The first date to compare. The format of the string is determined by the --datefmt option.')
    parser.add_argument('op', help='The operation to use to compare the two dates. Can be:\n  =, ==, eq (equality) \n  !=, ne (not equal)'
                                    '\n  <, lt (less than) \n  <=, le (less than or equal to) \n  >, gt (greater than),'
                                    '\n  >=, ge (greater than or equal to) \n'
                                    '        Note: most of the symbolic operations (e.g. <, >) will need to be quoted when presented as arguments \n'
                                    '        to avoid the shell interpreting them as special symbols for, e.g. redirection.')
    parser.add_argument('date2', help='The second date to compare. The comparison is date1 op date2.')
    return parser.parse_args()

def convert_dates(date1str, date2str, datefmt):
    date1 = dt.datetime.strptime(date1str, datefmt)
    date2 = dt.datetime.strptime(date2str, datefmt)
    return date1, date2

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
        print('{0}: Operation "{1}" not recognized'.format( sys.argv[0], format(op) ), file=sys.stderr)
        exit(2)

args=parse_args()
d1, d2 = convert_dates(args.date1, args.date2, args.datefmt)
result = compare_dates(d1, d2, args.op)
if result:
    exit(0)
else:
    exit(1)
