"""Lightweight Linux system-locale internationalization helpers using pure stdlib."""

from __future__ import annotations

from collections.abc import Mapping
import locale
import os


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "es")

_CATALOGS: dict[str, dict[str, str]] = {
    "en": {
        "cli.description": (
            "Resolve a public Google Drive link into a direct streaming URL "
            "and launch VLC in the background."
        ),
        "cli.help.url_or_id": "Public Google Drive sharing link or video FILE_ID.",
        "cli.help.url_only": "Print only the resolved URL to stdout without launching VLC.",
        "cli.help.cache": (
            "VLC network cache in milliseconds (default: 3000 or DRIVE_VLC_CACHE_MS)."
        ),
        "cli.help.fullscreen": "Launch VLC directly in fullscreen mode.",
        "cli.help.copy": (
            "Copy the resolved URL to the clipboard (requires xclip, xsel, or wl-copy)."
        ),
        "cli.help.method": "Resolution backend to use (default: auto).",
        "cli.help.lang": (
            "Force CLI output language (default: Linux system locale, fallback: en)."
        ),
        "cli.help.verbose": "Emit diagnostic details via stderr logging.",
        "cli.error.negative_cache": "--cache cannot be negative.",
        "cli.error.vlc_launch": "Failed to launch VLC: {error}",
        "cli.verbose.details": "method={method} | title={title} | type={content_type}",
        "cli.unknown": "unknown",
        "cli.copy.success": "URL copied to clipboard ({backend}).",
        "cli.vlc.launched": (
            "VLC launched (PID {pid}, method: {method}, cache: {cache_ms} ms){title_suffix}"
        ),
        "config.error.cache_int": (
            "DRIVE_VLC_CACHE_MS must be an integer in milliseconds, got: {value!r}"
        ),
        "config.error.cache_negative": "DRIVE_VLC_CACHE_MS cannot be negative.",
        "url.error.empty": "You must provide a Google Drive URL or file ID.",
        "url.error.invalid": (
            "Invalid input: {raw!r}. Pass a full Google Drive URL or a valid file ID."
        ),
        "url.error.non_drive": "Domain {host!r} does not belong to Google Drive.",
        "url.error.folder": (
            "Google Drive folder links are not supported; pass an individual video link."
        ),
        "url.error.no_id": "Could not extract a valid FILE_ID from the provided URL: {raw!r}",
        "player.error.missing_bin": "VLC executable not found at {vlc_bin!r}.",
        "player.error.launch_failed": "Could not start VLC ({vlc_bin}): {error}",
        "player.copy.no_backend": (
            "No supported clipboard tool found (wl-copy, xclip, or xsel). "
            "Install xclip with: sudo apt install xclip"
        ),
        "resolver.error.quota": (
            "Google Drive has temporarily exceeded the download/view quota for this file."
        ),
        "resolver.error.private": (
            "This file appears to be private or requires sign-in; "
            "share it with a public read-only link."
        ),
        "resolver.error.login_redirect": (
            "Google Drive redirects to accounts.google.com: the file is private or not public."
        ),
        "resolver.error.access_denied": (
            "Access denied (HTTP {code}). Ensure the file is shared publicly "
            "(Anyone with the link - Viewer)."
        ),
        "resolver.error.not_found": "File not found on Google Drive or invalid link (HTTP 404).",
        "resolver.error.http_probe": "HTTP {code} error while verifying the direct URL.",
        "resolver.error.network": "Network error connecting to Google Drive: {reason}",
        "resolver.error.confirmed_html": (
            "The confirmed URL still returned HTML without session cookies."
        ),
        "resolver.error.http_failed": (
            "Could not obtain a portable direct HTTP streaming URL "
            "(possible cookie-dependent HTML page)."
        ),
        "resolver.error.yt_dlp_missing": "yt-dlp is not installed or configured on the system.",
        "resolver.error.yt_dlp_exec": "Failed to execute yt-dlp: {error}",
        "resolver.error.yt_dlp_failed": "yt-dlp could not resolve the link: {detail}",
        "resolver.error.yt_dlp_exit": "exit code {code}",
        "resolver.error.yt_dlp_empty_json": "yt-dlp returned no JSON metadata.",
        "resolver.error.yt_dlp_invalid_json": "Invalid JSON output from yt-dlp: {error}",
        "resolver.warn.yt_dlp_split": (
            "yt-dlp selected separate video/audio streams; "
            "the returned URL may lack audio in VLC."
        ),
        "resolver.error.yt_dlp_no_url": "yt-dlp did not return a direct playable URL.",
        "resolver.warn.yt_dlp_cookies": (
            "The URL returned by yt-dlp may depend on temporary cookies/headers on some systems."
        ),
        "resolver.error.api_key_missing": (
            "GOOGLE_DRIVE_API_KEY is not configured "
            "(in environment, ~/.config/drive-vlc/.env, or .env)."
        ),
        "resolver.error.api_rejected": (
            "Google Drive API rejected the request (HTTP {code}). "
            "Check your API key or public file permissions."
        ),
        "resolver.error.api_not_found": (
            "File not found or not publicly accessible via API (HTTP 404)."
        ),
        "resolver.error.api_http": "HTTP {code} error querying Google Drive API metadata.",
        "resolver.error.api_network": "Network error querying Google Drive API: {reason}",
        "resolver.error.api_html": (
            "Google Drive API returned unexpected HTML instead of the media file."
        ),
        "resolver.error.unknown_method": "Unknown resolution method: {method!r}",
        "resolver.error.yt_dlp_unavailable": "yt-dlp: unavailable on system",
        "resolver.error.cascade_failed": "Could not resolve a portable direct URL ({summary}).",
    },
    "es": {
        "cli.description": (
            "Resuelve un enlace público de Google Drive a una URL directa de streaming "
            "y lanza VLC automáticamente en segundo plano."
        ),
        "cli.help.url_or_id": "Enlace compartido público de Google Drive o FILE_ID del vídeo.",
        "cli.help.url_only": "Devuelve únicamente la URL resuelta por stdout sin abrir VLC.",
        "cli.help.cache": (
            "Caché de red de VLC en milisegundos (por defecto: 3000 o DRIVE_VLC_CACHE_MS)."
        ),
        "cli.help.fullscreen": "Lanza VLC directamente en pantalla completa.",
        "cli.help.copy": (
            "Copia la URL resuelta al portapapeles (requiere xclip, xsel o wl-copy)."
        ),
        "cli.help.method": "Motor de resolución a utilizar (por defecto: auto).",
        "cli.help.lang": (
            "Forzar idioma de salida de la CLI (por defecto: locale del sistema Linux, respaldo: en)."
        ),
        "cli.help.verbose": "Muestra detalles diagnósticos mediante logging por stderr.",
        "cli.error.negative_cache": "--cache no puede ser negativo.",
        "cli.error.vlc_launch": "Error al abrir VLC: {error}",
        "cli.verbose.details": "método={method} | título={title} | tipo={content_type}",
        "cli.unknown": "desconocido",
        "cli.copy.success": "URL copiada al portapapeles ({backend}).",
        "cli.vlc.launched": (
            "VLC lanzado (PID {pid}, método: {method}, caché: {cache_ms} ms){title_suffix}"
        ),
        "config.error.cache_int": (
            "DRIVE_VLC_CACHE_MS debe ser un entero en milisegundos, recibido: {value!r}"
        ),
        "config.error.cache_negative": "DRIVE_VLC_CACHE_MS no puede ser negativo.",
        "url.error.empty": "Debes indicar una URL de Google Drive o un ID de archivo.",
        "url.error.invalid": (
            "Entrada no válida: {raw!r}. Pasa una URL completa de Google Drive o un ID válido."
        ),
        "url.error.non_drive": "El dominio {host!r} no pertenece a Google Drive.",
        "url.error.folder": (
            "Los enlaces de carpetas de Google Drive no están soportados; "
            "pasa el enlace de un vídeo individual."
        ),
        "url.error.no_id": (
            "No se pudo extraer un FILE_ID válido de la URL proporcionada: {raw!r}"
        ),
        "player.error.missing_bin": "No se encontró el ejecutable de VLC en {vlc_bin!r}.",
        "player.error.launch_failed": "No se pudo iniciar VLC ({vlc_bin}): {error}",
        "player.copy.no_backend": (
            "No se encontró ninguna herramienta de portapapeles compatible "
            "(wl-copy, xclip o xsel). Puedes instalar xclip con: sudo apt install xclip"
        ),
        "resolver.error.quota": (
            "Google Drive ha superado temporalmente la cuota de descargas/visualizaciones "
            "para este archivo."
        ),
        "resolver.error.private": (
            "El archivo parece ser privado o requerir inicio de sesión; "
            "compártelo con enlace público de solo lectura."
        ),
        "resolver.error.login_redirect": (
            "Google Drive redirige a accounts.google.com: el archivo es privado o no es público."
        ),
        "resolver.error.access_denied": (
            "Acceso denegado (HTTP {code}). Verifica que el archivo tenga permisos públicos "
            "de solo lectura."
        ),
        "resolver.error.not_found": (
            "Archivo no encontrado en Google Drive o enlace inválido (HTTP 404)."
        ),
        "resolver.error.http_probe": "Error HTTP {code} al verificar la URL directa.",
        "resolver.error.network": "Error de red al conectar con Google Drive: {reason}",
        "resolver.error.confirmed_html": (
            "La URL confirmada siguió devolviendo HTML sin cookies de sesión."
        ),
        "resolver.error.http_failed": (
            "No se pudo obtener una URL directa reproducible por HTTP "
            "(posible página HTML dependiente de cookies)."
        ),
        "resolver.error.yt_dlp_missing": "yt-dlp no está instalado o configurado en el sistema.",
        "resolver.error.yt_dlp_exec": "Error al ejecutar yt-dlp: {error}",
        "resolver.error.yt_dlp_failed": "yt-dlp no pudo resolver el enlace: {detail}",
        "resolver.error.yt_dlp_exit": "código de salida {code}",
        "resolver.error.yt_dlp_empty_json": "yt-dlp no devolvió metadatos JSON.",
        "resolver.error.yt_dlp_invalid_json": "Salida JSON inválida de yt-dlp: {error}",
        "resolver.warn.yt_dlp_split": (
            "yt-dlp seleccionó pistas separadas de vídeo/audio; "
            "la URL devuelta podría no incluir audio en VLC."
        ),
        "resolver.error.yt_dlp_no_url": "yt-dlp no devolvió una URL directa reproducible.",
        "resolver.warn.yt_dlp_cookies": (
            "La URL devuelta por yt-dlp podría depender de cookies/cabeceras temporales "
            "en algunos sistemas."
        ),
        "resolver.error.api_key_missing": (
            "No hay GOOGLE_DRIVE_API_KEY configurada "
            "(en entorno, ~/.config/drive-vlc/.env o .env)."
        ),
        "resolver.error.api_rejected": (
            "La API de Google Drive rechazó la petición (HTTP {code}). "
            "Revisa tu API Key o los permisos públicos del archivo."
        ),
        "resolver.error.api_not_found": (
            "Archivo no encontrado o no accesible públicamente vía API (HTTP 404)."
        ),
        "resolver.error.api_http": (
            "Error HTTP {code} al consultar metadatos en Google Drive API."
        ),
        "resolver.error.api_network": "Error de red al consultar Google Drive API: {reason}",
        "resolver.error.api_html": (
            "La API de Google Drive devolvió HTML inesperado en lugar del archivo."
        ),
        "resolver.error.unknown_method": "Método de resolución desconocido: {method!r}",
        "resolver.error.yt_dlp_unavailable": "yt-dlp: no disponible en el sistema",
        "resolver.error.cascade_failed": (
            "No se pudo resolver una URL directa portable ({summary})."
        ),
    },
}

