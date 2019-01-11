from __future__ import print_function, absolute_import, division, unicode_literals

from glob import glob
import os
import shutil
import tarfile
from textui import uiutils

from .. import common_utils, preplogs_dir, _pretty_n_col
from ..configuration import AUTOMATION, MET_TYPE, MET_TOP_DIR, config_utils, autowrf_classlib as awclib
from . import PrepInputError
from .list_grib_files import narr, era_interim


class GeogridTableError(PrepInputError):
    """
    Error for no valid geogrid table or table is missing
    """
    pass


class UngribVtableError(PrepInputError):
    """
    Error for no valid ungrib Vtable or table is missing
    """
    pass


def _link_helper(link_target, link_file):
    if os.path.exists(link_file):
        common_utils.backup_file(link_file)
        os.remove(link_file)

    # link_target shouldn't have any path in front. os.symlink should create a symbolic link at dst (the second arg)
    # that points to the first arg, as if you were in `dirname link_file` and did ln -s link_target `basename
    # link_file`
    print('Linking {} -> {}'.format(link_file, link_target))
    os.symlink(link_target, link_file)


def _link_geogrid_table(config_obj, wps_dir):
    core = config_utils.get_selected_core(config_obj)
    is_chem = config_utils.get_is_chem(config_obj)

    if is_chem:
        if core == 'arw':
            gg_table_suffix = 'ARW_CHEM'
        else:
            raise GeogridTableError('The {} core does not have a GEOGRID table with chemistry'.format(core))
    else:
        gg_table_suffix = core.upper()

    geogrid_dir = os.path.join(wps_dir, 'geogrid')
    gg_table_file = 'GEOGRID.TBL.{}'.format(gg_table_suffix)

    # make sure the required GEOGRID table exists
    if not os.path.isfile(os.path.join(geogrid_dir, gg_table_file)):
        raise GeogridTableError('Required geogrid table ({}) does not exist'.format(gg_table_file))

    gg_table_link = os.path.join(geogrid_dir, 'GEOGRID.TBL')
    _link_helper(gg_table_file, gg_table_link)


def _link_ungrib_table(config_obj, wps_dir):
    met_type = config_obj[AUTOMATION][MET_TYPE]
    met = config_utils.get_met_presets(met_type)

    # make sure that the required Vtable exists
    target_vtable = os.path.join('ungrib', 'Variable_Tables', 'Vtable.{}'.format(met_type))
    if not os.path.isfile(os.path.join(wps_dir, target_vtable)):
        raise UngribVtableError('Required ungrib Vtable ({vtable}) for met "{met}" does not exist'.format(
            vtable=target_vtable, met=met
        ))

    _link_helper(target_vtable, os.path.join(wps_dir, 'Vtable'))


def _log_filename_helper(wps_dir, step):
    wps_basedir = os.path.basename(wps_dir.rstrip(os.pathsep))
    return os.path.join(preplogs_dir, '{}_{}.log'.format(wps_basedir, step))


def _run_geogrid(config_obj, wps_dir):
    _link_geogrid_table(config_obj, wps_dir)

    geogrid_log_file = _log_filename_helper(wps_dir, 'geogrid')
    with open(geogrid_log_file, 'w') as logfile:
        common_utils.run_external(['./geogrid.exe'], cwd=wps_dir, logfile_handle=logfile, config_obj=config_obj)


def _list_met_files(met_type, met_dir, start_date, end_date):
    met_type = met_type.lower()
    if met_type == 'narr':
        return narr.get_required_met_files(met_dir, start_date, end_date)
    elif met_type.startswith('era-interim'):
        _, level_type = met_type.split('.')
        return era_interim.get_required_met_files(met_dir, start_date, end_date, level_type)
    else:
        raise ValueError('met_type {} not recognized'.format(met_type))


def _untar_grib_files(met_files, wps_dir):
    untar_dir = os.path.join(wps_dir, "MetTARs")
    if os.path.exists(untar_dir):
        os.remove(untar_dir)
    os.mkdir(untar_dir)

    for f in met_files:
        shutil.unpack_archive(f, untar_dir)

    new_met_files = glob(os.path.join(untar_dir, '*'))

    with open(os.path.join(untar_dir, 'A_NOTICE.txt'), 'w') as fobj:
        msg = 'This directory is created exclusively to untar met files for WPS and will be deleted without warning ' \
              'by AutoWRFChem. Do NOT put anything important here!'
        fobj.write(uiutils.hard_wrap(msg, _pretty_n_col))

    return new_met_files


def _link_grib_files(config_obj, wps_dir):
    nlc = awclib.NamelistContainer.load_namelists()
    start_date, end_date = nlc.get_time_period()
    met_type = config_obj[AUTOMATION][MET_TYPE]
    met_dir = config_obj[AUTOMATION][MET_TOP_DIR]
    if not os.path.isdir(met_dir):
        raise config_utils.ConfigurationError('MET_TOP_DIR is not a valid directory')

    met_files, req_untarring = _list_met_files(met_type, met_dir, start_date, end_date)
    if req_untarring:
        met_files = _untar_grib_files(met_files, wps_dir)

    # remove old links
    common_utils.rmfiles(os.path.join(wps_dir, 'GRIBFILE*'))

    common_utils.run_external(['./link_grib.csh'] + met_files, cwd=wps_dir, config_obj=config_obj)


def _run_ungrib(config_obj, wps_dir):
    _link_ungrib_table(config_obj, wps_dir)

    _link_grib_files(config_obj, wps_dir)

    ungrib_log_file = _log_filename_helper(wps_dir, 'ungrib')
    with open(ungrib_log_file, 'w') as logfile:
        common_utils.run_external(['./ungrib.exe'], cwd=wps_dir, logfile_handle=logfile, config_obj=config_obj)


def _run_metgrid(config_obj, wps_dir):
    common_utils.rmfiles(os.path.join(wps_dir, 'met_em*'))
    metgrid_log_file = _log_filename_helper(wps_dir, 'metgrid')
    with open(metgrid_log_file, 'w') as logfile:
        common_utils.run_external(['./metgrid.exe'], cwd=wps_dir, logfile_handle=logfile, config_obj=config_obj)


def _link_to_wrf(config_obj, wps_dir):
    wrf_dir = config_utils.get_wrf_run_dir(config_obj)
    common_utils.rmfiles(os.path.join(wrf_dir, 'met_em*'))

    final_met_files = glob(os.path.join(wps_dir, 'met_em*'))

    for f in final_met_files:
        fbase = os.path.basename(f)
        fabs = os.path.abspath(f)
        link_file = os.path.join(wrf_dir, fbase)
        if os.path.exists(link_file):
            # deleting only the files we need to recreate should make implementing split WPS easier since we don't have
            # to worry about different WPS instances removing each others' links
            os.remove(link_file)
        os.symlink(fabs, link_file)


def prepwps(config_obj, finish=False, parallel=None):
    if finish:
        raise NotImplementedError('prepwps not yet taught how to figure out if it needed to run with --finish')

    if parallel is not None:
        raise NotImplementedError('WPS-Split not implemented yet')

    wps_dir = config_utils.get_wps_run_dir(config_obj)

    _run_geogrid(config_obj, wps_dir)
    _run_ungrib(config_obj, wps_dir)
    _run_metgrid(config_obj, wps_dir)
    _link_to_wrf(config_obj, wps_dir)
