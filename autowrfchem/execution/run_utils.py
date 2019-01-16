from __future__ import print_function, absolute_import, division, unicode_literals

from datetime import datetime as dtime, timedelta as tdel
from glob import glob
import os
import re

from ..configuration import autowrf_classlib as awclib


def is_wrf_run_complete(wrf_dir, wrf_namelist):
    if isinstance(wrf_namelist, str):
        wrf_namelist = awclib.WrfNamelist(wrf_namelist, awclib.Registry.load_standard_registry())
    _, end_date = wrf_namelist.get_time_period()
    n_dom = wrf_namelist.max_domains
    history_intervals = wrf_namelist.get_opt_val_no_sect('history_interval')  # given in minutes

    wrf_date_re = re.compile(r'\d{4}-\d\d-\d\d_\d\d:\d\d:\d\d')
    are_domains_done = [False for d in range(n_dom)]

    for dom in range(1, n_dom+1):
        wrfout_pattern = 'wrfout_d{:02d}*'.format(dom)
        output_files = glob(os.path.join(wrf_dir, wrfout_pattern))
        required_time_interval = tdel(minutes=history_intervals[dom-1])

        for f in output_files:
            wrf_date_str = wrf_date_re.search(f).group()
            wrf_date = dtime.strptime(wrf_date_str, '%Y-%m-%d_%H:%M:%S')
            time_interval = end_date - wrf_date
            if tdel(0) < time_interval < required_time_interval:
                are_domains_done[dom-1] = True
                break

    return all(are_domains_done)
