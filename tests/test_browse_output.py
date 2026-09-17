#!/usr/bin/env python3
"""Regression test for lazy creation of the tmux Browse pane."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ozrepl.cli import BrowseOutput


with patch("ozrepl.cli.subprocess.run") as run:
    run.return_value = SimpleNamespace(stdout="%42\n")
    browser = BrowseOutput("tmux")
    assert browser.path is None
    assert browser.pane is None
    run.assert_not_called()

    browser.write("0", "3")
    assert browser.path is not None
    assert browser.path.read_text(encoding="utf-8") == "B\t0\t3\n"
    assert run.call_args.args[0][:3] == ["tmux", "split-window", "-h"]

    old_path = browser.path
    run.side_effect = [
        # tmux can return success when a target pane is gone, so liveness is
        # determined from exact pane IDs rather than the command's status.
        SimpleNamespace(returncode=0, stdout="%99\t0\n"),
        SimpleNamespace(returncode=0, stdout="%43\n"),
    ]
    browser.write("1", "4")
    assert not old_path.exists()
    assert browser.path is not None
    assert browser.path != old_path
    assert browser.path.read_text(encoding="utf-8") == "B\t1\t4\n"
    assert browser.pane == "%43"

    path = browser.path
    run.side_effect = None
    browser.close()
    assert not Path(path).exists()

print("ozrepl lazy Browse pane test passed")
