import os

#######################################
# Paths relevant to the whole package #
#######################################

_pkg_dir = os.path.abspath(os.path.dirname(__file__))
automation_top_dir = os.path.abspath(os.path.join(_pkg_dir, '..'))

_config_dir = os.path.abspath(os.path.join(_pkg_dir, '..', 'CONFIG'))
_config_defaults_dir = os.path.join(_config_dir, 'Defaults')
_namelists_dir = os.path.join(_config_dir, 'NAMELISTS')
_wrf_dir_default = os.path.abspath(os.path.join(_pkg_dir, '..', 'WRFV3'))


##############
# Components #
##############

wrf_components = ['wrf', 'wps', 'nei', 'megan', 'mozbc']


###########################
# Environmental variables #
###########################

use_env_const = 'use_env_var'
_alt_mpi_cmd_var = 'AWC_MPICMD'
