from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import patch

from drive_vlc.cli import main
from drive_vlc.config import AppConfig
from drive_vlc.player import build_vlc_command, copy_to_clipboard, launch_vlc
from drive_vlc.resolver import ResolvedStream


class TestPlayerAndCli(unittest.TestCase):
    def test_build_vlc_command(self) -> None:
        cmd = build_vlc_command(
            "https://example.com/video.mp4",
            vlc_bin="/usr/bin/vlc",
            cache_ms=4000,
            title="Mi Video",
            fullscreen=True,
        )
        self.assertEqual(
            cmd,
            [
                "/usr/bin/vlc",
                "--network-caching=4000",
                "--fullscreen",
                "--meta-title=Mi Video",
                "https://example.com/video.mp4",
            ],
        )

    def test_launch_vlc_detaches_process(self) -> None:
        with (
            patch("drive_vlc.player.shutil.which", return_value="/usr/bin/vlc"),
            patch("drive_vlc.player.subprocess.Popen") as mock_popen,
        ):
            mock_popen.return_value.pid = 4321
            pid = launch_vlc("https://example.com/video.mp4", vlc_bin="/usr/bin/vlc")

        self.assertEqual(pid, 4321)
        kwargs = mock_popen.call_args.kwargs
        self.assertTrue(kwargs["start_new_session"])

    def test_copy_to_clipboard_warns_when_no_backend(self) -> None:
        with patch("drive_vlc.player.shutil.which", return_value=None):
            ok, message = copy_to_clipboard("https://example.com/video.mp4")
        self.assertFalse(ok)
        self.assertIn("xclip", message)

    def test_cli_url_only_does_not_launch_vlc(self) -> None:
        cfg = AppConfig(api_key=None, cache_ms=3000, vlc_bin="/usr/bin/vlc", yt_dlp_bin=None)
        resolved = ResolvedStream(url="https://cdn.example/stream.mp4", method="http", title="demo.mp4")
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with (
            patch("drive_vlc.cli.load_config", return_value=cfg),
            patch("drive_vlc.cli.resolve_drive_stream", return_value=resolved),
            patch("drive_vlc.cli.launch_vlc") as mock_launch,
            redirect_stdout(stdout_buf),
            redirect_stderr(stderr_buf),
        ):
            code = main(["--url-only", "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view"])

        self.assertEqual(code, 0)
        self.assertEqual(stdout_buf.getvalue().strip(), "https://cdn.example/stream.mp4")
        mock_launch.assert_not_called()

    def test_cli_default_launches_vlc(self) -> None:
        cfg = AppConfig(api_key=None, cache_ms=3000, vlc_bin="/usr/bin/vlc", yt_dlp_bin=None)
        resolved = ResolvedStream(url="https://cdn.example/stream.mp4", method="http", title="demo.mp4")
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with (
            patch("drive_vlc.cli.load_config", return_value=cfg),
            patch("drive_vlc.cli.resolve_drive_stream", return_value=resolved),
            patch("drive_vlc.cli.launch_vlc", return_value=9876) as mock_launch,
            redirect_stdout(stdout_buf),
            redirect_stderr(stderr_buf),
        ):
            code = main(["-f", "--cache", "5000", "1AbCdEfGhIjKlMnOpQrStUvWxYz"])

        self.assertEqual(code, 0)
        self.assertEqual(stdout_buf.getvalue().strip(), "https://cdn.example/stream.mp4")
        mock_launch.assert_called_once_with(
            "https://cdn.example/stream.mp4",
            vlc_bin="/usr/bin/vlc",
            cache_ms=5000,
            title="demo.mp4",
            fullscreen=True,
        )
        self.assertIn("PID 9876", stderr_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
