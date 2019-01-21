Namelists
=========

.. _NLBasics:

Namelist basics
---------------

In order to automate WRF(-Chem), AutoWRFChem needs to be able to modify the WRF and WPS namelists on the fly to do
things like change the run time for certain steps, or disable certain options until the input files for them have been
generated. Of course, when we do this, we also need to keep track of the settings that *you* made. To handle this,
AutoWRFChem works with **two** copies of the namelists;

 1. **Persistent namelists:** (a.k.a. *permanent* or *static* namelists) these are the ones that store the settings the
    user last made. These are kept in the :file:`CONFIG` directory. These can be edited either manually, as you would
    normally edit them, or through AutoWRFChem's configuration program.
 2. **Temporary namelists:** these are the ones that will be modified as-needed to make WRF, WPS, or any of the input
    components run what AutoWRFChem needs them to. These are put in the WRF and WPS run directories, respectively, and
    *should not* be edited by the user, as changes to them will be lost.

.. warning::

   If you're using AutoWRFChem for the first time after using WRF manually, you'll be used to editing the namelists in
   the WRF and WPS run directories. *Don't do that.* Your changes will be overwritten the next time AutoWRFChem runs.


Modifying the namelists
-----------------------

In AutoWRFChem, you can either edit the namelists through its configuration program, or by editing the copies in the
:file:`CONFIG` directory manually.


Modifying the namelists manually
********************************

With v2.0.0, you can use any plain text editor to modify the namelist files in :file:`CONFIG` just as you would modify
the WRF and WPS namelists if you aren't using AutoWRFChem. After you finish modifying them, you should run the command
:command:`./awc config --quick-sync-namelists` (short form, :command:`./awc config -s`). This both checks that options
required to be synchronized between WRF and WPS are, and copies changes to the permanent namelists to the temporary
namelists. If any WRF and WPS shared options are out of sync, you'll get the following menu::

   parent_id differs between WRF (0, 1, 2, 3) and WPS (1, 1, 2, 3) namelists.
   How do you want to synchronize them?
       1: Use WRF
       2: Use WPS
       3: Use WRF (and for all following options)
       4: Use WPS (and for all following options)
       5: Do not sync

The initial message will change to reflect which option is in conflict and the values in the WRF and WPS namelists.

* **1: Use WRF** and **2: Use WPS** will copy the value from the WRF namelist to the WPS namelist (``1``) or vice versa
  (``2``).
* **3: Use WRF (and for all following options)** and **4: Use WPS (and for all following options)** will similarly copy
  the WRF options to WPS (``3``) or vice versa (``4``) but will automatically do the same for all conflicting options.
* **5: Do not sync** will leave this option alone in both namelists.

.. note::

   Some options, such as ``dx`` and ``dy`` *must* have different values in WRF and WPS. For example, ``dx`` and ``dy``
   are to be given for all domains in the WRF namelist, but only the first in the WPS namelist. In those cases,
   AutoWRFChem will convert the value behind-the-scenes if you choose to sync it.

Using the configuration program
*******************************

The advantage of using the configuration program is that 1) it makes sure the values are the correct type, and 2) it
can help set up groups of related options all at once and helps keep them in sync.
The downside is that, since you can only edit one option at a time, it can feel clunky if you need to iteratively tweak
several options. (This is why in v2.0.0 we changed its functionality so that you could edit the permanent namelists
directly.)

.. note::

   You won't be able to do use this program to modify the namelists until you've compiled WRF. The namelist
   configuration part of AutoWRFChem relies on the
   `WRF registry <http://www2.mmm.ucar.edu/wrf/users/tutorial/201407/Wednesday/4_gill_registry.pdf>`_
   to know what type (boolean, integer, float, or string) each option is, and whether each option should be specified
   for each domain or just once for the whole model.

To use this method, launch the configuration program::

   ./awc config

You'll get the main configuration menu::

   === AutoWRFChem - Configuration ===
       1: Setup environmental variables
       2: Setup automation config
       3: Check configuration
       4: Run WRF/WPS config scripts
       5: Edit namelists and related config options
       6: Quit
   Enter 1-6:

In this case, we want to choose ``5`` to edit the namelists. If there are already namelists in :file:`CONFIG`, then
you'll see this menu::

   === Namelists ===
       1: Load different namelists       3: Select meteorology
       2: Edit namelist options          4: Back & save namelists
   Enter 1-4:

If not, you'll only see option 1. Choosing ``1`` will bring you to::

   === Load different namelists ===
       1: Load/reload existing namelists        3: Load the standard templates
       2: Load previously saved namelists       4: Back
   Enter 1-4:

(Note that your numbering will differ if one of these options is not available).

If you already had the "Edit namelist options" choice before, you don't need to do anything here. If not, choose
``Load the standard templates`` to load a default WRF and WPS namelist.

.. note::

   Choosing ``3`` will load a reasonable standard template for WRF or WRF-Chem, depending if you have the ``WRF_CHEM``
   environmental variable set or not in the configuration. Choosing ``2`` lets you load a WRF and/or WPS namelist from the
   :file:`CONFIG/NAMELISTS` directory that you've saved there before. Choosing ``1`` tries to reload the namelists saved in
   :file:`CONFIG`. This won't work if they aren't there yet; but once they exist, this lets you revert to the last saved
   version. Once you've loaded the namelists


