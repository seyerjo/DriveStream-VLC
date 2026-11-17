"""Linux VLC launcher and clipboard integration."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from drive_vlc.i18n import t


class PlayerError(RuntimeError):
    """Raised when launching VLC fails."""


def build_vlc_command(
    url: str,
    *,
    vlc_bin: str,
    cache_ms: int = 3000,
    title: str | None = None,
    fullscreen: bool = False,
) -> list[str]:
    """Builds the argument list for invoking VLC.

    Args:
        url (str): Direct streaming URL to play.
        vlc_bin (str): Path or command name of the VLC executable.
        cache_ms (int): Network cache duration in milliseconds.
        title (str | None): Optional media title displayed in VLC.
        fullscreen (bool): Whether to pass --fullscreen.

    Returns:
        list[str]: Sanitized argument list suitable for subprocess execution.
    """
    cmd = [vlc_bin, f"--network-caching={cache_ms}"]
    if fullscreen:
        cmd.append("--fullscreen")
    if title:
        cmd.append(f"--meta-title={title}")
    cmd.append(url)
    return cmd


def launch_vlc(
    url: str,
    *,
    vlc_bin: str,
    cache_ms: int = 3000,
    title: str | None = None,
    fullscreen: bool = False,
) -> int:
    """Launches VLC detached in a new session and returns its PID.

    Args:
        url (str): Direct streaming URL to play.
        vlc_bin (str): Path or command name of the VLC executable.
        cache_ms (int): Network cache duration in milliseconds.
        title (str | None): Optional media title displayed in VLC.
        fullscreen (bool): Whether to start VLC in fullscreen mode.

    Returns:
        int: Process ID of the launched VLC instance.

    Raises:
        PlayerError: If the VLC binary is missing or fails to start.
    """
    resolved_bin = shutil.which(vlc_bin) or (vlc_bin if Path(vlc_bin).is_file() else None)
    if not resolved_bin:
        raise PlayerError(t("player.error.missing_bin", vlc_bin=vlc_bin))

    cmd = build_vlc_command(
        url,
        vlc_bin=resolved_bin,
        cache_ms=cache_ms,
        title=title,
        fullscreen=fullscreen,
    )
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise PlayerError(
            t("player.error.launch_failed", vlc_bin=resolved_bin, error=exc)
        ) from exc

    return proc.pid


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    """Copies text to the system clipboard using available Linux CLI tools.

    Args:
        text (str): String to place into the clipboard.

    Returns:
        tuple[bool, str]: Success flag paired with the backend name or an informational message.
    """
    backends: list[tuple[str, list[str]]] = [
        ("wl-copy", ["wl-copy"]),
        ("xclip", ["xclip", "-selection", "clipboard"]),
        ("xsel", ["xsel", "--clipboard", "--input"]),
    ]
    for name, args in backends:
        binary = shutil.which(name)
        if not binary:
            continue
        try:
            proc = subprocess.run(
                [binary, *args[1:]],
                input=text,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            return True, name

    return (
        False,
        t("player.copy.no_backend"),
    )
