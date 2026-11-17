"""Google Drive public link resolution engines for portable direct VLC streaming."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import json
import re
import subprocess
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from drive_vlc.drive_url import build_view_url


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15


class ResolutionError(RuntimeError):
    """Raised when resolving a Google Drive video into a direct URL fails."""


class PrivateOrBlockedError(ResolutionError):
    """Raised when the file is private, requires login, or hits a quota limit."""


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
    """Parses the virus-scan confirmation form and filename from Drive HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.in_target_form = False
        self.form_action: str | None = None
        self.form_inputs: dict[str, str] = {}
        self.in_name_span = False
        self.in_name_link = False
        self.filename_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l == "form" and self.in_target_form:
            self.in_target_form = False
        elif tag_l == "a" and self.in_name_link:
            self.in_name_link = False
        elif tag_l == "span" and self.in_name_span:
            self.in_name_span = False

    def handle_data(self, data: str) -> None:
        if self.in_name_link:
            self.filename_parts.append(data)


class _CaptureRedirectHandler(HTTPRedirectHandler):
    """Records intermediate redirect URLs during HTTP resolution."""

    def __init__(self) -> None:
        super().__init__()
        self.visited_urls: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
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
    host = urlparse(url).netloc.lower()
    return "accounts.google.com" in host


def _detect_html_block_reason(html_text: str) -> str | None:
    lowered = html_text.lower()
    if "too many users have viewed or downloaded this file recently" in lowered or "quota exceeded" in lowered:
        return "Google Drive ha superado temporalmente la cuota de descargas/visualizaciones para este archivo."
    if "you need access" in lowered or "request access" in lowered or "sign in" in lowered:
        return "El archivo parece ser privado o requerir inicio de sesión; compártelo con enlace público de solo lectura."
    return None


