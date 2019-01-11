from __future__ import print_function, absolute_import, division, unicode_literals

import os
import shutil

from .. import common_utils
from ..configuration import config_utils


def run_real(config_obj, log_file=None, **_):
    wrf_run_dir = config_utils.get_wrf_run_dir(config_obj)

    # when compiled in parallel, real.exe generates rsl.out.0000 and rsl.error.0000 instead of printing to stdout/stderr
    # need to find a way to figure out if it is compiled in parallel or serial. might be able to read configure.wrf
    common_utils.run_external_mpi('./real.exe', cwd=wrf_run_dir, config_obj=config_obj)

    if log_file is not None:
        shutil.copy2(os.path.join(wrf_run_dir, 'rsl.error.0000'), log_file)
