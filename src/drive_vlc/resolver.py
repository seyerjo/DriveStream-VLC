"""Google Drive public link resolution engines for portable direct VLC streaming."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from http.client import HTTPMessage
import json
import re
import subprocess
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from drive_vlc.drive_url import build_view_url
from drive_vlc.i18n import t


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15


class ResolutionError(RuntimeError):
    """Raised when resolving a Google Drive video into a direct URL fails."""


class PrivateOrBlockedError(ResolutionError):
    """Raised when the file is private, requires login, or hits a quota limit.

    Attributes:
        is_private (bool): True when the failure clearly stems from private access.
    """

    def __init__(self, message: str, *, is_private: bool = False) -> None:
        """Initializes PrivateOrBlockedError with privacy classification.

        Args:
            message (str): Localized error message.
            is_private (bool): Whether the remote response indicated a login/private wall.
        """
        super().__init__(message)
        self.is_private = is_private


@dataclass(frozen=True)
class ResolvedStream:
    """Resolved streaming metadata ready to be passed to VLC.

    Attributes:
        url (str): Direct portable streaming URL.
        method (str): Resolution engine used ('http', 'yt-dlp', or 'api').
        title (str | None): Optional video filename or title.
        content_type (str | None): Detected MIME type if available.
        warnings (tuple[str, ...]): Non-fatal warnings surfaced during resolution.
    """

    url: str
    method: str
    title: str | None = None
    content_type: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


class _DownloadFormParser(HTMLParser):
    """Parses the virus-scan confirmation form and title candidates from Drive HTML."""

    def __init__(self) -> None:
        """Initializes parser state for form inputs, filename link, and HTML title."""
        super().__init__()
        self.in_target_form = False
        self.form_action: str | None = None
        self.form_inputs: dict[str, str] = {}
        self.in_name_span = False
        self.in_name_link = False
        self.in_title = False
        self.filename_parts: list[str] = []
        self.title_parts: list[str] = []
        self.og_title: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Processes HTML opening tags to locate the download form and title metadata.

        Args:
            tag (str): Lowercase or raw HTML tag name.
            attrs (list[tuple[str, str | None]]): Tag attribute key-value pairs.
        """
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        tag_l = tag.lower()

        if tag_l == "form":
            action = attr_map.get("action", "")
            form_id = attr_map.get("id", "")
            if form_id == "download-form" or "download" in action:
                self.in_target_form = True
                self.form_action = action
                self.form_inputs = {}
        elif tag_l == "input" and self.in_target_form:
            name = attr_map.get("name", "")
            if name:
                self.form_inputs[name] = attr_map.get("value", "")
        elif tag_l == "span" and "uc-name-size" in attr_map.get("class", ""):
            self.in_name_span = True
        elif tag_l == "a" and self.in_name_span:
            self.in_name_link = True
        elif tag_l == "title":
            self.in_title = True
        elif tag_l == "meta" and attr_map.get("property", "").lower() == "og:title":
            content = attr_map.get("content", "").strip()
            if content:
                self.og_title = content

    def handle_endtag(self, tag: str) -> None:
        """Processes HTML closing tags to reset active parser sections.

        Args:
            tag (str): HTML closing tag name.
        """
        tag_l = tag.lower()
        if tag_l == "form" and self.in_target_form:
            self.in_target_form = False
        elif tag_l == "a" and self.in_name_link:
            self.in_name_link = False
        elif tag_l == "span" and self.in_name_span:
            self.in_name_span = False
        elif tag_l == "title" and self.in_title:
            self.in_title = False

    def handle_data(self, data: str) -> None:
        """Collects character data inside the filename link and HTML title elements.

        Args:
            data (str): Text content encountered within the current tag.
        """
        if self.in_name_link:
            self.filename_parts.append(data)
        elif self.in_title:
            self.title_parts.append(data)


