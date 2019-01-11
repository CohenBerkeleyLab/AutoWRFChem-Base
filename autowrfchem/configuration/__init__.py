ENVIRONMENT = 'ENVIRONMENT'

AUTOMATION_PATHS = 'AUTOMATION_PATHS'
WRF_TOP_DIR = 'WRF_TOP_DIR'
WPS_TOP_DIR = 'WPS_TOP_DIR'

AUTOMATION = 'AUTOMATION'
MET_TYPE = 'MET_TYPE'
MET_TOP_DIR = 'MET_TOP_DIR'
TARGET = 'WRF_TARGET'
MPI_CMD = 'MPI_CMD'

_pgrm_main_check_key = 'auto_check_main'
_pgrm_cfg_key = 'configuration'
_pgrm_clargs_key = 'command_line_args'
_pgrm_warn_to_choose_env = 'default_env_var_warn'
_pgrm_nl_key = 'namelists'


class ConfigurationError(Exception):
    pass


