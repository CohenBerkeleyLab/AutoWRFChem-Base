import os

from ... import common_utils
from .. import MetFilesMissingError

_era_grib_pattern = 'e5.oper.an.{levels}.{variable}.regn320{scuv}.{start}_{end}.grb'


def _format_era_filename(levels, variable, start, end):
    if variable.endswith('_u') or variable.endswith('_v') and levels != 'sfc':
        scuv = 'uv'
    else:
        scuv = 'sc'

    return _era_grib_pattern.format(levels=levels, variable=variable, scuv=scuv, start=start, end=end)


def _make_era_3d_list(start_date, end_date, level_type):
    vars_3d = ('128_060_pv', '128_075_crwc', '128_076_cswc', '128_129_z', '128_130_t', '128_131_u', '128_132_v',
               '128_133_q', '128_135_w', '128_138_vo', '128_155_d', '128_157_r', '128_203_o3', '128_246_clwc',
               '128_247_ciwc', '128_248_cc')

    files = []
    for var in vars_3d:
        for date in common_utils.iter_dates(start_date, end_date):
            dstr1 = date.strftime('%Y%m%d00')
            dstr2 = date.strftime('%Y%m%d23')
            files.append(_format_era_filename(level_type, var, dstr1, dstr2))

    return files


def _make_era_surface_list(start_date, end_date):
    vars_sfc = ('128_015_aluvp', '128_016_aluvd', '128_017_alnip', '128_018_alnid', '128_031_ci', '128_032_asn',
                '128_033_rsn', '128_034_sstk', '128_035_istl1', '128_036_istl2', '128_037_istl3', '128_038_istl4',
                '128_039_swvl1', '128_040_swvl2', '128_041_swvl3', '128_042_swvl4', '128_059_cape', '128_066_lailv',
                '128_067_laihv', '128_078_tclw', '128_079_tciw', '128_134_sp', '128_136_tcw', '128_137_tcwv',
                '128_139_stl1', '128_141_sd', '128_148_chnk', '128_151_msl', '128_159_blh', '128_164_tcc',
                '128_165_10u', '128_166_10v', '128_167_2t', '128_168_2d', '128_170_stl2', '128_183_stl3', '128_186_lcc',
                '128_187_mcc', '128_188_hcc', '128_198_src', '128_206_tco3', '128_229_iews', '128_230_inss', '128_231_ishf',
                '128_232_ie', '128_235_skt', '128_236_stl4', '128_238_tsn', '128_243_fal', '128_244_fsr',
                '128_245_flsr', '228_008_lmlt', '228_009_lmld', '228_010_lblt', '228_011_ltlt', '228_012_lshf',
                '228_013_lict', '228_014_licd', '228_089_tcrw', '228_090_tcsw', '228_131_u10n', '228_132_v10n',
                '228_246_100u', '228_247_100v')

    files = []
    for var in vars_sfc:
        curr_date = start_date
        while curr_date <= end_date:
            dstr1 = common_utils.som_date(curr_date).strftime('%Y%m%d00')
            dstr2 = common_utils.eom_date(curr_date).strftime('%Y%m%d23')
            files.append(_format_era_filename('sfc', var, dstr1, dstr2))

            new_month = curr_date.month + 1 if curr_date.month < 12 else 1
            curr_date = curr_date.replace(month=new_month)

    return files


def _make_era_grib_list(start_date, end_date, level_type):
    return _make_era_3d_list(start_date, end_date, level_type) + _make_era_surface_list(start_date, end_date)


def get_required_met_files(met_dir, start_date, end_date, level_type='pl'):
    met_files = _make_era_grib_list(start_date, end_date, level_type)
    req_untar = False

    met_files = [os.path.join(met_dir, f) for f in met_files]

    # TODO: here's where I'd make the function smarter about file hierarchies
    missing_files = [f for f in met_files if not os.path.isfile(f)]
    n_missing_files = len(missing_files)
    if n_missing_files > 0:
        raise MetFilesMissingError('{n} met files missing:\n  * {files}'.format(
            n=n_missing_files, files='\n  * '.join(missing_files)
        ))
    else:
        return met_files, req_untar
