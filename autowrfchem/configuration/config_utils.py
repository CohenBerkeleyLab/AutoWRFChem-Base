#!/usr/bin/env python3
from __future__ import print_function, absolute_import, division, unicode_literals

from configobj import ConfigObj
from glob import glob
import os
from pkg_resources import parse_version
import re

from .. import automation_top_dir
from . import AUTOMATION, WRF_TOP_DIR, WPS_TOP_DIR


from .. import _config_dir, _config_defaults_dir, ui
from . import ConfigurationError


class ConfigurationLoadError(ConfigurationError):
    """
    Error to use if there's an error loading the config file
    """
    pass


class ComponentMissingError(Exception):
    """
    Exception to use if a required component (either model or input tool) does not exist.
    """
    pass


class AutoWRFChemConfig(ConfigObj):
    """
    Class that represents the configuration (except for the namelists) of the AutoWRFChem package

    Inherits from configparser.SafeConfigParser. Option parsing changed so that capitalization is
    retained for option names. Adds load_config() and save_config() methods, which have the standard
    location for the configuration file baked in.
    """
    _config_file = os.path.join(_config_dir, 'autowrfchem.cfg')
    _default_config_file = os.path.join(_config_defaults_dir, 'autowrfchem_default.cfg')

    # used to replace the initial comment in the defaults file
    _std_initial_comment = ['# This is the configuration file for AutoWRFChem.',
                            '# You may modify settings here if desired, so long as the format is maintained.',
                            '# Each section must be defined with the title in square brackets.',
                            '# Each option must begin at the start of the line (no leading whitespace) and be',
                            '# separated from the value with an =.']

    @property
    def read_from_defaults(self):
        return self._read_from_defaults

    def __init__(self, config_file=None, reload_defaults=True, *args, **kwargs):
        config_file = self._choose_config_file(config_file, reload_defaults=reload_defaults)
        super(AutoWRFChemConfig, self).__init__(config_file, *args, **kwargs)

        # ConfigObj uses the filename attribute to determine where to write the file by default. We never want to
        # overwrite the defaults file, so if that's where we read from, we instead want to by default write to the
        # standard config location. Further, we also want to swap out the initial comment from one that says "do not
        # modify the defaults" to one that says "it's okay to modify this file"
        if config_file != self._default_config_file:
            self.filename = config_file
        else:
            self.filename = self._config_file
            self.initial_comment = self._std_initial_comment
        self._read_from_defaults = config_file == self._default_config_file

    @classmethod
    def _choose_config_file(cls, config_file, reload_defaults=True):
        def get_std_configs():
            if os.path.isfile(cls._config_file):
                return cls._config_file
            elif reload_defaults:
                if os.path.isfile(cls._default_config_file):
                    return cls._default_config_file
                else:
                    raise ConfigurationLoadError('The default configuration file does not exist! '
                                                 'Restore it from the git repo if necessary.')
            else:
                raise ConfigurationLoadError('Not permitted to reload defaults, but the standard config file does not exist.')

        if config_file is None:
            return get_std_configs()
        elif os.path.isfile(config_file):
            return config_file
        else:
            raise ConfigurationLoadError('Given custom config file ({}) does not exist!'.format(config_file))


def get_envvar_presets(preset=None):
    presets = conpar.ConfigParser()
    presets.optionxform = str  # avoid lowercasing the env var names
    presets.read(os.path.join(_config_dir, 'Defaults', 'env_var_presets.cfg'))
    presets_dict = presets._sections
    for subdict in presets_dict.values():
        # The _sections dict includes the extra "__name__" entry, which we don't want
        subdict.pop('__name__')

    if preset is not None:
        return presets_dict[preset]
    else:
        return presets_dict


