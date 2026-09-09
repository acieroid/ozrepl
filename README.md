# ozrepl

A terminal REPL for Mozart/Oz.

## Installation

You need Mozart/Oz 2 and Python 3. Make sure the Mozart commands `ozc` and
`ozengine` are on your `PATH`, then install ozrepl with
[pipx](https://pipx.pypa.io/):

```sh
pipx install git+https://github.com/acieroid/ozrepl.git
ozrepl
```

## Using the REPL

- `Enter` submits the current fragment.
- `Alt-Enter` or `Shift-Enter` inserts a newline.
- `Ctrl-X Ctrl-E` edits the fragment in your editor (with Oz highlighting if it's vim).
- `Ctrl-C` cancels the current input; `Ctrl-D` exits.

Available REPL commands are:

- `:load FILE` loads an Oz source file (paths cannot contain spaces).
- `:watch FILE` loads a file immediately and reloads it whenever it changes,
  replacing the previous Browse view each time.
- `:watch --clear FILE` additionally resets the compiler before every load.
- `:unwatch` stops watching the current file.
- `:reset` clears all user declarations and the Browse window or pane.
- `:help` shows help; `:quit` exits.

## Browse

Inside tmux, `{Browse X}` opens a pane on the right. An unbound dataflow value
is updated in place when it becomes bound. Outside tmux, the native Mozart Tk
Browser is used.
