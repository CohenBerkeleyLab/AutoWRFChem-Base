from __future__ import print_function, absolute_import, division, unicode_literals

from collections import OrderedDict
import os
import subprocess

from .. import common_utils, _pretty_n_col, preplogs_dir
from ..configuration import config_utils
from . import prep_utils, prepwps, RealExeFailedError


_prep_fxns = OrderedDict([('real.exe', prep_utils.run_real), ('WPS', prepwps.prepwps)])


def decode_exit_code(ecode, print_to_screen=False):
    """
    Decode what a particular exit code means.

    :param ecode: the exit code
    :type ecode: int

    :param print_to_screen: optional, if ``True``, prints each component and whether is succeeded or failed.
    :type print_to_screen: bool

    :return: a dictionary with each component's name as the key and a boolean indicating if it succeeded.
    :rtype: dict
    """
    component_names = ['real.exe'] + list(_prep_fxns.keys())
    return common_utils.decode_exit_code(ecode, component_names, print_to_screen=print_to_screen)


def _run_prep_function(fxn, ecode, error_bit_idx, component_name, config_obj, **kwargs):
    ecode = common_utils.set_bit(error_bit_idx, ecode)

    try:
        fxn(config_obj, **kwargs)
    except subprocess.CalledProcessError:
        # something went wrong during the actual compilation
        common_utils.eprint('{} failed to run to completion.'.format(component_name))
    except RealExeFailedError as err:
        common_utils.eprint(err.args[0], max_columns=_pretty_n_col)
        ecode = common_utils.set_bit(0, ecode)
    else:
        # execution succeeded
        ecode = common_utils.set_bit(error_bit_idx, ecode, 0)

    return ecode


def _setup_input_functions(met_only=False, chem_only=False):
    if met_only:
        to_run = ['WPS']  # real.exe added later with a lambda function to set the log file location
    elif chem_only:
        to_run = []
    else:
        to_run = ['WPS']  # TODO: add chem parts

    command_list = []
    prep_fxn_keys = list(_prep_fxns.keys())
    for cmd in to_run:
        idx = prep_fxn_keys.index(cmd)
        command_list.append((idx, cmd, _prep_fxns[cmd]))

    if met_only:
        idx = 0
        real_log_file = os.path.join(preplogs_dir, 'real.log')
        prep_fxn = lambda config_obj, **kwargs: _prep_fxns['real.exe'](config_obj, log_file=real_log_file, **kwargs)
        command_list.append((idx, 'real.exe', prep_fxn))

    return command_list


def drive_input_prep(config_obj=None, finish=False, met_only=False):

    if config_obj is None:
        config_obj = config_utils.AutoWRFChemConfig()

    if config_utils.get_is_chem(config_obj):
        met_only = True

    ecode = 0

    for idx, name, fxn in _setup_input_functions(met_only=met_only):
        # assume the component failed, then only mark that it succeeded if it actually did or it was not required.
        # unlike the compile
        ecode = _run_prep_function(fxn, ecode, idx, name, config_obj, finish=finish)

    return ecode


def setup_clargs(parser):
    parser.description = 'Prepare input data for WRF(-Chem)'
    parser.add_argument('-f', '--finish', action='store_true', help='Only complete unfinished input prep steps (default '
                                                                    'behavior is to do all prep steps regardless of '
                                                                    'whether it is necessary)')
    parser.set_defaults(exec_func=drive_input_prep)
