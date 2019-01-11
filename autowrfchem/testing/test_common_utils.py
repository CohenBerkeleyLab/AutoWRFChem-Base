from __future__ import print_function, absolute_import, division, unicode_literals

from datetime import timedelta as tdel
import unittest

from .. import common_utils


class TestTimeUtilities(unittest.TestCase):

    def setUp(self):
        self.test_times = {'2': tdel(days=2),
                           '2-12': tdel(days=2, hours=12),
                           '2-12:00': tdel(days=2, hours=12),
                           '2-12:30': tdel(days=2, hours=12, minutes=30),
                           '2-12:30:45': tdel(days=2, hours=12, minutes=30, seconds=45),
                           '12:00': tdel(hours=12),
                           '00:30': tdel(minutes=30),
                           '00:00:45': tdel(seconds=45),
                           '12:30:45': tdel(hours=12, minutes=30, seconds=45),
                           '2d': tdel(days=2),
                           '12h': tdel(hours=12),
                           '30m': tdel(minutes=30),
                           '45s': tdel(seconds=45),
                           '2d12h30m45s': tdel(days=2, hours=12, minutes=30, seconds=45)}

    def test_parsing_timestring(self):
        for tstr, time_diff in self.test_times.items():
            with self.subTest(time_string=tstr):
                self.assertEqual(time_diff, common_utils.parse_time_string(tstr))
