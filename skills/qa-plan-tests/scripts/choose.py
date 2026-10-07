#!/usr/bin/env python3
"""
A checkbox menu in the terminal, for agents without a multiple-choice question tool. Reads groups of options from a JSON
file, lets the user tick them with the keyboard, and prints the chosen values as JSON.

Options file:
    {"groups": [{"id": "roles", "title": "Roles", "other": true,
                 "options": [{"value": "Admin", "label": "Admin (config/security.yaml:3)", "checked": true}]}]}
`label` defaults to `value`; `checked` to false; `other: true` lets the user type one more value.

Output: {"<group id>": ["<chosen value>", ...], ...}, on stdout or in the file named by --out.
Keys: up/down move, space ticks, a adds a value of your own (when the group allows it), enter confirms the group,
q quits without output (exit 1).

Usage:
    python3 choose.py <options.json> [--out <file>]
    python3 choose.py --self-test

Run it in a real terminal. A coding agent's own shell has no keyboard attached: ask the user to run it themselves
(in Claude Code, by typing `! python3 choose.py ...` in the prompt). Exit codes: 0 ok, 1 quit, 2 usage error or no terminal.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


def load_groups(data):
    """Validate the options and fill in the defaults; raise ValueError naming the first problem."""
    groups = data.get('groups') if isinstance(data, dict) else None
    if not isinstance(groups, list) or not groups:
        raise ValueError('options need a non-empty "groups" list')
    out = []
    for g in groups:
        if not isinstance(g, dict) or not g.get('id') or not isinstance(g.get('options'), list):
            raise ValueError('every group needs an "id" and an "options" list')
        options = []
        for o in g['options']:
            if not isinstance(o, dict) or not isinstance(o.get('value'), str) or not o['value']:
                raise ValueError(f'group {g["id"]!r}: every option needs a non-empty string "value"')
            options.append({'value': o['value'], 'label': o.get('label') or o['value'], 'checked': bool(o.get('checked'))})
        out.append({'id': g['id'], 'title': g.get('title') or g['id'], 'other': bool(g.get('other')), 'options': options})
    return out


class Menu:
    """The state of one group: no drawing, so it can be tested."""

    def __init__(self, options):
        self.options = [dict(o) for o in options]
        self.cursor = 0

    def move(self, delta):
        if self.options:
            self.cursor = (self.cursor + delta) % len(self.options)

    def toggle(self):
        if self.options:
            self.options[self.cursor]['checked'] = not self.options[self.cursor]['checked']

    def add(self, text):
        text = text.strip()
        known = next((i for i, o in enumerate(self.options) if o['value'].lower() == text.lower()), None)
        if known is None and text:
            self.options.append({'value': text, 'label': text, 'checked': True})
            known = len(self.options) - 1
        if known is not None:
            self.options[known]['checked'] = True
            self.cursor = known

    def selected(self):
        return [o['value'] for o in self.options if o['checked']]


def _ask(groups):
    import curses

    def run(screen):
        curses.curs_set(0)
        chosen = {}
        for g in groups:
            menu = Menu(g['options'])
            while True:
                screen.erase()
                screen.addstr(0, 0, g['title'], curses.A_BOLD)
                hint = 'up/down move   space tick   ' + ('a add your own   ' if g['other'] else '') + 'enter confirm   q quit'
                screen.addstr(1, 0, hint, curses.A_DIM)
                for i, o in enumerate(menu.options):
                    attr = curses.A_REVERSE if i == menu.cursor else curses.A_NORMAL
                    screen.addstr(3 + i, 0, f"[{'x' if o['checked'] else ' '}] {o['label']}"[:curses.COLS - 1], attr)
                key = screen.getch()
                if key in (curses.KEY_UP, ord('k')):
                    menu.move(-1)
                elif key in (curses.KEY_DOWN, ord('j')):
                    menu.move(1)
                elif key == ord(' '):
                    menu.toggle()
                elif key == ord('a') and g['other']:
                    curses.echo()
                    curses.curs_set(1)
                    screen.addstr(4 + len(menu.options), 0, 'Add: ')
                    menu.add(screen.getstr().decode('utf-8', 'replace'))
                    curses.noecho()
                    curses.curs_set(0)
                elif key in (10, 13, curses.KEY_ENTER):
                    chosen[g['id']] = menu.selected()
                    break
                elif key in (ord('q'), 27):
                    return None
        return chosen

    return curses.wrapper(run)


def _self_test():
    class ChooseTest(unittest.TestCase):
        def test_load_groups_fills_defaults(self):
            groups = load_groups({'groups': [{'id': 'roles', 'options': [{'value': 'Admin'}]}]})
            self.assertEqual(groups, [{'id': 'roles', 'title': 'roles', 'other': False,
                                       'options': [{'value': 'Admin', 'label': 'Admin', 'checked': False}]}])

        def test_load_groups_rejects_bad_input(self):
            for bad in ({}, {'groups': []}, {'groups': [{'options': []}]}, {'groups': [{'id': 'a', 'options': [{}]}]},
                        {'groups': [{'id': 'a', 'options': [{'value': 3}]}]}):
                with self.assertRaises(ValueError):
                    load_groups(bad)

        def test_menu_moves_wraps_and_toggles(self):
            menu = Menu([{'value': 'a', 'checked': True}, {'value': 'b', 'checked': False}])
            menu.move(1)
            menu.toggle()
            menu.move(1)
            self.assertEqual((menu.cursor, menu.selected()), (0, ['a', 'b']))
            menu.toggle()
            self.assertEqual(menu.selected(), ['b'])
            menu.move(-1)
            self.assertEqual(menu.cursor, 1)

        def test_menu_adds_a_value_once_ignoring_case_and_ticks_it(self):
            menu = Menu([{'value': 'Admin', 'checked': False}])
            menu.add(' Teamlead ')
            menu.add('teamlead')
            menu.add('admin')
            self.assertEqual(menu.selected(), ['Admin', 'Teamlead'])
            menu.add('   ')
            self.assertEqual(len(menu.options), 2)

        def test_without_a_terminal_it_exits_2(self):
            with tempfile.TemporaryDirectory() as d:
                opts = Path(d) / 'o.json'
                opts.write_text('{"groups": [{"id": "a", "options": [{"value": "x"}]}]}')
                self.assertEqual(main([str(opts)], tty=False), 2)

        def test_the_whole_menu_in_a_pseudo_terminal(self):
            import pty
            import select
            import subprocess
            with tempfile.TemporaryDirectory() as d:
                opts, out = Path(d) / 'o.json', Path(d) / 'out.json'
                opts.write_text(json.dumps({'groups': [
                    {'id': 'roles', 'title': 'Roles', 'other': True, 'options': [{'value': 'Admin'}, {'value': 'User', 'checked': True}]},
                    {'id': 'env', 'title': 'Environments', 'options': [{'value': 'Desktop Chrome'}, {'value': 'iPhone 13'}]}]}))
                master, slave = pty.openpty()
                env = dict(os.environ, TERM='xterm', LINES='24', COLUMNS='80')
                proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(opts), '--out', str(out)],
                                        stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
                os.close(slave)

                def read_until(text, seconds=5):
                    seen = b''
                    while text not in seen and select.select([master], [], [], seconds)[0]:
                        seen += os.read(master, 65536)
                    return seen

                def press(keys):
                    for k in keys:
                        os.write(master, k)
                        read_until(b'\x1b', 1)                      # the menu redraws after each key

                read_until(b'Roles')                              # keys sent before curses starts are discarded
                press([b' ', b'\n'])                              # tick Admin, confirm roles (User was pre-ticked)
                read_until(b'Environments')
                press([b'j', b' ', b'\n'])                        # move to iPhone 13, tick it, confirm
                for _ in range(100):                               # keep draining: a full terminal buffer blocks the child
                    if proc.poll() is not None:
                        break
                    if select.select([master], [], [], 0.1)[0]:
                        os.read(master, 65536)
                proc.wait(timeout=5)
                os.close(master)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(json.loads(out.read_text()), {'roles': ['Admin', 'User'], 'env': ['iPhone 13']})

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ChooseTest)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main(argv, tty=None):
    if argv[:1] in (['-h'], ['--help']):
        print(__doc__.strip())
        return 0
    if argv == ['--self-test']:
        return _self_test()
    out = None
    if '--out' in argv:
        i = argv.index('--out')
        out, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        groups = load_groups(json.loads(Path(argv[0]).read_text(encoding='utf-8')))
    except (OSError, ValueError) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 2
    if not (sys.stdin.isatty() if tty is None else tty):
        print('Error: no terminal. Run this in a real terminal (in Claude Code: `! python3 choose.py ...`).', file=sys.stderr)
        return 2
    chosen = _ask(groups)
    if chosen is None:
        return 1
    text = json.dumps(chosen, indent=2)
    if out:
        Path(out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
