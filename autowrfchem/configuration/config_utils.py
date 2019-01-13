#!/usr/bin/env python3
from __future__ import print_function, absolute_import, division, unicode_literals

from configobj import ConfigObj
from copy import deepcopy
from glob import glob
import os
from pkg_resources import parse_version
import re
import subprocess

from .. import automation_top_dir, common_utils
from . import ENVIRONMENT, AUTOMATION, AUTOMATION_PATHS, WRF_TOP_DIR, WPS_TOP_DIR


from .. import config_dir, config_defaults_dir, ui
from . import ConfigurationError


class ConfigurationLoadError(ConfigurationError):
    """
    Error to use if there's an error loading the config file
    """
    pass


class ConfigurationSetupError(ConfigurationError):
    """
    Error to use if there's a problem setting up the configuration for the first time

    In addition to the regular error message, the second (optional) argument is intended to be a suggestion that an
    interactive program can print to give the user a hint how to fix the problem.
    """
    def __init__(self, msg, suggestion=None):
        self.args = (msg, suggestion)

    def __str__(self):
        return self.args[0]


class ConfigurationSettingsError(ConfigurationError):
    """
    Error to use if there's a problem with the value of a config setting.

    :param msg: the regular error message
    :type msg: str

    :param failures: a dictionary giving information about what settings specifically are wrong and potentially why they
     are wrong.
    :type failures: dict
    """
    def __init__(self, msg, failures):
        """
        See class help.
        """
        self.args = (msg, failures)

    def __str__(self):
        return self.args[0] + '\n(Details in error args[1])'


class ComponentMissingError(Exception):
    """
    Exception to use if a required component (either model or input tool) does not exist.
    """
    pass


