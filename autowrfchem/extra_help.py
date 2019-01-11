from __future__ import print_function, absolute_import, division, unicode_literals

from textui import uielements as uiel

from . import _pretty_n_col

_time_str_help = \
"""Time strings can be in one of two formats:

  * DDdHHhMMmSSs, e.g. 2d12h30m45s
  * DD-HH:MM:SS, e.g. 2-12:30:45
  
In the first format, any combination of parts can be used,
e.g. 2d, 12h, 30m, 2d12h, 2d30m, and so on. d is days, h
is hours, m is minutes, and s is seconds. So these values
are 2 days, 12 hours, 30 minutes, 2 days + 12 hours, and 
2 days + 30 minutes, respectively. 

You may specify the time however you want, there is no upper
limit on each part, so 2d and 48h are equivalent.

The second format is straightforward if all parts are included,
i.e. 2-12:30:45 is 2 day, 12 hours, 30 minutes, and 45 seconds.
However, omitting parts is more complicated:

  * If a single number (e.g. "2") is given, that is assumed to
    be days.
  * If the string includes a colon, it is interpreted as hours,
    minutes, and seconds.
      - Trailing components can be omitted (e.g. "12:30") is 12
        hours and 30 minutes) but a number must be on both sides
        of the colon (i.e. "12:" and ":30" are illegal).
      - There is no upper limit on the value of each part, i.e.
        24:1440:00 is allowed and will represent 2 days.
  * If the string includes a dash, the part before the dash is
    interpreted as days and the part after as hours, minutes and
    seconds.
      - A colon is not required after the dash, i.e. 2-12 is a 
        valid representation of 2 days, 12 hours, but 2-12: is
        still illegal.
"""


_topics = {'timefmt': (_time_str_help, False)}


def print_extra_help(topic):
    try:
        help_str, do_wrap = _topics[topic]
    except KeyError:
        avail_topics = '", "'.join(_topics.keys())
        msg = 'Available topics are:\n\n    {}'.format(avail_topics)
        if topic != '':
            msg = 'No entry for topic "{}". '.format(topic) + msg
        else:
            msg += '\n\nUse -h or --help for regular AutoWRFChem command line help.'
        uiel.user_message(msg, max_columns=_pretty_n_col)
    else:
        if do_wrap:
            uiel.user_message(help_str, max_columns=_pretty_n_col)
        else:
            print(help_str)


def setup_clargs(parser):
    parser.add_argument('topic', nargs='?', default='')
    parser.set_defaults(exec_func=print_extra_help)
