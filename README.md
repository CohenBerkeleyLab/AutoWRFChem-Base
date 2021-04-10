# AutoWRFChem-Base
This contains the stand-alone code necessary to automatically run WRF-Chem with NEI and MEGAN emissions, and MOZART boundary conditions

## Prerequisites
AutoWRFChem is designed to run on Unix/Linux-like systems. It requires the following programs to be installed on your system and available on your `PATH`:

* Bash (at `/bin/bash`)
* Python (2 or 3, note that 3 compatibility not fully tested)
* Perl
* Git

## Setup
AutoWRFChem is intended to be placed alongside directories for WRF-Chem, WPS, the NEI emissions converter tool, MEGAN, 
and MOZART boundary condition tool, that is, in a directory structure like this:

```bash
AutoWRFChem-Root/
├── AutoWRFChem-Base
├── MEGAN
├── MOZBC
├── NEI
├── WPS
└── WRFV3
    └── run
```

AutoWRFChem can clone forks of the WPS, MEGAN, NEI, and MOZBC directories if needed, but you must download the WRFV3 directory yourself. To get the WPS etc. 
repos, run the `Runme` script in AutoWRFChem-Base. This will clone them as well as provide a link to the main AutoWRFChem executable in the top directory 
(here, `AutoWRFChem-Root`).

## Usage

For a full list of subcommands, call `./autowrfchem_main --help` in the `AutoWRFChem-Base` directory, or `./autowrfchem --help` in the top directory if you 
ran `Runme` to generate that link. 

AutoWRFChem usage is generally broken down into four main subcommands:

* `config` runs all of the component configuration scripts. It requires user input, so do not run as part of a batch job.
  - `config namelist` starts an interactive program to edit the WRF-Chem namelists. **Note:** AutoWRFChem modifies the namelists
    written in `WRFV3/run` for parts of its functionality, so it is safest to use this interactive tool.
* `compile` compiles all of the components.
* `prepinpt` generates the input files needed to run WRF-Chem with NEI emissions, MEGAN biogenic emissions, and MOZART chemical boundary
  conditions. 
  - There are options to generate just met files, just chemistry files, or just missing files.
* `run` will start WRF-Chem, and has options to automatically resume from the last restart file.

## FAQ

* *What versions of WRF is this compatible with?* Only v3.5 and 3.6 have been tested. Other versions may work, but are not guaranteed.
* *How can I try a newer version?* Download WRF and WPS manually to the correct directory structure. Emissions preparation may not work, 
  so you may need to handle that manually.
* *Can I use multiple domains?* Not with this version. A 2.0 version is planned that will be more flexible, but I cannot give any sort of timeline
  for when that will be ready.