_ACTIVE_LANGUAGE: str | None = None


def _normalize_locale_code(raw_locale: str) -> str | None:
    """Extracts the primary lowercase ISO-639-1 language code from a Linux locale string.

    Args:
        raw_locale (str): Locale value such as ``es_ES.UTF-8`` or ``C``.

    Returns:
        str | None: Normalized two-letter code or ``None`` for C/POSIX/empty locales.
    """
    cleaned = raw_locale.strip()
    if not cleaned:
        return None
    base = cleaned.split(".", 1)[0].split("@", 1)[0].split("_", 1)[0].lower()
    if base in ("", "c", "posix"):
        return None
    return base


def detect_system_language(
    environ: Mapping[str, str] | None = None,
    *,
    cli_lang: str | None = None,
) -> str:
    """Detects the active Linux CLI language with English as universal fallback.

    Args:
        environ (Mapping[str, str] | None): Optional environment variable mapping.
        cli_lang (str | None): Explicit CLI override (e.g., ``--lang es``).

    Returns:
        str: Supported language code (``'en'`` or ``'es'``).
    """
    if cli_lang:
        normalized = _normalize_locale_code(cli_lang)
        if normalized in SUPPORTED_LANGUAGES:
            return normalized
        return DEFAULT_LANGUAGE

    env_source = os.environ if environ is None else environ

    # Linux gettext convention checks LANGUAGE (colon-separated), then LC_ALL, LC_MESSAGES, LANG.
    language_list = env_source.get("LANGUAGE", "").strip()
    if language_list:
        for candidate in language_list.split(":"):
            code = _normalize_locale_code(candidate)
            if code in SUPPORTED_LANGUAGES:
                return code

    for var_name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw_val = env_source.get(var_name, "").strip()
        if not raw_val:
            continue
        if raw_val.strip().upper() in ("C", "POSIX"):
            return DEFAULT_LANGUAGE
        code = _normalize_locale_code(raw_val)
        if code in SUPPORTED_LANGUAGES:
            return code
        if code is not None:
            return DEFAULT_LANGUAGE

    if environ is None:
        loc_lang, _ = locale.getlocale()
        if loc_lang:
            code = _normalize_locale_code(loc_lang)
            if code in SUPPORTED_LANGUAGES:
                return code

    return DEFAULT_LANGUAGE


