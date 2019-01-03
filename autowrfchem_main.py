from __future__ import print_function
import argparse
import pdb

from autowrfchem import wrf_components, use_env_const, _alt_mpi_cmd_var


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
    config_parser.add_argument('--override', action='store_true', help='will include the necessary environmental variables to run WRF-Chem (EM_CORE=1, WRF_CHEM=1, etc) regardless of how those variables are set in your shell. It will NOT modify these variables in your shell except when this program is running.')
    config_parser.add_argument('--namelist', action='store_true', help='will just edit the WRF and WPS namelists.')
    config_parser.set_defaults(exec_func=configure_all)

    namelist_parser = subparsers.add_parser('namelist', help='Modify the namelists. Alias for "config --namelist')
    namelist_parser.set_defaults(exec_func=modify_namelists)

    compile_parser = subparsers.add_parser('compile', help='Compile all components. By default, will skip compiling any component that already exists')
    compile_parser.add_argument('-f', '--force', action='store_true', help='Recompile even if the component exists')
    compile_parser.add_argument('-o', '--only', action='append', default=[], choices=wrf_components, help='Compile only specific components. Implies --force, i.e. components specified will always be recompiled. May be specified multiple times to compile multiple components.')
    compile_parser.set_defaults(exec_func=compile_all)

    clean_parser = subparsers.add_parser('clean', help='Remove all compiled components for a clean recompile.')
    clean_parser.add_argument('--inputs', action='store_true', help='Only clean the input files, not the code.')
    clean_parser.add_argument('--all', action='store_true', help='Clean both the compiled code and the input files.')
    clean_parser.set_defaults(exec_func=clean_all)

    prep_parser = subparsers.add_parser('prepinpt', help='Prepare all necessary input')
    prep_parser.add_argument('--check', action='store_true', help='will just check that everything required for preparing the input data is ready to go. Add --met-only as an additional argument to only check what is necessary for preparing meteorology')
    prep_parser.add_argument('--met-only', action='store_true', help='will just run WPS and execute real.exe after finishing WPS')
    prep_parser.add_argument('--no-real', action='store_true', help='will not run real.exe after finishing WPS in met-only mode. Has no effect if --met-only not also specified')
    prep_parser.add_argument('--split-met', dest='exec_func', const=split_met_prep, action='store_const', help='Split up WPS preparation into multiple jobs')

    split_met_group = prep_parser.add_argument_group('Split-met options')
    split_met_group.add_argument('--ndays', type=int, default=30, help='Specify how many days each WPS job should do. Default is %(default)s')
    split_met_group.add_argument('--submit-file', help='If given, a batch job submission file to use to automatically submit the separate WPS jobs.')

    prep_parser.set_defaults(exec_func=prepare_input)


    run_parser = subparsers.add_parser('run', help='Start WRF-Chem', description='Execute WRF-Chem. Exactly one of --no-mpi, --ntasks, or --alt-mpi-cmd is required')
    run_req_group = run_parser.add_mutually_exclusive_group(required=True)
    run_req_group.add_argument('--no-mpi', '--nompi', action='store_true', help='Run WRF without MPI, using just ./wrf.exe in the WRFV3/run directory')
    run_req_group.add_argument('--ntasks', type=int, help='How many MPI tasks to use when executing WRF')
    run_req_group.add_argument('--alt-mpi-cmd', nargs='?', default=None, const=use_env_const, help='Use a different MPI command to launch WRF-Chem (the default is "mpirun -np $NTASKS wrf.exe"). A command can be given as the argument to this option or in the environmental variable "{envvar}"'.format(envvar=_alt_mpi_cmd_var))

    rst_group = run_parser.add_argument_group('Restart options')
    rst_group.add_argument('--rst', action='store_true', help='will try to find the last wrfrst file within the time period in the namelist in WRFV3/run and start from there. If it cannot find a wrfrst file, it will abort.')
    rst_group.add_argument('--allow-no-file', action='store_true', help='if no restart files in the proper time period is found, this will start from the beginning instead of aborting.')

    run_general_group = run_parser.add_argument_group('General options')
    run_general_group.add_argument('--run-for', type=int, help='only run for x, where x is a time period in days, hours, minutes, and seconds. Works with rst, in fact, is primarily intended to work with rst so that you can break a long run up into smaller chunks. Example: %(prog)s run rst --run-for=28d will run for 28 days from the last restart file.')
    run_general_group.add_argument('--dry-run', action='store_true', help='do everything normally done for run except start WRF; instead, it will print out the command it would use This can be used with any of the previous flags to check how %(prog)s would modify the namelist, try to execute WRF, etc.')

    run_parser.set_defaults(exec_func=run_wrf)

    args = vars(parser.parse_args())
    exec_func = args.pop('exec_func')
    exec_func(**args)


if __name__ == '__main__':
    entry_point()
