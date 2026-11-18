from contextlib import redirect_stdout
import io
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from drive_vlc.cli import main
from drive_vlc.config import AppConfig
from drive_vlc.i18n import set_active_language
from drive_vlc.resolver import ResolvedStream, resolve_drive_stream
from drive_vlc.ui import ConsolePresenter


class _FakeTtyBuffer(io.StringIO):
    """In-memory text buffer simulating an interactive TTY stream."""

    def isatty(self) -> bool:
        return True


class TestUiAndInteractiveCli(unittest.TestCase):
    def tearDown(self) -> None:
        set_active_language(None)

    def test_presenter_tty_renders_nala_panels_and_steps(self) -> None:
        out = _FakeTtyBuffer()
        inp = _FakeTtyBuffer("1AbCdEfGhIjKlMnOpQrStUvWxYz\n")
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=False):
            os.environ.pop("NO_COLOR", None)
            presenter = ConsolePresenter(stream=out, input_stream=inp, animate_spinner=True)
            self.assertTrue(presenter.enabled)
            self.assertTrue(presenter.use_color)

            presenter.render_header("DriveStream VLC", "Streaming directo")
            entered = presenter.prompt_input("Pega la URL: ")
            self.assertEqual(entered, "1AbCdEfGhIjKlMnOpQrStUvWxYz")

            with presenter.live_step("Ajustando URL...", animate=True) as step:
                time.sleep(0.05)
                step.update("Verificando stream...")
                step.succeed("URL directa lista")

            presenter.render_summary("Listo", [("Título", "demo.mp4"), ("Método", "http")])

        rendered = out.getvalue()
        self.assertIn("╭─ DriveStream VLC", rendered)
        self.assertIn("╰─", rendered)
        self.assertIn("✓", rendered)
        self.assertIn("URL directa lista", rendered)
        self.assertIn("Título", rendered)
        self.assertIn("demo.mp4", rendered)
        self.assertIn("\033[", rendered)

    def test_presenter_respects_no_color_and_plain(self) -> None:
        out_nocolor = _FakeTtyBuffer()
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            presenter = ConsolePresenter(stream=out_nocolor, animate_spinner=False)
            self.assertTrue(presenter.enabled)
            self.assertFalse(presenter.use_color)
            presenter.render_header("DriveStream VLC", "Subtitle")
        self.assertIn("╭─ DriveStream VLC", out_nocolor.getvalue())
        self.assertNotIn("\033[", out_nocolor.getvalue())

        out_plain = _FakeTtyBuffer()
        presenter_plain = ConsolePresenter(stream=out_plain, plain=True)
        self.assertFalse(presenter_plain.enabled)
        presenter_plain.render_header("DriveStream VLC", "Subtitle")
        presenter_plain.render_summary("Summary", [("Key", "Val")])
        self.assertEqual(out_plain.getvalue(), "")

    def test_cli_prompts_when_url_omitted_in_tty_and_keeps_stdout_clean(self) -> None:
        cfg = AppConfig(api_key=None, cache_ms=3000, vlc_bin="/usr/bin/vlc", yt_dlp_bin=None)
        resolved = ResolvedStream(
            url="https://cdn.example/stream.mp4",
            method="http",
            title="pelicula.mp4",
        )
        stdout_buf = io.StringIO()
        stderr_tty = _FakeTtyBuffer()
        stdin_tty = _FakeTtyBuffer("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}, clear=False),
                patch("drive_vlc.cli.sys.stderr", stderr_tty),
                patch("drive_vlc.cli.sys.stdin", stdin_tty),
                patch("drive_vlc.cli.load_config", return_value=cfg),
                patch("drive_vlc.cli.resolve_drive_stream", return_value=resolved),
                patch("drive_vlc.cli.launch_vlc", return_value=5555) as mock_launch,
                redirect_stdout(stdout_buf),
            ):
                code = main(["--lang", "es", "--no-color"])

        self.assertEqual(code, 0)
        self.assertEqual(stdout_buf.getvalue().strip(), "https://cdn.example/stream.mp4")
        mock_launch.assert_called_once()
        err_text = stderr_tty.getvalue()
        self.assertIn("╭─ DriveStream VLC", err_text)
        self.assertIn("Pega la URL de Google Drive o el FILE_ID:", err_text)
        self.assertIn("Configuración cargada", err_text)
        self.assertIn("Enlace de Drive validado", err_text)
        self.assertIn("URL directa lista mediante http", err_text)
        self.assertIn("Vídeo abierto en VLC (PID 5555", err_text)
        self.assertIn("╭─ Reproducción lista", err_text)
        for color_seq in ("\033[0m", "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[96m"):
            self.assertNotIn(color_seq, err_text)

    def test_cli_missing_url_in_non_tty_returns_error(self) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        stdin_buf = io.StringIO("")

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}, clear=False),
                patch("drive_vlc.cli.sys.stderr", stderr_buf),
                patch("drive_vlc.cli.sys.stdin", stdin_buf),
                redirect_stdout(stdout_buf),
            ):
                code = main(["--lang", "en"])

        self.assertEqual(code, 1)
        self.assertEqual(stdout_buf.getvalue(), "")
        self.assertIn("Missing Google Drive URL or FILE_ID in non-interactive mode.", stderr_buf.getvalue())

    def test_cli_prompt_eof_cancels_cleanly(self) -> None:
        stdout_buf = io.StringIO()
        stderr_tty = _FakeTtyBuffer()
        stdin_tty = _FakeTtyBuffer("")

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}, clear=False),
                patch("drive_vlc.cli.sys.stderr", stderr_tty),
                patch("drive_vlc.cli.sys.stdin", stdin_tty),
                redirect_stdout(stdout_buf),
            ):
                code = main(["--lang", "es", "--no-color"])

        self.assertEqual(code, 1)
        self.assertEqual(stdout_buf.getvalue(), "")
        self.assertIn("Entrada cancelada por el usuario.", stderr_tty.getvalue())

    def test_cli_plain_flag_uses_structured_logging_even_on_tty(self) -> None:
        cfg = AppConfig(api_key=None, cache_ms=3000, vlc_bin="/usr/bin/vlc", yt_dlp_bin=None)
        resolved = ResolvedStream(url="https://cdn.example/stream.mp4", method="http", title="demo.mp4")
        stdout_buf = io.StringIO()
        stderr_tty = _FakeTtyBuffer()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}, clear=False),
                patch("drive_vlc.cli.sys.stderr", stderr_tty),
                patch("drive_vlc.cli.load_config", return_value=cfg),
                patch("drive_vlc.cli.resolve_drive_stream", return_value=resolved),
                patch("drive_vlc.cli.launch_vlc", return_value=7777),
                redirect_stdout(stdout_buf),
            ):
                code = main(["--lang", "en", "--plain", "1AbCdEfGhIjKlMnOpQrStUvWxYz"])

        self.assertEqual(code, 0)
        err_text = stderr_tty.getvalue()
        self.assertNotIn("╭─", err_text)
        self.assertIn(" - INFO - VLC launched (PID 7777", err_text)

    def test_resolver_emits_status_legends(self) -> None:
        set_active_language("es")
        statuses: list[str] = []

        from drive_vlc.resolver import ResolutionError

        with (
            patch(
                "drive_vlc.resolver.resolve_via_http",
                side_effect=lambda *args, **kwargs: (
                    kwargs["on_status"]("Ajustando URL de Drive y verificando stream HTTP directo..."),
                    (_ for _ in ()).throw(ResolutionError("fallo http")),
                ),
            ),
            patch(
                "drive_vlc.resolver.resolve_via_yt_dlp",
                side_effect=lambda *args, **kwargs: (
                    kwargs["on_status"]("Alternativa: extrayendo metadatos con yt-dlp..."),
                    ResolvedStream(url="https://cdn.example/v.mp4", method="yt-dlp"),
                )[1],
            ),
        ):
            result = resolve_drive_stream(
                "FILE123",
                method="auto",
                yt_dlp_bin="/usr/bin/yt-dlp",
                on_status=statuses.append,
            )

        self.assertEqual(result.method, "yt-dlp")
        self.assertEqual(
            statuses,
            [
                "Ajustando URL de Drive y verificando stream HTTP directo...",
                "Alternativa: extrayendo metadatos con yt-dlp...",
            ],
        )


if __name__ == "__main__":
    unittest.main()
