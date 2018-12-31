import os

from ..configuration import config_utils, autowrf_classlib as awclib
from . import testing_input_dir, testing_namelist_dir


def get_envvar_config():
    env_cfg_file = os.path.join(testing_input_dir, 'autowrfchem_testing.cfg')
    return config_utils.AutoWRFChemConfig.load_config(env_cfg_file)


def get_registry():
    env = get_envvar_config()
    reg_file = os.path.join(testing_input_dir, 'RegistryExamples', 'Registry')
    return awclib.Registry(reg_file, env)


def get_wrf_namelist(with_chem=False):
    reg = get_registry()
    if with_chem:
        namelist_file = os.path.join(testing_namelist_dir, 'namelist.input.chem')
    else:
        namelist_file = os.path.join(testing_namelist_dir, 'namelist.input.nochem')
    return awclib.WrfNamelist(namelist_file, reg)
