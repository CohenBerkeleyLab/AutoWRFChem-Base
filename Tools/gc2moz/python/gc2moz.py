from __future__ import print_function
import argparse
from bpch import bpch
import datetime as dt
import netCDF4 as ncdf
import numpy as np
import os
import re
import sys
import pdb

# Local modules
import gcCH4bins

__author__ = 'Josh Laughner'
__debug_level__ = 2

######################################
##### GEOS-Chem Static variables #####
######################################

fill_val = 0.0;

gclon = np.arange(-180.0, 180.0, 2.5)
gclat = np.append(np.arange(-90.0, 90.0, 2.0), 89.5)
gclat[0] = -89.5

# These are given at
# http://wiki.seas.harvard.edu/geos-chem/index.php/GEOS-Chem_vertical_grids#Vertical_grids_for_GEOS-5.2C_GEOS-FP.2C_MERRA.2C_and_MERRA-2
# but need to be flipped b/c GEOS-Chem puts index 1 at the surface, but GMAO (and MOZART) put it at the top of the
# atmosphere

# A is given in hPa at the above length, we convert to kPa essentially to be consistent with how MOZART defines its A.
# In MOZART, both A and B are considered dimensionless, but A is multiplied by P0 = 100000 Pa, so we can kind of think
# of A as being either in kPa or unitless.
gc_hya = np.flipud(0.001*np.array([0.000000e+00, 4.804826e-02, 6.593752e+00, 1.313480e+01, 1.961311e+01, 2.609201e+01,
                             3.257081e+01, 3.898201e+01, 4.533901e+01, 5.169611e+01, 5.805321e+01, 6.436264e+01,
                             7.062198e+01, 7.883422e+01, 8.909992e+01, 9.936521e+01, 1.091817e+02, 1.189586e+02,
                             1.286959e+02, 1.429100e+02, 1.562600e+02, 1.696090e+02, 1.816190e+02, 1.930970e+02,
                             2.032590e+02, 2.121500e+02, 2.187760e+02, 2.238980e+02, 2.243630e+02, 2.168650e+02,
                             2.011920e+02, 1.769300e+02, 1.503930e+02, 1.278370e+02, 1.086630e+02, 9.236572e+01,
                             7.851231e+01, 5.638791e+01, 4.017541e+01, 2.836781e+01, 1.979160e+01, 9.292942e+00,
                             4.076571e+00, 1.650790e+00, 6.167791e-01, 2.113490e-01, 6.600001e-02, 1.000000e-02]))
gc_hyb = np.flipud(np.array([1.000000e+00, 9.849520e-01, 9.634060e-01, 9.418650e-01, 9.203870e-01, 8.989080e-01,
                             8.774290e-01, 8.560180e-01, 8.346609e-01, 8.133039e-01, 7.919469e-01, 7.706375e-01,
                             7.493782e-01, 7.211660e-01, 6.858999e-01, 6.506349e-01, 6.158184e-01, 5.810415e-01,
                             5.463042e-01, 4.945902e-01, 4.437402e-01, 3.928911e-01, 3.433811e-01, 2.944031e-01,
                             2.467411e-01, 2.003501e-01, 1.562241e-01, 1.136021e-01, 6.372006e-02, 2.801004e-02,
                             6.960025e-03, 8.175413e-09, 0.000000e+00, 0.000000e+00, 0.000000e+00, 0.000000e+00,
                             0.000000e+00, 0.000000e+00, 0.000000e+00, 0.000000e+00, 0.000000e+00, 0.000000e+00,
                             0.000000e+00, 0.000000e+00, 0.000000e+00, 0.000000e+00, 0.000000e+00, 0.000000e+00]))
gc_hya_mid = 0.5*(gc_hya[:-1] + gc_hya[1:])
gc_hyb_mid = 0.5*(gc_hyb[:-1] + gc_hyb[1:])

gc_base_date = dt.datetime(1985, 1, 1)


def shell_error(msg, exitcode=1):
    print(msg, file=sys.stderr)
    exit(exitcode)


def shell_msg(msg):
    print(msg, file=sys.stderr)


def format_error(lineno, spcfile, msg):
    shell_error('Format error, line {0} in species map file ({1}): {2}'.format(lineno, spcfile, msg))


def bpch_error(bpch_filename, varname, req_for):
    if isinstance(req_for, str):
        shell_error('Variable {0} not found in {1} (requested by {2})'.format(varname, bpch_filename, req_for))
    elif isinstance(req_for, Mapping):
        err_str = ''
        shell_error('Variable {0} not found in {1} (requested by {2})'.format(varname, bpch_filename, err_str))


