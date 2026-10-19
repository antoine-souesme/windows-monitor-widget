# -*- coding: utf-8 -*-
"""Tests of the language of the texts."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor_widget import i18n, probes


class LanguageTest(unittest.TestCase):

    def tearDown(self):
        i18n.set_language(i18n.DEFAULT)

    def test_english_by_default(self):
        self.assertEqual(i18n.DEFAULT, "en")
        self.assertEqual(i18n.tr("Quitter"), "Quit")

    def test_french_is_the_text_itself(self):
        i18n.set_language("fr")
        self.assertEqual(i18n.tr("Quitter"), "Quitter")
        self.assertEqual(i18n.decimal_mark(), ",")

    def test_unknown_language_falls_back_to_the_default(self):
        i18n.set_language("klingon")
        self.assertEqual(i18n.language(), i18n.DEFAULT)

    def test_a_missing_translation_shows_the_french_text(self):
        self.assertEqual(i18n.tr("Pas encore traduit"), "Pas encore traduit")

    def test_every_metric_name_is_translated(self):
        for cls in probes.PROBES.values():
            self.assertIn(cls.label, set(i18n.ENGLISH) | {"CPU", "GPU", "RAM"})


if __name__ == "__main__":
    unittest.main()