class AutoWRFChemConfig(ConfigObj):
    """
    Class that represents the configuration (except for the namelists) of the AutoWRFChem package

    This is a subclass of `configobj.ConfigObj`. There are a few additional methods (mainly to check option values) and
    attributes, but the main difference is that this class automatically knows where to read the config file from if it
    isn't specified.

    If the file to read isn't specified, then this class will default to reading the standard config file in the
    AutoWRFChem CONFIG directory. If that file doesn't exist, it reads the defaults file in CONFIG/Defaults. However, if
    the defaults file is read, the `filename` attribute will be changed to point to the standard config file so that
    when it is saved, it writes to the standard location and not the defaults file. The `read_from_defaults` property
    will be ``True`` if the defaults file was read.

    Finally, note that it is possible to tell this class not to reload the defaults file. This is intended to provide a
    mechanism to prevent accidentally loading the defaults (which usually need at least a little tweaking) when it's
    time to actually run part of AutoWRFChem.

    :param config_file: optional, allows you to specify a different configuration file to load. If not given, then
     the standard or default config file will be read.
    :type config_file: str

    :param reload_defaults: optional, controls whether the defaults file should be read if the standard file does
     not exist. Default is ``True``.
    :type reload_defaults: bool

    :param args: additional arguments to ConfigObj

    :param kwargs: additional keyword args to ConfigObj
    """
    _config_file = os.path.join(config_dir, 'autowrfchem.cfg')
    _default_config_file = os.path.join(config_defaults_dir, 'autowrfchem_default.cfg')

    _missing_env_var = 'Undefined'

    # used to replace the initial comment in the defaults file
    _std_initial_comment = ['# This is the configuration file for AutoWRFChem.',
                            '# You may modify settings here if desired, so long as the format is maintained.',
                            '# Each section must be defined with the title in square brackets.',
                            '# Each option must begin at the start of the line (no leading whitespace) and be',
                            '# separated from the value with an =.']

    @property
    def read_from_defaults(self):
        return self._read_from_defaults

    @property
    def has_changed(self):
        return self.dict() != self._original_values

    def __init__(self, config_file=None, reload_defaults=True, ignore_differences_with_defaults=False, *args, **kwargs):
        """
        See class help.
        """
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
        if not ignore_differences_with_defaults and not self._read_from_defaults:
            self._check_all_opts_present()

        self._original_values = deepcopy(self.dict())

    @classmethod
    def _choose_config_file(cls, config_file, reload_defaults=True):
        """
        Helper function that determines which config file the __init__ method should read.

        :param config_file: either a path to a custom config file or None to load the standard or default file.
        :type config_file: str or None

        :param reload_defaults: controls whether we are allowed to load the default config file. Default ``True``.
        :type reload_defaults: bool

        :return: the path to the config file to load.
        :rtype: str
        """
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

    def _check_all_opts_present(self):
        section_hierarchy = []

        def walk_section(my_section, default_section):
            for key in default_section.keys():
                if key not in my_section:
                    section_hierarchy.append(key)
                    raise ConfigurationSetupError('Key {} from default config file is missing from active one'.
                        format('/'.join(section_hierarchy)))
                elif key in default_section.sections:
                    section_hierarchy.append(key)
                    walk_section(my_section[key], default_section[key])
                    section_hierarchy.remove(key)

        default_cfg = ConfigObj(self._default_config_file)
        walk_section(self, default_cfg)

    def update_from_defaults(self, no_backup=False):
        if not no_backup:
            with open(common_utils.backup_file_name(self.filename), 'wb') as backup_file:
                self.write(backup_file)

        defaults = AutoWRFChemConfig(AutoWRFChemConfig._default_config_file)
        defaults.merge(self)
        defaults.filename = self.filename
        return defaults

    def check_env_vars(self):
        """
        Check that the values of the environmental variables are valid.

        Currently, the only checks are:
            * if any variables undefined in a preset failed to be defined during setup
            * if any of the netCDF, YACC, or FLEX_LIB paths are wrong (the latter two are only checked if WRF_KPP = '1')

        :return: None
        :raises ConfigurationSettingsError: if there is a problem with any of the environmental variables.
        """
        failures = {'undefined_vars': [], 'bad_netcdf_dir': False, 'netcdf_causes': dict(),
                    'bad_yacc_path': False, 'bad_flex_path': False}
        for opt, val in self[ENVIRONMENT].items():
            if val.strip() == self._missing_env_var:
                failures['undefined_vars'].append(opt)

        failures['bad_netcdf_dir'] = not _check_ncdf_dir(self[ENVIRONMENT]['NETCDF'], failures['netcdf_causes'])

        wrf_kpp = self[ENVIRONMENT]['WRF_KPP']
        if wrf_kpp == '1':
            yacc_path = self[ENVIRONMENT]['YACC'].strip().rstrip('-d')
            failures['bad_yacc_path'] = not os.path.isfile(yacc_path)

            flexlib_glob = os.path.join(self[ENVIRONMENT]['FLEX_LIB_DIR'], 'libfl.*')
            failures['bad_flex_path'] = len(glob(flexlib_glob)) == 0

        if len(failures['undefined_vars']) > 0 or failures['bad_netcdf_dir'] or failures['bad_yacc_path'] or failures['bad_flex_path']:
            raise ConfigurationSettingsError('There is a problem with the current environmental variables', failures)

    def check_auto_paths(self, options_to_check=None):
        """
        Check that the automation config settings are valid.

        This checks that each of the top directories for WRF, WPS, etc. given exist and contain certain expected files
        or directories.

        :param options_to_check: optional, if given, limits which options should be checked. In that case, must be a
         list of option names. If not given, all options are checked.
        :type options_to_check: None or list of str

        :return: None
        :raises ConfigurationSettingsError: if any of the directories do not exist or are missing the expected
         files/subdirectories.
        """
        # Once chemistry is added, will need to look at the environment variables in order to decide whether to
        req_files_and_dirs = {'WRF_TOP_DIR': ['configure', 'compile', 'run'],
                              'WPS_TOP_DIR': ['configure', 'compile', 'geogrid', 'ungrib', 'metgrid']}

        auto_paths = self[AUTOMATION_PATHS]
        failures = {k: False for k in auto_paths.keys()}
        for opt, val in auto_paths.items():
            if options_to_check is not None and opt not in options_to_check:
                continue

            if not os.path.isdir(val):
                failures[opt] = True
                continue

            for f in req_files_and_dirs[opt]:
                if not os.path.exists(os.path.join(val, f)):
                    failures[opt] = True

        if any(failures.values()):
            raise ConfigurationSettingsError('There is a problem with the current automation configs', failures)


