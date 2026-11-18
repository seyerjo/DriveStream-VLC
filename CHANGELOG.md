# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-18

### Added
- Interactive `sys.stderr` prompt when `drive-vlc` is invoked without a URL or `FILE_ID` in a TTY (`FR-06`).
- Nala-inspired pure-stdlib terminal UI presenter (`src/drive_vlc/ui.py`) with rounded Unicode panels, ANSI accents, threaded Braille spinner on `stderr`, and `--plain` / `--no-color` / `NO_COLOR` support (`FR-07`).
- Localized (`en`/`es`) process-completion progress legends across configuration loading, Drive link validation, cascading resolution (`http`, `yt-dlp`, `api`), clipboard copy, and detached VLC launch (`FR-08`).
- Standalone `v0.2.0` single-file Python `zipapp` release packaging (`.releases/v0.2.0/drive-vlc` + `SHA256SUMS`) and updated `README.md` feature/usage documentation.

## [0.1.0] - 2026-11-17

### Added
- Pure Python 3 standard-library CLI (`drive-vlc`) resolving public Google Drive links via cascading backends (`http`, `yt-dlp`, optional Drive API v3) and launching VLC detached in Linux.
- Legacy `resourcekey` query parameter extraction and propagation (`extract_drive_link`, `DriveLinkInfo`) alongside HTML `<meta property="og:title">` / `<title>` fallback when `Content-Disposition` is absent.
- Layered configuration loader (`env` -> `~/.config/drive-vlc/.env` -> `.env`) and offline `unittest` suite (`26` tests).
- Linux system-locale CLI localization (`i18n.py`) supporting English (`en` fallback) and Spanish (`es`) with `--lang` override.
- Structured CLI event logging (`TIMESTAMP - LEVEL - MESSAGE`) to `stderr` and `$XDG_STATE_HOME/drive-vlc/drive-vlc.log`.
- Public repository documentation (`README.md`, MIT `LICENSE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING_GUIDELINES.md`) and consolidated Memory Bank (`/docs/`).
- Standalone single-file Python `zipapp` release packaging (`.releases/v0.1.0/drive-vlc` + `SHA256SUMS`) and GitHub Releases installation instructions in `README.md`.

### Fixed
- UTF-8 mojibake decoding for `Content-Disposition` filenames returned by Google Drive headers.
