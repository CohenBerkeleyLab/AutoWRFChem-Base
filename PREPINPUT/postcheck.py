#!/bin/env python

# This will spot check the various input files and make sure that 
# things seem to be ok. Check that wrfinput_d01 and wrfbdy_d01 have
# non-zero values for no, no2, o3, co.
#
# Should be executed in the WRFV3/run directory
#
# Exit codes:   1 bit = some problem (summary)
#               2 bit = problem with wrfinput
#               4 bit: on = wrfinput missing variables, off = variables below min threshold
#               8 bit = problem with wrfbdy
#               16 bit: on = wrfbdy missing variables, off = variables below min threshold
from __future__ import print_function
import pdb
import argparse
import re
import numpy as np
import os
import sys
from warnings import warn
try:
    from netCDF4 import Dataset as ncdat
    use_ncdump = False
except ImportError:
    import pyncdf as pync
    use_ncdump = True
    warn('package netCDF4 not found, using pyncdf. Some operations may not be possible or will be limited.')

min_nonzero_conc = 1e-15

def __shell_error(msg, exitcode=1):
    print(msg, file=sys.stderr)
    exit(exitcode)

def get_var_names(filename):
    if use_ncdump:
        return pync.call_ncdump_varnames(filename)
    else:
        rgrp = ncdat(filename)
        return rgrp.variables.keys()

def get_var_values(varnames, filename):
    if use_ncdump:
        var_vals = pync.call_ncdump_vals(varnames, filename)
    else:
        var_vals = dict()
        rgrp = ncdat(filename)
        for var in varnames:
            var_vals[var] = rgrp.variables[var][:]
    return var_vals
            

def check_vars(varnames, filename):
    print('Checking {0} in {1}'.format(', '.join(varnames), filename))
    filevars = get_var_names(filename)

    ecode = 0

    for var in varnames:
        if var not in filevars:
            print('  WARNING: {0} not present in {1}'.format(var, filename))
            ecode = 6

    if ecode > 0:
        return ecode
    vals = get_var_values(varnames, filename)
    for var in varnames:
        varmean = np.nanmean(vals[var])
        varmed = np.nanmedian(vals[var])
        varmin = np.nanmin(vals[var])
        varmax = np.nanmax(vals[var])
        statstr = 'mean = {0}, median = {1}, min = {2}, max = {3}'.format(varmean, varmed, varmin, varmax)
        if abs(varmed) < min_nonzero_conc:
            print('  WARNING: |median({0})| < {1} ({2})'.format(var, min_nonzero_conc, statstr))
            ecode = 2
        else:
            print('  {0}: {1}'.format(var, statstr))
        
    return ecode

def check_input_bdy(wrfin_file, wrfbdy_file, invars):
    ecode_in = check_vars(invars, wrfin_file)

    bdyvars = []
    bdy_ncdump_lim = {var: True for var in invars} # used to check just one boundary variable per species if using ncdump
    allbdyvars = get_var_names(wrfbdy_file)
    restr = '(' + '|'.join(invars) + ')(?=_)'
    for v in allbdyvars:
        match = re.match(restr,v)
        if not use_ncdump and match:
            bdyvars.append(v)
        elif match and bdy_ncdump_lim[match.group()]:
            bdy_ncdump_lim[match.group()] = False
            bdyvars.append(v)

    ecode_bdy = check_vars(bdyvars, wrfbdy_file)
    
    ecode = ecode_in | ecode_bdy << 2

    return ecode

def get_args():
    parser = argparse.ArgumentParser(description='Check the results of WRF-Chem input preparation')
    parser.add_argument('wrfinput_file',help='Path to the wrfinput_dXX file to check')
    parser.add_argument('wrfbdy_file',help='Path to the wrfbdy_dXX file to check')
    parser.add_argument('--mode',default='chem',help='Mode of operation, can be "met", "chem", or "both". Default is "chem"')

    args = parser.parse_args()
    
    wrfin_file = args.wrfinput_file
    wrfbdy_file = args.wrfbdy_file

    wrfin_re = 'wrfinput_d\d+'
    wrfbdy_re = 'wrfbdy_d\d+'


    if not os.path.isfile(wrfin_file):
        __shell_error('{0} does not exist'.format(wrfin_file))
    elif not re.match(wrfin_re, os.path.basename(wrfin_file)):
        __shell_error('{0} does not appear to be a wrfinput file (base name did not match regular expression {1})'.format(wrfin_file, wrfin_re))
    
    if not os.path.isfile(wrfbdy_file):
        __shell_error('{0} does not exist'.format(wrfbdy_file))
    elif not re.match(wrfbdy_re, os.path.basename(wrfbdy_file)):
        __shell_error('{0} does not appear to be a wrfbdy file (base name did not match regular expression {1})'.format(wrfbdy_file, wrfbdy_re))

    return args

def main():
    args = get_args()

    metvars = ['U','V','T']
    chemvars = ['no','no2','o3','co']
    if args.mode.lower() == 'chem':
        checkvars = chemvars
    elif args.mode.lower() == 'met':
        checkvars = metvars
    elif args.mode.lower() == 'both':
        checkvars = chemvars + metvars
    else:
        __shell_error('{0} is not a recognized value for --mode'.format(args.mode))
    ecode = check_input_bdy(args.wrfinput_file, args.wrfbdy_file, checkvars)
    exit(ecode)

if __name__ == '__main__':
    main()
