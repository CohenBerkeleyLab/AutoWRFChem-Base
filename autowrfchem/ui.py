from __future__ import print_function, absolute_import, division
from collections import OrderedDict
import datetime as dt


def user_input_list(prompt, options, returntype="value", currentvalue=None, emptycancel=True):
    # Method will give the user their list of options, sequentially numbered, and ask them to chose one. It will
    # ensure that the selection is in the permissible range and return, by default, the value selected. The keyword
    # argument "returntype" can be set to "index" to have this function return the index within the list options
    # rather than the value. The keyword currentvalue can be used to mark which option is currently selected
    # Returns None if the user enters an empty value to abort

    # Input checking
    if type(prompt) is not str:
        raise TypeError("PROMPT must be a string")
    if type(options) is not list and type(options) is not tuple:
        raise TypeError("OPTIONS must be a list or tuple")
    if type(returntype) is not str or returntype.lower() not in ["value", "index"]:
        raise TypeError("RETURNTYPE must be one of the strings 'value' or 'index'")

    print(prompt)
    if emptycancel:
        print("A empty answer will cancel.")
    if currentvalue is not None:
        print("The current value is marked with a *")
    for i in range(1, len(options)+1):
        if currentvalue is not None and options[i-1] == currentvalue:
            currstr = "*"
        else:
            currstr = " "
        print("  {2}{0}: {1}".format(i, options[i-1], currstr))

    while True:
        userans = raw_input("Enter 1-{0}: ".format(len(options)))
        if len(userans) == 0:
            if emptycancel:
                return None
            else:
                continue

        try:
            userans = int(userans)
        except ValueError:
            print("Input invalid")
        else:
            if userans > 0 and userans <= len(options):
                break

    if returntype.lower() == "value":
        return options[userans-1]
    elif returntype.lower() == "index":
        return userans - 1
    else:
        raise ValueError("Value '{0}' for keyword 'returntype' is not recognized".format(returntype))


def user_input_date(prompt, currentvalue=None):
    # Prompts the user for a date in yyyy-mm-dd or yyyy-mm-dd HH:MM:SS format. Only input is a prompt describing
    # what the date is. Returns a datetime object. The currentvalue keyword can be used to display the current
    # setting, but it must be a datetime object as well. Returns none if user ever enters an empty string.
    if currentvalue is not None and type(currentvalue) is not dt.datetime:
        raise TypeError("If given, currentvalue must be a datetime object")

    print(prompt)
    print("Enter in the format yyyy-mm-dd or yyyy-dd-mm HH:MM:SS")
    print("i.e. both 2016-04-01 and 2016-04-01 00:00:00 represent midnight on April 1st, 2016")
    print("Entering nothing will cancel")
    if currentvalue is not None:
        print("Current value is {0}".format(currentvalue))

    while True:
        userdate = raw_input("--> ")
        userdate = userdate.strip()
        if len(userdate) == 0:
            return None

        date_and_time = userdate.split(" ")
        date_and_time = [s.strip() for s in date_and_time]
        if len(date_and_time) == 1:
            # No time passed, set to midnight
            hour = 0
            min = 0
            sec = 0
        else:
            time = date_and_time[1].split(':')
            if len(time) != 3:
                print('Time component must be of form HH:MM:SS (three 2-digit numbers separated by colons')
                continue

            try:
                hour = int(time[0])
                min = int(time[1])
                sec = int(time[2])
            except ValueError:
                print("Error parsing time. Be sure only numbers 0-9 are used to define HH, MM, and SS")
                continue

        date = date_and_time[0].split("-")
        if len(date) != 3:
            print("Date component must be of form yyyy-mm-dd (4-, 2-, and 2- digits separated by dashed")
            continue

        try:
            yr = int(date[0])
            mn = int(date[1])
            dy = int(date[2])
        except ValueError:
            print("Error parsing date. Be sure only numbers 0-9 are used to define yyyy, mm, and dd.")
            continue

        # Take advantage of datetime's built in checking to be sure we have a valid date
        try:
            dateout = dt.datetime(yr,mn,dy,hour,min,sec)
        except ValueError as e:
            print("Problem with date/time entered: {0}".format(str(e)))
            continue

        # If we get here, nothing went wrong
        return dateout


def user_input_value(optname, isbool=False, currval=None, noempty=False):
    # Allows user to input a value simply. The isbool keyword input allows this function to behave differently if
    # the option is a boolean, since those options must be given as .true. or .false.
    # As with others, a value for currval will print the current value
    # Returns None if no value given
    print("Enter a new value for {0}".format(optname))
    if currval is not None:
        print("The current value is {0}".format(currval))

    while True:
        if isbool:
            userans = raw_input("T/F: ").lower().strip()
            if userans == "t":
                return ".true."
            elif userans == "f":
                return ".false."
            elif len(userans) == 0:
                return None
            else:
                print("Option is a boolean. Must enter T or F.")
        else:
            userans = raw_input("--> ").strip()
            if len(userans) == 0 and not noempty:
                return None
            elif len(userans) == 0 and noempty:
                print("Cannot enter an empty value.")
            else:
                return userans


def user_input_yn(prompt, default="y"):
    while True:
        if default in "Yy":
            defstr = " [y]/n"
            defaultans = True
        else:
            defstr = " y/[n]"
            defaultans = False
        userans = raw_input(prompt + defstr + ": ")

        if userans == "":
            return defaultans
        elif userans.lower() == "y":
            return True
        elif userans.lower() == "n":
            return False
        else:
            print("Enter y or n only. ", end="")


def user_input_menu(prompt, options, fxn_args, fxn_kwargs):
    if not isinstance(options, OrderedDict):
        raise TypeError('options must be an OrderedDict')

    selection = user_input_list(prompt, options.keys())
    options[selection](*fxn_args, **fxn_kwargs)