def flip_dim(M, dim):
    if not isinstance(M, np.ndarray):
        raise TypeError('M must be an instance of np.ndarray')
    elif not isinstance(dim, int):
        raise TypeError('dim must be an integer')
    elif dim < 0 or dim > M.ndim-1:
        raise IndexError('dim must be in the range 0 to M.ndim - 1 ({0} in this case)'.format(M.ndim-1))

    pvec = np.delete(np.arange(0, M.ndim), dim)
    pvec = np.insert(pvec, 0, dim)
    M = M.transpose(pvec)
    M = M[::-1]
    M = M.transpose(np.argsort(pvec))
    return M


def mozdate(date_in):
    # MOZART defines time two different ways:
    #  1) With the date as a 8-digit integer (yyyymmdd) and then number of seconds since midnight
    #  2) As days since 0000-01-01 + seconds since midnight.
    # Unfortunately, Python's datetime module does not like year 0. So we need to adjust by using year 1 then adding
    # 366 days (because year 0 is technically a leap year - if it exists).

    date_int = 10000 * date_in.year + 100 * date_in.month + date_in.day
    date_secs = date_in.hour * 3600 + date_in.minute * 60 + date_in.second

    timedel = date_in - dt.datetime(1,1,1)
    return date_int, date_secs, timedel.days+366, timedel.seconds


def mozdate_array(dates_in):
    date_ints = []
    date_secs = []
    days_since = []
    since_secs = []
    for d in dates_in:
        dint, dsec, dsince, ssince = mozdate(d)
        date_ints.append(dint)
        date_secs.append(dsec)
        days_since.append(dsince)
        since_secs.append(ssince)

    return np.array(date_ints), np.array(date_secs), np.array(days_since), np.array(since_secs)


class Mapping(object):
    gc_category = 'IJ-AVG-$_'
    moz_suffix = '_VMR_inst'

    def __init__(self, moz_spc, *gc_spcs):
        self.moz = moz_spc

        # Parse the variable argument, which should be each GEOS-Chem species, possibly preceeded by a multiplicative
        # factor, e.g. in ALD, 0.5, ALK4 the 0.5 is associated with ALK4 and means that whatever the mozart species
        # is will be equal to ALD + 0.5*ALK
        self.gc = {}
        this_factor = 1.0
        for arg in gc_spcs:
            if isinstance(arg, float):
                this_factor *= arg  # allow for multiple factors to be given for a single species
            elif isinstance(arg, str):
                self.gc[arg] = this_factor
                this_factor = 1.0
            else:
                raise TypeError('Position arguments gc_spcs must be either floats or strings')

    def return_mapping(self, gcfile):
        if not isinstance(gcfile, bpch):
            raise TypeError('gcfile must be an instance of bpch.bpch')

        first_var = True
        for var, factor in self.gc.iteritems():
            gc_fullname = self.gc_category + var
            if first_var:
                moz_val = gcfile.variables[gc_fullname] * factor
                first_var = False
            else:
                moz_val += gcfile.variables[gc_fullname] * factor

        return moz_val

    def moz_fullname(self):
        return self.moz + self.moz_suffix


class FilesAndTimes(object):
    def __init__(self, bfiles):
        if not isinstance(bfiles, (list, tuple)):
            raise TypeError('bfiles must be a list or tuple of strings')
        else:
            for f in bfiles:
                if not isinstance(f, str):
                    raise TypeError('bfiles must be a list or tuple of strings')

        self.files, self.datetimes = self.populate_times(bfiles)

    def populate_times(self, bfiles):
        tmp_name_list = []
        tmp_date_list = []

        for filename in bfiles:
            f = bpch(filename)
            times = f.variables['time']
            for t in times:
                tmp_date_list.append(gc_base_date + dt.timedelta(hours=t))
                tmp_name_list.append(filename)

        date_list = sorted(tmp_date_list)
        name_list = []
        for d in date_list:
            i = tmp_date_list.index(d)
            name_list.append(tmp_name_list[i])

        return name_list, date_list

    def iter_times(self):
        for i in range(len(self.datetimes)):
            yield self.datetimes[i], self.files[i]

    def ntimes(self):
        return len(self.datetimes)

    def unique_files(self):
        unique = []
        for fname in self.files:
            if fname not in unique:
                unique.append(fname)
        return unique


