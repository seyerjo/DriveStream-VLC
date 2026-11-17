"""Configuration loader for drive-vlc."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from drive_vlc.i18n import t


DEFAULT_CACHE_MS = 3000
REPO_ROOT = Path(__file__).resolve().parents[2]
USER_CONFIG_ENV = Path.home() / ".config" / "drive-vlc" / ".env"
REPO_CONFIG_ENV = REPO_ROOT / ".env"


class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Effective configuration resolved across environment and .env files.

    Attributes:
        api_key (str | None): Optional Google Drive API v3 key.
        cache_ms (int): VLC network cache duration in milliseconds.
        vlc_bin (str): Path or executable name for VLC.
        yt_dlp_bin (str | None): Path or executable name for yt-dlp, if available.
    """

    api_key: str | None
    cache_ms: int
    vlc_bin: str
    yt_dlp_bin: str | None


def parse_env_file(path: Path) -> dict[str, str]:
    """Parses a simple .env file using only the Python standard library.

    Args:
        path (Path): Path to the .env file.

    Returns:
        dict[str, str]: Key-value pairs parsed from the file.
    """
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, raw_val = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        val = raw_val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        values[key] = val

    return values


def _resolve_vlc_bin(configured: str | None) -> str:
    """Resolves the VLC executable path from config, PATH, or standard Linux location.

    Args:
        configured (str | None): Explicit VLC binary path configured by the user.

    Returns:
        str: Executable name or path for VLC.
    """
    if configured:
        return configured
    found = shutil.which("vlc")
    if found:
        return found
    return "/usr/bin/vlc"


def _resolve_yt_dlp_bin(configured: str | None) -> str | None:
    """Resolves the optional yt-dlp executable path from config, PATH, or ~/.local/bin.

    Args:
        configured (str | None): Explicit yt-dlp binary path configured by the user.

    Returns:
        str | None: Path to yt-dlp if available, otherwise ``None``.
    """
    if configured:
        return configured
    found = shutil.which("yt-dlp")
    if found:
        return found
    local_bin = Path.home() / ".local" / "bin" / "yt-dlp"
    if local_bin.is_file():
        return str(local_bin)
    return None


def load_config(
    *,
    user_env_path: Path = USER_CONFIG_ENV,
    repo_env_path: Path = REPO_CONFIG_ENV,
    environ: dict[str, str] | None = None,
) -> AppConfig:
    """Loads configuration with precedence: env -> ~/.config/drive-vlc/.env -> repo/.env.

    Args:
        user_env_path (Path): User-level .env configuration path.
        repo_env_path (Path): Repository-level .env configuration path.
        environ (dict[str, str] | None): Optional environment mapping override.

    Returns:
        AppConfig: Resolved runtime configuration.

    Raises:
        ConfigError: If DRIVE_VLC_CACHE_MS is not a valid non-negative integer.
    """
    merged: dict[str, str] = {}
    merged.update(parse_env_file(repo_env_path))
    merged.update(parse_env_file(user_env_path))

    env_source = os.environ if environ is None else environ
    for key in (
        "GOOGLE_DRIVE_API_KEY",
        "DRIVE_VLC_CACHE_MS",
        "DRIVE_VLC_BIN",
        "DRIVE_VLC_YT_DLP_BIN",
    ):
        if key in env_source and env_source[key].strip() != "":
            merged[key] = env_source[key].strip()

    api_key = merged.get("GOOGLE_DRIVE_API_KEY", "").strip() or None

    raw_cache = merged.get("DRIVE_VLC_CACHE_MS", "").strip()
    if raw_cache:
        try:
            cache_ms = int(raw_cache)
        except ValueError as exc:
            raise ConfigError(t("config.error.cache_int", value=raw_cache)) from exc
        if cache_ms < 0:
            raise ConfigError(t("config.error.cache_negative"))
    else:
        cache_ms = DEFAULT_CACHE_MS

    vlc_bin = _resolve_vlc_bin(merged.get("DRIVE_VLC_BIN", "").strip() or None)
    yt_dlp_bin = _resolve_yt_dlp_bin(merged.get("DRIVE_VLC_YT_DLP_BIN", "").strip() or None)

    return AppConfig(
        api_key=api_key,
        cache_ms=cache_ms,
        vlc_bin=vlc_bin,
        yt_dlp_bin=yt_dlp_bin,
    )
