AutoWRFChem Overview
====================

AutoWRFChem is a Python package designed to automate the process of preparing input and executing WRF or WRF-Chem. I
originally created it to facilitate a 10-year run of WRF-Chem over the continental US domain for my Ph.D. by
streamlining all the necessary input preparation (including metereology preprocessing with WPS, NEI anthropogenic
emissions gridding, MEGAN biogenic emissions preparation, and MOZBC chemical initial and boundary conditions addition)
into a single command, in order to save me time and reduce user error by automating the tedious number of steps
required. It also gave me a mechanism to automatically break the long run down into shorter segments that could each
finish within the wall-clock time limit on the computing clusters I was using.

What's new in v2.0
------------------

* All components rewritten in Python; bash scripts are no longer used.
* Python 3 compatibility is preferred; Python 2 compatibility will be maintained if possible, but not guaranteed.
* New mechanism for handling temporary vs. permanent namelist changes: two copies of the namelist files are now written,
  instead of using a Python pickle file for the permanent namelists. This permits the user to edit the permanent
  namelists manually if they prefer that over using the config program. For more details, see...
* Support for multiple domains added
* All configuration options are now stored in a single file, :file:`CONFIG/autowrfchem.cfg`, which makes it easier to
  keep organized.
* The directories for the various components (WRF, WPS, etc.) are now configurable options, so no particular directory
  structure is enforced.
* Support added for reinitialization runs, where the model is reinitialized from external initial conditions at a
  specified frequency.
* Support added for configuration ensembles, where an ensemble of runs each using a slightly different namelist can be
  quickly generated and submitted to run.


Fair use policy
---------------

By using this code in your research, your agree to the following terms in addition to the terms of reuse given in the
license:

1. Any publication that uses this code will include a citation to this repository
   (`doi: 10.5281/zenodo.834797 <https://doi.org/10.5281/zenodo.834797>`_)
2. Only the master branch is considered stable. All other branches are under development, subject to change, and not
   recommended for scientific use.
3. We do our best to ensure that the master branch is bug-free and scientifically sound. However, we cannot test all
   possible use cases. The user is ultimately responsible for ensuring than any results obtained using this code are
   scientifically accurate.
4. If your research uses a branch other than master,
   please notify us as soon as possible that you intend to publish a manuscript using unpublished features of
   this code. If the publication competes with one of our own, we may ask that you delay publishing until we
   submit our manuscript.
5. If you make a copy of this code publicly available, please link back to the original repo. If your copy is hosted
   on GitHub, it should be a fork of this repository.