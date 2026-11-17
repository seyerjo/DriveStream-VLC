# Project Blueprint: DriveStream VLC (`drive-vlc`)

## Vision

Provide a lightweight, zero-dependency Python 3 CLI tool (`drive-vlc`, globally symlinked at `~/.local/bin/drive-vlc`) that converts public read-only Google Drive video share links into portable, direct HTTP streaming URLs and launches VLC detached in Linux without relying on a local HTTP proxy server.

The project prioritizes stability, minimal footprint, strict standard-library portability, and clean maintainability across Google Drive redirect/confirmation changes.

---

## Requirements

### Functional Requirements

- **`FR-01` (Drive Identifier Parsing):** Extract and validate `FILE_ID` values from standard Google Drive URL formats (`/file/d/<ID>`, `/d/<ID>`, `open?id=<ID>`, `uc?id=<ID>`, `drive.usercontent.google.com/download?id=<ID>`) or raw IDs, rejecting folder links and non-Drive domains.
- **`FR-02` (Cascading Stream Resolution):** Resolve links via an automatic fallback cascade (`http` unauthenticated direct resolution -> `yt-dlp` JSON extraction -> Google Drive API v3 `alt=media` when `GOOGLE_DRIVE_API_KEY` is configured), or force a specific backend with `--method`.
- **`FR-03` (CLI Output & VLC Playback):** Print the clean resolved URL to `stdout` and launch VLC detached in the background by default, or print only the URL when `--url-only` is passed.
- **`FR-04` (Configuration & Playback Controls):** Load optional settings in precedence order (`os.environ` -> `~/.config/drive-vlc/.env` -> `<repo>/.env`) and support `--cache`, `-f`/`--fullscreen`, `--copy`, and `-v`/`--verbose`.
- **`FR-05` (System-Locale CLI Localization — Linux First):** Automatically display CLI help, status messages, warnings, and errors in the Linux system language (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`), starting with English (`en` as universal fallback) and Spanish (`es`) via a pure-stdlib catalog plus an optional `--lang` override.

### Non-Functional Requirements

- **`NFR-01` [Priority: High] (Standard Library Only):** Keep `src/drive_vlc/` free of third-party `pip` dependencies (Python 3.12+ standard library only) so `~/.local/bin/drive-vlc` executes globally without activating a virtual environment.
- **`NFR-02` [Priority: High] (Portable Direct URLs):** Never spawn a local HTTP proxy; probe candidate URLs without cookies (`Range: bytes=0-0`) to ensure VLC receives a binary media stream instead of an HTML interstitial.
- **`NFR-03` [Priority: High] (Code Quality & Security):** Execute external binaries with `shell=False` argument lists, enforce strict Python type hints and Google-style English docstrings, and localize CLI output via `FR-05` with English as the base/fallback language.
- **`NFR-04` [Priority: Medium] (Git Isolation & Offline Testing):** Keep `.env` credentials and local developer tooling untracked via `.gitignore` / `.git/info/exclude`, and maintain offline `unittest` coverage across URL parsing, configuration, i18n, resolution backends, and CLI execution (`24` tests).

---

## Product Features

### `FEAT-01` — Google Drive URL & ID Validator (`drive_url.py`)
- **Status:** Implemented (`extract_file_id`, `build_view_url`).
- **Known Edge Cases / Limitations:** Legacy Drive links carrying a `resourcekey` query parameter do not currently propagate `resourcekey`; shortened URLs (e.g., `bit.ly`) are rejected as non-Drive domains.

### `FEAT-02` — Cascading Portable Stream Resolver (`resolver.py`)
- **Status:** Implemented (`resolve_via_http`, `resolve_via_yt_dlp`, `resolve_via_api`, `resolve_drive_stream`).
- **Capabilities:** Parses Drive antivirus confirmation HTML forms (`_DownloadFormParser`), detects private/login redirects (`accounts.google.com`) and quota limits, decodes UTF-8/RFC-5987 `Content-Disposition` filenames (including Latin-1 mojibake recovery), and verifies streams cookieless.
- **Known Edge Cases / Limitations:** Resolved `uuid` / signed CDN URLs may expire after prolonged playback pauses in VLC; files without `Content-Disposition` leave `title=None` under the `http` backend.

### `FEAT-03` — Detached VLC Launcher & Clipboard Helper (`player.py`)
- **Status:** Implemented (`build_vlc_command`, `launch_vlc`, `copy_to_clipboard`).
- **Capabilities:** Launches `/usr/bin/vlc` in a new session (`start_new_session=True`) with `--network-caching=3000` (configurable), `--meta-title`, and optional `--fullscreen`.
- **Known Edge Cases / Limitations:** Clipboard copying requires `wl-copy`, `xclip`, or `xsel`; if none is installed on the host, `--copy` emits a non-fatal warning on `stderr`.

### `FEAT-04` — Layered Config & Script-Friendly CLI (`config.py`, `cli.py`, `drive-vlc`)
- **Status:** Implemented.
- **Capabilities:** Clean separation between `stdout` (resolved URL only) and `stderr` (status, warnings, errors), invoked globally via `~/.local/bin/drive-vlc`.

### `FEAT-05` — Linux System-Locale CLI Localization (`i18n.py`)
- **Status:** Implemented (`FR-05`, `NFR-03`).
- **Scope (Linux-First):** Detects OS locale from `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, and `LANG` without external dependencies or compiled `.mo` files, providing English (`en`, universal fallback) and Spanish (`es`) message catalogs plus an optional `--lang` CLI override (including localized `--help` output).