class _CaptureRedirectHandler(HTTPRedirectHandler):
    """Records intermediate redirect URLs during HTTP resolution."""

    def __init__(self) -> None:
        """Initializes an empty redirect history list."""
        super().__init__()
        self.visited_urls: list[str] = []

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        """Logs each HTTP redirect target before delegating to the base handler.

        Args:
            req (Request): Original HTTP request.
            fp (IO[bytes]): Response body stream.
            code (int): HTTP redirect status code.
            msg (str): HTTP status reason phrase.
            headers (HTTPMessage): Response headers.
            newurl (str): Target redirect URL.

        Returns:
            Request | None: Follow-up request object or ``None``.
        """
        self.visited_urls.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fix_latin1_utf8_mojibake(value: str) -> str:
    """Fixes HTTP header values containing UTF-8 bytes decoded as latin-1.

    Args:
        value (str): Raw decoded header string.

    Returns:
        str: Re-decoded UTF-8 string when applicable, or original string.
    """
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _decode_content_disposition_filename(header_value: str | None) -> str | None:
    """Extracts and decodes the filename from a Content-Disposition header.

    Args:
        header_value (str | None): Raw Content-Disposition HTTP header.

    Returns:
        str | None: Decoded filename if present, otherwise ``None``.
    """
    if not header_value:
        return None
    star_match = re.search(r"filename\*\s*=\s*([^;]+)", header_value, flags=re.IGNORECASE)
    if star_match:
        raw = star_match.group(1).strip().strip('"').strip("'")
        if "''" in raw:
            _, encoded = raw.split("''", 1)
            return unquote(encoded)
        return unquote(raw)

    plain_match = re.search(r'filename\s*=\s*"([^"]+)"', header_value, flags=re.IGNORECASE)
    if plain_match:
        return _fix_latin1_utf8_mojibake(plain_match.group(1).strip())

    bare_match = re.search(r"filename\s*=\s*([^;]+)", header_value, flags=re.IGNORECASE)
    if bare_match:
        return _fix_latin1_utf8_mojibake(bare_match.group(1).strip().strip('"'))
    return None


def _is_login_redirect(url: str) -> bool:
    """Checks whether a resolved URL points to Google's sign-in host.

    Args:
        url (str): Target or final URL to inspect.

    Returns:
        bool: True if the host belongs to ``accounts.google.com``.
    """
    host = urlparse(url).netloc.lower()
    return "accounts.google.com" in host


def _detect_html_block_reason(html_text: str) -> str | None:
    """Detects quota exhaustion or private access messages inside Drive HTML.

    Args:
        html_text (str): Decoded HTML body from Google Drive.

    Returns:
        str | None: Localized reason message if blocked, otherwise ``None``.
    """
    lowered = html_text.lower()
    if "too many users have viewed or downloaded this file recently" in lowered or "quota exceeded" in lowered:
        return t("resolver.error.quota")
    if "you need access" in lowered or "request access" in lowered or "sign in" in lowered:
        return t("resolver.error.private")
    return None


def _build_url_with_params(base_url: str, params: dict[str, str]) -> str:
    """Merges query parameters onto a base URL cleanly.

    Args:
        base_url (str): Target endpoint URL.
        params (dict[str, str]): Query parameters to add or override.

    Returns:
        str: Reconstructed URL with merged query string.
    """
    parsed = urlparse(base_url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update(params)
    return urlunparse(parsed._replace(query=urlencode(existing)))


def _probe_direct_stream(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, str | None, str | None, str]:
    """Probes a candidate URL without cookies to confirm it returns binary media instead of HTML.

    Args:
        url (str): Candidate direct download URL.
        timeout (int): Network timeout in seconds.

    Returns:
        tuple[bool, str | None, str | None, str]: Success flag, filename, MIME type, final URL.

    Raises:
        PrivateOrBlockedError: If redirected to login or denied with 401/403.
        ResolutionError: On 404, unexpected HTTP error, or network error.
    """
    redirect_handler = _CaptureRedirectHandler()
    opener = build_opener(redirect_handler)
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Range": "bytes=0-0",
        },
        method="GET",
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            if _is_login_redirect(final_url):
                raise PrivateOrBlockedError(t("resolver.error.login_redirect"), is_private=True)
            content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            filename = _decode_content_disposition_filename(resp.headers.get("Content-Disposition"))
            if content_type == "text/html":
                return False, filename, content_type, final_url
            return True, filename, (content_type or None), final_url
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise PrivateOrBlockedError(
                t("resolver.error.access_denied", code=exc.code)
            ) from exc
        if exc.code == 404:
            raise ResolutionError(t("resolver.error.not_found")) from exc
        raise ResolutionError(t("resolver.error.http_probe", code=exc.code)) from exc
    except URLError as exc:
        raise ResolutionError(t("resolver.error.network", reason=exc.reason)) from exc


def _clean_html_title(raw_title: str | None) -> str | None:
    """Normalizes a Drive HTML title/og:title and discards generic boilerplate titles.

    Args:
        raw_title (str | None): Raw title text extracted from HTML metadata.

    Returns:
        str | None: Cleaned video filename/title or ``None`` if generic/empty.
    """
    if not raw_title:
        return None
    cleaned = unescape(raw_title).strip()
    if cleaned.endswith(" - Google Drive"):
        cleaned = cleaned[: -len(" - Google Drive")].strip()
    generic = {
        "",
        "google drive",
        "google drive - virus scan warning",
        "virus scan warning",
        "sign in - google accounts",
    }
    if cleaned.lower() in generic:
        return None
    return cleaned


