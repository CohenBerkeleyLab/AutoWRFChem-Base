from __future__ import print_function, absolute_import, division, unicode_literals

from collections import OrderedDict
import os
import subprocess

from .. import common_utils, _pretty_n_col, complogs_dir
from ..configuration import config_utils, AUTOMATION, AUTOMATION_PATHS, TARGET


class CompilationNotRequired(Exception):
    """
    Exception to use if a component's compilation is not required, given the environment
    """
    pass


class CompilationCannotProceed(Exception):
    """
    Exception to use if pre-compile checks indicate the compilation cannot proceed
    """
    pass


###################################
# COMPONENT COMPILATION FUNCTIONS #
###################################

# Each function here should compile one component of WRF or its input prep. Each function will receive an
# AutoWRFChemConfig object and the current exit code of the program. It is up to each function to decide whether it
# can compile and needs to compile. Each function should use the above exceptions to indicate if it cannot or doesn't
# need to compile.

def _compile_wrf(config_obj, ecode):
    """
    Compile the WRF model.

    :param config_obj: and AutoWRFChemConfig object representing the current configuration.
    :type config_obj: `AutoWRFChemConfig`

    :param ecode: the current exit code for the compile all program.
    :type ecode: int

    :return: None
    """
    wrf_top_dir = config_utils.get_wrf_top_dir(config_obj)
    if not os.path.isfile(os.path.join(wrf_top_dir, 'configure.wrf')):
        raise CompilationCannotProceed('WRF cannot be compiled because "configure.wrf" does not exist in {dir}. Use '
                                       'autowrfchem config to produce it. Remember "clean -a" removes it.'.
                                       format(dir=wrf_top_dir))
    target = config_obj[AUTOMATION][TARGET]
    with open(os.path.join(complogs_dir, 'compile_wrf.log'), 'w') as logfile:
        common_utils.run_external(['./compile', target], config_obj, cwd=wrf_top_dir, logfile_handle=logfile)


def _compile_wps(config_obj, ecode):
    """
    Compile the WPS met preprocessor.

    :param config_obj: and AutoWRFChemConfig object representing the current configuration.
    :type config_obj: `AutoWRFChemConfig`

    :param ecode: the current exit code for the compile all program.
    :type ecode: int

    :return: None
    """
    component_state = decode_exit_code(ecode)
    wps_top_dir = config_utils.get_wps_top_dir(config_obj)

    if not component_state['WRF']:
        raise CompilationCannotProceed('WPS cannot compile if WRF failed to do so')
    elif not os.path.isfile(os.path.join(wps_top_dir, 'configure.wps')):
        raise CompilationCannotProceed('WPS cannot be compiled because "configure.wps" does not exist in {dir}. Use '
                                       'autowrfchem config to produce it. Remember "clean -a" removes it.'.
                                       format(dir=wps_top_dir))

    with open(os.path.join(complogs_dir, 'compile_wps.log'), 'w') as logfile:
        common_utils.run_external(['./compile'], config_obj, cwd=wps_top_dir, logfile_handle=logfile)


# Add components here in the order they should be compiled, assuming all will be compiled.
_compile_fxns = OrderedDict([('WRF', _compile_wrf),
                             ('WPS', _compile_wps)])


####################
# DRIVER FUNCTIONS #
####################

def clean_all_exe(config_obj):
    """
    Clean all components' executable.

    :param config_obj: and AutoWRFChemConfig object representing the current configuration.
    :type config_obj: `AutoWRFChemConfig`

    :return: None
    """
    wrf_top_dir = config_utils.get_wrf_top_dir(config_obj)
    common_utils.run_external(['./clean', '-a'], config_obj, cwd=wrf_top_dir)
    wps_top_dir = config_utils.get_wps_top_dir(config_obj)
    common_utils.run_external(['./clean', '-a'], config_obj, cwd=wps_top_dir)


def compile_all(config_obj=None):
    """
    Compile all required components of WRF and its preprocessors

    :param config_obj: and AutoWRFChemConfig object representing the current configuration.
    :type config_obj: `AutoWRFChemConfig`

    :return: None
    """
    #TODO: add chemistry parts
    if config_obj is None:
        config_obj = config_utils.AutoWRFChemConfig()

    ecode = 0

    for idx, (name, fxn) in enumerate(_compile_fxns.items()):
        # assume the component failed, then only mark that it succeeded if it actually did or it was not required
        ecode = common_utils.set_bit(idx, ecode)

        try:
            fxn(config_obj, ecode)
        except CompilationNotRequired:
            # this component isn't required, based on the current environmental variables or another check.
            ecode = common_utils.set_bit(idx, ecode, 0)
        except subprocess.CalledProcessError:
            # something went wrong during the actual compilation
            common_utils.eprint('{} failed to compile.'.format(name))
        except CompilationCannotProceed as err:
            # the compile function decided that the compilation could not even be attempted
            common_utils.eprint(err.args[0], max_columns=_pretty_n_col)
        else:
            # compilation succeeded
            ecode = common_utils.set_bit(idx, ecode, 0)

    return ecode


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
    return common_utils.decode_exit_code(ecode, _compile_fxns.keys(), print_to_screen=print_to_screen)


def drive_compile(explain_ecode=None, **_):
    """
    Driver function to compile all components from the command line.

    :param explain_ecode: an error code to explain. If given, does not compile.
    :type explain_ecode: int

    :param _: consumes extra keyword args

    :return: exit code
    :rtype: int
    """
    if explain_ecode is not None:
        ecode = decode_exit_code(explain_ecode, print_to_screen=True)
    else:
        config_obj = config_utils.AutoWRFChemConfig()
        ecode = compile_all(config_obj)

    if ecode is None:
        ecode = 0

    return ecode


def drive_clean(**_):
    """
    Driver function to clean all compiled components

    :param _: consumes extra keyword args

    :return: exit code
    :rtype: int
    """
    config_obj = config_utils.AutoWRFChemConfig()
    clean_all_exe(config_obj)

    return 0


def setup_compile_clargs(parser):
    """

    :param parser: :class:`argparse.ArgumentParser`
    :return:
    """
    parser.description = 'Compile all components needed for WRF or WRF-Chem. Which components are compiled may depend ' \
                         'on the environmental variables set in the AutoWRFChem config file.'
    parser.add_argument('-e', '--explain-ecode', type=int, help="Given an exit code, explain which parts' compilations "
                                                                "succeeded and which failed.")
    parser.set_defaults(exec_func=drive_compile)


def setup_clean_clargs(parser):
    parser.set_defaults(exec_func=drive_clean)
