"""Command-line interface for drive-vlc."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from drive_vlc.config import ConfigError, load_config
from drive_vlc.drive_url import DriveUrlError, extract_file_id
from drive_vlc.player import PlayerError, copy_to_clipboard, launch_vlc
from drive_vlc.resolver import ResolutionError, resolve_drive_stream


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser for drive-vlc.
    """
    parser = argparse.ArgumentParser(
        prog="drive-vlc",
        description=(
            "Resuelve un enlace público de Google Drive a una URL directa de streaming "
            "y lanza VLC automáticamente en segundo plano."
        ),
    )
    parser.add_argument(
        "url_or_id",
        help="Enlace compartido público de Google Drive o FILE_ID del vídeo.",
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        help="Devuelve únicamente la URL resuelta por stdout sin abrir VLC.",
    )
    parser.add_argument(
        "--cache",
        type=int,
        default=None,
        metavar="MS",
        help="Caché de red de VLC en milisegundos (por defecto: 3000 o DRIVE_VLC_CACHE_MS).",
    )
    parser.add_argument(
        "-f",
        "--fullscreen",
        action="store_true",
        help="Lanza VLC directamente en pantalla completa.",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copia la URL resuelta al portapapeles (requiere xclip, xsel o wl-copy).",
    )
    parser.add_argument(
        "--method",
        choices=("auto", "http", "yt-dlp", "api"),
        default="auto",
        help="Motor de resolución a utilizar (por defecto: auto).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Muestra detalles diagnósticos de la resolución por stderr.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the CLI entry point.

    Args:
        argv (Sequence[str] | None): Optional argument sequence for testing.

    Returns:
        int: Process exit code (0 on success, non-zero on failure).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cache is not None and args.cache < 0:
        print("Error: --cache no puede ser negativo.", file=sys.stderr)
        return 1

    try:
        config = load_config()
        file_id = extract_file_id(args.url_or_id)
        resolved = resolve_drive_stream(
            file_id,
            method=args.method,
            yt_dlp_bin=config.yt_dlp_bin,
            api_key=config.api_key,
        )
    except (ConfigError, DriveUrlError, ResolutionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Always emit only the clean URL to stdout for easy piping and automated reading.
    print(resolved.url)

    for warning in resolved.warnings:
        print(f"Aviso: {warning}", file=sys.stderr)

    if args.verbose:
        print(
            f"Detalles: método={resolved.method} | título={resolved.title or 'desconocido'} "
            f"| tipo={resolved.content_type or 'desconocido'}",
            file=sys.stderr,
        )

    if args.copy:
        copied, copy_info = copy_to_clipboard(resolved.url)
        if copied:
            print(f"URL copiada al portapapeles ({copy_info}).", file=sys.stderr)
        else:
            print(f"Aviso: {copy_info}", file=sys.stderr)

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
            print(f"Error al abrir VLC: {exc}", file=sys.stderr)
            return 1

        title_info = f" — {resolved.title}" if resolved.title else ""
        print(
            f"VLC lanzado (PID {pid}, método: {resolved.method}, caché: {cache_ms} ms){title_info}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
