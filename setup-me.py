import os
import sys

_mydir = os.path.dirname(__file__)
awcfile = os.path.join(_mydir, 'awc')
with open(awcfile, 'w') as fobj:
    fobj.write('#!{}\n\n'.format(sys.executable))
    fobj.write('from autowrfchem_main import entry_point\n')
    fobj.write('entry_point()')

os.chmod(awcfile, 0o744)
