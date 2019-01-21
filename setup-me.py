import os
import sys

#TODO: convert to regular setup.py file with dependencies that also installs the autowrfchem package.
# This will require moving autowrfchem_main:entry_point into the package and making sure that the awc file imports
# from the installed package, not the one in the current directory.
#
# Should we also add a command line flag to put awc on the environment's path
# instead/as well?

_mydir = os.path.dirname(__file__)
awcfile = os.path.join(_mydir, 'awc')
with open(awcfile, 'w') as fobj:
    fobj.write('#!{}\n\n'.format(sys.executable))
    fobj.write('from autowrfchem_main import entry_point\n')
    fobj.write('entry_point()')

os.chmod(awcfile, 0o744)