def get_args():
    parser = argparse.ArgumentParser(description='Convert a GEOS-Chem ND49 binary punch file to a netCDF file that MOZBC can use',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     epilog='This method is intended to read ND49 diagnostic files because generally\n'
                                            'one needs output multiple times per day, rather than one daily average,\n'
                                            'to set initial and boundary conditions for WRF with any sort of accuracy.\n'
                                            'Those ND49 files must contain whatever tracers are referenced in the\n'
                                            'species input file, plus the PEDGE-$_PSURF diagnostic.')
    parser.add_argument('-o', '--output-file', default='geosBC.nc', help='the name (and path if desired) of the output file')
    parser.add_argument('bpchfiles', nargs='+', help='All the ND49 bpch files to draw data from')

    args = parser.parse_args()

    argout = {'bpchfiles': args.bpchfiles, 'outfile': output_file}
    return argout


def parse_species_map(species_file):
    mappings = []
    in_mapping = False
    with open(species_file, 'r') as spcf:
        file_line = 0
        for line in spcf:
            file_line += 1

            if not in_mapping:
                if 'BEGIN MAPPING' in line:
                    in_mapping = True
            else:
                if 'END MAPPING' in line:
                    in_mapping = False
                else:
                    if '->' not in line:
                        format_error(file_line, species_file, 'does not contain "->"')

                    moz_spc, gc_spc = line.split('->')
                    moz_spc = moz_spc.strip()
                    gc_spc = gc_spc.strip()

                    if re.search('\W', moz_spc):
                        format_error(file_line, species_file,
                                     'mozart species name must only include alphanumeric characters\n'
                                     'and there must only be one mozart species per line')

                    gc_str_list = [x.strip() for x in gc_spc.split('+')]
                    gc_list = []

                    for gc_el in gc_str_list:
                        gc_spc = [x.strip() for x in gc_el.split('*')]
                        gc_spc_name = gc_spc.pop(
                            -1)  # assume that the name is the last element, as it should be factor * name
                        gc_factor = 1.0
                        for fac in gc_spc:
                            try:
                                fac_float = float(fac)
                            except ValueError:
                                format_error(file_line, species_file,
                                             'could not convert {0} to a float'.format(fac_float))
                            gc_factor *= fac_float

                        gc_list.append(gc_factor)
                        gc_list.append(gc_spc_name)

                    mappings.append(Mapping(moz_spc, *gc_list))

    return mappings


def write_netcdf(outfile, map_file, bpchfiles, overwrite=True):
    ncfile = ncdf.Dataset(outfile, 'w', clobber=overwrite, format='NETCDF3_CLASSIC')

    if __debug_level__ > 0:
        shell_msg('Reading times from BPCH files')
    file_times = FilesAndTimes(bpchfiles)

    if __debug_level__ > 0:
        shell_msg('Writing dimensions')
    define_dimensions(ncfile, file_times)

    if __debug_level__ > 0:
        shell_msg('Reading species mapping')
    mappings = parse_species_map(map_file)

    if __debug_level__ > 0:
        shell_msg('Writing chemical species')
    write_mappings(ncfile, mappings, file_times)

    if __debug_level__ > 0:
        shell_msg('Adding CH4 from latitudinal bins')
    add_methane(ncfile)

    ncfile.close()


