#!/bin/env python

# This will spot check the various input files and make sure that 
# things seem to be ok. Check that wrfinput_d01 and wrfbdy_d01 have
# non-zero values for no, no2, o3, co.
#
# Should be executed in the WRFV3/run directory
from __future__ import print_function
import os
import sys

import pyncdf as pync

def __shell_error(msg, exitcode=1):
    print(msg, file=sys.stderr)
    exit(exitcode)

def check_input_bdy():
    invars = ['no','no2','o3','co']
    bdyvars = []

def main():
    mypath = os.getcwd().split('/')
    if mypath[-2] != 'WRFV3' or mypath[-1] != 'run':
        shell_error('Execute {0} within a WRFV3/run directory'.format(__file__))

    
    
