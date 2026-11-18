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
from drive_vlc.ui import ConsolePresenter


def _default_log_path() -> Path:
    """Returns the XDG-compliant local log file path for diagnostic logs.

    Returns:
        Path: Target path for the rotating/appended CLI log file.
    """
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    state_root = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return state_root / "drive-vlc" / "drive-vlc.log"


def _configure_logging(
    verbose: bool,
    *,
    stream_to_stderr: bool = True,
    log_path: Path | None = None,
) -> logging.Logger:
    """Configures structured logging to stderr and an optional local log file.

    Args:
        verbose (bool): Enables DEBUG output on stderr when True; INFO otherwise.
        stream_to_stderr (bool): Attaches a stderr StreamHandler when True.
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

    if stream_to_stderr:
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
        nargs="?",
        default=None,
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
    parser.add_argument(
        "--plain",
        action="store_true",
        help=t("cli.help.plain"),
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help=t("cli.help.no_color"),
    )
    return parser


def _emit_error(presenter: ConsolePresenter, logger: logging.Logger, message: str) -> None:
    """Records an error in structured logs and renders it on the TTY presenter if active.

    Args:
        presenter (ConsolePresenter): Active console presenter.
        logger (logging.Logger): Package logger instance.
        message (str): Localized error message.
    """
    logger.error("%s", message)
    presenter.render_error(message)


def _emit_warning(presenter: ConsolePresenter, logger: logging.Logger, message: str) -> None:
    """Records a warning in structured logs and renders it on the TTY presenter if active.

    Args:
        presenter (ConsolePresenter): Active console presenter.
        logger (logging.Logger): Package logger instance.
        message (str): Localized warning message.
    """
    logger.warning("%s", message)
    presenter.render_warning(message)


def _resolve_input_url_or_id(
    raw_arg: str | None,
    presenter: ConsolePresenter,
    logger: logging.Logger,
) -> str | None:
    """Obtains the Drive URL or FILE_ID from CLI args or an interactive TTY prompt.

    Args:
        raw_arg (str | None): Positional CLI argument value, if supplied.
        presenter (ConsolePresenter): Active console presenter for prompting.
        logger (logging.Logger): Package logger instance.

    Returns:
        str | None: Non-empty trimmed URL/ID, or ``None`` if missing or cancelled.
    """
    cleaned = (raw_arg or "").strip()
    if cleaned:
        return cleaned

    if not bool(getattr(presenter.input_stream, "isatty", lambda: False)()):
        _emit_error(presenter, logger, t("cli.error.missing_url"))
        return None

    try:
        entered = presenter.prompt_input(t("cli.prompt.url"))
    except (EOFError, KeyboardInterrupt):
        if presenter.enabled:
            presenter.write_line()
        _emit_error(presenter, logger, t("cli.prompt.cancelled"))
        return None

    if not entered:
        _emit_error(presenter, logger, t("url.error.empty"))
        return None

    return entered


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
    presenter = ConsolePresenter(
        plain=args.plain,
        no_color=args.no_color,
        verbose=args.verbose,
    )
    logger = _configure_logging(args.verbose, stream_to_stderr=not presenter.enabled)

    if args.cache is not None and args.cache < 0:
        _emit_error(presenter, logger, t("cli.error.negative_cache"))
        return 1

    presenter.render_header(t("ui.banner.title"), t("ui.banner.subtitle"))

    raw_input = _resolve_input_url_or_id(args.url_or_id, presenter, logger)
    if raw_input is None:
        return 1

    with presenter.live_step(t("ui.step.config.start"), animate=False) as step:
        logger.info(t("ui.step.config.start"))
        try:
            config = load_config()
        except ConfigError as exc:
            step.fail(str(exc))
            logger.error("%s", exc)
            return 1
        step.succeed(t("ui.step.config.done"))
        logger.info(t("ui.step.config.done"))

    with presenter.live_step(t("ui.step.parse.start"), animate=False) as step:
        logger.info(t("ui.step.parse.start"))
        try:
            link_info = extract_drive_link(raw_input)
        except DriveUrlError as exc:
            step.fail(str(exc))
            logger.error("%s", exc)
            return 1
        parse_done = t("ui.step.parse.done", file_id=link_info.file_id)
        step.succeed(parse_done)
        logger.info(parse_done)

    with presenter.live_step(t("ui.step.resolve.start"), animate=True) as step:
        logger.info(t("ui.step.resolve.start"))
        try:
            resolved = resolve_drive_stream(
                link_info.file_id,
                method=args.method,
                yt_dlp_bin=config.yt_dlp_bin,
                api_key=config.api_key,
                resource_key=link_info.resource_key,
                on_status=step.update,
            )
        except ResolutionError as exc:
            step.fail(str(exc))
            logger.error("%s", exc)
            return 1
        resolve_done = t("ui.step.resolve.done", method=resolved.method)
        step.succeed(resolve_done)
        logger.info(resolve_done)

    # Always emit only the clean URL to stdout for easy piping and automated reading.
    print(resolved.url)

    for warning in resolved.warnings:
        _emit_warning(presenter, logger, warning)

    unknown_label = t("cli.unknown")
    logger.debug(
        t(
            "cli.verbose.details",
            method=resolved.method,
            title=resolved.title or unknown_label,
            content_type=resolved.content_type or unknown_label,
        )
    )

    clipboard_status: str | None = None
    if args.copy:
        with presenter.live_step(t("ui.step.copy.start"), animate=False) as step:
            logger.info(t("ui.step.copy.start"))
            copied, copy_info = copy_to_clipboard(resolved.url)
            if copied:
                step.succeed(t("ui.step.copy.done", backend=copy_info))
                logger.info(t("cli.copy.success", backend=copy_info))
                clipboard_status = copy_info
            else:
                step.warn(copy_info)
                logger.warning("%s", copy_info)

    summary_rows: list[tuple[str, str]] = [
        (t("ui.label.title"), resolved.title or unknown_label),
        (t("ui.label.method"), resolved.method),
    ]
    if clipboard_status:
        summary_rows.append((t("ui.label.clipboard"), clipboard_status))

    if not args.url_only:
        cache_ms = config.cache_ms if args.cache is None else args.cache
        with presenter.live_step(t("ui.step.vlc.start"), animate=True) as step:
            logger.info(t("ui.step.vlc.start"))
            try:
                pid = launch_vlc(
                    resolved.url,
                    vlc_bin=config.vlc_bin,
                    cache_ms=cache_ms,
                    title=resolved.title,
                    fullscreen=args.fullscreen,
                )
            except PlayerError as exc:
                err_msg = t("cli.error.vlc_launch", error=exc)
                step.fail(err_msg)
                logger.error("%s", err_msg)
                return 1
            step.succeed(t("ui.step.vlc.done", pid=pid, cache_ms=cache_ms))

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
        summary_rows.append((t("ui.label.cache"), f"{cache_ms} ms"))
        summary_rows.append((t("ui.label.pid"), str(pid)))
        presenter.render_summary(t("ui.summary.title"), summary_rows)
    else:
        presenter.render_summary(t("ui.summary.url_only"), summary_rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
