import unittest

from drive_vlc.drive_url import DriveUrlError, build_view_url, extract_file_id
from drive_vlc.i18n import set_active_language


class TestDriveUrl(unittest.TestCase):
    def tearDown(self) -> None:
        set_active_language(None)

    def test_extracts_from_file_view_url(self) -> None:
        url = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view?usp=sharing"
        self.assertEqual(extract_file_id(url), "1AbCdEfGhIjKlMnOpQrStUvWxYz")

    def test_extracts_from_open_and_uc_and_usercontent_urls(self) -> None:
        file_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
        for url in (
            f"https://drive.google.com/open?id={file_id}",
            f"https://drive.google.com/uc?export=download&id={file_id}",
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download",
            file_id,
        ):
            with self.subTest(url=url):
                self.assertEqual(extract_file_id(url), file_id)

    def test_rejects_folder_url_in_spanish_and_english(self) -> None:
        set_active_language("es")
        with self.assertRaises(DriveUrlError) as ctx_es:
            extract_file_id("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertIn("carpetas", str(ctx_es.exception))

        set_active_language("en")
        with self.assertRaises(DriveUrlError) as ctx_en:
            extract_file_id("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertIn("folder", str(ctx_en.exception))

    def test_rejects_non_drive_domain_and_empty(self) -> None:
        with self.assertRaises(DriveUrlError):
            extract_file_id("")
        with self.assertRaises(DriveUrlError):
            extract_file_id("https://example.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view")

    def test_build_view_url(self) -> None:
        self.assertEqual(
            build_view_url("1AbCdEfGhIjKlMnOpQrStUvWxYz"),
            "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view?usp=sharing",
        )


if __name__ == "__main__":
    unittest.main()