def _get_presets_file(filename, preset=None):
    if not os.path.isabs(filename):
        filename = os.path.join(config_defaults_dir, filename)

    cfg = ConfigObj(filename)
    if preset is None:
        return cfg
    else:
        return cfg[preset]


def get_envvar_presets(preset=None):
    """
    Read in the file defining the environmental variable presets.

    :param preset: If given, returns just the section corresponding to that preset. Otherwise, returns the whole config
     object.
    :type preset: str

    :return: the ConfigObj holding all the presets as different sections, or the section of the ConfigObj for the given
     preset if ``preset`` is given.
    """
    return _get_presets_file(os.path.join(config_defaults_dir, 'env_var_presets.cfg'), preset=preset)


def get_met_presets(preset=None):
    """
    Read in the file defining the meteorology types' namelist option presets.

    :param preset: If given, returns just the section corresponding to that preset. Otherwise, returns the whole config
     object.
    :type preset: str

    :return: the ConfigObj holding all the presets as different sections, or the section of the ConfigObj for the given
     preset if ``preset`` is given.
    :raises ConfigurationLoadError: if the requested preset cannot be found.
    """
    try:
        return _get_presets_file(os.path.join(config_defaults_dir, 'met_presets.cfg'), preset=preset)
    except KeyError:
        raise ConfigurationLoadError('Requested met type "{}" is not defined'.format(preset))


def get_chem_presets(preset=None):
    """
    Read in the file defining the chemistry mechanisms' namelist option presets.

    :param preset: If given, returns just the section corresponding to that preset. Otherwise, returns the whole config
     object.
    :type preset: str

    :return: the ConfigObj holding all the presets as different sections, or the section of the ConfigObj for the given
     preset if ``preset`` is given.
    """
    return _get_presets_file(os.path.join(config_defaults_dir, 'chem_presets.cfg'), preset=preset)


def _check_ncdf_dir(ncdf_dir, causes=None):
    """
    Check that the given directory is a valid directory for the netCDF library.

    Requires that this directory contains a subdirectory "lib" with "libnetcdf*" and "libnetcdff*" files and a
    subdirectory "include" with files "netcdf.h" and "netcdf.inc".

    :param ncdf_dir: the directory to check
    :type ncdf_dir: str

    :return: True if the directory contains the expected files, False otherwise.
    :rtype: bool
    """
    if isinstance(causes, dict):
        causes['ncdf_dir_nonexistant'] = False
        causes['missing_files'] = []
    elif causes is not None:
        raise TypeError('causes must be a dict or None')

    if not os.path.isdir(ncdf_dir):
        if causes is not None:
            causes['ncdf_dir_nonexistant'] = True
        return False


    # Require that we find the "lib/libnetcdf", "lib/libnetcdff", "include/netcdf.h", and "include/netcdf.inc" files.
    # Allow static (.a) or shared (.so) files.
    req_globs = [('lib', 'libnetcdf*'), ('lib', 'libnetcdff*'), ('include', 'netcdf.h'), ('include', 'netcdf.inc')]
    for g in req_globs:
        check_files = glob(os.path.join(ncdf_dir, *g))
        if len(check_files) == 0:
            if causes is None:
                return False
            else:
                causes['missing_files'].append(os.path.join(*g))

    if causes['ncdf_dir_nonexistant'] or len(causes['missing_files']) > 0:
        return False
    else:
        return True


