#!/usr/bin/env python3
"""Small live viewer used by ozrepl's tmux Browse pane."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import time


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("parent", type=int)
    args = parser.parse_args()

    values: dict[str, str] = {}
    order: list[str] = []
    position = 0
    while alive(args.parent):
        try:
            with args.file.open("r", encoding="utf-8") as stream:
                stream.seek(position)
                chunk = stream.read()
                position = stream.tell()
        except FileNotFoundError:
            chunk = ""
        if chunk:
            for line in chunk.splitlines():
                fields = line.split("\t", 2)
                if fields == ["C"]:
                    values.clear()
                    order.clear()
                    continue
                if len(fields) != 3:
                    continue
                operation, identifier, encoded = fields
                value = encoded.replace("\\n", "\n").replace("\\\\", "\\")
                if identifier not in values:
                    order.append(identifier)
                values[identifier] = value
            print("\033[2J\033[H", end="")
            print("Oz Browse")
            print("---------")
            for identifier in order:
                print(values[identifier])
            print(flush=True)
        time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
