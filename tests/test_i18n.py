import unittest

from drive_vlc.i18n import (
    _CATALOGS,
    detect_system_language,
    set_active_language,
    t,
)


class TestI18n(unittest.TestCase):
    def tearDown(self) -> None:
        set_active_language(None)

    def test_catalogs_share_identical_keys(self) -> None:
        self.assertEqual(set(_CATALOGS["en"].keys()), set(_CATALOGS["es"].keys()))

    def test_detect_system_language_precedence_and_fallback(self) -> None:
        self.assertEqual(
            detect_system_language({"LANGUAGE": "fr_FR:es_ES:en", "LANG": "en_US.UTF-8"}),
            "es",
        )
        self.assertEqual(
            detect_system_language({"LC_ALL": "es_ES.UTF-8", "LANG": "en_US.UTF-8"}),
            "es",
        )
        self.assertEqual(
            detect_system_language({"LC_MESSAGES": "en_GB.UTF-8", "LANG": "es_ES.UTF-8"}),
            "en",
        )
        self.assertEqual(detect_system_language({"LANG": "fr_FR.UTF-8"}), "en")
        self.assertEqual(detect_system_language({"LANG": "C"}), "en")
        self.assertEqual(detect_system_language({"LANG": "POSIX"}), "en")
        self.assertEqual(
            detect_system_language({"LANG": "es_ES.UTF-8"}, cli_lang="en"),
            "en",
        )

    def test_translate_switches_with_active_language(self) -> None:
        set_active_language("en")
        self.assertIn("folder links", t("url.error.folder"))
        set_active_language("es")
        self.assertIn("carpetas", t("url.error.folder"))