def get_ncdf_dir(interactive=False):
    """
    Find a netCDF library directory on the system.

    This function will search existing environmental variables for any that contain the string "NETCDF".
    For each environmental variable, it checks that it points to a directory containing "lib/libnetcdf.so"
    of some version. By default, it will choose the highest available version, but this can be overridden
    with the interactive parameter.

    :param interactive: optional, if set to True, will present the user with a list of possible
     netCDF directories.
    :type interactive: bool

    :return: the netCDF directory.

    :raises ConfigurationSetupError: if cannot find the netCDF directory
    """
    ncdf_regex = re.compile('.*NETCDF.*')
    matching_vars = [v for v in os.environ if ncdf_regex.search(v)]
    if len(matching_vars) == 0:
        # Try the nc-config and nf-config programs. They both better return the same installation prefix, or we're in
        # trouble
        try:
            nc_prefix = subprocess.check_output(['nc-config', '--prefix'])
            nf_prefix = subprocess.check_output(['nf-config', '--prefix'])
        except FileNotFoundError:
            raise ConfigurationSetupError(
                'No NETCDF (or similar) environmental error found, and nc-config or nf-config are not installed.',
                'WRF requires the netCDF library to read and write output files. I cannot find at least one of the C '
                'or Fortran netCDF libraries (both are needed). \n\n'
                'I am looking for either an environmental variable with "NETCDF" in its name that points to the path '
                'where these libraries are installed (the path would have subdirectories "lib" that has files like '
                '"libnetcdf.a", "libnetcdf.so", "libnetcdff.a", "libnetcdff.so", or similar and "include" that has, '
                'among others, "netcdf.inc") or the programs "nc-config" and "nf-config" that get installed with these '
                'libraries and can tell me where there are installed.\n\n'
                'The fact that I cannot find these programs suggests that the netCDF libraries are not installed, or '
                'are installed in an unusual place. If the former, get them installed; if the latter either set the '
                'environmental variable NETCDF to the path described above or edit it in the config file.'
            )
        else:
            nc_prefix = nc_prefix.decode('utf-8').strip()
            nf_prefix = nf_prefix.decode('utf-8').strip()
            if nc_prefix != nf_prefix:
                raise ConfigurationSetupError(
                    'nc-config and nf-config return different installation paths',
                    'I am trying to use the nc-config and nf-config programs to find out where your netCDF installation'
                    ' is. However, they return different paths, which means your default C and Fortran netCDF libraries'
                    ' are in different locations. This will not work with WRF. There are a few possible fixes:\n\n'
                    '* If the two are built with different compilers, that will not work. You will need to rebuild '
                    'one or both of them so that the same compiler built both.\n\n'
                    '* If the two were built with the same compiler, but installed in different places, you can create '
                    'a new directory with "include" and "lib" subdirectories, and link all the netCDF-C and '
                    'netCDF-Fortran library and include files to those directories. In this case you will need to set '
                    'the NETCDF path manually, either in the shell or the AutoWRFChem config file.'
                )
            else:
                return nc_prefix

    elif len(matching_vars) == 1:
        ncdf_dir = os.getenv(matching_vars[0])
        if not _check_ncdf_dir(ncdf_dir):
            raise ConfigurationSetupError('Directory from env. var "{}" is not a valid netCDF directory'.format(matching_vars[0]),
                                          'The environmental variable "{}" points to the path "{}", but this does not '
                                          'look like a valid netCDF directory (I consider a valid netCDF directory to '
                                          'have files lib/libnetcdf*, lib/libnetcdff*, include/netcdf.h, and '
                                          'include/netcdf.inc). Either fix this environmental variable before '
                                          'launching AutoWRFChem or set the NETCDF value in the config file now.')
    else:
        # Get the value for each matching environmental variable and check if it points to a directory containing
        # lib/libnetcdf.so* and lib/libnetcdff.so*. Grab the version numbers from the end of those files, we'll either
        # choose the most recent one or present the user with a list
        highest_version = parse_version('0.0.0')
        highest_version_dir = None
        ncdf_dir_dict = dict()
        for v in matching_vars:
            ncdf_dir = os.getenv(v)

            if not _check_ncdf_dir(ncdf_dir):
                continue

            file_list = glob(os.path.join(ncdf_dir, 'lib', 'libnetcdf.so.*'))
            lib_file = _longest_filename(file_list)
            lib_version, version_string = _file_version(lib_file)
            if lib_version > highest_version:
                highest_version = lib_version
                highest_version_dir = ncdf_dir

            ncdf_dir_dict[version_string] = ncdf_dir

        if highest_version_dir is None:
            raise ConfigurationSetupError('No valid netCDF directory found',
                                          'I found multiple environmental variables with "NETCDF" in their names, '
                                          'but none of them seem to point to a valid netCDF directory. '
                                          '(I consider a valid netCDF directory to have files lib/libnetcdf*, '
                                          'lib/libnetcdff*, include/netcdf.h, and include/netcdf.inc.) Either fix at '
                                          'least one of these variables, or set the NETCDF value in the config file '
                                          'now.')

        if not interactive:
            return highest_version_dir
        else:
            # Prepare a list of the versions found in descending order
            keys = sorted(ncdf_dir_dict.keys(), key=parse_version, reverse=True)
            user_choices = ['{} ({})'.format(k, ncdf_dir_dict[k]) for k in keys]
            choice_ind = ui.user_input_list('Multiple netCDF libraries found. Choose which one to use.\n'
                                            '(If you do not know which one, usually the highest version compiled\n'
                                            '    by the same compiler you want to use to compile WRF is best.)',
                                            user_choices, returntype='index', emptycancel=False)
            return ncdf_dir_dict[keys[choice_ind]]