def _build_url_with_params(base_url: str, params: dict[str, str]) -> str:
    parsed = urlparse(base_url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update(params)
    return urlunparse(parsed._replace(query=urlencode(existing)))


def _probe_direct_stream(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[bool, str | None, str | None, str]:
    """Probes a candidate URL without cookies to confirm it returns binary media instead of HTML."""
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
                raise PrivateOrBlockedError(
                    "Google Drive redirige a accounts.google.com: el archivo no es público."
                )
            content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            filename = _decode_content_disposition_filename(resp.headers.get("Content-Disposition"))
            if content_type == "text/html":
                return False, filename, content_type, final_url
            return True, filename, (content_type or None), final_url
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise PrivateOrBlockedError(
                f"Acceso denegado (HTTP {exc.code}). Verifica que el archivo tenga permisos públicos de solo lectura."
            ) from exc
        if exc.code == 404:
            raise ResolutionError("El archivo no existe o el enlace es inválido (HTTP 404).") from exc
        raise ResolutionError(f"Error HTTP {exc.code} al verificar la URL directa.") from exc
    except URLError as exc:
        raise ResolutionError(f"Error de red al conectar con Google Drive: {exc.reason}") from exc


def resolve_via_http(file_id: str, timeout: int = DEFAULT_TIMEOUT) -> ResolvedStream:
    """Resolves a direct streaming URL via unauthenticated HTTP requests.

    Args:
        file_id (str): Google Drive file ID.
        timeout (int): Network timeout in seconds per request.

    Returns:
        ResolvedStream: Verified direct streaming URL and metadata.

    Raises:
        PrivateOrBlockedError: If the file requires authentication or is forbidden.
        ResolutionError: If no direct non-HTML stream could be confirmed.
    """
    candidates = [
        f"https://drive.google.com/uc?export=download&id={file_id}",
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
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
                    raise PrivateOrBlockedError(
                        "El archivo requiere iniciar sesión en Google Drive (no es público)."
                    )
                content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
                title = _decode_content_disposition_filename(resp.headers.get("Content-Disposition"))
                if content_type != "text/html":
                    return ResolvedStream(
                        url=final_url,
                        method="http",
                        title=title or extracted_title,
                        content_type=content_type or None,
                    )

                # Read up to 256 KB of the intermediate confirmation HTML page.
                html_bytes = resp.read(262_144)
                html_text = html_bytes.decode("utf-8", errors="replace")
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise PrivateOrBlockedError(
                    f"Acceso denegado (HTTP {exc.code}). Asegúrate de compartir el archivo como público (cualquier persona con el enlace)."
                ) from exc
            if exc.code == 404:
                raise ResolutionError("Archivo no encontrado en Google Drive (HTTP 404).") from exc
            last_error = f"HTTP {exc.code}"
            continue
        except URLError as exc:
            raise ResolutionError(f"Error de red al consultar Google Drive: {exc.reason}") from exc

        block_reason = _detect_html_block_reason(html_text)
        if block_reason:
            last_error = block_reason

        parser = _DownloadFormParser()
        parser.feed(html_text)
        parsed_name = unescape("".join(parser.filename_parts)).strip()
        if parsed_name and not extracted_title:
            extracted_title = parsed_name

        if parser.form_action and parser.form_inputs:
            action_url = urljoin(final_url, parser.form_action)
            confirmed_url = _build_url_with_params(action_url, parser.form_inputs)
            ok, verified_title, verified_type, verified_url = _probe_direct_stream(
                confirmed_url, timeout=timeout
            )
            if ok:
                return ResolvedStream(
                    url=verified_url,
                    method="http",
                    title=verified_title or extracted_title,
                    content_type=verified_type,
                )
            last_error = "La URL confirmada siguió devolviendo HTML sin cookies de sesión."

        confirm_match = re.search(r"confirm=([0-9A-Za-z_-]+)", html_text)
        uuid_match = re.search(r"uuid=([0-9A-Za-z_-]+)", html_text)
        if confirm_match:
            params = {"id": file_id, "export": "download", "confirm": confirm_match.group(1)}
            if uuid_match:
                params["uuid"] = uuid_match.group(1)
            fallback_confirm_url = _build_url_with_params(
                "https://drive.usercontent.google.com/download", params
            )
            ok, verified_title, verified_type, verified_url = _probe_direct_stream(
                fallback_confirm_url, timeout=timeout
            )
            if ok:
                return ResolvedStream(
                    url=verified_url,
                    method="http",
                    title=verified_title or extracted_title,
                    content_type=verified_type,
                )

    raise ResolutionError(
        last_error
        or "No se pudo obtener una URL directa reproducible por HTTP (posible página HTML dependiente de cookies)."
    )


def resolve_via_yt_dlp(
    file_id: str,
    yt_dlp_bin: str | None,
    timeout: int = 30,
) -> ResolvedStream:
    """Resolves the stream URL by invoking yt-dlp in JSON metadata mode.

    Args:
        file_id (str): Google Drive file ID.
        yt_dlp_bin (str | None): Path to the yt-dlp binary.
        timeout (int): Subprocess execution timeout in seconds.

    Returns:
        ResolvedStream: Extracted stream URL and metadata.

    Raises:
        ResolutionError: If yt-dlp is unavailable, fails, or returns invalid JSON.
    """
    if not yt_dlp_bin:
        raise ResolutionError("yt-dlp no está instalado o configurado en el sistema.")

    view_url = build_view_url(file_id)
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
        raise ResolutionError(f"Error al ejecutar yt-dlp: {exc}") from exc

    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = err_msg[-1] if err_msg else f"código de salida {proc.returncode}"
        raise ResolutionError(f"yt-dlp no pudo resolver el enlace: {detail}")

    first_line = next((line for line in proc.stdout.splitlines() if line.strip()), "")
    if not first_line:
        raise ResolutionError("yt-dlp no devolvió metadatos JSON.")

    try:
        info = json.loads(first_line)
    except json.JSONDecodeError as exc:
        raise ResolutionError(f"Salida JSON inválida de yt-dlp: {exc}") from exc

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
            warnings.append(
                "yt-dlp seleccionó pistas separadas de vídeo/audio; la URL devuelta podría no incluir audio en VLC."
            )

    if not stream_url or not isinstance(stream_url, str):
        raise ResolutionError("yt-dlp no devolvió una URL directa reproducible.")

    if isinstance(http_headers, dict) and any(k.lower() == "cookie" for k in http_headers):
        warnings.append(
            "La URL devuelta por yt-dlp podría depender de cookies/cabeceras temporales en algunos sistemas."
        )

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
) -> ResolvedStream:
    """Resolves the stream using Google Drive API v3 with a public API key.

    Args:
        file_id (str): Google Drive file ID.
        api_key (str | None): Google Drive API v3 key.
        timeout (int): Network timeout in seconds.

    Returns:
        ResolvedStream: Direct API media URL and metadata.

    Raises:
        PrivateOrBlockedError: If the API rejects the key or permissions.
        ResolutionError: If the key is missing or the file cannot be probed.
    """
    if not api_key:
        raise ResolutionError(
            "No hay GOOGLE_DRIVE_API_KEY configurada (en entorno, ~/.config/drive-vlc/.env o .env)."
        )

    meta_url = (
        f"https://www.googleapis.com/drive/v3/files/{file_id}"
        f"?{urlencode({'fields': 'name,mimeType', 'key': api_key})}"
    )
    title: str | None = None
    mime_type: str | None = None

    opener = build_opener()
    meta_req = Request(meta_url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with opener.open(meta_req, timeout=timeout) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
            title = meta.get("name")
            mime_type = meta.get("mimeType")
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise PrivateOrBlockedError(
                f"La API de Google Drive rechazó la petición (HTTP {exc.code}). Revisa tu API Key o los permisos públicos del archivo."
            ) from exc
        if exc.code == 404:
            raise ResolutionError("Archivo no encontrado o no accesible públicamente vía API (HTTP 404).") from exc
        raise ResolutionError(f"Error HTTP {exc.code} al consultar metadatos en Google Drive API.") from exc
    except URLError as exc:
        raise ResolutionError(f"Error de red al consultar Google Drive API: {exc.reason}") from exc

    media_url = (
        f"https://www.googleapis.com/drive/v3/files/{file_id}"
        f"?{urlencode({'alt': 'media', 'key': api_key})}"
    )
    ok, _, probed_type, verified_url = _probe_direct_stream(media_url, timeout=timeout)
    if not ok:
        raise ResolutionError("La API de Google Drive devolvió HTML inesperado en lugar del archivo.")

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
) -> ResolvedStream:
    """Resolves a Google Drive FILE_ID using the selected backend or auto cascade.

    Args:
        file_id (str): Validated Google Drive file ID.
        method (str): Resolution strategy ('auto', 'http', 'yt-dlp', or 'api').
        yt_dlp_bin (str | None): Optional path to yt-dlp executable.
        api_key (str | None): Optional Google Drive API v3 key.

    Returns:
        ResolvedStream: Portable direct streaming URL and metadata.

    Raises:
        ValueError: If an unknown resolution method is specified.
        PrivateOrBlockedError: If the file requires private authentication.
        ResolutionError: If all configured backends fail.
    """
    if method == "http":
        return resolve_via_http(file_id)
    if method == "yt-dlp":
        return resolve_via_yt_dlp(file_id, yt_dlp_bin=yt_dlp_bin)
    if method == "api":
        return resolve_via_api(file_id, api_key=api_key)
    if method != "auto":
        raise ValueError(f"Método de resolución desconocido: {method!r}")

    errors: list[str] = []

    try:
        return resolve_via_http(file_id)
    except PrivateOrBlockedError as exc:
        # Fail fast on private login redirects rather than masking the root cause.
        if "accounts.google.com" in str(exc) or "privado" in str(exc).lower():
            raise
        errors.append(f"http: {exc}")
    except ResolutionError as exc:
        errors.append(f"http: {exc}")

    if yt_dlp_bin:
        try:
            return resolve_via_yt_dlp(file_id, yt_dlp_bin=yt_dlp_bin)
        except ResolutionError as exc:
            errors.append(f"yt-dlp: {exc}")
    else:
        errors.append("yt-dlp: no disponible en el sistema")

    if api_key:
        try:
            return resolve_via_api(file_id, api_key=api_key)
        except ResolutionError as exc:
            errors.append(f"api: {exc}")

    summary = " | ".join(errors)
    raise ResolutionError(f"No se pudo resolver una URL directa portable ({summary}).")
