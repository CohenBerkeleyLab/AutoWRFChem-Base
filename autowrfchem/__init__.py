import os

#######################################
# Paths relevant to the whole package #
#######################################

_pkg_dir = os.path.abspath(os.path.dirname(__file__))
_wrf_dir_default = os.path.abspath(os.path.join(_pkg_dir, '..', 'WRFV3'))


def get_wrf_dir():
    """
    Get the top level WRF directory (usually WRFV3).
    :return: absolute path to the WRF directory as a string
    """

    # Eventually this should query a configuration file so that a different WRF directory
    # can be set
    return _wrf_dir_default


##############
# Components #
##############

wrf_components = ['wrf', 'wps', 'nei', 'megan', 'mozbc']


###########################
# Environmental variables #
###########################

use_env_const = 'use_env_var'
_alt_mpi_cmd_var = 'AWC_MPICMD'
