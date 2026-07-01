from __future__ import print_function

import unittest
import re
import argparse

from tar_scm import TarSCM


class CliTestCases(unittest.TestCase):
    def setUp(self):
        self.cli = TarSCM.Cli()

    def test_parse_args_valid_revision(self):

        valid_rev = ['1.2.3', 'v1.2.3', '1.2-3', '@PARENT_TAG@']
        for rev in valid_rev:
            self.cli.parse_args([
                '--outdir', '.',
                '--scm', 'git',
                '--revision', rev
            ])

    def test_parse_args_invalid_revision(self):
        for rev in ['1.2.3 --config', '1.2 3']:
            with self.assertRaisesRegex(SystemExit, r"option revision \(.*\) contains forbidden characters"):
                self.cli.parse_args([
                    '--outdir', '.',
                    '--scm', 'git',
                    '--revision', rev
                ])

        for rev in ['1.2.3 --config', '-p123', '1.2 -p']:
            with self.assertRaisesRegex(SystemExit, r"2"):
                self.cli.parse_args([
                    '--outdir', '.',
                    '--scm', 'git',
                    '--revision', rev
                ])