Back at the following menu::

   === Namelists ===
       1: Load different namelists       3: Select meteorology
       2: Edit namelist options          4: Back & save namelists
   Enter 1-4:

you can choose ``2`` to edit individual namelist options or ``3`` to preset a whole bunch of options for a specific
meteorology used for the initial and boundary conditions.

.. note::

   Setting the meteorology will also record which meteorology type was chosen in the :file:`CONFIG/autowrfchem.cfg`
   file, which will be used to link the correct ungrib Vtable for WPS. So you should choose which meteorology your
   using via option ``3`` at least once, and update that if you change meteorology.

Choosing ``2`` brings up::

   === Edit namelist options ===
       1: Set start/end date
       2: Set shared domain options
       3: Revert met-relevant options to recommended
       4: Set other WRF options
       5: Set other WPS options
       6: Display WRF options
       7: Display WPS options
       8: Back
   Enter 1-8:

This menu is the central one for modifying namelists:

1. **Set start/end date:** Set the start and end date for the model run. This sets them in both the WRF and WPS
   namelist. *Note:* right now, all domains are set to the same start and end date; there's no mechanism to start or end
   a nested domain at a different time.
2. **Set shared domain options:** Set options for the domain shared between WRF and WPS. This is things like ``e_we``,
   ``e_ns``, ``dx``, ``dy``, etc. Options dealing with the domain's position on the real Earth (like ``ref_lon`` and
   ``ref_lat``) are set by the ``Set other WPS options`` choice.
3. **Revert met-relevant options to recommended:** Each initial/boundary condition global meteorology that can be
   selected by ``Select meteorology`` on the previous menu comes with certain recommended namelist settings. You can
   modify them (at your own risk), this option changes any of those back to the recommended values.
4. **Set other WRF options:** choosing this will bring up a list of WRF namelist sections. Choose one to modify options
   within it, then choose the particular option to edit.  There's a fairly flexible syntax to set specific domains only,
   see :ref:`NLConfigSyntax` for more details.
5. **Set other WPS options:** same as previous, but for the WPS namelist.
6. **Display WRF options:** brings up a list of WRF namelist sections, choose one to print its current values to the
   terminal in its entirety.
7. **Display WPS options:** same, but for the WPS namelist.

Once you're done, choose ``8`` (Back) to get back to the main ``Namelists`` menu::

   === Namelists ===
       1: Load different namelists       3: Select meteorology
       2: Edit namelist options          4: Back & save namelists
   Enter 1-4:

Choosing ``4`` here will bring up options for how to write the changes you just made to the namelist files::

   Save changes to namelists
       1: Save namelists
       2: Save namelists for later
       3: Discard changes
       4: Make further changes
   Enter 1-4:

1. **Save namelists:** this will write your changes to both the permanent and temporary namelists (see :ref:`NLBasics`)
2. **Save namelists for later:** this will let you save the changed namelists to the :file:`CONFIG/NAMELISTS` directory
   to load at a later time.
3. **Discard changes:** The changes you made will not be saved, anywhere.
4. **Make further changes:** Brings you back to the namelist menu to further edit the files.

.. _NLConfigSyntax:

Syntax for setting namelist option values in the config program
***************************************************************

When modifying namelist option in the config program, the program allows you to modify any subset of the domains you
wish. For example, let's assume you're modifying an option that take a value for each domain, we have four domains,
and each value should be an integer. You could:

* Enter values for each domain separated by commas, e.g. ``5, 6, 7, 8``, to set each domain to a different value.
* If you enter fewer values than there are domains, then the last value
  will be repeated (e.g. ``5, 6`` is the same as entering ``5, 6, 6, 6`` and just entering ``5`` is the same as entering
  ``5, 5, 5, 5``).
* You may specify which domains to edit with an @ command at the beginning of the value. In this case, the number of
  values given must exactly match the number of domains being modified.

  - ``@1 5`` would set the first domain only to 5. (The ``@1`` indicated to modify just domain 1 and the ``5`` is the
    value.
  - ``@2:3 6, 7`` would set domains 2 and 3 to ``6`` and ``7``, respectively. (The ``@2:3`` means tp set domains 2
    through 3.) There must be exactly as many values specified as the are domains to change; this form does *not*
    automatically expand the list of values to have the correct number of values.
  - ``@1:3 5, 6, 7`` and ``@:3 5, 6, 7`` would set the first two domains to 5 and 6, respectively. (Omitting the first
    index as in ``@:3`` is shorthand for starting from the first domain.)
  - ``@3:4 7, 8`` and ``@3: 7, 8`` would set domains 3 and 4 to ``7`` and ``8``, respectively. (Similarly to the last
    point, omitting the last index, as in ``@3:``, is shorthand for ending on the last domain.)
  - ``@: 5, 6, 7, 8`` sets the domains 1 through 4 to ``5``, ``6``, ``7``, and ``8``, respectively. (Omitting the first
    *and* last indices automatically includes all domains. Unlike the very first method, where we entered ``5, 6, 7, 8``
    without the ``@`` syntax, exactly the right number of values must be given.)
