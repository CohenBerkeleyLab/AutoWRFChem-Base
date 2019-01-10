import copy
import os
import shlex
import subprocess
import sys

from textui import uiutils

from .configuration import ENVIRONMENT
from .configuration.config_utils import AutoWRFChemConfig


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


def run_external(command, cwd='.', config_obj=None, logfile_handle=None, **subproc_args):
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

    subprocess.check_call(command, cwd=cwd, env=env, **subproc_args)


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