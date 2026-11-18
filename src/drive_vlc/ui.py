"""Pure standard-library Nala-inspired terminal UI presenter for drive-vlc."""

from __future__ import annotations

from collections.abc import Sequence
import os
import shutil
import sys
import threading
from types import TracebackType
from typing import TextIO

SPINNER_FRAMES: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_SPINNER_INTERVAL_SEC = 0.08
_MIN_BOX_WIDTH = 52
_MAX_BOX_WIDTH = 84

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_BRIGHT_CYAN = "\033[96m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CLEAR_LINE = "\r\033[2K"


def _terminal_width(default: int = 72) -> int:
    """Returns a clamped terminal width suitable for rounded Unicode cards.

    Args:
        default (int): Fallback column width when terminal size cannot be queried.

    Returns:
        int: Clamped column count between ``_MIN_BOX_WIDTH`` and ``_MAX_BOX_WIDTH``.
    """
    columns = shutil.get_terminal_size((default, 24)).columns
    return max(_MIN_BOX_WIDTH, min(_MAX_BOX_WIDTH, columns))


def _truncate_text(text: str, max_len: int) -> str:
    """Truncates plain text cleanly with an ellipsis when exceeding max_len.

    Args:
        text (str): Plain text without ANSI escape sequences.
        max_len (int): Maximum visible character budget.

    Returns:
        str: Original or truncated string ending in ``…``.
    """
    if max_len <= 1:
        return text[:max_len]
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}…"


