#!/usr/bin/env python3
from __future__ import print_function, absolute_import, division, unicode_literals

from glob import glob
import os
from pkg_resources import parse_version
import re

from .. import automation_top_dir
from . import AUTOMATION, WRF_TOP_DIR, WPS_TOP_DIR

try:
    # Python 3 names it with lower case and Python 2 has a backported version named lowercase
    import configparser as conpar
except ImportError:
    # Only if we can't find the newer version do we fall back on the Python 2.x version
    import ConfigParser as conpar

from .. import _config_dir, _config_defaults_dir, ui
from . import ConfigurationError


class ComponentMissingError(Exception):
    """
    Exception to use if a required component (either model or input tool) does not exist.
    """
    pass


class AutoWRFChemConfig(conpar.ConfigParser):
    """
    Class that represents the configuration (except for the namelists) of the AutoWRFChem package

    Inherits from configparser.SafeConfigParser. Option parsing changed so that capitalization is
    retained for option names. Adds load_config() and save_config() methods, which have the standard
    location for the configuration file baked in.
    """
    _config_file = os.path.join(_config_dir, 'autowrfchem.cfg')
    _default_config_file = os.path.join(_config_defaults_dir, 'autowrfchem_default.cfg')

    @property
    def source_file(self):
        return self._source_file

    @property
    def read_from_defaults(self):
        return self._read_from_defaults

    def __init__(self, *args, **kwargs):
        super(AutoWRFChemConfig, self).__init__(*args, **kwargs)
        self._source_file = None
        self._read_from_defaults = False

    def optionxform(self, optionstr):
        # Keep options case sensitive
        return str(optionstr)

    @classmethod
    def load_config(cls, config_file=None, reload_defaults=False):
        """
        Read in the AutoWRFChem configuration file.

        :param config_file: optional, the path to a configuration file to load. If not given, this method will first
        look for the standard config file at AutoWRFChem-Base/CONFIG/autowrfchem.cfg, then if that does not exist, the
        defaults file at AutoWRFChem-BASE/CONFIG/Defaults/autowrfchem_default.cfg
        :return: a new instance of AutoWRFChemConfig with the options loaded. The
        """
        config = cls()

        # TODO: decide if the options in the loaded file should be checked against the default one to be sure they are all there?
        if not reload_defaults and config_file is not None:
            if not os.path.isfile(config_file):
                raise IOError('Custom config file ({}) does not exist'.format(config_file))
            else:
                config_file_to_load = config_file
        elif not reload_defaults and os.path.isfile(cls._config_file):
            config_file_to_load = cls._config_file
        elif os.path.isfile(cls._default_config_file):
            config_file_to_load = cls._default_config_file
            config._read_from_defaults = True
        else:
            raise ConfigurationError('No configuration file exists (including the default file)')

        config.read(config_file_to_load)
        config._source_file = config_file_to_load

        return config

    def save_config(self, config_file=_config_file):
        """
        Save the configuration.
        :param config_file: optional, if given, overrides the standard save location, which is AutoWRFChem-Base/CONFIG/
        autowrfchem.cfg
        :return: none.
        """

        header = \
"""# This is the configuration file for AutoWRFChem.
# You may modify settings here if desired, so long as the format is maintained.
# Each section must be defined with the title in square brackets.
# Each option must begin at the start of the line (no leading whitespace) and be
# separated from the value with an =."""

        with open(config_file, 'w') as fobj:
            fobj.write(header + '\n\n')
            self.write(fobj)


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

    component_dir = config_obj.get(AUTOMATION, component_var)
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
