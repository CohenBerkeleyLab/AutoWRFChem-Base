ENVIRONMENT = 'ENVIRONMENT'
AUTOMATION = 'AUTOMATION'
WRF_TOP_DIR = 'WRF_TOP_DIR'
WPS_TOP_DIR = 'WPS_TOP_DIR'
MET_TYPE = 'MET_TYPE'


class ConfigurationError(Exception):
    pass


_pretty_n_col = 72
_pgrm_main_check_key = 'auto_check_main'
_pgrm_cfg_key = 'configuration'
_pgrm_clargs_key = 'command_line_args'
_pgrm_warn_to_choose_env = 'default_env_var_warn'