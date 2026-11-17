"""Command-line interface for drive-vlc."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import logging
import os
from pathlib import Path
import sys

from drive_vlc.config import ConfigError, load_config
from drive_vlc.drive_url import DriveUrlError, extract_drive_link
from drive_vlc.i18n import (
    SUPPORTED_LANGUAGES,
    detect_system_language,
    set_active_language,
    t,
)
from drive_vlc.player import PlayerError, copy_to_clipboard, launch_vlc
from drive_vlc.resolver import ResolutionError, resolve_drive_stream


def _default_log_path() -> Path:
    """Returns the XDG-compliant local log file path for diagnostic logs.

    Returns:
        Path: Target path for the rotating/appended CLI log file.
    """
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    state_root = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return state_root / "drive-vlc" / "drive-vlc.log"


def _configure_logging(verbose: bool, *, log_path: Path | None = None) -> logging.Logger:
    """Configures structured logging to stderr and an optional local log file.

    Args:
        verbose (bool): Enables DEBUG output on stderr when True; INFO otherwise.
        log_path (Path | None): Optional override path for the local debug log file.

    Returns:
        logging.Logger: Configured package logger instance.
    """
    logger = logging.getLogger("drive_vlc")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    target_log = _default_log_path() if log_path is None else log_path
    try:
        target_log.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target_log, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Do not abort CLI execution if the local log directory is read-only.
        pass

    return logger


def _resolve_pre_lang(argv: Sequence[str] | None) -> str | None:
    """Pre-parses --lang via argparse so --help renders in the chosen language.

    Args:
        argv (Sequence[str] | None): Optional argument sequence passed to main().

    Returns:
        str | None: Explicit language flag value if valid, otherwise ``None``.
    """
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--lang", choices=SUPPORTED_LANGUAGES, default=None)
    pre_args, _ = pre_parser.parse_known_args(argv)
    return pre_args.lang


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser using the active language catalog.

    Returns:
        argparse.ArgumentParser: Configured argument parser for drive-vlc.
    """
    parser = argparse.ArgumentParser(
        prog="drive-vlc",
        description=t("cli.description"),
    )
    parser.add_argument(
        "url_or_id",
        help=t("cli.help.url_or_id"),
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        help=t("cli.help.url_only"),
    )
    parser.add_argument(
        "--cache",
        type=int,
        default=None,
        metavar="MS",
        help=t("cli.help.cache"),
    )
    parser.add_argument(
        "-f",
        "--fullscreen",
        action="store_true",
        help=t("cli.help.fullscreen"),
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help=t("cli.help.copy"),
    )
    parser.add_argument(
        "--method",
        choices=("auto", "http", "yt-dlp", "api"),
        default="auto",
        help=t("cli.help.method"),
    )
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        default=None,
        help=t("cli.help.lang"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=t("cli.help.verbose"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the CLI entry point.

    Args:
        argv (Sequence[str] | None): Optional argument sequence for testing.

    Returns:
        int: Process exit code (0 on success, non-zero on failure).
    """
    selected_lang = detect_system_language(cli_lang=_resolve_pre_lang(argv))
    set_active_language(selected_lang)

    parser = build_parser()
    args = parser.parse_args(argv)
    logger = _configure_logging(args.verbose)

    if args.cache is not None and args.cache < 0:
        logger.error(t("cli.error.negative_cache"))
        return 1

    try:
        config = load_config()
        link_info = extract_drive_link(args.url_or_id)
        resolved = resolve_drive_stream(
            link_info.file_id,
            method=args.method,
            yt_dlp_bin=config.yt_dlp_bin,
            api_key=config.api_key,
            resource_key=link_info.resource_key,
        )
    except (ConfigError, DriveUrlError, ResolutionError) as exc:
        logger.error("%s", exc)
        return 1

    # Always emit only the clean URL to stdout for easy piping and automated reading.
    print(resolved.url)

    for warning in resolved.warnings:
        logger.warning("%s", warning)

    unknown_label = t("cli.unknown")
    logger.debug(
        t(
            "cli.verbose.details",
            method=resolved.method,
            title=resolved.title or unknown_label,
            content_type=resolved.content_type or unknown_label,
        )
    )

    if args.copy:
        copied, copy_info = copy_to_clipboard(resolved.url)
        if copied:
            logger.info(t("cli.copy.success", backend=copy_info))
        else:
            logger.warning("%s", copy_info)

    if not args.url_only:
        cache_ms = config.cache_ms if args.cache is None else args.cache
        try:
            pid = launch_vlc(
                resolved.url,
                vlc_bin=config.vlc_bin,
                cache_ms=cache_ms,
                title=resolved.title,
                fullscreen=args.fullscreen,
            )
        except PlayerError as exc:
            logger.error(t("cli.error.vlc_launch", error=exc))
            return 1

        title_suffix = f" — {resolved.title}" if resolved.title else ""
        logger.info(
            t(
                "cli.vlc.launched",
                pid=pid,
                method=resolved.method,
                cache_ms=cache_ms,
                title_suffix=title_suffix,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
