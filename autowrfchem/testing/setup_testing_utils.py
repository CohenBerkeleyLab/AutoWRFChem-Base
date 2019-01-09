import os

from ..configuration import config_utils, autowrf_classlib as awclib
from . import testing_input_dir, testing_namelist_dir


def _wrf_nl(with_chem=False):
    if with_chem:
        return os.path.join(testing_namelist_dir, 'namelist.input.chem')
    else:
        return os.path.join(testing_namelist_dir, 'namelist.input.nochem')


def _wps_nl():
    return os.path.join(testing_namelist_dir, 'namelist.wps')


def get_envvar_config():
    env_cfg_file = os.path.join(testing_input_dir, 'autowrfchem_testing.cfg')
    return config_utils.AutoWRFChemConfig(env_cfg_file)


def get_registry():
    env = get_envvar_config()
    reg_file = os.path.join(testing_input_dir, 'RegistryExamples', 'Registry')
    return awclib.Registry(reg_file, env)


def get_wrf_namelist(with_chem=False):
    reg = get_registry()
    return awclib.WrfNamelist(_wrf_nl(with_chem), reg)


def get_namelist_container(with_chem=False):
    return awclib.NamelistContainer(wrffile=_wrf_nl(with_chem), wpsfile=_wps_nl(), registry=get_registry())