def get_yacc_exec(extra_search_dirs=[]):
    """
    Find the YACC (Yet Another Compiler Compiler) executable.

    This searches all directories on your PATH for the yacc executable needed by WRF-Chem's kinetic preprocessor (KPP).
    Note that the KPP is only needed for certain chemical mechanisms in WRF-Chem.

    :param extra_search_dirs: optional, if given, should be a list of extra directories to search for yacc.
    :type extra_search_dirs: list of str

    :return: the path to the yacc executable (including the executable file and the "-d" flag)
    :rtype: str
    :raises ConfigurationSetupError: if yacc cannot be found
    """
    search_dirs = os.getenv('PATH').split(':') + extra_search_dirs
    try:
        yacc_path = _search_paths_for_file(search_dirs, 'yacc')
    except ConfigurationSetupError as err:
        suggestion = "Either yacc (Yet Another Compiler Compiler) is not installed on your system, or it is installed " \
                     "in an unusual location. If it's not installed (which is likely, because I just searched the " \
                     "places it should be) install it and rerun this setup. If it is installed, you can edit the config " \
                     "file to give the path to it manually. For example, if yacc is in /home/you/tools, then set the " \
                     "YACC variable in the config to '/home/you/tools/yacc -d'"
        raise ConfigurationSetupError(err.args[0], suggestion)
    return os.path.join(yacc_path, 'yacc -d')


def get_flexlib_dir(extra_search_dirs=[]):
    """
    Search for the Fast Lexical Analyzer Generator (FLEX) library.

    The FLEX library is needed to compiler WRF-Chem's kinetic preprocessor, which is needed for only some of the
    chemical mechanisms in WRF-Chem, or to make custom chemical mechanisms. This function searches the standard places
    where it might be installed.

    :param extra_search_dirs: additional directories to search for the FLEX library file (libfl.a).
    :type extra_search_dirs: list of str

    :return: the directory containing libfl.a.
    :raises ConfigurationSetupError: if libfl.a cannot be found.
    """
    search_dirs = ['/usr/lib64', '/usr/lib'] + extra_search_dirs
    try:
        return _search_paths_for_file(search_dirs, 'libfl.a')
    except ConfigurationSetupError as err:
        raise ConfigurationSetupError(err.args[0], "Either the FLEX library is not installed on your system, or it is "
                                                   "installed in an unusual location. If it's not "
                                                   "installed (which is likely, because I just searched the places it "
                                                   "should be) install it and rerun this setup. If it is installed, "
                                                   "you can edit the config file to give the path to it manually. For "
                                                   "example, if libfl.a is in /home/you/tools/lib, then set the "
                                                   "FLEX_LIB_DIR variable in the config to '/home/you/tools/lib'")