def _fetch_view_page_title(
    file_id: str,
    *,
    resource_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str | None:
    """Fetches the Drive viewer page to extract a fallback title when Content-Disposition is absent.

    Args:
        file_id (str): Google Drive file ID.
        resource_key (str | None): Optional legacy resourcekey parameter.
        timeout (int): Network timeout in seconds.

    Returns:
        str | None: Extracted title if available, otherwise ``None``.
    """
    view_url = build_view_url(file_id, resource_key=resource_key)
    opener = build_opener()
    req = Request(view_url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with opener.open(req, timeout=timeout) as resp:
            content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type != "text/html":
                return None
            html_text = resp.read(131_072).decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError):
        return None

    parser = _DownloadFormParser()
    parser.feed(html_text)
    return _clean_html_title(parser.og_title) or _clean_html_title("".join(parser.title_parts))


def resolve_via_http(
    file_id: str,
    timeout: int = DEFAULT_TIMEOUT,
    *,
    resource_key: str | None = None,
) -> ResolvedStream:
    """Resolves a direct streaming URL via unauthenticated HTTP requests.

    Args:
        file_id (str): Google Drive file ID.
        timeout (int): Network timeout in seconds per request.
        resource_key (str | None): Optional legacy resourcekey parameter.

    Returns:
        ResolvedStream: Verified direct streaming URL and metadata.

    Raises:
        PrivateOrBlockedError: If the file requires authentication or is forbidden.
        ResolutionError: If no direct non-HTML stream could be confirmed.
    """
    extra_params = {"resourcekey": resource_key} if resource_key else {}
    candidates = [
        _build_url_with_params(
            "https://drive.google.com/uc",
            {"export": "download", "id": file_id, **extra_params},
        ),
        _build_url_with_params(
            "https://drive.usercontent.google.com/download",
            {"id": file_id, "export": "download", "confirm": "t", **extra_params},
        ),
    ]
    extracted_title: str | None = None
    last_error: str | None = None

    for candidate in candidates:
        redirect_handler = _CaptureRedirectHandler()
        opener = build_opener(redirect_handler)
        req = Request(
            candidate,
            headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
            method="GET",
        )
        try:
            with opener.open(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                if _is_login_redirect(final_url):
                    raise PrivateOrBlockedError(t("resolver.error.login_redirect"), is_private=True)
                content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
                title = _decode_content_disposition_filename(resp.headers.get("Content-Disposition"))
                if content_type != "text/html":
                    resolved_title = title or extracted_title or _fetch_view_page_title(
                        file_id, resource_key=resource_key, timeout=timeout
                    )
                    return ResolvedStream(
                        url=final_url,
                        method="http",
                        title=resolved_title,
                        content_type=content_type or None,
                    )

                # Read up to 256 KB of the intermediate confirmation HTML page.
                html_bytes = resp.read(262_144)
                html_text = html_bytes.decode("utf-8", errors="replace")
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise PrivateOrBlockedError(
                    t("resolver.error.access_denied", code=exc.code)
                ) from exc
            if exc.code == 404:
                raise ResolutionError(t("resolver.error.not_found")) from exc
            last_error = f"HTTP {exc.code}"
            continue
        except URLError as exc:
            raise ResolutionError(t("resolver.error.network", reason=exc.reason)) from exc

        block_reason = _detect_html_block_reason(html_text)
        if block_reason:
            last_error = block_reason

        parser = _DownloadFormParser()
        parser.feed(html_text)
        parsed_name = unescape("".join(parser.filename_parts)).strip()
        html_title = _clean_html_title(parser.og_title) or _clean_html_title(
            "".join(parser.title_parts)
        )
        if parsed_name and not extracted_title:
            extracted_title = parsed_name
        elif html_title and not extracted_title:
            extracted_title = html_title

        if parser.form_action and parser.form_inputs:
            action_url = urljoin(final_url, parser.form_action)
            form_params = dict(parser.form_inputs)
            if resource_key and "resourcekey" not in form_params:
                form_params["resourcekey"] = resource_key
            confirmed_url = _build_url_with_params(action_url, form_params)
            ok, verified_title, verified_type, verified_url = _probe_direct_stream(
                confirmed_url, timeout=timeout
            )
            if ok:
                resolved_title = verified_title or extracted_title or _fetch_view_page_title(
                    file_id, resource_key=resource_key, timeout=timeout
                )
                return ResolvedStream(
                    url=verified_url,
                    method="http",
                    title=resolved_title,
                    content_type=verified_type,
                )
            last_error = t("resolver.error.confirmed_html")

        confirm_match = re.search(r"confirm=([0-9A-Za-z_-]+)", html_text)
        uuid_match = re.search(r"uuid=([0-9A-Za-z_-]+)", html_text)
        if confirm_match:
            params = {
                "id": file_id,
                "export": "download",
                "confirm": confirm_match.group(1),
                **extra_params,
            }
            if uuid_match:
                params["uuid"] = uuid_match.group(1)
            fallback_confirm_url = _build_url_with_params(
                "https://drive.usercontent.google.com/download", params
            )
            ok, verified_title, verified_type, verified_url = _probe_direct_stream(
                fallback_confirm_url, timeout=timeout
            )
            if ok:
                resolved_title = verified_title or extracted_title or _fetch_view_page_title(
                    file_id, resource_key=resource_key, timeout=timeout
                )
                return ResolvedStream(
                    url=verified_url,
                    method="http",
                    title=resolved_title,
                    content_type=verified_type,
                )

    raise ResolutionError(last_error or t("resolver.error.http_failed"))


def resolve_via_yt_dlp(
    file_id: str,
    yt_dlp_bin: str | None,
    timeout: int = 30,
    *,
    resource_key: str | None = None,
) -> ResolvedStream:
    """Resolves the stream URL by invoking yt-dlp in JSON metadata mode.

    Args:
        file_id (str): Google Drive file ID.
        yt_dlp_bin (str | None): Path to the yt-dlp binary.
        timeout (int): Subprocess execution timeout in seconds.
        resource_key (str | None): Optional legacy resourcekey parameter.

    Returns:
        ResolvedStream: Extracted stream URL and metadata.

    Raises:
        ResolutionError: If yt-dlp is unavailable, fails, or returns invalid JSON.
    """
    if not yt_dlp_bin:
        raise ResolutionError(t("resolver.error.yt_dlp_missing"))

    view_url = build_view_url(file_id, resource_key=resource_key)
    cmd = [yt_dlp_bin, "--no-warnings", "--no-playlist", "-j", view_url]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResolutionError(t("resolver.error.yt_dlp_exec", error=exc)) from exc

    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = err_msg[-1] if err_msg else t("resolver.error.yt_dlp_exit", code=proc.returncode)
        raise ResolutionError(t("resolver.error.yt_dlp_failed", detail=detail))

    first_line = next((line for line in proc.stdout.splitlines() if line.strip()), "")
    if not first_line:
        raise ResolutionError(t("resolver.error.yt_dlp_empty_json"))

    try:
        info = json.loads(first_line)
    except json.JSONDecodeError as exc:
        raise ResolutionError(t("resolver.error.yt_dlp_invalid_json", error=exc)) from exc

    warnings: list[str] = []
    stream_url = info.get("url")
    http_headers = info.get("http_headers") or {}

    if not stream_url and isinstance(info.get("requested_formats"), list):
        # Prefer a muxed video+audio stream if yt-dlp returned separate formats.
        for fmt in info["requested_formats"]:
            if fmt.get("vcodec") != "none" and fmt.get("acodec") != "none" and fmt.get("url"):
                stream_url = fmt["url"]
                http_headers = fmt.get("http_headers") or http_headers
                break
        if not stream_url and info["requested_formats"]:
            stream_url = info["requested_formats"][0].get("url")
            warnings.append(t("resolver.warn.yt_dlp_split"))

    if not stream_url or not isinstance(stream_url, str):
        raise ResolutionError(t("resolver.error.yt_dlp_no_url"))

    if isinstance(http_headers, dict) and any(k.lower() == "cookie" for k in http_headers):
        warnings.append(t("resolver.warn.yt_dlp_cookies"))

    title = info.get("title") or info.get("fulltitle")
    ext = info.get("ext")
    content_type = f"video/{ext}" if isinstance(ext, str) and ext else None

    return ResolvedStream(
        url=stream_url,
        method="yt-dlp",
        title=title if isinstance(title, str) and title.strip() else None,
        content_type=content_type,
        warnings=tuple(warnings),
    )


def resolve_via_api(
    file_id: str,
    api_key: str | None,
    timeout: int = DEFAULT_TIMEOUT,
    *,
    resource_key: str | None = None,
) -> ResolvedStream:
    """Resolves the stream using Google Drive API v3 with a public API key.

    Args:
        file_id (str): Google Drive file ID.
        api_key (str | None): Google Drive API v3 key.
        timeout (int): Network timeout in seconds.
        resource_key (str | None): Optional legacy resourcekey parameter.

    Returns:
        ResolvedStream: Direct API media URL and metadata.

    Raises:
        PrivateOrBlockedError: If the API rejects the key or permissions.
        ResolutionError: If the key is missing or the file cannot be probed.
    """
    if not api_key:
        raise ResolutionError(t("resolver.error.api_key_missing"))

    meta_url = (
        f"https://www.googleapis.com/drive/v3/files/{file_id}"
        f"?{urlencode({'fields': 'name,mimeType', 'key': api_key})}"
    )
    title: str | None = None
    mime_type: str | None = None

    opener = build_opener()
    meta_headers = {"User-Agent": USER_AGENT}
    if resource_key:
        meta_headers["X-Goog-Drive-Resource-Keys"] = f"{file_id}/{resource_key}"
    meta_req = Request(meta_url, headers=meta_headers, method="GET")
    try:
        with opener.open(meta_req, timeout=timeout) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
            title = meta.get("name")
            mime_type = meta.get("mimeType")
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise PrivateOrBlockedError(
                t("resolver.error.api_rejected", code=exc.code)
            ) from exc
        if exc.code == 404:
            raise ResolutionError(t("resolver.error.api_not_found")) from exc
        raise ResolutionError(t("resolver.error.api_http", code=exc.code)) from exc
    except URLError as exc:
        raise ResolutionError(t("resolver.error.api_network", reason=exc.reason)) from exc

    media_url = (
        f"https://www.googleapis.com/drive/v3/files/{file_id}"
        f"?{urlencode({'alt': 'media', 'key': api_key})}"
    )
    ok, _, probed_type, verified_url = _probe_direct_stream(media_url, timeout=timeout)
    if not ok:
        raise ResolutionError(t("resolver.error.api_html"))

    return ResolvedStream(
        url=verified_url,
        method="api",
        title=title,
        content_type=mime_type or probed_type,
    )


def resolve_drive_stream(
    file_id: str,
    *,
    method: str = "auto",
    yt_dlp_bin: str | None = None,
    api_key: str | None = None,
    resource_key: str | None = None,
) -> ResolvedStream:
    """Resolves a Google Drive FILE_ID using the selected backend or auto cascade.

    Args:
        file_id (str): Validated Google Drive file ID.
        method (str): Resolution strategy ('auto', 'http', 'yt-dlp', or 'api').
        yt_dlp_bin (str | None): Optional path to yt-dlp executable.
        api_key (str | None): Optional Google Drive API v3 key.
        resource_key (str | None): Optional legacy resourcekey parameter.

    Returns:
        ResolvedStream: Portable direct streaming URL and metadata.

    Raises:
        ValueError: If an unknown resolution method is specified.
        PrivateOrBlockedError: If the file requires private authentication.
        ResolutionError: If all configured backends fail.
    """
    if method == "http":
        return resolve_via_http(file_id, resource_key=resource_key)
    if method == "yt-dlp":
        return resolve_via_yt_dlp(file_id, yt_dlp_bin=yt_dlp_bin, resource_key=resource_key)
    if method == "api":
        return resolve_via_api(file_id, api_key=api_key, resource_key=resource_key)
    if method != "auto":
        raise ValueError(t("resolver.error.unknown_method", method=method))

    errors: list[str] = []

    try:
        return resolve_via_http(file_id, resource_key=resource_key)
    except PrivateOrBlockedError as exc:
        # Fail fast on private login redirects rather than masking the root cause.
        if exc.is_private or "accounts.google.com" in str(exc):
            raise
        errors.append(f"http: {exc}")
    except ResolutionError as exc:
        errors.append(f"http: {exc}")

    if yt_dlp_bin:
        try:
            return resolve_via_yt_dlp(file_id, yt_dlp_bin=yt_dlp_bin, resource_key=resource_key)
        except ResolutionError as exc:
            errors.append(f"yt-dlp: {exc}")
    else:
        errors.append(t("resolver.error.yt_dlp_unavailable"))

    if api_key:
        try:
            return resolve_via_api(file_id, api_key=api_key, resource_key=resource_key)
        except ResolutionError as exc:
            errors.append(f"api: {exc}")

    summary = " | ".join(errors)
    raise ResolutionError(t("resolver.error.cascade_failed", summary=summary))
