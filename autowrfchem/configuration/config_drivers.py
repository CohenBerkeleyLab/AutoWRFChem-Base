from __future__ import print_function, absolute_import, division
from collections import OrderedDict
import os

from . import config_utils as cu, ENVIRONMENT
from .. import ui


_preset_fxns = {'get_netcdf_dir()': cu.get_ncdf_dir,
                'get_yacc_exec()': cu.get_yacc_exec,
                'get_flexlib_dir()': cu.get_flexlib_dir}


def setup_envvars(config_obj):
    presets = cu.get_envvar_presets()
    menu_opts = OrderedDict()
    menu_opts['Keep current configuration'] = _keep_config_envvars
    menu_opts['Merge shell environmental variables'] = _merge_environment
    for name, preset in presets.items():
        menu_opts['Preset: {}'.format(name)] = lambda cobj: _set_preset(cobj, preset)

    ui.user_input_menu('How would you like to set the necessary environmental variables?',
                       menu_opts, fxn_args=[config_obj])


def _keep_config_envvars(config_obj):
    if config_obj.read_from_defaults:
        prompt = \
"""The default configuration variables are set.
It is recommended that you choose a preset rather than use the defaults,
as the defaults are only placeholders.
Go back and select a preset?
"""
        if ui.user_input_yn(prompt, default='y'):
            setup_envvars(config_obj)
        else:
            return
    else:
        return


def _merge_environment(config_obj):
    for opt in config_obj.options(ENVIRONMENT):
        env_val = os.getenv(opt)
        if env_val is not None:
            config_obj.set(ENVIRONMENT, opt, env_val)


def _set_preset(config_obj, preset_dict):
    for opt in config_obj.options(ENVIRONMENT):
        preset_val = preset_dict[opt]
        if preset_val.strip().endswith('()'):
            preset_val = _preset_fxns[preset_val]()
        config_obj.set(ENVIRONMENT, opt, preset_val)