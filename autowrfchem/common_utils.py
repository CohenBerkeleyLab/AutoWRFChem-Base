import copy
from datetime import datetime as dtime, timedelta as tdel
from glob import glob
import os
import re
import shlex
import shutil
import subprocess
import sys

from textui import uiutils

from .configuration import ENVIRONMENT, AUTOMATION, AUTOMATION_PATHS, MPI_CMD
from .configuration.config_utils import AutoWRFChemConfig


wrf_date_re = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2}')


def eprint(msg, max_columns=None):
    """
    Print a message to stderr.

    :param msg: the message to print
    :type msg: str

    :param max_columns: The maximum number of columns to print before beginning a new line. If there is a word in the
     message that exceeds this limit, it will be printed on one line.
    :type max_columns: int

    :return: None
    """
    if max_columns is not None:
        msg = '\n'.join(uiutils.hard_wrap(msg, max_columns=max_columns))
    print(msg, file=sys.stderr)


def _create_env_dict(config_obj):
    """
    Creates a dictionary that contains all existing environmental variables overwritten by those defined in the config
    :param config_obj: the object containing the AutoWRFChem configuration data

    :return: the dictionary that can be given to a subprocess function's ``env`` keyword to set the environment
    :rtype: dict
    """
    extant_env = copy.copy(os.environ)
    extant_env.update(config_obj[ENVIRONMENT])
    return extant_env


def run_external(command, cwd='.', config_obj=None, logfile_handle=None, dry_run=False, **subproc_args):
    """
    Run an external program

    This is a wrapper around `subprocess.check_call` that makes sure the environment is set correctly before running
    the given command. It also makes piping output to a log file more convenient.

    :param command: The shell command to run, give as a string or a list of arguments accepted by
     `subprocess.check_call`. If given as a string, it is split into a list by `shlex.split`.
    :type command: list or str

    :param cwd: the working directory to use to run the command.
    :type cwd: str

    :param config_obj: an `AutoWRFChemConfig` object to use to set the environment. If not given, the standard config
     is used.
    :type config_obj: `AutoWRFChemConfig`

    :param logfile_handle: a handle, returned by `open()` to a file to write a log (stdout + stderr) to.
    :type logfile_handle: file handle

    :param dry_run: optional, if ``True`` does not execute the command but just prints it
    :type dry_run: bool

    :param subproc_args: additional keyword arguments to pass to `subprocess.check_call`. Note that ``cwd`` and ``env``
     are already given, and if ``logfile_handle`` is not None, then ``stdout`` and ``stderr`` will be overridden to
     point to that log file.

    :return: None
    :raises subprocess.CalledProcessError: if the command returns a non-zero exit code.
    """
    if config_obj is None:
        config_obj = AutoWRFChemConfig()

    if isinstance(command, str):
        command = shlex.split(command)
    elif not isinstance(command, list):
        raise TypeError('command must be a string or list')

    env = _create_env_dict(config_obj)
    if logfile_handle is not None:
        subproc_args.update({'stdout': logfile_handle, 'stderr': logfile_handle})

    if dry_run:
        print(' '.join(command))
    else:
        subprocess.check_call(command, cwd=cwd, env=env, **subproc_args)


def run_external_mpi(command, ntasks=1, config_obj=None, *args, **kwargs):
    """
    Run an external program using MPI.

    MPI compiled programs usually need to be launched by calling something like "mpirun". For example,
     "mpirun -np 20 wrf.exe" would run WRF with 20 MPI tasks. This function will launch a program with the MPI command
     defined in the config file.

    :param command: the command to execute with MPI.
    :type command: str

    :param ntasks: how many MPI tasks to launch.
    :type ntasks: int

    :param config_obj: the AutoWRFChemConfig object that will define the environmental variables for the command as well
     as the MPI command.
    :type config_obj: `AutoWRFChemConfig`

    :param args: additional positional arguments passed through to `run_external`
    :param kwargs: additional keyword arguments passed through to `run_external`

    :return: None
    :raises subprocess.CalledProcessError: if the command returns a non-zero exit code.
    """

    if config_obj is None:
        config_obj = AutoWRFChemConfig()
    elif ntasks < 1:
        raise ValueError('ntasks must be >= 1')

    command = config_obj[AUTOMATION][MPI_CMD].format(ntasks=ntasks, cmd=command)
    run_external(command, config_obj=config_obj, *args, **kwargs)