def define_dimensions(ncfile, filetimes):
    """
    Defines all relevant dimensions in the netCDF file and writes any time invariant variables used to describe those
    dimensions.
    :param ncfile: an instance of netCDF4.Dataset that is the file to be written to
    :param filetimes: a FilesAndTimes instance listing all the BPCH files
    :return:
    """
    if not isinstance(ncfile, ncdf.Dataset):
        raise TypeError('ncfile must be an instance of netCDF4.Dataset')

    if not isinstance(filetimes, FilesAndTimes):
        raise TypeError('filetimes must be an instance of FilesAndTimes')

    bfile = bpch(filetimes.files[0])

    lon = bfile.variables['longitude']
    lat = bfile.variables['latitude']
    psurf = bfile.variables['PEDGE-$_PSURF']

    # Write the dimensions
    ncfile.createDimension('lon', size=len(lon))
    ncfile.createDimension('lat', size=len(lat))
    ncfile.createDimension('lev', size=len(gc_hya_mid))
    ncfile.createDimension('ilev', size=len(gc_hya))
    ncfile.createDimension('time', size=0)  # unlimited

    # and the variables that define their values
    ncfile.createVariable('lon', np.float32, dimensions=('lon'))
    ncfile.variables['lon'][:] = lon
    ncfile.variables['lon'].long_name = 'longitude'
    ncfile.variables['lon'].units = 'degrees_east'

    ncfile.createVariable('lat', np.float32, dimensions=('lat'))
    ncfile.variables['lat'][:] = lat
    ncfile.variables['lat'].long_name = 'latitude'
    ncfile.variables['lat'].units = 'degrees_north'

    # Time dimensions
    ncfile.createVariable('time', np.float64, dimensions=('time'))
    ncfile.variables['time'].long_name = 'simulation_time'
    ncfile.variables['time'].units = 'days since 0000-01-01'
    ncfile.variables['time'].calendar = 'gregorian'

    ncfile.createVariable('secs', np.int32, dimensions=('time'))
    ncfile.variables['secs'].long_name = 'seconds to complete elapsed days'
    ncfile.variables['secs'].units = 's'

    ncfile.createVariable('date', np.int32, dimensions=('time'))
    ncfile.variables['date'].long_name = 'current date as 8 digit integer (YYYYMMDD)'

    ncfile.createVariable('datesec', np.int32, dimensions=('time'))
    ncfile.variables['datesec'].long_name = 'seconds to complete current date'
    ncfile.variables['datesec'].units = 's'

    date_int, date_sec, days_since, sec_since = mozdate_array(filetimes.datetimes)
    ncfile.variables['date'][:] = date_int
    ncfile.variables['datesec'][:] = date_sec
    ncfile.variables['time'][:] = days_since
    ncfile.variables['secs'][:] = sec_since

    # GEOS-Chem uses the hybrid sigma-eta coordinate system
    # (http://wiki.seas.harvard.edu/geos-chem/index.php/GEOS-Chem_vertical_grids#Vertical_grids_for_GEOS-5.2C_GEOS-FP.2C_MERRA.2C_and_MERRA-2)
    # and we usually run on the 47-layer reduced vertical grid. The A and B coefficients are given at the above link
    # and the formula for converting to actual pressure levels is given at
    # http://wiki.seas.harvard.edu/geos-chem/index.php/GEOS-Chem_vertical_grids#Hybrid_grid_definition
    # and is Pedge(I,J,L) = Ap(L) + [ Bp(L) * Psurface(I,J) ], Pcenter(I,J,L) = [ Pedge(I,J,L) + Pedge(I,J,L+1) ]/2
    #
    # In MOZBC, pressures are computed as ps_mozi(I,J) * hybm + ps0 * hyam; where hybm and hyam are vectors (that are
    # the same for every column) of the A and B corefficients at level midpoints, ps_mozi is the MOZART surface pressure
    # interpolated to the WRF grid, and ps0 is just a constant, always 100000 Pa. The GEOS-Chem B parameter and the
    # MOZART B parameter are both unitless. The GC and MOZART A parameters just differ by a scaling factor, A_moz * P0 =
    # A_gc * 100 (GC A is in hPa, moz P0 has units of Pa).
    #
    # MOZART uses the GMAO standard that the first index in the vertical dimension is the top of the
    # atmosphere, whereas GEOS-Chem says the first index is the surface.

    ncfile.createVariable('lev', np.float32, dimensions='lev')
    ncfile.variables['lev'][:] = 1000*(gc_hya_mid + gc_hyb_mid)
    ncfile.variables['lev'].long_name = 'hybrid level at layer midpoints (1000*(A+B))'
    ncfile.variables['lev'].units = 'hybrid_sigma_pressure'
    ncfile.variables['lev'].positive = 'down'
    ncfile.variables['lev'].A_var = 'hyam'
    ncfile.variables['lev'].B_var = 'hybm'
    ncfile.variables['lev'].P0_var = 'P0'
    ncfile.variables['lev'].PS_var = 'PS'
    ncfile.variables['lev'].bounds = 'ilev'

    ncfile.createVariable('ilev', np.float32, dimensions='ilev')
    ncfile.variables['ilev'][:] = 1000*(gc_hya + gc_hyb)
    ncfile.variables['ilev'].long_name = 'hybrid level at layer interface (1000*(A+B))'
    ncfile.variables['ilev'].units = 'hybrid_sigma_pressure'
    ncfile.variables['ilev'].positive = 'down'
    ncfile.variables['ilev'].A_var = 'hyai'
    ncfile.variables['ilev'].B_var = 'hybi'
    ncfile.variables['ilev'].P0_var = 'P0'
    ncfile.variables['ilev'].PS_var = 'PS'

    ncfile.createVariable('hyam', np.float32, dimensions='lev')
    ncfile.variables['hyam'][:] = gc_hya_mid
    ncfile.variables['hyam'].long_name = 'hybrid A coefficient at layer midpoints'

    ncfile.createVariable('hybm', np.float32, dimensions='lev')
    ncfile.variables['hybm'][:] = gc_hyb_mid
    ncfile.variables['hybm'].long_name = 'hybrid B coefficient at layer midpoints'

    ncfile.createVariable('hyai', np.float32, dimensions='ilev')
    ncfile.variables['hyai'][:] = gc_hya
    ncfile.variables['hyai'].long_name = 'hybrid A coefficient at layer interfaces'

    ncfile.createVariable('hybi', np.float32, dimensions='ilev')
    ncfile.variables['hybi'][:] = gc_hyb
    ncfile.variables['hybi'].long_name = 'hybrid B coefficient at layer interfaces'

    ncfile.createVariable('P0', np.float32) # scalar
    ncfile.variables['P0'][:] = 1e5
    ncfile.variables['P0'].long_name = 'reference pressure'
    ncfile.variables['P0'].units = 'Pa'

    bfile.close()

    # Surface pressure has a time component, so first we need to concatenate all the values
    ps_list = []
    for fname in filetimes.unique_files():
        b = bpch(fname)
        ps_list.append(b.variables['PEDGE-$_PSURF'][:,0,:,:].squeeze()*100) # get surface only and convert from hPa to Pa
        b.close()

    ncfile.createVariable('PS', np.float32, dimensions=('time', 'lat', 'lon'))
    ncfile.variables['PS'][:] = np.concatenate(ps_list, 0)
    ncfile.variables['PS'].units = 'Pa'


