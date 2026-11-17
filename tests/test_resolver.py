import json
import subprocess
import unittest
from unittest.mock import patch

from drive_vlc.resolver import (
    PrivateOrBlockedError,
    ResolutionError,
    ResolvedStream,
    _decode_content_disposition_filename,
    resolve_drive_stream,
    resolve_via_api,
    resolve_via_http,
    resolve_via_yt_dlp,
)


class _FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        headers: dict[str, str],
        body: bytes = b"",
    ) -> None:
        self._url = url
        self.headers = headers
        self._body = body

    def geturl(self) -> str:
        return self._url

    def read(self, _n: int = -1) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class TestResolver(unittest.TestCase):
    def test_decode_content_disposition_filename(self) -> None:
        self.assertEqual(
            _decode_content_disposition_filename('attachment; filename="mi_video.mp4"'),
            "mi_video.mp4",
        )
        self.assertEqual(
            _decode_content_disposition_filename("attachment; filename*=UTF-8''pel%C3%ADcula%204K.mkv"),
            "película 4K.mkv",
        )
        mojibake = "Día 2.mp4".encode("utf-8").decode("latin-1")
        self.assertEqual(
            _decode_content_disposition_filename(f'attachment; filename="{mojibake}"'),
            "Día 2.mp4",
        )
        self.assertEqual(
            _decode_content_disposition_filename('attachment; filename="Día 2.mp4"'),
            "Día 2.mp4",
        )

    def test_resolve_via_http_direct_binary_stream(self) -> None:
        direct_url = "https://drive.usercontent.google.com/download?id=FILE123&export=download&authuser=0"
        fake_resp = _FakeResponse(
            url=direct_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Disposition": 'attachment; filename="demo.mp4"',
            },
        )
        with patch("drive_vlc.resolver.build_opener") as mock_opener_cls:
            mock_opener_cls.return_value.open.return_value = fake_resp
            result = resolve_via_http("FILE123")

        self.assertEqual(result.url, direct_url)
        self.assertEqual(result.method, "http")
        self.assertEqual(result.title, "demo.mp4")
        self.assertEqual(result.content_type, "video/mp4")

    def test_resolve_via_http_parses_virus_scan_form_and_verifies_cookieless(self) -> None:
        interstitial_html = (
            '<html><body><span class="uc-name-size"><a href="#">concierto.mkv</a> (2.1G)</span>'
            '<form id="download-form" action="https://drive.usercontent.google.com/download" method="get">'
            '<input type="hidden" name="id" value="FILE123">'
            '<input type="hidden" name="export" value="download">'
            '<input type="hidden" name="confirm" value="t">'
            '<input type="hidden" name="uuid" value="uuid-999">'
            "</form></body></html>"
        ).encode("utf-8")

        html_resp = _FakeResponse(
            url="https://drive.google.com/uc?export=download&id=FILE123",
            headers={"Content-Type": "text/html; charset=utf-8"},
            body=interstitial_html,
        )
        final_bin_url = (
            "https://drive.usercontent.google.com/download"
            "?id=FILE123&export=download&confirm=t&uuid=uuid-999"
        )
        bin_resp = _FakeResponse(
            url=final_bin_url,
            headers={"Content-Type": "video/x-matroska"},
        )

        with patch("drive_vlc.resolver.build_opener") as mock_opener_cls:
            mock_opener_cls.return_value.open.side_effect = [html_resp, bin_resp]
            result = resolve_via_http("FILE123")

        self.assertEqual(result.url, final_bin_url)
        self.assertEqual(result.title, "concierto.mkv")
        self.assertEqual(result.method, "http")

    def test_resolve_via_http_detects_private_login_redirect(self) -> None:
        login_resp = _FakeResponse(
            url="https://accounts.google.com/v3/signin/identifier",
            headers={"Content-Type": "text/html"},
        )
        with patch("drive_vlc.resolver.build_opener") as mock_opener_cls:
            mock_opener_cls.return_value.open.return_value = login_resp
            with self.assertRaises(PrivateOrBlockedError):
                resolve_via_http("FILE123")

    def test_resolve_via_yt_dlp_parses_json(self) -> None:
        payload = json.dumps(
            {
                "url": "https://rr1---sn.googlevideo.com/videoplayback?id=abc",
                "title": "Video de prueba",
                "ext": "mp4",
            }
        )
        completed = subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=0, stdout=payload + "\n", stderr=""
        )
        with patch("drive_vlc.resolver.subprocess.run", return_value=completed):
            result = resolve_via_yt_dlp("FILE123", yt_dlp_bin="/usr/local/bin/yt-dlp")

        self.assertEqual(result.method, "yt-dlp")
        self.assertEqual(result.title, "Video de prueba")
        self.assertEqual(result.url, "https://rr1---sn.googlevideo.com/videoplayback?id=abc")

    def test_resolve_via_api_uses_metadata_and_media_endpoint(self) -> None:
        meta_resp = _FakeResponse(
            url="https://www.googleapis.com/drive/v3/files/FILE123",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"name": "documental.mp4", "mimeType": "video/mp4"}).encode("utf-8"),
        )
        media_url = "https://www.googleapis.com/drive/v3/files/FILE123?alt=media&key=KEY123"
        media_resp = _FakeResponse(
            url=media_url,
            headers={"Content-Type": "video/mp4"},
        )
        with patch("drive_vlc.resolver.build_opener") as mock_opener_cls:
            mock_opener_cls.return_value.open.side_effect = [meta_resp, media_resp]
            result = resolve_via_api("FILE123", api_key="KEY123")

        self.assertEqual(result.method, "api")
        self.assertEqual(result.title, "documental.mp4")
        self.assertEqual(result.url, media_url)

    def test_auto_cascade_falls_back_to_yt_dlp_then_api(self) -> None:
        expected = ResolvedStream(url="https://cdn.example/video.mp4", method="api", title="clip.mp4")
        with (
            patch("drive_vlc.resolver.resolve_via_http", side_effect=ResolutionError("html")),
            patch("drive_vlc.resolver.resolve_via_yt_dlp", side_effect=ResolutionError("yt fail")),
            patch("drive_vlc.resolver.resolve_via_api", return_value=expected) as mock_api,
        ):
            result = resolve_drive_stream(
                "FILE123",
                method="auto",
                yt_dlp_bin="/usr/bin/yt-dlp",
                api_key="KEY123",
            )
        self.assertEqual(result, expected)
        mock_api.assert_called_once_with("FILE123", api_key="KEY123", resource_key=None)

    def test_resolve_via_http_propagates_resourcekey_and_fetches_html_title_fallback(self) -> None:
        direct_url = (
            "https://drive.usercontent.google.com/download"
            "?id=FILE123&export=download&resourcekey=0-Rk123"
        )
        bin_resp = _FakeResponse(
            url=direct_url,
            headers={"Content-Type": "video/mp4"},
        )
        view_html = (
            "<html><head><title>Charla Python - Google Drive</title></head><body></body></html>"
        ).encode("utf-8")
        view_resp = _FakeResponse(
            url="https://drive.google.com/file/d/FILE123/view?usp=sharing&resourcekey=0-Rk123",
            headers={"Content-Type": "text/html; charset=utf-8"},
            body=view_html,
        )

        with patch("drive_vlc.resolver.build_opener") as mock_opener_cls:
            mock_opener_cls.return_value.open.side_effect = [bin_resp, view_resp]
            result = resolve_via_http("FILE123", resource_key="0-Rk123")

        self.assertEqual(result.title, "Charla Python")
        first_req = mock_opener_cls.return_value.open.call_args_list[0].args[0]
        self.assertIn("resourcekey=0-Rk123", first_req.full_url)
        second_req = mock_opener_cls.return_value.open.call_args_list[1].args[0]
        self.assertIn("resourcekey=0-Rk123", second_req.full_url)


if __name__ == "__main__":
    unittest.main()
