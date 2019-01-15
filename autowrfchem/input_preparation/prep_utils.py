from __future__ import print_function, absolute_import, division, unicode_literals

import os
import shutil

from .. import common_utils
from ..configuration import config_utils, autowrf_classlib as awclib, RUNTIME, REINIT_FREQ, REINIT_RUN_TIME, DO_REINIT


def run_real(config_obj, log_file=None, wrf_run_dir=None, **_):
    if wrf_run_dir is None:
        wrf_run_dir = config_utils.get_wrf_run_dir(config_obj)

    # when compiled in parallel, real.exe generates rsl.out.0000 and rsl.error.0000 instead of printing to stdout/stderr
    # need to find a way to figure out if it is compiled in parallel or serial. might be able to read configure.wrf
    common_utils.run_external_mpi('./real.exe', cwd=wrf_run_dir, config_obj=config_obj)

    if log_file is not None:
        shutil.copy2(os.path.join(wrf_run_dir, 'rsl.error.0000'), log_file)


def run_real_with_reinit(config_obj, log_file=None, **_):
    if not config_obj[RUNTIME].as_bool(DO_REINIT):
        return run_real(config_obj, log_file=log_file)

    # If we get here, then we must be running with reinitialization. This means that we have to create wrfinput and
    # wrfbdy files for multiple overlapping time periods.
    wrf_run_dir = config_utils.get_wrf_run_dir(config_obj)

    reinit_freq = config_utils.get_reinit_freq(config_obj)
    reinit_run_time = config_utils.get_reinit_runtime(config_obj)
    nlc = awclib.NamelistContainer.load_namelists()
    model_start, model_end = nlc.get_time_period()

    n_dom = nlc.wrf_namelist.max_domains

    for reinit_dir, reinit_start_time in common_utils._iter_reinit_dirs(wrf_run_dir, model_start, model_end, reinit_freq):
        print('Preparing input files for {}'.format(reinit_start_time))
        nlc.set_run_time(reinit_run_time, reinit_start_time)
        nlc.wrf_namelist.write_namelist(os.path.join(wrf_run_dir, 'namelist.input'), is_temporary=True)
        # todo: make log files for each run of real.exe
        run_real(config_obj, wrf_run_dir=wrf_run_dir)

        common_utils._prep_reinit_dir(reinit_dir)
        shutil.move(os.path.join(wrf_run_dir, 'wrfbdy_d01'), reinit_dir)
        for dom in range(1, n_dom+1):
            wrfinput = 'wrfinput_d{:02d}'.format(dom)
            shutil.move(os.path.join(wrf_run_dir, wrfinput), reinit_dir)
