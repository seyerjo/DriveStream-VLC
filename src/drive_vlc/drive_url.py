"""Google Drive file identifier extraction and validation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlencode, urlparse

from drive_vlc.i18n import t


_FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{15,}$")
_RESOURCE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
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


@dataclass(frozen=True)
class DriveLinkInfo:
    """Parsed Google Drive file identifier and optional legacy resource key.

    Attributes:
        file_id (str): Validated Google Drive file identifier.
        resource_key (str | None): Optional legacy ``resourcekey`` parameter.
    """

    file_id: str
    resource_key: str | None = None


def extract_drive_link(raw_input: str) -> DriveLinkInfo:
    """Extracts and validates the FILE_ID and optional resourcekey from a Drive input.

    Args:
        raw_input (str): Google Drive sharing URL or raw file identifier.

    Returns:
        DriveLinkInfo: Parsed file identifier and optional resourcekey.

    Raises:
        DriveUrlError: If the input is empty, non-Drive, a folder link, or invalid.
    """
    value = raw_input.strip()
    if not value:
        raise DriveUrlError(t("url.error.empty"))

    if _FILE_ID_PATTERN.match(value):
        return DriveLinkInfo(file_id=value, resource_key=None)

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise DriveUrlError(t("url.error.invalid", raw=raw_input))

    host = parsed.netloc.split(":", 1)[0].lower()
    if host not in _SUPPORTED_HOSTS:
        raise DriveUrlError(t("url.error.non_drive", host=host))

    if "/folders/" in parsed.path:
        raise DriveUrlError(t("url.error.folder"))

    query_params = parse_qs(parsed.query)
    raw_resource_key = (query_params.get("resourcekey") or [""])[0].strip()
    resource_key = (
        raw_resource_key if raw_resource_key and _RESOURCE_KEY_PATTERN.match(raw_resource_key) else None
    )

    for pattern in _PATH_ID_PATTERNS:
        match = pattern.search(parsed.path)
        if match:
            return DriveLinkInfo(file_id=match.group(1), resource_key=resource_key)

    query_id = query_params.get("id", [])
    if query_id and _FILE_ID_PATTERN.match(query_id[0]):
        return DriveLinkInfo(file_id=query_id[0], resource_key=resource_key)

    raise DriveUrlError(t("url.error.no_id", raw=raw_input))


def extract_file_id(raw_input: str) -> str:
    """Extracts and validates the FILE_ID from a Google Drive URL or raw ID.

    Args:
        raw_input (str): Google Drive sharing URL or raw file identifier.

    Returns:
        str: Validated Google Drive file ID.

    Raises:
        DriveUrlError: If the input is empty, non-Drive, a folder link, or invalid.
    """
    return extract_drive_link(raw_input).file_id


def build_view_url(file_id: str, resource_key: str | None = None) -> str:
    """Builds the standard Google Drive viewer URL for a file ID.

    Args:
        file_id (str): Google Drive file identifier.
        resource_key (str | None): Optional legacy resourcekey query parameter.

    Returns:
        str: Canonical Google Drive share viewer URL.
    """
    params: dict[str, str] = {"usp": "sharing"}
    if resource_key:
        params["resourcekey"] = resource_key
    return f"https://drive.google.com/file/d/{file_id}/view?{urlencode(params)}"
