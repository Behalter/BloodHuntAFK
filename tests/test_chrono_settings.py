"""Settings upgrade regression tests. Never touch the installed settings file."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bloodhunt import settings_file as sf


class ChronoMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings.py"

    def write(self, data):
        self.path.write_bytes(data)

    def test_preserves_existing_values_and_bytes(self):
        raw = b'# User settings\nWAVE_AWARE = True\nWAVE_AUTHORIZED_TEST = True\nSMELT_RATING = 6500\nMAX_HOURS = 0\nPAUSE_KEY = 0x77\nQUIT_KEY = 0x79'
        self.write(raw)
        self.assertTrue(sf.migrate_chrono_setting(self.path))
        self.assertTrue(self.path.read_bytes().startswith(raw + b'\n'))
        _, settings = sf.read(self.path)
        self.assertEqual(settings["SMELT_RATING"].value, 6500)
        self.assertEqual(settings["MAX_HOURS"].value, 0)
        self.assertEqual(settings["PAUSE_KEY"].value, 0x77)
        self.assertEqual(settings["QUIT_KEY"].value, 0x79)
        self.assertIs(settings["WAVE_AWARE"].value, True)
        self.assertIs(settings["WAVE_AUTHORIZED_TEST"].value, True)
        self.assertIs(settings["WAVE_CHRONO"].value, False)

    def test_preserves_bom_crlf_and_unicode(self):
        raw = b'\xef\xbb\xbf' + '# réglages\r\nSMELT_RATING = 6500\r\n'.encode()
        self.write(raw)
        self.assertTrue(sf.migrate_chrono_setting(self.path))
        updated = self.path.read_bytes()
        self.assertTrue(updated.startswith(raw))
        self.assertNotIn(b'\n', updated.replace(b'\r\n', b''))
        self.assertIs(sf.read(self.path)[1]["WAVE_CHRONO"].value, False)

    def test_idempotent(self):
        self.write(b'WAVE_AWARE = True\n')
        self.assertTrue(sf.migrate_chrono_setting(self.path))
        before = self.path.read_bytes()
        self.assertFalse(sf.migrate_chrono_setting(self.path))
        self.assertEqual(self.path.read_bytes(), before)

    def test_existing_enabled_value_unchanged(self):
        raw = b'WAVE_CHRONO = True  # my choice\n'
        self.write(raw)
        self.assertFalse(sf.migrate_chrono_setting(self.path))
        self.assertEqual(self.path.read_bytes(), raw)

    def test_invalid_settings_untouched(self):
        for raw in (b'WAVE_AWARE = "yes"\n', b'WAVE_CHRONO =\n', b'import os\n', b'\xff'):
            with self.subTest(raw=raw):
                self.write(raw)
                with self.assertRaises(sf.SettingsError):
                    sf.migrate_chrono_setting(self.path)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_new_field_can_be_saved(self):
        self.write(b'WAVE_AWARE = True\n')
        sf.migrate_chrono_setting(self.path)
        sf.save({"WAVE_CHRONO": True}, self.path)
        self.assertIs(sf.read(self.path)[1]["WAVE_CHRONO"].value, True)

    def test_failed_replace_leaves_original_and_no_temp(self):
        raw = b'WAVE_AWARE = True\n'
        self.write(raw)
        with patch.object(sf.os, "replace", side_effect=OSError("locked")):
            with self.assertRaises(sf.SettingsError):
                sf.migrate_chrono_setting(self.path)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
