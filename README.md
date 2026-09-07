# ozrepl

A terminal REPL for Mozart/Oz.

## Setup

You need Mozart/Oz 2, Python 3, and the Python dependencies:

```sh
python3 -m pip install -r requirements.txt
make
./ozrepl
```

`make run` builds and starts the REPL. Command history is saved in
`~/.oz_repl_history`.

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

