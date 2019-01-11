from __future__ import print_function
import argparse
import sys
import pdb

from autowrfchem import extra_help
from autowrfchem.configuration import config_drivers
from autowrfchem.compilation import compile_drivers
from autowrfchem.input_preparation import prepinput_drivers
from autowrfchem.execution import run_wrf_drivers


def configure_all(**kwargs):
    print('Configure everything! {}'.format(kwargs))


def modify_namelists(**kwargs):
    print('Modify the namelists! {}'.format(kwargs))


def compile_all(**kwargs):
    print('Compile everything! {}'.format(kwargs))


def clean_all(**kwargs):
    print('Clean everything! {}'.format(kwargs))


def split_met_prep(**kwargs):
    print('Split up the met prep! {}'.format(kwargs))


def prepare_input(**kwargs):
    print('Prepare all the input! {}'.format(kwargs))


def run_wrf(**kwargs):
    print('RUN WORF, RUN! {}'.format(kwargs))


def entry_point():
    parser = argparse.ArgumentParser(description='Wrapper to automatically configure, compile, prepare input for, and execute WRF-Chem')
    subparsers = parser.add_subparsers(help='Primary commands used to prepare and execute WRF-Chem')

    config_parser = subparsers.add_parser('config', help='Configure all components, including WRF, WPS, and AutoWRFChem')
    config_drivers.setup_config_clargs(config_parser)

    #namelist_parser = subparsers.add_parser('namelist', help='Modify the namelists. Alias for "config --namelist')

    compile_parser = subparsers.add_parser('compile', help='Compile all components.')
    compile_drivers.setup_compile_clargs(compile_parser)

    clean_parser = subparsers.add_parser('clean', help='Remove all compiled components for a clean recompile.')
    compile_drivers.setup_clean_clargs(clean_parser)

    prep_parser = subparsers.add_parser('prepinpt', help='Prepare all necessary input')
    prepinput_drivers.setup_clargs(prep_parser)

    run_parser = subparsers.add_parser('run', help='Start WRF-Chem', description='Execute WRF-Chem. Exactly one of --no-mpi, --ntasks, or --alt-mpi-cmd is required')
    run_wrf_drivers.setup_clargs(run_parser)

    help_parser = subparsers.add_parser('help', help='Extra in-depth help')
    extra_help.setup_clargs(help_parser)

    args = vars(parser.parse_args())
    try:
        exec_func = args.pop('exec_func')
    except KeyError:
        parser.print_help()
    else:
        sys.exit(exec_func(**args))


if __name__ == '__main__':
    entry_point()
