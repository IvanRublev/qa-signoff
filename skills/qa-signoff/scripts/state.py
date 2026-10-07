#!/usr/bin/env python3
"""
Read where a test project stands on the QA sign-off pipeline and print the stages left, as JSON.

Usage:
    python3 state.py [--dir DIR] [--cases FOLDER] [--app APP_PATH] --pro yes|no [--changed yes|no]
        --dir      test project root (default: the current folder)
        --cases    test cases folder (default: test-cases)
        --app      the app's source folder; commits touching it since qa-spec.md was last written show whether
                   the app changed (it may sit inside the test project's repository). The folder is saved in the
                   test project's .qa-signoff folder, so a later run without --app uses it
        --pro      yes when the pack detection of qa-write-tests/references/pro-detection.md says so
        --changed  yes|no overrides the app-changed signal, for the user's answer
    python3 state.py --self-test

Output keys: app (the app folder used, or null), spec, test_cases (total, open, partial, done), tests (files), runs (rows, failing, regressions,
last_run), app_changed (true, false or null when unknown), mode (`scratch` or `change-loop`), stages (a list of
{stage, skill, why}). Test files are the TC-*.spec.* files git tracks or would track. A todo.md mark of a space is open, `?` is partial, any other glyph is done.
"""

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

LINE = re.compile(r'^\s*- \[(.)\] TC-[A-Z0-9]+-\d{3}\b', re.M)


def stages(spec, cases, tests, app_changed, pro):
    run = ({'stage': 'run', 'skill': 'qa-run-tests', 'why': 'run the suite, track results and regressions, apply the release gates'} if pro
           else {'stage': 'run', 'skill': None, 'why': 'run `npx playwright test`; the results are read by hand'})
    write = {'stage': 'write', 'skill': 'qa-write-tests', 'why': 'write a Playwright test per open test case'}
    plan = {'stage': 'plan', 'skill': 'qa-plan-tests', 'why': 'crawl, write the spec, write and review the test cases'}
    if not spec or cases['total'] == 0:
        return 'scratch', [plan, write, run]
    if app_changed:
        return 'change-loop', [dict(plan, why='the app changed: re-crawl, update the spec, rewrite the changed test cases'), write, run]
    if cases['open'] + cases['partial'] > 0 or tests == 0:
        return 'change-loop', [write, run]
    return 'change-loop', [run]


