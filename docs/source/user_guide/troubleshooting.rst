Troubleshooting
===============

.. _TroubleEnvVar:

Environmental variables
-----------------------

Trouble setting NETCDF
**********************

**Why is the NETCDF variable necessary?** WRF relies on the netCDF library to read and write its input and output files.
During compilation, WRF needs to know where that library is so that it can include the code from the library in its own
executable. It's important to note that the netCDF library itself is written in C, and has a Fortran interface. WRF
needs both parts, it uses the Fortran interface to talk to the C core that does the actual reading/writing.

**What does AutoWRFChem do to try and find it?** When you select a set of present environmental variables, AutoWRFChem
tries several things to find the netCDF library:

1. *Looks for any :term:`environmental variable` with "NETCDF" in its name.* Sometimes computing clusters will define
   something like this for you when you load the netCDF libraries. In this case, all AutoWRFChem has to do is point the
   ``NETCDF`` variable that WRF expects to that path.
2. *Tries to run the nc-config and nf-config programs.* These are programs installed with the libraries that provide
   information about how the libraries are configured, including where they are installed. AutoWRFChem will use these
   to try to find out where the libraries are installed, and, if successful, use that path.

**AutoWRFChem is listing a lot of NETCDF versions/My compute cluster has more than one version of the library installed. Which one do I choose?**
Generally, pick the highest version one *compiled with the same version of the compiler you will use to compile WRF*.
Trying to mix version of libraries compiled with different versions of a compile can end badly (usually compilation won't
succeed).

**AutoWRFChem says that the Fortran and C netCDF libraries are in different places.** As far as I can tell, WRF expects
the install location for both the C and Fortran libraries to be the same, that is, :command:`nc-config --prefix` and
:command:`nf-config --prefix` should return the same path, which will contain subdirectories :file:`lib` and
:file:`include`. If your C and Fortran netCDF libraries are in different places, the easiest fix is to link both
libraries' files to one directory::

    # Assume $NCDIR is the directory containing lib and include subdirectories for C-netCDF
    # Assume $NFDIR is the same for Fortran-NETCDF
    # Lastly, $LINKDIR is the directory we'll use to make the links
    # This is all in the terminal
    cd $LINKDIR
    mkdir lib include
    cd lib
    ln -sv "$NCDIR/lib/"* .
    ln -sv "$NFDIR/lib/"* .
    cd ../include
    ln -sv "$NCDIR/include/"* .
    ln -sv "$NFDIR/include/"* .

**My cluster doesn't have netCDF available.** You'll have to either build it yourself (not fun) or ask the admins of
your cluster to install it. It's used in enough scientific applications that it's worth it to get installed.


Trouble setting YACC
********************

YACC is a lexer program that is used by the kinetic preprocessor to generate Fortran code from simple chemical mechanism
input files. Many linux systems will have it installed by default at :file:`/bin` or :file:`/usr/bin`. AutoWRFChem
searches the likely places; if it can't find it, it may not be installed. Check that:

1. if your cluster uses module files to load different programs or libraries into your shell that YACC is not loaded by
   that mechanism.
2. ask the cluster admins if YACC is already installed in a non-standard place.

Note that the original YACC has been superseded by `GNU Bison <https://savannah.gnu.org/projects/bison/>_` in many
cases.

If not, the options are the same as for netCDF: build it yourself (`GNU Bison` <https://savannah.gnu.org/projects/bison/>_`
is probably your best bet, though I have never tried it myself) or ask the cluster admins to add it.


Trouble setting FLEX_LIB_DIR
****************************

The FLEX library is also used by the kinetic preprocessor. The specific file you are looking for is :file:`libfl.a`.
AutoWRFChem searches the standard places for it (:file:`/usr/lib` and :file:`/usr/lib64`), so if it can't find it, it's
not installed in a usual place. As with YACC:

1. check if the FLEX library is available as a module on your cluster that needs loaded
2. ask the cluster admins if it is installed in a non-standard place
3. either ask the admins to install it or build it yourself (https://github.com/westes/flex).