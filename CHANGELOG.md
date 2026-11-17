# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Pure Python 3 standard-library CLI (`drive-vlc`) resolving public Google Drive links via cascading backends (`http`, `yt-dlp`, optional Drive API v3) and launching VLC detached in Linux.
- Layered configuration loader (`env` -> `~/.config/drive-vlc/.env` -> `.env`) and offline `unittest` suite (20 tests).
- Public repository documentation (`README.md`, MIT `LICENSE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING_GUIDELINES.md`) and consolidated Memory Bank (`/docs/`).

### Fixed
- UTF-8 mojibake decoding for `Content-Disposition` filenames returned by Google Drive headers.
