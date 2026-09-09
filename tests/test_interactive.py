#!/usr/bin/env python3
"""Regression test for prompt display and per-line execution."""

from pathlib import Path
import os
import shlex
import sys
import tempfile

import pexpect


root = Path(__file__).resolve().parent.parent
environment = dict(os.environ, TERM="xterm-256color")
environment.pop("NO_COLOR", None)
child = pexpect.spawn(
    sys.executable,
    ["-m", "ozrepl", "--browse=terminal"],
    cwd=str(root),
    env=environment,
    encoding="utf-8",
    timeout=10,
)

try:
    child.expect_exact("Oz>")
    child.sendline(":help")
    child.expect_exact("Commands:")
    child.expect_exact("Alt-Enter")
    child.expect_exact("Oz>")
    child.sendline("declare X = 21")
    child.expect_exact("Oz>")
    child.sendline("{Show X*2}")
    child.expect_exact("42")
    child.expect_exact("Oz>")

    child.send("declare")
    child.send("\x1b\r")
    child.expect_exact("...")
    child.send("fun {Double N}")
    child.send("\x1b\r")
    child.expect_exact("...")
    child.send("   N*2")
    child.send("\x1b\r")
    child.expect_exact("...")
    child.sendline("end")
    child.expect_exact("Oz>")
    child.sendline("{Double 4}")
    child.expect_exact("8")
    child.expect_exact("Oz>")

    child.sendline("declare Pending")
    child.expect_exact("Oz>")
    child.sendline("{Browse Pending}")
    child.expect_exact("Oz>")
    child.sendline("Pending=123")
    child.expect_exact("123")
    child.expect_exact("Oz>")

    with tempfile.TemporaryDirectory(prefix="ozrepl watch ") as directory:
        watched = Path(directory) / "watched file.oz"
        watched.write_text("declare Watched = 1\n", encoding="utf-8")
        child.sendline(f":watch --clear {shlex.quote(str(watched))}")
        child.expect_exact("watching ")
        child.expect_exact("reloaded ")
        child.expect_exact("Oz>")
        child.sendline("Watched")
        child.expect_exact("1")
        child.expect_exact("Oz>")

        watched.write_text("declare Watched = 2\n", encoding="utf-8")
        child.expect_exact("reloaded ")
        child.sendline("Watched")
        child.expect_exact("2")
        child.expect_exact("Oz>")
        child.sendline("X")
        child.expect_exact("Error:")
        child.expect_exact("Oz>")
        child.sendline(":unwatch")
        child.expect_exact("file watch stopped")
        child.expect_exact("Oz>")

    child.sendline("2+")
    child.expect(r"\x1b\[[0-9;]*(?:31|91)(?:;[0-9;]*)?m")
    child.expect_exact("Error: Parse error")
    child.expect_exact("Oz>")

    child.sendcontrol("d")
    child.expect_exact("bye")
    child.expect(pexpect.EOF)
finally:
    child.close(force=True)

print("ozrepl interactive prompt test passed")

with tempfile.TemporaryDirectory(prefix="ozrepl argument watch ") as directory:
    watched = Path(directory) / "argument watched.oz"
    watched.write_text(
        "local X Y in X=[Y] Y=42 X.1+2=40 {Browse X} end\n",
        encoding="utf-8",
    )
    child = pexpect.spawn(
        sys.executable,
        ["-m", "ozrepl", "--browse=terminal", "--clear", str(watched)],
        cwd=str(root),
        env=environment,
        encoding="utf-8",
        timeout=10,
    )
    try:
        child.expect_exact("watching ")
        child.expect_exact("reloaded ")
        child.expect_exact("Oz>")

        watched.write_text(
            "local X Y in X=[Y] Y=42 X.1+2=40 {Browse X} end\n",
            encoding="utf-8",
        )
        child.expect_exact("Error:")
        child.expect_exact("backend restarted; compiler environment was reset")
        child.expect_exact("Oz>")

        watched.write_text(
            "declare ArgumentWatched = 41 {Browse ArgumentWatched+1}\n",
            encoding="utf-8",
        )
        child.expect_exact("42")
        child.expect_exact("reloaded ")
        child.expect_exact("Oz>")
        child.sendline("ArgumentWatched + 1")
        child.expect_exact("42")
        child.expect_exact("Oz>")
        child.sendline(":quit")
        child.expect_exact("bye")
        child.expect(pexpect.EOF)
    finally:
        child.close(force=True)

print("ozrepl file argument watch test passed")