def _search_paths_for_file(search_dirs, target):
    """
    Helper function that searches all given directories for a target file.

    :param search_dirs: list of directories to search
    :type search_dirs: list of str

    :param target: the file to look for
    :type target: str

    :return: the path containing the target file
    :rtype: str
    :raises ConfigurationSetupError: if the target file cannot be found in any of the given directories.
    """
    for path_dir in search_dirs:
        if os.path.isdir(path_dir):
            for item in os.listdir(path_dir):
                if item == target and os.path.isfile(os.path.join(path_dir, item)):
                    return path_dir
    raise ConfigurationSetupError('Could not find "{}" in the directories: {}'.format(target, ', '.join(search_dirs)))


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
    version_str = re.search(r'\d+\.\d+\.\d+$', filename).group()
    return parse_version(version_str), version_str


def get_selected_core(config_obj=None):
    """
    Figure out which WRF core is selected by the current environmental variables

    The ARW core is considered selected if either EM_CORE or WRF_EM_CORE == '1'. The NMM core is considered selected if
    either NMM_CORE or WRF_NMM_CORE == '1'.

    :param config_obj: the AutoWRFChemConfig object containing the environmental variables. May be omitted, in which
     case the default one is loaded.
    :type config_obj: `AutoWRFChemConfig`

    :return: one of the strings 'arw' or 'nmm' indicating which core is selected
    :rtype: str
    :raises ConfigurationSettingsError: if either both or neither of the cores are selected.
    """
    if config_obj is None:
        config_obj = AutoWRFChemConfig()

    em_core = config_obj[ENVIRONMENT]['EM_CORE'] == '1' or config_obj[ENVIRONMENT]['WRF_EM_CORE'] == '1'
    nmm_core = config_obj[ENVIRONMENT]['NMM_CORE'] == '1' or config_obj[ENVIRONMENT]['WRF_NMM_CORE'] == '1'

    if em_core and nmm_core:
        raise ConfigurationSettingsError('Conflicting settings for the WRF core: both ARW (EM) and NMM selected')
    elif em_core:
        return 'arw'
    elif nmm_core:
        return 'nmm'
    else:
        raise ConfigurationSettingsError('No core (ARW or NMM) selected!')


def get_is_chem(config_obj=None):
    """
    Check if the env. var. config indicates we are building WRF-Chem

    :param config_obj: the AutoWRFChemConfig object containing the environmental variables. May be omitted, in which
     case the default one is loaded.
    :type config_obj: `AutoWRFChemConfig`

    :return: boolean indicating if the WRF_CHEM env. var. is set
    :rtype: bool
    """
    if config_obj is None:
        config_obj = AutoWRFChemConfig()

    if config_obj[ENVIRONMENT]['WRF_CHEM'] == '1':
        return True
    else:
        return False

##########################################
# FUNCTIONS DEALING WITH COMPONENT PATHS #
##########################################

def rel_dir_to_abs(top_dir):
    """
    Make a directory relative to the top automation directory into an absolute path.

    Paths that are already absolute are returned unmodified.

    :param top_dir: the directory to make absolute.
    :type top_dir: str

    :return: the absolute version of top_dir
    :rtype: str
    """
    if not os.path.isabs(top_dir):
        top_dir = os.path.abspath(os.path.join(automation_top_dir, top_dir))

    return top_dir


def make_component_top_dir(component_var, config_obj=None):
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

    component_dir = rel_dir_to_abs(config_obj[AUTOMATION_PATHS][component_var])

    if not os.path.isdir(component_dir):
        raise ComponentMissingError('The directory {} pointed to by config {} does not exist'.format(
            component_dir, component_var
        ))

    return component_dir


def get_wrf_top_dir(config_obj=None):
    return make_component_top_dir(WRF_TOP_DIR, config_obj)


def get_wrf_run_dir(config_obj=None):
    return os.path.join(get_wrf_top_dir(config_obj), 'run')


def get_wps_top_dir(config_obj=None):
    return make_component_top_dir(WPS_TOP_DIR, config_obj)


def get_wps_run_dir(config_obj=None):
    return get_wps_top_dir(config_obj)
