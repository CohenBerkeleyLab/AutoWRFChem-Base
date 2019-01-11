from __future__ import print_function, absolute_import, division, unicode_literals

from argparse import ArgumentParser
from collections import OrderedDict
import subprocess

from .. import common_utils
from ..configuration import config_utils
from . import prepwps


_prep_fxns = OrderedDict([('WPS', prepwps.prepwps)])


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
    return common_utils.decode_exit_code(ecode, _prep_fxns.keys(), print_to_screen=print_to_screen)


def drive_input_prep(config_obj=None, finish=False):

    if config_obj is None:
        config_obj = config_utils.AutoWRFChemConfig()

    ecode = 0

    for idx, (name, fxn) in enumerate(_prep_fxns.items()):
        # assume the component failed, then only mark that it succeeded if it actually did or it was not required
        ecode = common_utils.set_bit(idx, ecode)

        try:
            fxn(config_obj, finish=finish)
        except subprocess.CalledProcessError:
            # something went wrong during the actual compilation
            common_utils.eprint('{} failed to run.'.format(name))
        else:
            # compilation succeeded
            ecode = common_utils.set_bit(idx, ecode, 0)

    return ecode


def setup_clargs(parser):
    parser.description = 'Prepare input data for WRF(-Chem)'
    parser.add_argument('-f', '--finish', action='store_true', help='Only complete unfinished input prep steps (default '
                                                                    'behavior is to do all prep steps regardless of '
                                                                    'whether it is necessary)')
    parser.set_defaults(exec_func=drive_input_prep)