class LiveStep:
    """Context-managed progress step with optional animated Braille spinner on stderr."""

    def __init__(
        self,
        presenter: ConsolePresenter,
        initial_message: str,
        *,
        animate: bool = True,
    ) -> None:
        """Initializes a progress step bound to a ConsolePresenter.

        Args:
            presenter (ConsolePresenter): Active terminal presenter.
            initial_message (str): Initial status legend shown while the step runs.
            animate (bool): Whether to run a background Braille spinner when enabled.
        """
        self._presenter = presenter
        self._message = initial_message
        self._animate = animate and presenter.enabled and presenter.animate_spinner
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame_idx = 0
        self._finished = False

    def __enter__(self) -> LiveStep:
        """Starts rendering the active step when the presenter is enabled.

        Returns:
            LiveStep: The active step controller.
        """
        if self._animate:
            self._render_spinner_frame()
            self._thread = threading.Thread(target=self._spin_loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Finalizes the spinner cleanly if the caller did not mark an explicit outcome.

        Args:
            exc_type (type[BaseException] | None): Raised exception class, if any.
            exc_val (BaseException | None): Raised exception instance, if any.
            exc_tb (TracebackType | None): Traceback object, if any.
        """
        if not self._finished:
            if exc_type is not None:
                self.fail()
            else:
                self.succeed()

    def _spin_loop(self) -> None:
        """Advances spinner frames periodically until stopped."""
        while not self._stop_event.wait(_SPINNER_INTERVAL_SEC):
            with self._lock:
                if self._finished:
                    break
                self._frame_idx = (self._frame_idx + 1) % len(SPINNER_FRAMES)
                self._render_spinner_frame()

    def _render_spinner_frame(self) -> None:
        """Writes the current Braille spinner frame and message to the presenter stream."""
        frame = SPINNER_FRAMES[self._frame_idx]
        max_msg = max(20, _terminal_width() - 6)
        clipped = _truncate_text(self._message, max_msg)
        styled_frame = self._presenter.style(frame, _BRIGHT_CYAN, _BOLD)
        styled_msg = self._presenter.style(clipped, _DIM)
        self._presenter.write_raw(f"{_CLEAR_LINE}  {styled_frame} {styled_msg}")

    def _stop_spinner(self) -> None:
        """Stops the background spinner thread and clears the temporary line."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0.3)
            self._thread = None
        if self._animate:
            self._presenter.write_raw(_CLEAR_LINE)

    def update(self, message: str) -> None:
        """Updates the live step legend while the step is in progress.

        Args:
            message (str): New descriptive progress text.
        """
        with self._lock:
            self._message = message
            if self._animate and not self._finished:
                self._render_spinner_frame()

    def succeed(self, message: str | None = None) -> None:
        """Marks the step as completed with a green checkmark.

        Args:
            message (str | None): Optional completion legend overriding the active text.
        """
        with self._lock:
            if self._finished:
                return
            self._finished = True
            final_text = message if message is not None else self._message
        self._stop_spinner()
        if self._presenter.enabled:
            icon = self._presenter.style("✓", _GREEN, _BOLD)
            self._presenter.write_line(f"  {icon} {final_text}")

    def warn(self, message: str) -> None:
        """Marks the step with a non-fatal warning badge.

        Args:
            message (str): Warning text to display.
        """
        with self._lock:
            if self._finished:
                return
            self._finished = True
        self._stop_spinner()
        if self._presenter.enabled:
            icon = self._presenter.style("⚠", _YELLOW, _BOLD)
            self._presenter.write_line(f"  {icon} {message}")

    def fail(self, message: str | None = None) -> None:
        """Marks the step as failed with a red cross.

        Args:
            message (str | None): Optional failure legend overriding the active text.
        """
        with self._lock:
            if self._finished:
                return
            self._finished = True
            final_text = message if message is not None else self._message
        self._stop_spinner()
        if self._presenter.enabled:
            icon = self._presenter.style("✗", _RED, _BOLD)
            self._presenter.write_line(f"  {icon} {final_text}")


class ConsolePresenter:
    """Renders Nala-inspired Unicode panels, color accents, and live steps to stderr."""

    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        input_stream: TextIO | None = None,
        plain: bool = False,
        no_color: bool = False,
        verbose: bool = False,
        force_tty: bool | None = None,
        animate_spinner: bool = True,
    ) -> None:
        """Initializes the terminal presenter with TTY and color capability checks.

        Args:
            stream (TextIO | None): Output stream (defaults to ``sys.stderr``).
            input_stream (TextIO | None): Input stream for prompts (defaults to ``sys.stdin``).
            plain (bool): Disables styled panels, icons, and spinners when True.
            no_color (bool): Disables ANSI color escapes while keeping Unicode layout.
            verbose (bool): Disables rich UI so structured verbose logs remain readable.
            force_tty (bool | None): Explicit TTY override for deterministic unit testing.
            animate_spinner (bool): Enables threaded Braille spinner animation on TTYs.
        """
        self.stream: TextIO = sys.stderr if stream is None else stream
        self.input_stream: TextIO = sys.stdin if input_stream is None else input_stream
        self.is_tty: bool = (
            bool(getattr(self.stream, "isatty", lambda: False)())
            if force_tty is None
            else force_tty
        )
        self.enabled: bool = self.is_tty and not plain and not verbose
        env_no_color = "NO_COLOR" in os.environ or os.environ.get("TERM", "").lower() == "dumb"
        self.use_color: bool = self.enabled and not no_color and not env_no_color
        self.animate_spinner: bool = animate_spinner

    def style(self, text: str, *codes: str) -> str:
        """Applies ANSI formatting codes to text when color output is active.

        Args:
            text (str): Plain text to decorate.
            *codes (str): ANSI escape prefixes such as ``_CYAN`` or ``_BOLD``.

        Returns:
            str: Decorated string if colors are enabled, otherwise plain ``text``.
        """
        if not self.use_color or not codes:
            return text
        return f"{''.join(codes)}{text}{_RESET}"

    def write_raw(self, text: str) -> None:
        """Writes raw text to the output stream and flushes immediately.

        Args:
            text (str): Pre-formatted output chunk.
        """
        self.stream.write(text)
        self.stream.flush()

    def write_line(self, text: str = "") -> None:
        """Writes a single line to the output stream and flushes immediately.

        Args:
            text (str): Line content without trailing newline.
        """
        self.stream.write(f"{text}\n")
        self.stream.flush()

    def render_header(self, title: str, subtitle: str) -> None:
        """Renders a rounded Nala-style top banner when rich UI is enabled.

        Args:
            title (str): Application banner title.
            subtitle (str): Concise descriptive tagline.
        """
        if not self.enabled:
            return
        width = _terminal_width()
        inner_width = width - 4
        clean_title = _truncate_text(title, max(10, inner_width - 4))
        clean_sub = _truncate_text(subtitle, inner_width)

        dash_fill = max(1, inner_width - len(clean_title) - 1)
        top = f"╭─ {clean_title} {'─' * dash_fill}╮"
        middle_pad = " " * max(0, inner_width - len(clean_sub))
        bottom = f"╰{'─' * (inner_width + 2)}╯"

        self.write_line(self.style(top, _CYAN))
        self.write_line(
            f"{self.style('│', _CYAN)} {self.style(clean_sub, _BOLD)}{middle_pad} {self.style('│', _CYAN)}"
        )
        self.write_line(self.style(bottom, _CYAN))

    def live_step(self, initial_message: str, *, animate: bool = True) -> LiveStep:
        """Creates a context-managed progress step for an operational stage.

        Args:
            initial_message (str): Initial descriptive legend for the stage.
            animate (bool): Whether to animate a spinner during blocking work.

        Returns:
            LiveStep: Context manager handling live updates and final status badge.
        """
        return LiveStep(self, initial_message, animate=animate)

    def prompt_input(self, prompt_text: str) -> str:
        """Prompts the user via stderr and reads a trimmed line from stdin.

        Args:
            prompt_text (str): Localized prompt legend shown to the user.

        Returns:
            str: Trimmed user input line.

        Raises:
            EOFError: If stdin reaches end-of-file before providing input.
        """
        if self.enabled:
            caret = self.style("›", _BRIGHT_CYAN, _BOLD)
            label = self.style(prompt_text, _BOLD)
            self.write_raw(f"  {caret} {label}")
        else:
            self.write_raw(prompt_text)

        line = self.input_stream.readline()
        if line == "":
            raise EOFError("End of input stream while reading URL or FILE_ID.")
        return line.rstrip("\r\n").strip()

    def render_warning(self, message: str) -> None:
        """Prints a warning line with a yellow badge when rich UI is enabled.

        Args:
            message (str): Localized warning message.
        """
        if not self.enabled:
            return
        icon = self.style("⚠", _YELLOW, _BOLD)
        self.write_line(f"  {icon} {self.style(message, _YELLOW)}")

    def render_error(self, message: str) -> None:
        """Prints an error line with a red badge when rich UI is enabled.

        Args:
            message (str): Localized error message.
        """
        if not self.enabled:
            return
        icon = self.style("✗", _RED, _BOLD)
        self.write_line(f"  {icon} {self.style(message, _RED)}")

    def render_summary(self, heading: str, rows: Sequence[tuple[str, str]]) -> None:
        """Renders a rounded Nala-style key/value summary card on stderr.

        Args:
            heading (str): Summary box title.
            rows (Sequence[tuple[str, str]]): Ordered ``(label, value)`` pairs to display.
        """
        if not self.enabled or not rows:
            return

        width = _terminal_width()
        inner_width = width - 4
        clean_heading = _truncate_text(heading, max(10, inner_width - 4))
        dash_fill = max(1, inner_width - len(clean_heading) - 1)
        top = f"╭─ {clean_heading} {'─' * dash_fill}╮"
        bottom = f"╰{'─' * (inner_width + 2)}╯"

        label_width = min(16, max(len(label) for label, _ in rows))
        value_budget = max(12, inner_width - label_width - 3)

        self.write_line()
        self.write_line(self.style(top, _GREEN))
        for raw_label, raw_value in rows:
            label = _truncate_text(raw_label, label_width)
            value = _truncate_text(raw_value, value_budget)
            plain_line = f"{label.ljust(label_width)} : {value}"
            pad = " " * max(0, inner_width - len(plain_line))
            styled_label = self.style(label.ljust(label_width), _DIM)
            styled_sep = self.style(":", _DIM)
            styled_val = self.style(value, _BOLD)
            self.write_line(
                f"{self.style('│', _GREEN)} {styled_label} {styled_sep} {styled_val}{pad} {self.style('│', _GREEN)}"
            )
        self.write_line(self.style(bottom, _GREEN))