def set_bit(bit, val=0, yn=True):
    """
    Set a bit in a binary value.

    :param bit: the 0-based index of the bit to set. Must be >= 0
    :type bit: int.

    :param val: the value to set the bit in. If not given, defaults to 0.
    :type val: int

    :param yn: Whether to set the bit to 1 (default) or 0.
    :type yn: truthy-type value

    :return: the modified value
    :rtype: int
    """
    # Modified from https://stackoverflow.com/a/12174051
    # << is a bit shift. 1 is 000..001 so if bit is a 0-based index, then bit-shifting 1 by `bit` effectively sets that
    # bit
    mask = 1 << bit
    if yn:
        # if yn is "truthy" then OR the value with the mask to set that bit to 1
        return val | mask
    else:
        # otherwise AND that bit with the negated mask to clear it
        return val & ~mask


def iter_dates(start_date, end_date, step=None):
    if step is None:
        step = tdel(days=1)
    curr_date = start_date
    while curr_date <= end_date:
        yield curr_date
        curr_date += step


def som_date(date):
    return date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def eom_date(date):
    date = date.replace(day=28) + tdel(days=4)
    return som_date(date) - tdel(microseconds=1)


def rmfiles(pattern):
    files = glob(pattern)
    for f in files:
        if os.path.isdir(f):
            shutil.rmtree(f)
        else:
            # need to test for directories because remove won't work on 
            # directories and rmtree won't on symbolic links
            os.remove(f)


def backup_file(filename):
    new_name = backup_file_name(filename)
    shutil.copy2(filename, new_name)


def backup_file_name(filename):
    now = dtime.now().strftime('%Y-%m-%d_%H_%M_%S')
    return '{}.backup.{}'.format(filename, now)


def decode_exit_code(ecode, component_names, print_to_screen=False):
    """
    Decode what a particular exit code means.

    :param ecode: the exit code
    :type ecode: int

    :param component_names: iterable of component names in the order corresponding to which bits represent them
    :type component_names: iterable of str

    :param print_to_screen: optional, if ``True``, prints each component and whether is succeeded or failed.
    :type print_to_screen: bool

    :return: a dictionary with each component's name as the key and a boolean indicating if it succeeded.
    :rtype: dict
    """
    component_states = dict()
    for idx, name in enumerate(component_names):
        if ecode & set_bit(idx):
            state = 'FAILED'
        else:
            state = 'SUCCEEDED'

        component_states[name] = state
        if print_to_screen:
            print('{}: {}'.format(name, state))

    return component_states


def parse_time_string(time_str):

    # The string can either be specified as dd-HH:MM:SS or #d#h#m#s. The two formats cannot be mixed
    if any([c in time_str for c in 'dhms']):
        return _parse_time_string_dhms(time_str)
    else:
        return _parse_time_string_colon(time_str)


def _parse_time_string_dhms(time_str):
    parts = {'days': re.compile(r'\d+(?=d)'),
             'hours': re.compile(r'\d+(?=h)'),
             'minutes': re.compile(r'\d+(?=m)'),
             'seconds': re.compile(r'\d+(?=s)')}

    durations = dict()
    for part, regex in parts.items():
        user_dur = regex.search(time_str)
        if user_dur is not None:
            durations[part] = int(user_dur.group())

    return tdel(**durations)


def _parse_time_string_colon(time_str):
    if '-' in time_str:
        days, hms = time_str.split('-')
    elif ':' in time_str:
        hms = time_str
        days = '0'
    else:
        days = time_str
        hms = '00:00:00'

    days = int(days)
    hms = hms.split(':')
    while len(hms) < 3:
        hms.append('00')

    hours, minutes, seconds = [int(p) for p in hms]
    return tdel(days=days, hours=hours, minutes=minutes, seconds=seconds)