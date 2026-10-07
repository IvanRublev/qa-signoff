#!/usr/bin/env python3
"""
Helpers for running a fleet of agents over the test cases backlog (todo.md).

Usage:
    python3 fleet.py cores                       print the agent count for a fleet: CPU cores minus 2, at least 2
    python3 fleet.py watch <todo.md> [--interval SECONDS]
        print one progress line at start and one each time test case marks change in todo.md,
        with the done count, the rate and the estimated completion time; exit 0 when no
        `[ ]` line is left. Run it in the background and stream its lines into the chat.
    python3 fleet.py audit <todo.md> <test cases folder>
        list each done test case (any mark except `[ ]` and `[?]`) whose `<ID>.md` still has an unticked
        `- [ ]` criterion, exit 1 when there is one. Kaizero ticks the box when a test lands, whether or
        not every criterion is ticked; the listed test cases get the mark `[?]`.
    python3 fleet.py --self-test

A test case line looks like `- [x] TC-ACT-001 — Title (P1, Interaction-level)`. any glyph in the
brackets (`[x]`, `[?]`, `[↑]`) is done, an empty `[ ]` is not.
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta

LINE = re.compile(r'^\s*- \[(.)\] (TC-[A-Z0-9]+-\d{3})\b')


def cores(n=None):
    return max(2, (n or os.cpu_count() or 4) - 2)


def marks(text):
    return {m.group(2): m.group(1) for m in map(LINE.match, text.splitlines()) if m}


def duration(seconds):
    m = int(seconds // 60)
    return f'{m // 60}h{m % 60:02d}m' if m >= 60 else f'{m}m'


def progress(prev, cur, start, started, now):
    """One progress line. `prev` is the marks at the last line, `start` the marks when watching began;
    `started` and `now` are epoch seconds."""
    total = len(cur)
    open_ = sum(m == ' ' for m in cur.values())
    landed = total - open_
    new = sorted(i for i, m in cur.items() if m != ' ' and prev.get(i, ' ') == ' ')
    parts = [f'Done {landed}/{total} ({100 * landed // max(total, 1)}%)']
    if new:
        parts.append('+' + ', '.join(new))
    gained = landed - sum(m != ' ' for m in start.values())
    if not open_:
        parts.append(f'done in {duration(now - started)}')
    elif gained > 0 and now > started:
        rate = gained / (now - started)
        eta = open_ / rate
        parts.append(f'{rate * 3600:.1f} per hour · {duration(eta)} left · done about {datetime.fromtimestamp(now + eta):%H:%M}')
    return ' · '.join(parts)


def watch(path, interval=30):
    started = time.time()
    start = last = marks(open(path).read())
    print(progress(last, last, start, started, started), flush=True)
    while ' ' in last.values():
        time.sleep(interval)
        cur = marks(open(path).read())
        if cur != last:
            print(progress(last, cur, start, started, time.time()), flush=True)
            last = cur


def audit(todo, folder):
    bad = []
    for i, m in marks(open(todo).read()).items():
        f = os.path.join(folder, i + '.md')
        if m not in ' ?' and os.path.isfile(f) and re.search(r'^\s*- \[ \]', open(f).read(), re.M):
            bad.append(i)
    for i in bad:
        print(f'{i}: marked done, criteria left unticked')
    return 1 if bad else 0


def self_test():
    assert cores(8) == 6 and cores(4) == 2 and cores(2) == 2 and cores(1) == 2
    text = '# t\n- [x] TC-A-001 — a (P1, X)\n- [ ] TC-A-002 — b\n  - [ ] TC-A-003 — c\n- [?] TC-B-001 — d\nnot a line\n'
    m = marks(text)
    assert m == {'TC-A-001': 'x', 'TC-A-002': ' ', 'TC-A-003': ' ', 'TC-B-001': '?'}, m
    t0 = 1_000_000.0
    assert progress(m, m, m, t0, t0) == 'Done 2/4 (50%)'
    nxt = dict(m, **{'TC-A-002': 'x'})
    line = progress(m, nxt, m, t0, t0 + 3600)
    assert line.startswith('Done 3/4 (75%) · +TC-A-002 · 1.0 per hour · 1h00m left'), line
    fin = {i: 'x' for i in m}
    assert progress(m, fin, m, t0, t0 + 600).endswith('done in 10m')
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        open(f'{t}/todo.md', 'w').write('- [x] TC-A-001 — a\n- [x] TC-A-002 — b\n- [?] TC-A-003 — c\n- [ ] TC-A-004 — d\n- [↑] TC-A-005 — e\n')
        for i, body in (('001', '- [x] ok\n'), ('002', '- [x] ok\n- [ ] left\n'), ('003', '- [ ] left\n'), ('004', '- [ ] left\n'), ('005', '  - [ ] left\n')):
            open(f'{t}/TC-A-{i}.md', 'w').write(body)
        assert audit(f'{t}/todo.md', t) == 1
        open(f'{t}/TC-A-002.md', 'w').write('- [x] ok\n')
        open(f'{t}/TC-A-005.md', 'w').write('- [x] ok\n')
        assert audit(f'{t}/todo.md', t) == 0
    print('fleet.py self-test ok')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a in (['-h'], ['--help']):
        print(__doc__)
    elif a == ['--self-test']:
        self_test()
    elif a == ['cores']:
        print(cores())
    elif a[:1] == ['audit'] and len(a) == 3:
        sys.exit(audit(a[1], a[2]))
    elif a[:1] == ['watch'] and len(a) in (2, 4) and (len(a) == 2 or a[2] == '--interval'):
        watch(a[1], int(a[3]) if len(a) == 4 else 30)
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
