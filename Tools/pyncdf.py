from __future__ import print_function
import os
import re
import subprocess
import sys

import pdb

def shell_error(msg, exitcode=1):
    print(msg, file=sys.stderr)
    exit(exitcode)

def parse_varlines(varlines, varfxns):
    vals = dict()
    for var in varlines:
        varname, fullstr = ''.join(var).split('=')
        varname = varname.strip()
        fullstr = fullstr.rstrip(';')
        valstrs = [s.strip() for s in fullstr.split(',')]
        this_var = []
        for val in valstrs:
            this_var.append(varfxns[varlines.index(var)](val))
        vals[varname] = this_var

    return vals

def call_ncdump(variables, filename):
    if not os.path.isfile(filename):
        shell_error('{0} does not exist'.format(filename))

    varstr=','.join(variables)
    ncout = subprocess.check_output(['ncdump', '-v', varstr, filename])
    lines = ncout.splitlines()

    # Variable lines all come after one with "data:" in it, and all start with
    # "varname = " followed by values
    varfxn = [0 for x in variables]
    varlines = [0 for x in variables]

    var_restr = '|'.join(variables)
    restr1 = '({0})(?=\()'.format(var_restr)
    restr2 = '({0})(?=\s\=)'.format(var_restr)

    in_data = False
    li = 0
    while li < len(lines):
        l = lines[li]
        if not in_data:
            if l == 'data:':
                in_data = True
            else:
                m = re.search(restr1, l)
                if m is not None:
                    vi = variables.index(m.group())
                    data_type = l.split(' ')[0].strip()
                    if data_type == 'int':
                        varfxn[vi] = int
                    elif data_type == 'float':
                        varfxn[vi] = float
                    elif data_type == 'char':
                        varfxn[vi] = str
                    else:
                        raise RuntimeError('Data type {0} not recognized (variable is {1})'.format(data_type, m.group()))
                    
        else:
            m = re.search(restr2, l)
            if m is not None:
                vi = variables.index(m.group())
                this_var = [l]
                while True:
                    li += 1
                    this_var.append(lines[li])
                    if ';' in lines[li]:
                        break

                varlines[vi] = this_var
                m = None
        li += 1

    return parse_varlines(varlines, varfxn)
