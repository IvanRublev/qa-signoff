#!/usr/bin/env python3
"""
Remember the writing mode the user chose, in the test project's .qa-signoff folder, and say whether it still works.

Usage:
    python3 write_mode.py get --pro yes|no [--dir DIR]
        print the saved mode (`kaizero`, `subagents` or `sequential`) when it still works, else `none: <cause>`,
        the cause naming what to fix (no mode saved, pack missing, isolated-run instructions missing, Kaizero commands missing).
        --pro  yes when the pack detection of qa-write-tests/references/pro-detection.md says so
    python3 write_mode.py save kaizero|subagents|sequential [--dir DIR]
    python3 write_mode.py --self-test

A saved mode works when: `sequential` always; `subagents` with the pack installed and the instruction file's
`## Isolated runs` section present; `kaizero` the same, plus `kaizero`, `kz-tmux` and `tmux` on PATH.
"""

import shutil
import sys
import tempfile
from pathlib import Path

MODES = ('kaizero', 'subagents', 'sequential')
INSTRUCTION_FILES = ('CLAUDE.md', 'AGENTS.md', 'GEMINI.md', '.github/copilot-instructions.md')


def saved_path(d):
    return d / '.qa-signoff' / 'write-mode'


def isolated(d):
    return any((d / f).is_file() and '## Isolated runs' in (d / f).read_text() for f in INSTRUCTION_FILES)


def get(d, pro):
    path = saved_path(d)
    mode = path.read_text().strip() if path.is_file() else None
    if mode == 'sequential':
        return mode
    if mode not in ('subagents', 'kaizero'):
        return 'none: no writing mode saved yet' if mode is None else f'none: saved mode {mode!r} is unknown'
    if not pro:
        return f'none: saved mode {mode} needs the qa-signoff-pro pack, which is not installed'
    if not isolated(d):
        return f'none: saved mode {mode} needs the isolated-run instructions; the instruction file has no "## Isolated runs" section (run qa-prepare-isolated-runs)'
    missing = [c for c in ('kaizero', 'kz-tmux', 'tmux') if mode == 'kaizero' and not shutil.which(c)]
    if missing:
        return f'none: saved mode kaizero needs {", ".join(missing)} on PATH (install Kaizero)'
    return mode


def save(d, mode):
    path = saved_path(d)
    path.parent.mkdir(exist_ok=True)
    path.write_text(mode + '\n')
    return mode


def self_test():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        assert get(d, True).startswith('none: no writing mode saved'), 'nothing saved'
        assert save(d, 'sequential') == 'sequential' and get(d, False) == 'sequential'
        save(d, 'subagents')
        assert 'pack' in get(d, False)
        assert 'Isolated runs' in get(d, True), 'no instruction file section'
        (d / 'CLAUDE.md').write_text('# x\n\n## Isolated runs\n')
        assert get(d, True) == 'subagents'
        save(d, 'kaizero')
        have = all(shutil.which(c) for c in ('kaizero', 'kz-tmux', 'tmux'))
        assert get(d, True) == 'kaizero' if have else get(d, True).startswith('none: saved mode kaizero needs ')
        save(d, 'bogus')
        assert 'unknown' in get(d, True)
    print('write_mode.py self-test ok')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a in (['-h'], ['--help']):
        print(__doc__)
    elif a == ['--self-test']:
        self_test()
    else:
        d = Path(a[a.index('--dir') + 1]) if '--dir' in a else Path('.')
        pro = a[a.index('--pro') + 1] if '--pro' in a[:-1] else None
        if a[:1] == ['get'] and pro in ('yes', 'no'):
            print(get(d, pro == 'yes'))
        elif a[:1] == ['save'] and len(a) > 1 and a[1] in MODES:
            print(save(d, a[1]))
        else:
            print(__doc__, file=sys.stderr)
            sys.exit(2)
