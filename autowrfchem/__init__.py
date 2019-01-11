import os

#######################################
# Paths relevant to the whole package #
#######################################

_pkg_dir = os.path.abspath(os.path.dirname(__file__))
automation_top_dir = os.path.abspath(os.path.join(_pkg_dir, '..'))

config_dir = os.path.abspath(os.path.join(_pkg_dir, '..', 'CONFIG'))
config_defaults_dir = os.path.join(config_dir, 'Defaults')
namelists_dir = os.path.join(config_dir, 'NAMELISTS')
wrf_dir_default = os.path.abspath(os.path.join(_pkg_dir, '..', 'WRFV3'))

complogs_dir = os.path.abspath(os.path.join(_pkg_dir, '..', 'COMPLOGS'))
preplogs_dir = os.path.abspath(os.path.join(_pkg_dir, '..', 'PREPLOGS'))

##############
# Components #
##############

wrf_components = ['wrf', 'wps', 'nei', 'megan', 'mozbc']


########################
# Formatting constants #
########################

_pretty_n_col = 72
wrf_date_fmt = '%Y-%m-%d_%H:%M:%S'
