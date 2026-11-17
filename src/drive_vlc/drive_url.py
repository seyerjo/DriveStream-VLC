"""Google Drive file identifier extraction and validation."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from drive_vlc.i18n import t


_FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{15,}$")
_PATH_ID_PATTERNS = (
    re.compile(r"^/file/d/([A-Za-z0-9_-]{15,})(?:/|$)"),
    re.compile(r"^/d/([A-Za-z0-9_-]{15,})(?:/|$)"),
)
_SUPPORTED_HOSTS = {
    "drive.google.com",
    "drive.usercontent.google.com",
    "docs.google.com",
}


class DriveUrlError(ValueError):
    """Raised when a Google Drive URL or file ID cannot be parsed or is unsupported."""


def extract_file_id(raw_input: str) -> str:
    """Extracts and validates the FILE_ID from a Google Drive URL or raw ID.

    Args:
        raw_input (str): Google Drive sharing URL or raw file identifier.

    Returns:
        str: Validated Google Drive file ID.

    Raises:
        DriveUrlError: If the input is empty, non-Drive, a folder link, or invalid.
    """
    value = raw_input.strip()
    if not value:
        raise DriveUrlError(t("url.error.empty"))

    if _FILE_ID_PATTERN.match(value):
        return value

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise DriveUrlError(t("url.error.invalid", raw=raw_input))

    host = parsed.netloc.split(":", 1)[0].lower()
    if host not in _SUPPORTED_HOSTS:
        raise DriveUrlError(t("url.error.non_drive", host=host))

    if "/folders/" in parsed.path:
        raise DriveUrlError(t("url.error.folder"))

    for pattern in _PATH_ID_PATTERNS:
        match = pattern.search(parsed.path)
        if match:
            return match.group(1)

    query_id = parse_qs(parsed.query).get("id", [])
    if query_id and _FILE_ID_PATTERN.match(query_id[0]):
        return query_id[0]

    raise DriveUrlError(t("url.error.no_id", raw=raw_input))


def build_view_url(file_id: str) -> str:
    """Builds the standard Google Drive viewer URL for a file ID.

    Args:
        file_id (str): Google Drive file identifier.

    Returns:
        str: Canonical Google Drive share viewer URL.
    """
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