def git(d, *args):
    r = subprocess.run(['git', '-C', str(d), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def test_files(d):
    """The test project's TC-*.spec.* files: in a git repository its tracked and unignored files, else every file."""
    listed = git(d, 'ls-files', '-co', '--exclude-standard')
    paths = [d / p for p in listed.splitlines()] if listed is not None else [f for f in d.rglob('*') if f.is_file()]
    return [f for f in paths if f.match('TC-*.spec.*') and 'node_modules' not in f.parts]


def remembered_app(d, app):
    """The app folder: the one given, saved in the test project's .qa-signoff folder for later launches, else the saved one."""
    saved = d / '.qa-signoff' / 'app'
    if app:
        app = str(Path(app).resolve())
        saved.parent.mkdir(exist_ok=True)
        saved.write_text(app + '\n')
        return app
    return saved.read_text().strip() if saved.is_file() else None


def read(d, cases_folder, app, pro, changed):
    d = Path(d)
    app = remembered_app(d, app)
    spec = d / 'qa-spec.md'
    todo = d / cases_folder / 'todo.md'
    marks = LINE.findall(todo.read_text()) if todo.is_file() else []
    cases = {'total': len(marks), 'open': marks.count(' '), 'partial': marks.count('?')}
    cases['done'] = cases['total'] - cases['open'] - cases['partial']
    files = test_files(d)
    runs = {'rows': 0, 'failing': 0, 'regressions': 0, 'last_run': None}
    csv_path = d / 'qa-runs' / 'tracking.csv'
    if csv_path.is_file():
        rows = list(csv.DictReader(csv_path.open()))
        runs['rows'] = len(rows)
        runs['failing'] = sum(r.get('status') == 'fail' for r in rows)
        runs['regressions'] = sum(r.get('status') == 'fail' and r.get('previous_status') in ('pass', 'flaky', 'PASS_PARTIAL') for r in rows)
        runs['last_run'] = max((r.get('last_run') or '' for r in rows), default='') or None
    app_changed = None
    if changed:
        app_changed = changed == 'yes'
    elif app and spec.is_file():
        # `-- .` keeps to the app's folder: the app may sit inside the test project's repository
        log = git(app, 'log', f'--since=@{int(spec.stat().st_mtime)}', '--oneline', '--', '.')
        if log is not None:
            app_changed = bool(log.strip())
    mode, st = stages(spec.is_file(), cases, len(files), app_changed, pro == 'yes')
    return {'app': app, 'spec': spec.is_file(), 'test_cases': cases, 'tests': {'files': len(files)}, 'runs': runs,
            'app_changed': app_changed, 'mode': mode, 'stages': st}


def self_test():
    c = lambda o, p, d: {'total': o + p + d, 'open': o, 'partial': p, 'done': d}
    names = lambda r: [s['stage'] for s in r[1]]
    assert stages(False, c(0, 0, 0), 0, None, False)[0] == 'scratch'
    assert names(stages(False, c(0, 0, 0), 0, None, True)) == ['plan', 'write', 'run']
    assert names(stages(True, c(0, 0, 0), 0, None, True)) == ['plan', 'write', 'run'], 'spec without test cases'
    assert names(stages(True, c(3, 0, 2), 2, True, True)) == ['plan', 'write', 'run'], 'app changed'
    assert names(stages(True, c(3, 0, 2), 2, False, True)) == ['write', 'run'], 'open test cases'
    assert names(stages(True, c(0, 1, 2), 2, None, False)) == ['write', 'run'], 'partial test cases'
    assert names(stages(True, c(0, 0, 3), 3, False, True)) == ['run'], 'all done'
    assert names(stages(True, c(0, 0, 3), 0, False, True)) == ['write', 'run'], 'done marks but no test files'
    assert stages(True, c(0, 0, 3), 3, False, True)[1][0]['skill'] == 'qa-run-tests'
    assert stages(True, c(0, 0, 3), 3, False, False)[1][0]['skill'] is None
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        r = read(d, 'test-cases', None, 'no', None)
        assert r['mode'] == 'scratch' and r['test_cases']['total'] == 0
        (d / 'qa-spec.md').write_text('# spec\n')
        (d / 'test-cases').mkdir()
        (d / 'test-cases' / 'todo.md').write_text('- [x] TC-A-001 — a\n- [ ] TC-A-002 — b\n- [?] TC-A-003 — c\n- [↑] TC-A-004 — d\n')
        (d / 'tests').mkdir()
        (d / 'tests' / 'TC-A-001.spec.ts').write_text('// x\n')
        (d / 'qa-runs').mkdir()
        (d / 'qa-runs' / 'tracking.csv').write_text('id,project,status,last_run,criteria_hash,previous_status,last_passed\n'
                                                    'TC-A-001,p,fail,2026-10-06,h,pass,2026-10-01\nTC-A-002,p,fail,2026-10-06,h,fail,\nTC-A-003,p,pass,2026-10-05,h,,\n'
                                                    'TC-A-004,p,fail,2026-10-06,h,PASS_PARTIAL,2026-10-01\n')
        r = read(d, 'test-cases', None, 'yes', None)
        assert r['test_cases'] == {'total': 4, 'open': 1, 'partial': 1, 'done': 2}, r['test_cases']
        assert r['tests']['files'] == 1
        assert r['runs'] == {'rows': 4, 'failing': 3, 'regressions': 2,'last_run': '2026-10-06'}, r['runs']
        assert r['mode'] == 'change-loop' and r['app_changed'] is None
        assert [s['stage'] for s in r['stages']] == ['write', 'run']
        assert read(d, 'test-cases', None, 'yes', 'yes')['stages'][0]['stage'] == 'plan'
        # app commits since the spec was written
        app = d / 'app'
        app.mkdir()
        g = lambda *a: subprocess.run(['git', '-C', str(app), '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
                                       '-c', 'core.hooksPath=/dev/null', *a], capture_output=True, check=True)
        g('init', '-q')
        (app / 'f').write_text('x')
        g('add', 'f')
        g('commit', '-qm', 'late', '--date=2999-01-01T00:00:00')
        g('commit', '-q', '--amend', '--no-edit', '--date=2999-01-01T00:00:00')
        assert read(d, 'test-cases', str(app), 'yes', None)['app_changed'] is True
        assert read(d, 'test-cases', str(app), 'yes', 'no')['app_changed'] is False
        assert read(d, 'test-cases', str(d / 'nope'), 'yes', None)['app_changed'] is None
        # a failed test's evidence folder, named after its test file, is not a test file
        (d / 'qa-runs' / 'S' / 'failed-S' / 'TC-A-001.spec.ts__p').mkdir(parents=True)
        assert read(d, 'test-cases', None, 'yes', None)['tests']['files'] == 1
    with tempfile.TemporaryDirectory() as t:
        # the app inside the test project's repository: only commits touching the app's folder count
        d = Path(t)

        def commit(message, date, *paths):
            git = ['git', '-C', str(d), '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null']
            env = {**os.environ, 'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date}
            subprocess.run(git + ['add', *paths], capture_output=True, check=True)
            subprocess.run(git + ['commit', '-qm', message], env=env, capture_output=True, check=True)

        subprocess.run(['git', '-C', str(d), 'init', '-q'], capture_output=True, check=True)
        (d / 'app').mkdir()
        (d / 'app' / 'f').write_text('x')
        (d / 'qa-spec.md').write_text('# spec\n')
        (d / 'tests').mkdir()
        (d / 'tests' / 'TC-A-001.spec.ts').write_text('// x\n')
        (d / 'tests' / 'TC-A-002.spec.ts').write_text('// ignored\n')
        (d / '.gitignore').write_text('tests/TC-A-002.spec.ts\n')
        commit('project', '2000-01-01T00:00:00', '-A')
        (d / 'notes.md').write_text('late\n')
        commit('late, outside the app', '2099-01-01T00:00:00', 'notes.md')
        r = read(d, 'test-cases', str(d / 'app'), 'yes', None)
        assert r['app_changed'] is False, 'a commit outside the app folder is not an app change'
        assert r['tests']['files'] == 1, "only the repository's files count; an ignored file does not"
        (d / 'app' / 'f').write_text('y')
        commit('late, in the app', '2099-01-01T00:00:00', 'app/f')
        assert read(d, 'test-cases', str(d / 'app'), 'yes', None)['app_changed'] is True
        # the app folder given once is remembered in the test project's .qa-signoff folder for the next launch
        r = read(d, 'test-cases', None, 'yes', None)
        assert r['app'] == str((d / 'app').resolve()) and r['app_changed'] is True, r
        assert (d / '.qa-signoff' / 'app').is_file()
    print('state.py self-test ok')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a in (['-h'], ['--help']):
        print(__doc__)
        sys.exit(0)
    if a == ['--self-test']:
        self_test()
        sys.exit(0)
    opts = {'--dir': '.', '--cases': 'test-cases', '--app': None, '--pro': None, '--changed': None}
    while a:
        k = a.pop(0)
        if k not in opts or not a:
            print(__doc__, file=sys.stderr)
            sys.exit(2)
        opts[k] = a.pop(0)
    if opts['--pro'] not in ('yes', 'no'):
        print('--pro is required: run the pack detection of qa-write-tests/references/pro-detection.md and pass its result', file=sys.stderr)
        sys.exit(2)
    print(json.dumps(read(opts['--dir'], opts['--cases'], opts['--app'], opts['--pro'], opts['--changed']), indent=2))
