from pathlib import Path
import tempfile
import unittest

from drive_vlc.config import ConfigError, DEFAULT_CACHE_MS, load_config, parse_env_file


class TestConfig(unittest.TestCase):
    def test_parse_env_file_handles_comments_export_and_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                '# Sample comment\n'
                'GOOGLE_DRIVE_API_KEY="abc123"\n'
                "export DRIVE_VLC_CACHE_MS='4500'\n"
                "EMPTY_KEY=\n",
                encoding="utf-8",
            )
            parsed = parse_env_file(env_path)
            self.assertEqual(parsed["GOOGLE_DRIVE_API_KEY"], "abc123")
            self.assertEqual(parsed["DRIVE_VLC_CACHE_MS"], "4500")
            self.assertEqual(parsed["EMPTY_KEY"], "")

    def test_priority_order_env_then_user_then_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo_env = tmp / "repo.env"
            user_env = tmp / "user.env"
            repo_env.write_text(
                "GOOGLE_DRIVE_API_KEY=repo_key\nDRIVE_VLC_CACHE_MS=2000\n",
                encoding="utf-8",
            )
            user_env.write_text(
                "GOOGLE_DRIVE_API_KEY=user_key\nDRIVE_VLC_CACHE_MS=5000\n",
                encoding="utf-8",
            )

            cfg = load_config(
                user_env_path=user_env,
                repo_env_path=repo_env,
                environ={"GOOGLE_DRIVE_API_KEY": "shell_key"},
            )
            self.assertEqual(cfg.api_key, "shell_key")
            self.assertEqual(cfg.cache_ms, 5000)

    def test_defaults_and_invalid_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            cfg = load_config(
                user_env_path=tmp / "missing_user.env",
                repo_env_path=tmp / "missing_repo.env",
                environ={},
            )
            self.assertEqual(cfg.cache_ms, DEFAULT_CACHE_MS)
            self.assertIsNone(cfg.api_key)

            with self.assertRaises(ConfigError):
                load_config(
                    user_env_path=tmp / "missing_user.env",
                    repo_env_path=tmp / "missing_repo.env",
                    environ={"DRIVE_VLC_CACHE_MS": "no_es_numero"},
                )


if __name__ == "__main__":
    unittest.main()