def write_mappings(ncfile, mappings, filetimes):
    nlev = ncfile.dimensions['lev'].size

    for m in mappings:
        val = []
        for fname in filetimes.unique_files():
            b = bpch(fname)
            this_val = m.return_mapping(b)
            sz = list(this_val.shape)
            n_to_add = nlev - sz[1]
            if n_to_add > 0:
                sz[1] = n_to_add
                padding = np.empty(sz)
                padding.fill(fill_val)
                this_val = np.concatenate([this_val, padding], 1)
            val.append(flip_dim(this_val, 1))  # remember, GEOS-Chem defines z=1 as surface; MOZART says that's TOA
            b.close()

        ncfile.createVariable(m.moz_fullname(), np.float32, dimensions=('time','lev','lat','lon'))
        ncfile.variables[m.moz_fullname()][:] = np.concatenate(val, 0)
        ncfile.variables[m.moz_fullname()].units = 'VMR'


def add_methane(ncfile):
    # Add methane based on the GEOS-Chem methane bins.
    # For each time, add the year-specific concentrations. This will cause a slight discontinuity at the end of each
    # year, but the percent change is small and I believe this is how GEOS-Chem does it (though that's based off of a
    # very quick examination of the code). Also, this really should decrease once you get into the stratosphere, but
    # generally WRF-Chem does not simulate the stratosphere (at least as I've used it) and I think GEOS-Chem sets the
    # CH4 concentration to be the same in all levels.

    years = ncfile.variables['date'][:]/10000
    lat = ncfile.variables['lat'][:]

    # Find a chemistry variable to get the shape of
    for k in ncfile.variables.keys():
        if Mapping.moz_suffix in k:
            chem_key = k
            break

    ch4 = np.zeros_like(ncfile.variables[chem_key][:])

    for i in range(len(years)):
        ch4_bins = gcCH4bins.get_global_ch4(years[i])

        xx = (lat >= gcCH4bins.north_lats[0])
        ch4[i, :, xx, :] = ch4_bins['north']

        xx = (lat >= gcCH4bins.north_trop_lats[0]) & (lat < gcCH4bins.north_trop_lats[1])
        ch4[i, :, xx, :] = ch4_bins['north_trop']

        xx = (lat >= gcCH4bins.south_trop_lats[0]) & (lat < gcCH4bins.south_trop_lats[1])
        ch4[i, :, xx, :] = ch4_bins['south_trop']

        xx =  (lat < gcCH4bins.south_lats[1])
        ch4[i, :, xx, :] = ch4_bins['south']

    ch4_varname = 'CH4' + Mapping.moz_suffix
    ncfile.createVariable(ch4_varname, np.float32, dimensions=('time','lev','lat','lon'))
    ncfile.variables[ch4_varname][:] = ch4
    ncfile.variables[ch4_varname].units = 'VMR'


def main():
    args = get_args()
    print(args['outfile'])


if __name__ == '__main__':
    main()
