Setting up AutoWRFChem
======================

Installation
------------

The recommended way to install AutoWRFChem is inside a Python virtual environment.

Vanilla Python 3 virtual environment
************************************

Create a virtual environment for AutoWRFChem named as such in the current directory::

    python3 -m venv AutoWRFChem
    cd AutoWRFChem

Activate this new virtual environment::

    source bin/activate

Make sure :command:`pip` is up to date::

    pip install --upgrade pip

Clone AutoWRFChem (this can be in the virtual environment directory or elsewhere)::

    git clone https://github.com/CohenBerkeleyLab/AutoWRFChem-Base.git
    cd AutoWRFChem-Base

Run :file:`setup.py`::

    python3 setup.py install

This will install any required dependencies and create the file :file:`awc` in this directory. That :file:`awc` file is
the main executable for AutoWRFChem - it will be configured to run AutoWRFChem with whatever Python executable was
used to build it, so doing :command:`./awc` in this directory will automatically run it using this virtual environment,
without you needing to activate it in the future.

Anaconda environment
********************

TBD

Install with system Python
**************************

You *may* skip the virtual environment and simply install with your system Python 3 if you wish::

    git clone https://github.com/CohenBerkeleyLab/AutoWRFChem-Base.git
    cd AutoWRFChem-Base
    python3 setup.py install --user

Note the addition of ``--user`` to the final install command. This will install AutoWRFChem under your user's package
library, instead of the main system library which requires root privileges. Generally, installing under the virtual
environment is preferred since it reduces the possibility of unexpected breakage if system packages are updated, since
the virtual environment will have its own copy of the required packages.

First configuration
-------------------

AutoWRFChem does its best to streamline the process of configuring WRF, however some of the setup is unavoidable. When
you first start AutoWRFChem's configuration program (:command:`./awc config`), it will check the configuration and give
you a summary of what needs corrected::

    Checking configuration...
      * One or more environmental variables need fixed
      * One or more automation variables need fixed

This tells us we need to correct our :ref:`environmental variables <SetupEnvVar>` and at least one of the
:ref:`variables that AutoWRFChem itself uses <SetupCompPaths>`.

The values of these settings that AutoWRFChem will use are store in the config file,
:file:`CONFIG/autowrfchem.cfg`. It will be created the first time you run AutoWRFChem and choose to save the config
changes on exit. You may always edit this file manually if needed to change the values for any of the settings discussed
below.

.. _SetupEnvVar:

Environmental variables
***********************

WRF used certain :term:`environmental variables` to define how it should be configured and compiled. These serve two
distinct purposes:

1. Tell WRF which components to build (i.e. include chemistry or not, which dynamics core to use, etc.)
2. Tell WRF where to find certain code libraries it needs (like netCDF)

From the main menu::

    === AutoWRFChem - Configuration ===
        1: Setup environmental variables
        2: Setup automation config
        3: Check configuration
        4: Run WRF/WPS config scripts
        5: Edit namelists and related config options
        6: Quit

Choose ``1`` to setup your environmental variables. This will present the following options::

    === Setup environmental variables ===
        1: Choose preset
        2: Merge shell environmental vars
        3: Diagnose problems with env. vars
        4: Back

If this is your first time running AutoWRFChem, you should select option ``1``. This will present a list of presets
that will set all the necessary environmental variables for you. Additionally, there is a help option that will provide
additional information about the differences between each preset.

After choosing a preset, or any time AutoWRFChem identifies a problem with your environmental variables, you can choose
option ``3`` ("Diagnose problems with env. vars.") to get more information. For help resolving those issues, see
:ref:`TroubleEnvVar` for common troubleshooting advice.

In most cases, you will not use option ``2`` ("Merge shell environmental vars"). This will check for relevant
environmental variables defined in the shell that launched AutoWRFChem and store their current values in the AutoWRFChem
config file. This is helpful only if you already have these variables setup by default in your shell from
configuring/compiling WRF or WRF-Chem manually.

.. note::

   AutoWRFChem doesn't change the environmental variables in the shell that launched it; instead it just makes sure to
   set the values of all the necessary environmental variables in the shell that's running any WRF or related external
   program.  This means you don't have to have those extra variables always defined in your shell, and ensures that the
   same set of environmental variables are set during configuration and compilation.

.. _SetupCompPaths:

Automation variables
********************

The settings in the AUTOMATION_PATHS section tell AutoWRFChem where to find the various components: WRF, WPS, etc.
By default, AutoWRFChem assumes it is a sibling directory to these components; that is, the repo directory
(:file:`AutoWRFChem-Base`) is in the same directory as the :file:`WRFV3` and :file:`WPS` directories. If this is true,
no extra setup is needed for these paths. If not, but WRFV3, WPS, etc. are all in the same directory, the
"Setup automation config" option on the main menu will give you the ability to set that directory for all the components
at once. If the components are in different places, or if the WRF and WPS directories themselves are not named
"WRFV3" and "WPS", respectively, then you will need to edit :file:`CONFIG/autowrfchem.cfg` manually.