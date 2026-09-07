#!/usr/bin/env python3
"""Check that the bundled Neovim runtime detects and highlights Oz."""

from pathlib import Path
import shutil
import subprocess


nvim = shutil.which("nvim")
if nvim is None:
    print("ozrepl Neovim syntax test skipped (nvim not installed)")
    raise SystemExit(0)

root = Path(__file__).resolve().parent.parent
result = subprocess.run(
    [
        nvim,
        "-u", "NONE",
        "-i", "NONE",
        "--headless",
        "--cmd", f"set runtimepath^={root / 'vim'}",
        "--cmd", "filetype plugin indent on",
        "--cmd", "syntax enable",
        str(root / "tests" / "loaded.oz"),
        "+echo &filetype",
        '+echo synIDattr(synID(1,1,1),"name")',
        "+qa",
    ],
    check=True,
    capture_output=True,
    text=True,
)
output = result.stdout + result.stderr
if "oz" not in output or "ozKeyword" not in output:
    raise SystemExit(f"Oz syntax was not loaded:\n{output}")

print("ozrepl Neovim syntax test passed")
