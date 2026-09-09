#!/usr/bin/env python3
"""Terminal frontend for the persistent Mozart/Oz compiler backend."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import queue
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.formatted_text import FormattedText, PygmentsTokens
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from pygments.lexer import RegexLexer
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String, Text


READY = "__OZREPL_READY__"
BROWSE_MARKER = "__OZREPL_BROWSE__"
BROWSE_UPDATE_MARKER = "__OZREPL_BROWSE_UPDATE__"
REQUEST_TIMEOUT = 5
ROOT = Path(__file__).resolve().parent
USE_COLOR = False

HELP = """Commands:
  :help             show this help
  :load FILE        feed an Oz source file
  :watch [--clear] FILE
                    reload a file whenever it changes
  :unwatch          stop watching the current file
  :reset            discard declarations and clear Browse
  :quit             leave the REPL

Editing:
  Alt-Enter         insert a newline
  Ctrl-X Ctrl-E     edit the fragment in $VISUAL/$EDITOR
  Enter             submit the complete fragment

Use declare when introducing persistent variables.
Use {Show Expression} to display a value.
Use {Browse Expression} for the tmux side pane."""


def find_mozart_command(name: str) -> str:
    """Find a Mozart executable, including common macOS application paths."""
    override = os.environ.get(name.upper())
    candidates = [override] if override else []
    discovered = shutil.which(name)
    if discovered:
        candidates.append(discovered)
    if sys.platform == "darwin":
        application = Path("/Applications/Mozart2.app/Contents/Resources")
        candidates.extend((str(application / name), str(application / "bin" / name)))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit(
        f"Mozart/Oz command '{name}' was not found. Install Mozart 2 and make "
        f"sure '{name}' is on PATH, or set {name.upper()} to its full path."
    )


def user_cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "ozrepl"


def compiled_backend() -> Path:
    """Return a development build or compile the packaged Oz source on demand."""
    development_build = ROOT.parent / "Repl.ozf"
    if (ROOT.parent / "Makefile").is_file() and development_build.is_file():
        return development_build

    source = ROOT / "Repl.oz"
    ozc = find_mozart_command("ozc")
    compiler = Path(ozc)
    compiler_identity = f"{compiler.resolve()}:{compiler.stat().st_mtime_ns}"
    digest = hashlib.sha256(source.read_bytes() + compiler_identity.encode()).hexdigest()[:16]
    cache = user_cache_dir()
    target = cache / f"Repl-{digest}.ozf"
    if target.is_file():
        return target

    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=cache) as directory:
        output = Path(directory) / "Repl.ozf"
        result = subprocess.run(
            [ozc, "--nowarnunused", "--nowarnunusedformals", "-c", str(source), "-o", str(output)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            diagnostic = (result.stderr or result.stdout).strip()
            raise SystemExit("Could not compile the ozrepl backend:\n\n" + diagnostic)
        os.replace(output, target)
    return target


# Mirrored from `oz-keywords` and the token matchers in Mozart's oz.el.
OZ_KEYWORDS = (
    "declare local in end proc fun functor require prepare import export define at "
    "case then else of elseof elsecase if elseif class from prop attr feat meth "
    "self true false unit div mod andthen orelse cond or dis choice not thread "
    "try catch finally raise lock skip fail for do suchthat"
).split()


class OzLexer(RegexLexer):
    name = "Oz"
    flags = re.MULTILINE | re.UNICODE
    tokens = {
        "root": [
            (r"%.*$", Comment.Single),
            (r'"(?:\\.|[^"\\])*"', String.Double),
            (r"'(?:\\.|[^'\\])*'", String.Single),
            (r"`(?:\\.|[^`\\])*`", Name.Variable),
            (r"&(?:\\(?:[0-7]{3}|x[0-9A-Fa-f]{2}|[abfnrtv'\"`])|.)", String.Char),
            (r"\\[a-zA-Z][^\s]*", Name.Decorator),
            (r"\b(?:" + "|".join(OZ_KEYWORDS) + r")\b", Keyword),
            (r"\b(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?)\b", Number),
            (r"\b[A-Z_][\w.]*\b|\$", Name.Variable),
            (r"\b[a-z][\w_]*\b", Name.Constant),
            (r"\[\]|:::?|:=|==|\\=|=<|>=|<|>|[!#|.@,~*/+\-=]", Operator),
            (r"[(){}\[\]]", Punctuation),
            (r"\s+", Text.Whitespace),
            (r".", Text),
        ]
    }


TERMINAL_STYLE = Style.from_dict(
    {
        "pygments.keyword": "bold #ansimagenta",
        "pygments.name.variable": "#ansicyan",
        "pygments.name.constant": "#ansiblue",
        "pygments.name.decorator": "#ansiyellow",
        "pygments.string": "#ansigreen",
        "pygments.number": "#ansiyellow",
        "pygments.operator": "#ansicyan",
        "pygments.punctuation": "#ansicyan",
        "pygments.comment": "italic #ansibrightblack",
        "error": "bold #ansired",
        "status": "#ansibrightblack",
    }
)


class BackendExited(Exception):
    """The Oz engine exited while processing a frontend request."""

    def __init__(self, diagnostic: str) -> None:
        super().__init__(diagnostic)
        self.diagnostic = diagnostic


class OzBackend:
    def __init__(self, backend: Path, *, no_gui: bool = False) -> None:
        self.lock = threading.RLock()
        self.no_gui = no_gui
        self.backend = backend
        self.child: subprocess.Popen[str] | None = None
        self.output: queue.Queue[str | None] = queue.Queue()
        self.connection: socket.socket | None = None
        self._start()

    def _start(self) -> None:
        self.output = queue.Queue()
        self.child = subprocess.Popen(
            [find_mozart_command("ozengine"), str(self.backend)],
            cwd=os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert self.child.stdout is not None
        threading.Thread(target=self._collect_output, daemon=True).start()
        diagnostic: list[str] = []
        deadline = REQUEST_TIMEOUT
        while True:
            try:
                line = self._read_line(deadline)
            except BackendExited as error:
                raise SystemExit(
                    "Mozart/Oz backend failed during startup:\n\n" + error.diagnostic
                ) from error
            if line is None:
                detail = "".join(diagnostic).strip()
                raise SystemExit(
                    "Mozart/Oz backend failed during startup:\n\n"
                    + (detail or "ozengine exited without printing a diagnostic")
                )
            match = re.search(r"__OZREPL_PORT__(\d+)", line)
            if match:
                self.port = int(match.group(1))
                break
            diagnostic.append(line)
        self.connection = socket.create_connection(("127.0.0.1", self.port))
        self._read_until_ready()
        if self.no_gui:
            self._send(":no-gui")
            self._read_until_ready()

    def _restart(self) -> None:
        self._close_transport()
        self._start()

    def _close_transport(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.child is not None and self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.child.kill()

    def _collect_output(self) -> None:
        assert self.child is not None and self.child.stdout is not None
        for line in self.child.stdout:
            self.output.put(line)
        self.output.put(None)

    def _read_line(self, timeout: float) -> str | None:
        try:
            return self.output.get(timeout=timeout)
        except queue.Empty as error:
            raise BackendExited("Error: Mozart/Oz backend did not finish the request") from error

    def _read_until_ready(self) -> str:
        lines: list[str] = []
        while True:
            line = self._read_line(REQUEST_TIMEOUT)
            if line is None:
                diagnostic = "".join(lines).strip()
                raise BackendExited(diagnostic or "Error: Mozart/Oz backend exited unexpectedly")
            if READY in line:
                before, _, after = line.partition(READY)
                lines.append(before)
                if after.strip():
                    lines.append(after)
                return "".join(lines).replace("\r\n", "\n").replace("\r", "\n").strip("\n")
            lines.append(line)

    def submit(self, source: str) -> str:
        with self.lock:
            try:
                self._send(source, expression=is_expression(source))
                return self._read_until_ready()
            except BackendExited:
                self._restart()
                raise

    def reload(self, path: Path, *, clear: bool) -> str:
        """Load path, optionally resetting first, without requests interleaving."""
        with self.lock:
            try:
                output = ""
                if clear:
                    self._send(":reset")
                    output = self._read_until_ready()
                self._send(str(path), tag=b"F")
                loaded = self._read_until_ready()
                return "\n".join(part for part in (output, loaded) if part)
            except BackendExited:
                self._restart()
                raise

    def _send(
        self, source: str, *, expression: bool = False, tag: bytes | None = None
    ) -> None:
        tag = tag or (b"E" if expression else b"S")
        encoded = (tag + source.encode("utf-8")).hex().encode("ascii") + b"\n"
        assert self.connection is not None
        self.connection.sendall(encoded)

    def quit(self) -> str:
        with self.lock:
            assert self.child is not None
            if self.child.poll() is not None:
                return ""
            self._send(":quit")
            lines: list[str] = []
            while True:
                line = self._read_line(REQUEST_TIMEOUT)
                if line is None:
                    break
                lines.append(line)
            self.child.wait(timeout=1)
            return "".join(lines).replace("\r\n", "\n").strip()

    def close(self) -> None:
        self._close_transport()


class BrowseOutput:
    """Route Browse results to a tmux side pane or to the main terminal."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.path: Path | None = None
        self.pane: str | None = None
        if self.mode == "tmux":
            temporary = tempfile.NamedTemporaryFile(
                prefix="ozrepl-browse-", suffix=".log", delete=False
            )
            temporary.close()
            self.path = Path(temporary.name)
            command = " ".join(
                shlex.quote(part)
                for part in (
                    sys.executable,
                    "-m",
                    "ozrepl.browse",
                    str(self.path),
                    str(os.getpid()),
                )
            )
            try:
                result = subprocess.run(
                    ["tmux", "split-window", "-h", "-d", "-P", "-F", "#{pane_id}", command],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.pane = result.stdout.strip()
            except (OSError, subprocess.CalledProcessError) as error:
                print(f"warning: cannot open tmux Browse pane: {error}", file=sys.stderr)
                self.mode = "terminal"

    def write(self, identifier: str, value: str, *, update: bool = False) -> None:
        if self.mode == "tmux" and self.path is not None:
            with self.path.open("a", encoding="utf-8") as stream:
                operation = "U" if update else "B"
                escaped = value.rstrip("\n").replace("\\", "\\\\").replace("\n", "\\n")
                stream.write(f"{operation}\t{identifier}\t{escaped}\n")
        else:
            emit(value)

    def reset(self) -> None:
        if self.mode == "tmux" and self.path is not None:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write("C\n")

    def close(self) -> None:
        if self.pane:
            subprocess.run(
                ["tmux", "kill-pane", "-t", self.pane],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        if self.path is not None:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


class FileWatcher:
    """Poll one source file and reload it after each observable change."""

    def __init__(self, reload_file) -> None:  # type: ignore[no-untyped-def]
        self.reload_file = reload_file
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.lock = threading.Lock()
        self.path: Path | None = None
        self.clear = False
        self.generation = 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def watch(self, path: Path, *, clear: bool) -> None:
        with self.lock:
            self.path = path.resolve()
            self.clear = clear
            self.generation += 1
        self.wake_event.set()

    def unwatch(self) -> bool:
        with self.lock:
            was_watching = self.path is not None
            self.path = None
            self.generation += 1
        self.wake_event.set()
        return was_watching

    def close(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        self.thread.join(timeout=1)

    def _run(self) -> None:
        seen: tuple[int, int, int, int] | None = None
        generation = -1
        while not self.stop_event.is_set():
            with self.lock:
                path, clear, current_generation = self.path, self.clear, self.generation
            if current_generation != generation:
                generation, seen = current_generation, None
            if path is not None:
                try:
                    stat = path.stat()
                    signature = (
                        stat.st_mtime_ns,
                        stat.st_ctime_ns,
                        stat.st_size,
                        stat.st_ino,
                    )
                except OSError:
                    signature = None
                if signature is not None and signature != seen:
                    seen = signature
                    self.reload_file(path, clear)
            self.wake_event.wait(0.25)
            self.wake_event.clear()


def split_browse_output(output: str) -> tuple[str, list[tuple[str, str, bool]]]:
    """Extract values preceded by the backend's Browse marker."""
    regular: list[str] = []
    browsed: list[tuple[str, str, bool]] = []
    lines = output.replace("\r\n", "\n").splitlines()
    index = 0
    while index < len(lines):
        marker = lines[index]
        is_browse = marker.startswith(BROWSE_MARKER)
        is_update = marker.startswith(BROWSE_UPDATE_MARKER)
        if is_browse or is_update:
            if index + 1 < len(lines):
                prefix = BROWSE_UPDATE_MARKER if is_update else BROWSE_MARKER
                browsed.append((marker[len(prefix):], lines[index + 1], is_update))
                index += 2
            else:
                index += 1
        else:
            regular.append(lines[index])
            index += 1
    return "\n".join(regular), browsed

class Input:
    def __init__(self, *, vi_mode: bool = False, color: bool = True) -> None:
        self.interactive = sys.stdin.isatty()
        bindings = KeyBindings()

        @bindings.add("enter", eager=True)
        def submit(event) -> None:  # type: ignore[no-untyped-def]
            event.current_buffer.validate_and_handle()

        @bindings.add("escape", "enter", eager=True)
        def newline(event) -> None:  # type: ignore[no-untyped-def]
            event.current_buffer.insert_text("\n")

        @bindings.add("c-x", "c-e", eager=True)
        def edit_fragment(event) -> None:  # type: ignore[no-untyped-def]
            event.current_buffer.open_in_editor()

        self.session = (
            PromptSession(
                history=FileHistory(str(Path.home() / ".oz_repl_history")),
                key_bindings=bindings,
                lexer=PygmentsLexer(OzLexer) if color else None,
                style=TERMINAL_STYLE,
                color_depth=ColorDepth.DEPTH_8_BIT if color else None,
                multiline=True,
                prompt_continuation="... ",
                enable_open_in_editor=True,
                tempfile_suffix=".oz",
                vi_mode=vi_mode,
            )
            if self.interactive
            else None
        )

    def read(self, prompt: str) -> str:
        if self.session is not None:
            return self.session.prompt(prompt)
        line = sys.stdin.readline()
        if line == "":
            raise EOFError
        return line.rstrip("\r\n")


STATEMENT_KEYWORDS = re.compile(
    r"^(declare|local|proc|fun|class|functor|thread|if|case|for|try|raise|skip|fail)\b"
)
ASSIGNMENT = re.compile(r"(?<![=<>\\])=(?!=|<)")


def is_expression(source: str) -> bool:
    """Recognize common Oz expressions without trying to replace its parser."""
    text = source.strip()
    if not text or text.startswith(":") or STATEMENT_KEYWORDS.match(text):
        return False
    if ASSIGNMENT.search(text):
        return False
    if re.match(r"^\{(?:Show|Browse|Print)\b", text):
        return False
    return True


def clean_output(output: str) -> str:
    """Condense Mozart's compiler boxes while leaving program output intact."""
    if not re.search(r"^%\*{5,}", output, re.MULTILINE):
        return output.strip("\n")

    lines = output.replace("\r\n", "\n").splitlines()
    errors: list[str] = []
    title_pattern = re.compile(r"^%\*{10,}\s+(.+?)\s+\*{10,}$")
    location_pattern = re.compile(
        r'^%\*\* in file "(?:top level|[^\"]+)", line (\d+), column (\d+)'
    )

    for index, line in enumerate(lines):
        title_match = title_pattern.match(line)
        if not title_match:
            continue
        title = title_match.group(1).strip().capitalize()
        detail = ""
        location = ""
        for following in lines[index + 1 :]:
            if title_pattern.match(following):
                break
            location_match = location_pattern.match(following)
            if location_match and not location:
                location = f"line {location_match.group(1)}, column {location_match.group(2)}"
            if following.startswith("%** "):
                candidate = following[4:].strip()
                if (
                    candidate
                    and not candidate.startswith(("in file ", "(", "Call Stack", "Query:"))
                    and "other candidates" not in candidate
                    and not candidate.startswith("-")
                ):
                    detail = detail or candidate
        message = f"{title}: {detail}" if detail else title
        if location:
            message += f" ({location})"
        errors.append(message)

    # Nested compiler errors usually contain a generic outer error followed by
    # the actionable one; show only the latter in that case.
    if len(errors) > 1 and errors[0].startswith("Compiler engine error"):
        errors = errors[1:]
    return "\n".join(f"Error: {message}" for message in errors)


def emit(output: str) -> None:
    cleaned = clean_output(output)
    if not cleaned:
        return
    if not USE_COLOR:
        print(cleaned, flush=True)
    elif cleaned.startswith("Error:"):
        print_formatted_text(
            FormattedText([("class:error", cleaned)]),
            style=TERMINAL_STYLE,
            color_depth=ColorDepth.DEPTH_8_BIT,
        )
    elif cleaned in {"bye", "compiler environment reset"}:
        print_formatted_text(
            FormattedText([("class:status", cleaned)]),
            style=TERMINAL_STYLE,
            color_depth=ColorDepth.DEPTH_8_BIT,
        )
    else:
        tokens = list(OzLexer().get_tokens(cleaned))
        print_formatted_text(
            PygmentsTokens(tokens),
            style=TERMINAL_STYLE,
            color_depth=ColorDepth.DEPTH_8_BIT,
            end="",
        )


def emit_routed(output: str, browser: BrowseOutput) -> None:
    regular, browsed = split_browse_output(output)
    emit(regular)
    for identifier, value, update in browsed:
        browser.write(identifier, value, update=update)


def main() -> int:
    global USE_COLOR
    parser = argparse.ArgumentParser(description="Interactive Mozart/Oz REPL")
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="Oz source file to load and watch for changes",
    )
    parser.add_argument(
        "--browse",
        choices=("auto", "tmux", "terminal", "gui"),
        default="auto",
        help=(
            "Browse destination: tmux in tmux, terminal on Windows, otherwise Tk "
            "(default: auto)"
        ),
    )
    parser.add_argument(
        "--vi",
        dest="vi",
        action="store_true",
        default=False,
        help="use Vi keybindings for inline prompt editing",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable syntax highlighting and colored output",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="reset the compiler before each watched-file load",
    )
    arguments = parser.parse_args()
    if arguments.clear and arguments.file is None:
        parser.error("--clear requires FILE")
    if arguments.file is not None and not arguments.file.is_file():
        parser.error(f"file not found: {arguments.file}")

    # Use the checkout's syntax-aware helper without overriding a configured editor.
    editor_helper = ROOT.parent / "oz-vim"
    if os.name == "posix" and editor_helper.is_file():
        os.environ.setdefault("VISUAL", f"sh {shlex.quote(str(editor_helper))}")

    USE_COLOR = sys.stdout.isatty() and not arguments.no_color and "NO_COLOR" not in os.environ
    terminal = Input(vi_mode=arguments.vi, color=USE_COLOR)
    browse_mode = arguments.browse
    if browse_mode == "auto":
        if os.environ.get("TMUX"):
            browse_mode = "tmux"
        elif sys.platform == "win32":
            browse_mode = "terminal"
        else:
            browse_mode = "gui"
    backend = OzBackend(compiled_backend(), no_gui=browse_mode != "gui")
    browser = BrowseOutput(browse_mode)
    output_lock = threading.Lock()

    def reload_file(path: Path, clear: bool) -> None:
        with output_lock:
            browser.reset()
            try:
                emit_routed(backend.reload(path, clear=clear), browser)
            except BackendExited as error:
                emit(error.diagnostic)
                print("backend restarted; compiler environment was reset", flush=True)
            else:
                print(f"reloaded {path}", flush=True)

    watcher = FileWatcher(reload_file)

    def start_watch(path: Path, *, clear: bool) -> None:
        watcher.watch(path, clear=clear)
        suffix = " (clear environment)" if clear else ""
        print(f"watching {path.resolve()}{suffix}")

    if terminal.interactive:
        print("Oz REPL -- type :help for help")
    if arguments.file is not None:
        start_watch(arguments.file, clear=arguments.clear)

    try:
        stdout_context = patch_stdout(raw=True) if terminal.interactive else nullcontext()
        with stdout_context:
            while True:
                try:
                    line = terminal.read("Oz> ")
                except KeyboardInterrupt:
                    print("^C")
                    continue
                except EOFError:
                    emit_routed(backend.quit(), browser)
                    return 0

                if line == ":help":
                    print(HELP)
                elif line == ":quit":
                    emit_routed(backend.quit(), browser)
                    return 0
                elif line == ":reset":
                    with output_lock:
                        try:
                            emit_routed(backend.submit(line), browser)
                        except BackendExited as error:
                            emit(error.diagnostic)
                            print("backend restarted; compiler environment was reset")
                        else:
                            browser.reset()
                elif line == ":unwatch":
                    message = (
                        "file watch stopped"
                        if watcher.unwatch()
                        else "no file is being watched"
                    )
                    print(message)
                elif line == ":watch" or line.startswith(":watch "):
                    try:
                        parts = shlex.split(line)
                    except ValueError as error:
                        emit(f"Error: {error}")
                        continue
                    clear = "--clear" in parts[1:]
                    files = [part for part in parts[1:] if part != "--clear"]
                    if len(files) != 1:
                        emit("Error: usage: :watch [--clear] FILE")
                        continue
                    path = Path(files[0])
                    if not path.is_file():
                        emit(f"Error: file not found: {path}")
                        continue
                    start_watch(path, clear=clear)
                else:
                    with output_lock:
                        try:
                            emit_routed(backend.submit(line), browser)
                        except BackendExited as error:
                            emit(error.diagnostic)
                            print("backend restarted; compiler environment was reset")
    finally:
        watcher.close()
        backend.close()
        browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