def set_active_language(lang: str | None) -> str:
    """Sets the process-wide active CLI language (or resets to auto-detection).

    Args:
        lang (str | None): Explicit language code or ``None`` to reset to OS locale.

    Returns:
        str: Effective active language code.
    """
    global _ACTIVE_LANGUAGE
    if lang is None:
        _ACTIVE_LANGUAGE = None
        return detect_system_language()
    _ACTIVE_LANGUAGE = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    return _ACTIVE_LANGUAGE


def get_active_language() -> str:
    """Returns the currently active CLI language code.

    Returns:
        str: Active language code (``'en'`` or ``'es'``).
    """
    if _ACTIVE_LANGUAGE is not None:
        return _ACTIVE_LANGUAGE
    return detect_system_language()


def t(key: str, *, lang: str | None = None, **kwargs: object) -> str:
    """Translates a message key using the active language or English fallback.

    Args:
        key (str): Message catalog key.
        lang (str | None): Optional language code override.
        **kwargs (object): Format arguments interpolated into the template string.

    Returns:
        str: Localized and formatted message string.
    """
    target_lang = lang if lang in SUPPORTED_LANGUAGES else get_active_language()
    template = _CATALOGS.get(target_lang, {}).get(key) or _CATALOGS[DEFAULT_LANGUAGE][key]
    return template.format(**kwargs) if kwargs else template
