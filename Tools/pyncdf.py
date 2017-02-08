from __future__ import print_function
import numpy as np
import os
import re
import subprocess
import sys

import pdb

def shell_error(msg, exitcode=1):
    print(msg, file=sys.stderr)
    exit(exitcode)

def which(program):
    import os
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

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

def parse_dims(lines):
    do_parse = False
    dims = dict()
    for l in lines:
        if do_parse:
            if 'variables:' in l:
                return dims
            varname, valstrraw = l.split('=')
            varname = varname.strip()
            valstr = valstrraw.split(';')[0].strip()
            #pdb.set_trace()
            if valstr == 'UNLIMITED':
                # Unlimited dimensions should be followed by (xx currently), which gives the current actual dimension length
                valstr = re.search('\d+(?=\s*currently)', valstrraw).group()

            dims[varname] = int(valstr) # dimension lengths should always be integers
        elif "dimensions:" in l:
            do_parse = True
            

def get_var_dims(lines, dims, varname):
    do_parse = False
    restr = '\s{0}\('.format(varname)
    for l in lines:
        if do_parse:
            if re.search(restr, l):
                dimstrs = re.search('(?<=\().*(?=\))',l).group().split(',')
                dimlen = []
                for d in dimstrs:
                    dimlen.append(dims[d.strip()])
                return dimlen
        else:
            if 'variables:' in l:
                do_parse = True
    raise RuntimeError('Variable {0} not found in the ncdump'.format(varname))

def get_var_dtype(lines, var):
    restr1 = '{0}(?=\()'.format(var)
    in_vars = False
    for l in lines:
        if in_vars:
            m = re.search(restr1, l)
            if m:
                data_type = l.split(' ')[0].strip()
                if data_type == 'int':
                    return int
                elif data_type == 'float':
                    return float
                elif data_type == 'char':
                    return str
                else:
                    raise RuntimeError('Data type {0} not recognized (variable is {1})'.format(data_type, m.group()))
        elif "variables:" in l:
            in_vars = True
    

def call_ncdump_varnames(filename):
    if not os.path.isfile(filename):
        shell_error('{0} does not exist'.format(filename))

    ncout = subprocess.check_output(['ncdump', '-h', filename])
    lines = ncout.splitlines()
    in_vars = False
    varnames = []
    for l in lines:
        if in_vars:
            m = re.search('(?<=\w\s)[\w\-]+(?=\()',l)
            if m:
                varnames.append(m.group())
        elif "variables:" in l:
            in_vars = True

    return varnames
    

def call_ncdump_vals(variables, filename):
    if not os.path.isfile(filename):
        shell_error('{0} does not exist'.format(filename))

    varstr=','.join(variables)
    ncout = subprocess.check_output(['ncdump', '-f', 'c', '-v', varstr, filename])
    lines = ncout.splitlines()
    dims_lengths = parse_dims(lines)

    # Variable lines all come after one with "data:" in it, and all start with
    # "varname = " followed by values
    varfxn = dict()
    varvals = dict()

    var_restr = '|'.join(variables)
    restr2 = '(?<=\s)({0})(?=\()'.format(var_restr)


    for var in variables:
        varfxn[var] = get_var_dtype(lines, var)
        vardims = get_var_dims(lines, dims_lengths, var)
        varvals[var] = np.zeros(vardims, dtype=varfxn[var])

    in_data = False
    for l in lines:
        if in_data:
            m = re.search(restr2, l)
            if m:
                # Get the coordinates for this value and the value itself
                val, comment_str = l.split('//')
                val = varfxn[m.group()](val.strip(',; '))
                # Seach for a series of numbers separated by commas within parentheses
                coord_str = re.search('(?<=\()(\d+,)*\d+(?=\))',comment_str).group()
                coords = tuple([int(x) for x in coord_str.split(',')]) # numpy arrays treat tuples as individual indices
                varvals[m.group()][coords] = val
        elif "data:" in l:
            in_data = True
    
    return varvals
    """
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
    """

def init():
    if which('ncdump') is None:
        raise OSError('Executable "ncdump" not found on path. ncdump is required for pyncdf to function')

# Always run init() even when importing
init()
if __name__ == '__main__':
    pass
    
