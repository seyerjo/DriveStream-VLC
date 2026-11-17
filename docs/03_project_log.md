# Project Log: DriveStream VLC (`drive-vlc`)

## To-Do List

- [x] **`TASK-01` [Completed]:** Design and implement `drive-vlc` in pure Python 3 stdlib, symlink `~/.local/bin/drive-vlc`, validate live Google Drive resolution + detached VLC playback (`PID 196144`), and pass 20 offline unit tests.
- [ ] **`TASK-02` [Pending]:** Refactor verbose/diagnostic output and error/warning reporting in [`cli.py`](../src/drive_vlc/cli.py) from raw `print(..., file=sys.stderr)` to Python's native `logging` module (`TIMESTAMP - LEVEL - MESSAGE`), keeping `stdout` strictly limited to the resolved URL.
- [ ] **`TASK-03` [Pending]:** Add Google-style English docstrings to remaining internal helper functions (`_decode_content_disposition_filename`, `_is_login_redirect`, `_detect_html_block_reason`, `_build_url_with_params`, `_DownloadFormParser` methods, `_resolve_vlc_bin`, `_resolve_yt_dlp_bin`) in [`resolver.py`](../src/drive_vlc/resolver.py) and [`config.py`](../src/drive_vlc/config.py).
- [x] **`TASK-04` [Completed]:** Create the initial Git commit on the repository following Conventional Commits standards (excluding `.env` and local developer tooling).
- [ ] **`TASK-05` [Pending]:** Optionally propagate `resourcekey` query parameters on legacy Google Drive links and add HTML `<title>` extraction fallback when `Content-Disposition` is missing.
- [ ] **`TASK-06` [Pending — `FEAT-05`]:** Implement a pure-stdlib Linux locale resolver and message catalog (`src/drive_vlc/i18n.py`) inspecting `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, and `LANG` (with `en` universal fallback and `es` catalog), plus an optional `--lang` flag in [`cli.py`](../src/drive_vlc/cli.py).
- [ ] **`TASK-07` [Pending — `FEAT-05`]:** Migrate hardcoded CLI help, status, warning, and error strings across [`cli.py`](../src/drive_vlc/cli.py), [`drive_url.py`](../src/drive_vlc/drive_url.py), [`resolver.py`](../src/drive_vlc/resolver.py), [`player.py`](../src/drive_vlc/player.py), and [`config.py`](../src/drive_vlc/config.py) to `i18n` message keys, and add deterministic `unittest` coverage for both `en` and `es` locales.

---

## Development Log

### 2026-11-17 — Initial MVP Architecture, Live Verification & Workspace Standardization
- **Design Decisions (`/grill-me`):** Selected a pure Python 3 standard-library CLI (`drive-vlc`), cascading resolution (`http` -> `yt-dlp` -> optional `api` key), portable direct HTTP URLs (no local HTTP proxy), detached VLC playback (`--network-caching=3000`), and layered configuration (`env > ~/.config/drive-vlc/.env > repo/.env`).
- **Live Google Drive Test & Bug Fix:** Testing against a real public Drive link revealed UTF-8 mojibake inside `Content-Disposition` (`filename="..."` decoded as Latin-1 by `http.client`). Added `_fix_latin1_utf8_mojibake` in [`resolver.py`](../src/drive_vlc/resolver.py) and unit tests in [`test_resolver.py`](../tests/test_resolver.py); verified detached VLC launch (`PID 196144`) in X11 (`DISPLAY=:1`).
- **Code & Docs Standardization:** Aligned code docstrings, comments, and public documentation to English while preserving Spanish user-facing CLI output until `FEAT-05` localization is implemented.
- **Memory Bank Initialization:** Created the 4-anchor Memory Bank (`/docs/01_project_blueprint.md`, `/docs/02_engineering_guidelines.md`, `/docs/03_project_log.md`, `/CHANGELOG.md`) after completing the 4-step predictive interview and Code Style Enforcement audit.
- **Public Readiness & CLI Localization Planning:** Added `FEAT-05` / `FR-05` (Linux-first system-locale CLI localization in pure stdlib, `en` fallback + `es`, `--lang` override) with `TASK-06` and `TASK-07`.
- **Public Documentation & Initial Git Baseline (`DriveStream VLC`):** Rebranded documentation to `DriveStream VLC (drive-vlc)`, sanitized local home paths before publishing, generated MIT `LICENSE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING_GUIDELINES.md`, and public `README.md`, and recorded initial commits `7c2a43e` and `6ff6136` on `master`.
