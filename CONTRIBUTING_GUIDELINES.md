# 🚀 Contributing to DriveStream VLC (`drive-vlc`)

Thank you for your interest in contributing! To maintain code health, efficiency, and a welcoming community, we request that all participants follow these structured guidelines.

## 1. 🐛 Reporting Issues & Bugs
Before creating a new issue, please search the active repository tracking system to ensure it has not already been reported. When filing an issue, include:
* 📝 A clear, descriptive title.
* 📝 Steps to reproduce the unexpected behavior (including the anonymized Google Drive link format and `--method` / `-v` output).
* 📝 Expected vs. actual outcomes, including Linux distribution, Python version, VLC version, and terminal logs.

## 2. 💡 Suggesting Enhancements
We welcome ideas for new features or optimizations! To propose a change:
* Open an enhancement issue explaining the explicit use case and the productivity or reliability value it adds to the codebase blueprint (`/docs/01_project_blueprint.md`).
* Keep in mind our core architectural constraint: pure Python 3 standard library only (zero third-party `pip` runtime dependencies) and portable direct URLs without local HTTP proxies.
* Wait for project maintainers to evaluate and greenlight the architectural impact before starting execution.

## 3. 🌿 Pull Request Process & Branching Strategy
To ensure swift reviews and zero code conflicts, follow this deployment protocol:
1. Fork the repository and create a feature branch off `master` using a semantic name (e.g., `feature/feat-05-cli-i18n` or `fix/issue-12-header-encoding`).
2. Implement your changes adhering strictly to the architecture and style guide laid out in `/docs/02_engineering_guidelines.md`, and verify everything passes with `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
3. Open a Pull Request (PR) targeted at the main branch. Ensure your PR description details the explicit problem solved and references any related issue IDs.
4. Maintain a clean commit history using Conventional Commits. A maintainer will review code style compliance and structural integrity before merging.

## ⚖️ Community Code of Conduct
By participating and contributing to this project, you agree to uphold and respect our community standards at all times.

> ⚠️ All interactions, code reviews, and issue discussions are strictly governed by the guidelines detailed in the official **`CODE_OF_CONDUCT.md`** file located in the root of this project. Violations will result in temporary or permanent suspension from the repository.