def get_ncdf_dir(interactive=False):
    """
    Find a netCDF library directory on the system.

    This function will search existing environmental variables for any that contain the string "NETCDF".
    For each environmental variable, it checks that it points to a directory containing "lib/libnetcdf.so"
    of some version. By default, it will choose the highest available version, but this can be overridden
    with the interactive parameter.
    :param interactive: boolean, optional, if set to True, will present the user with a list of possible
    netCDF directories.
    :return: the netCDF directory. Raises ConfigurationError if cannot find one.
    """
    ncdf_regex = re.compile('.*NETCDF.*')
    matching_vars = [v for v in os.environ if ncdf_regex.search(v)]
    if len(matching_vars) == 0:
        raise ConfigurationError('No NETCDF or similar environmental variable found')
    elif len(matching_vars) == 1:
        return os.getenv(matching_vars[0])
    else:
        # Get the value for each matching environmental variable and check if it points to a directory containing
        # lib/libnetcdf.so and lib/libnetcdff.so. Grab the version numbers from the end of those files, we'll either
        # choose the most recent one or present the user with a list
        highest_version = parse_version('0.0.0')
        highest_version_dir = ''
        ncdf_dir_dict = dict()
        for v in matching_vars:
            ncdf_dir = os.getenv(v)
            file_list = glob(os.path.join(ncdf_dir, 'lib', 'libnetcdf.so.*'))
            if len(file_list) == 0:
                continue

            lib_file = _longest_filename(file_list)
            lib_version, version_string = _file_version(lib_file)
            if lib_version > highest_version:
                highest_version = lib_version
                highest_version_dir = ncdf_dir

            ncdf_dir_dict[version_string] = ncdf_dir

        if len(highest_version_dir) == 0:
            raise ConfigurationError('No valid netCDF directory found')

        if not interactive:
            return highest_version_dir
        else:
            # Prepare a list of the versions found in descending order
            keys = sorted(ncdf_dir_dict.keys(), key=parse_version, reverse=True)
            user_choices = ['{} ({})'.format(k, ncdf_dir_dict[k]) for k in keys]
            choice_ind = ui.user_input_list('Multiple netCDF libraries found. Choose which one to use.\n'
                                            '(If you do not know which one, usually the highest version is best.)',
                                            user_choices, returntype='index', emptycancel=False)
            return ncdf_dir_dict[keys[choice_ind]]


def get_yacc_exec(extra_search_dirs=[]):
    search_dirs = os.getenv('PATH').split(':') + extra_search_dirs
    yacc_path = _search_paths_for_file(search_dirs, 'yacc')
    return os.path.join(yacc_path, 'yacc -d')


def get_flexlib_dir(extra_search_dirs=[]):
    search_dirs = ['/usr/lib64', '/usr/lib'] + extra_search_dirs
    return _search_paths_for_file(search_dirs, 'libfl.a')


def printwait(msg):
    print(msg)
    input('Press ENTER to continue.')


def _search_paths_for_file(search_dirs, target):
    for path_dir in search_dirs:
        for item in os.listdir(path_dir):
            if item == target and os.path.isfile(os.path.join(path_dir, item)):
                return path_dir
    raise ConfigurationError('Could not find "{}" in the directories: {}'.format(target, ', '.join(search_dirs)))


def _longest_filename(file_list):
    """
    Return the longest file name in a list
    :param file_list: the list of file names
    :return: the longest file name
    """
    sorted_list = sorted(file_list, key=len)
    return sorted_list[-1]


def _file_version(filename):
    """
    Return the parsed version number of the given file, assuming the version is at the end.
    :param filename: the filename containing the version number
    :return: the Version instance
    """
    version_str = re.search('\d+\.\d+\.\d+$', filename).group()
    return parse_version(version_str), version_str


##########################################
# FUNCTIONS DEALING WITH COMPONENT PATHS #
##########################################


def _make_component_top_dir(component_var, config_obj=None):
    """
    Create the path to the top directory of a component, i.e. WRF, WPS, etc.

    For flexibility, AutoWRFChem v2.0 allows the paths to the WRF, WPS, etc. directories to be specified in the config
    file rather that requiring that the be in a specific place. These paths may be given as absolute or relative paths;
    if given as relative paths, they must be relative to the top of the automation directory (so not the autowrfchem
    package directory, but the one above that). This function returns the absolute path to whichever component is
    requested.

    :param component_var: the config variable that has the path to the component stored.
    :type component_var: str

    :param config_obj: optional, the object representing the AWC configuration file. If omitted, the standard config
     file is read automatically.
    :type config_obj: AutoWRFChemConfig

    :return: the absolute path to the component.
    :rtype: str
    """
    if config_obj is None:
        config_obj = AutoWRFChemConfig()

    component_dir = config_obj[AUTOMATION][component_var]
    if not os.path.isabs(component_dir):
        component_dir = os.path.abspath(os.path.join(automation_top_dir, component_dir))

    if not os.path.isdir(component_dir):
        raise ComponentMissingError('The directory {} pointed to by config {} does not exist'.format(
            component_dir, component_var
        ))

    return component_dir


def get_wrf_top_dir(config_obj=None):
    return _make_component_top_dir(WRF_TOP_DIR, config_obj)


def get_wrf_run_dir(config_obj=None):
    return os.path.join(get_wrf_top_dir(config_obj), 'run')


def get_wps_top_dir(config_obj=None):
    return _make_component_top_dir(WPS_TOP_DIR, config_obj)


def get_wps_run_dir(config_obj=None):
    return get_wps_top_dir(config_obj)
