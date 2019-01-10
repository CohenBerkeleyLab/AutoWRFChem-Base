from __future__ import print_function, unicode_literals, absolute_import, division

import copy
import unittest

from . import setup_testing_utils as stu
from ..configuration import autowrf_classlib as awclib


class TestNamelistSetOptions(unittest.TestCase):
    def setUp(self):
        self.nlc = stu.get_namelist_container(sync='wrf')
        if self.nlc.wrf_namelist.max_domains != 4:
            raise ValueError('Testing expects a WRF namelist with 4 domains')

    def test_parse_nl_set_opt_by_string(self):
        """
        Verify that various ways of setting a namelist option from a string work as they should
        """
        optname = 'e_we'

        def replace_slice(slice, vals):
            curr_val = copy.copy(self.nlc.wrf_namelist.get_opt_val_no_sect(optname))
            curr_val[slice] = vals
            return curr_val

        # Need to test that the last value gets expanded and that the @ commands work
        test_inputs = {'1': ['1', '1', '1', '1'],
                       '1,': ['1', '1', '1', '1'],
                       '1,2': ['1', '2', '2', '2'],
                       '1,2,3,4': ['1', '2', '3', '4'],
                       '@1 1': replace_slice(slice(1), ['1']),
                       '@:2 1, 2': replace_slice(slice(2), ['1', '2']),
                       '@3: 1, 2': replace_slice(slice(2, None), ['1', '2']),
                       '@2:3 1, 2': replace_slice(slice(1, 3), ['1', '2']),
                       '@: 1, 2, 3, 4': replace_slice(slice(None), ['1', '2', '3', '4'])}

        for input_str, expected_value in test_inputs.items():
            with self.subTest(input_str=input_str):
                test_value = self.nlc._parse_option_input(self.nlc.wrf_namelist, optname, input_str)
                self.assertEqual(test_value, expected_value)

    def test_parse_nl_set_opt_by_string_wrong_num_domains(self):
        """
        Verify that giving the wrong number of domain values with an @ command fails
        """
        input_string = ['@2:3 1, 2, 3, 4',  # too many domain values
                        '@2:3 1']           # too few domain values
        for s in input_string:
            with self.subTest(input_string=s):
                with self.assertRaisesRegex(awclib.NamelistValueError, r'\d+ domain\(s\) specified to change, but \d+ values provided'):
                    self.nlc._parse_option_input(self.nlc.wrf_namelist, 'e_we', s)

    def test_parse_nl_set_opt_by_string_wrong_type_format(self):
        """
        Verify that passing the wrong format of a value fails
        """
        opts = {'e_we': 'integer', 'diff_6th_factor': 'real', 'input_from_file': 'logical', 'physics_suite': 'character'}

        # Test that the right format gets through, but giving a different type's format fails. Also test some formats
        # that should fail for all.
        input_strs = {'integer': '1', 'real': '1.0', 'logical': '.false.', 'character': "'bob'",
                      'bad_logical': 'False', 'char_no_quotes': 'bob', 'char_wrong_quotes': '"bob"'}

        # Try giving each type to each option, make sure the right ones succeed and the rest fail.
        for optname, opttype in opts.items():
            for inputtype, inputstr in input_strs.items():
                with self.subTest(optname=optname, inputstr=inputstr, opttype=opttype, inputtype=inputtype):
                    if inputtype == opttype:
                        # Should not be an error if the input type and the expected type are the same
                        self.nlc._parse_option_input(self.nlc.wrf_namelist, optname, inputstr)

                    else:
                        with self.assertRaisesRegex(awclib.NamelistValueError, 'incorrect format for the "{}" type'.format(opttype)):
                            self.nlc._parse_option_input(self.nlc.wrf_namelist, optname, inputstr)

    def test_parse_nl_set_opt_by_string_per_model_setting(self):
        """
        Verify that giving any number of values other than 1 to a single-value option fails
        """
        opt = 'time_step'
        with self.assertRaisesRegex(awclib.NamelistValueError, 'requires exactly 1 value'):
            self.nlc._parse_option_input(self.nlc.wrf_namelist, opt, '1, 2')
        with self.assertRaisesRegex(awclib.NamelistValueError, 'requires exactly 1 value'):
            self.nlc._parse_option_input(self.nlc.wrf_namelist, opt, ',')

    def test_parse_nl_set_opt_by_string_too_many_values(self):
        """
        Verify that giving too many values for the current number of domains errors
        """
        with self.assertRaisesRegex(awclib.NamelistValueError, r'More values given \(\d+\) than domains \(\d+\)'):
            self.nlc._parse_option_input(self.nlc.wrf_namelist, 'e_we', '1,2,3,4,5,6,7,8')

    def test_nlc_sync_vars(self):
        """
        Test that all expected variables synchronize between WRF and WPS namelists properly
        """
        nlc = stu.get_namelist_container(sync='no sync')

        def check_opt_is_different(opt):
            wrf_opt = nlc.wrf_namelist.get_opt_val_no_sect(opt)
            wps_opt = nlc.wps_namelist.get_opt_val_no_sect(opt)
            if wrf_opt == wps_opt:
                raise RuntimeError('{} already the same in WRF and WPS namelists - test will not work'.format(opt))

        all_test_opts = nlc.sync_options
        check_opt_is_different('max_dom')   # to really test this, we want the namelists to have different numbers of
                                            # domains to begin with
        for opt in all_test_opts:
            check_opt_is_different(opt)

        for opt in all_test_opts:
            wrf_val = nlc.wrf_namelist.get_opt_val_no_sect(opt)
            wps_val = nlc.wps_namelist.get_opt_val_no_sect(opt)

            nlc_test = stu.get_namelist_container(sync='wrf')
            with self.subTest(opt=opt, direction='wrf -> wps'):
                self.assertEqual(nlc_test.wrf_namelist.get_opt_val_no_sect(opt), wrf_val)
                self.assertEqual(nlc_test.wps_namelist.get_opt_val_no_sect(opt), wrf_val)

            nlc_test = stu.get_namelist_container(sync='wps')
            with self.subTest(opt=opt, direction='wps -> wrf'):
                self.assertEqual(nlc_test.wrf_namelist.get_opt_val_no_sect(opt), wps_val)
                self.assertEqual(nlc_test.wps_namelist.get_opt_val_no_sect(opt), wps_val)


if __name__ == '__main__':
    unittest.main()
