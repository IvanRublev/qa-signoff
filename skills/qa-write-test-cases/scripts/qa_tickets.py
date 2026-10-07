#!/usr/bin/env python3
"""
Read QA test cases written by qa-write-test-cases. This module owns the test case ID format, the
criteria hash, and the test file's first line; the other QA scripts import them.

The criteria hash covers what the test does and asserts:
- every `### How to build` line, Test file rules block included; trailing whitespace and blank
  lines are ignored;
- every `### Acceptance criteria` line except `>` notes and the `Output test file contains
  comment` item, with checkbox marks dropped, so ticking a criterion leaves it unchanged.
A section ends at the next `##` or `###`
heading, so a `#` shell comment or a `####` sub-heading inside it doesn't end it.

Usage:
    python3 qa_tickets.py hash <test-case.md|dir>...   print each test case's test file first line
    python3 qa_tickets.py check <test-case.md|dir>...  list test cases with a missing or stale hash, a bad heading, no How to build,
        a template `<…>` placeholder left in How to build, no Priority, Tier, Type or Feature, one left as its `<…>`
        placeholder, or a Priority not P0-P3 or a Tier not Journey-level/Interaction-level; for a folder, also a
        missing todo.md and every ID it lists more than once, lists without a test case file, or leaves out (exit 1)
    python3 qa_tickets.py index <test-case.md|dir>...  print one line per test case, the re-run match key:
        ID | Feature | Tier | Type | Journey | Projects | title (`-` for a missing value)
    python3 qa_tickets.py write <test-case.md|dir>...  write the computed hash into each test case's hash criterion
    python3 qa_tickets.py rehash <test-case.md|dir>... for a test case whose How to build and criteria are unchanged
        but whose stored hash came from an older recipe: write the computed hash into the test case and into
        line 1 of its **Test file:** (resolved against the test cases folder's parent), keeping every mark;
        refuses (exit 1) a test case whose stored hash no earlier recipe gives from its current text, whose
        test file's line 1 doesn't carry the stored hash, or that is done (`[x]` in todo.md) but has
        no test file
    python3 qa_tickets.py --self-test

Exit codes: 0 ok, or -h/--help; 1 problems found (check) or no hash criterion (write); 2 usage error or no test cases found.
"""

import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

TICKET_ID = r'TC-[A-Z0-9]+-\d{3}'
HASH_ITEM = 'Output test file contains comment'
CRITERION = re.compile(r'^- \[[ xX]\] (.*)$')
NOTE = re.compile(r'^\s*>')
ATTRIBUTE = re.compile(r'^\*\*([^*]+):\*\*\s*(.*)$')
HEADING = re.compile(r'^## (\S+) - (.*)')
STORED = re.compile(r'criteria-hash: ([0-9a-f]{8})\b')
HASH_SPAN = re.compile(r'(//\s*\S+\s+)?criteria-hash:\s*[^`\s]*')
ITEM_ID = re.compile(r'//\s*(\S+)\s+criteria-hash:')
FIRST_LINE = re.compile(r'^//\s*((?i:TC-[A-Za-z0-9]+-\d+))\s+criteria-hash:\s*([0-9a-f]{8})\b')
TODO_LINE = re.compile(rf'^- \[(.)\] ({TICKET_ID})\b')
SECTION_END = re.compile(r'^#{2,3}(\s|$)')
# The `<…>` placeholders of SKILL.md's Test file rules block; any other `<…>` (an HTML tag, an XSS payload) is test case text.
PLACEHOLDER = re.compile(r"<(Test file|Test case ID|exactly one of|role|ROLE|helper role|helper role's [^<>]*|project|reason"
                         r"|only [^<>]*)>")
REQUIRED = ('Priority', 'Tier', 'Type', 'Feature')
ALLOWED = {'Priority': ('P0', 'P1', 'P2', 'P3'), 'Tier': ('Journey-level', 'Interaction-level')}


def _lines(text):
    """Split on newlines only; a trailing CR is a line ending, not text."""
    return [line[:-1] if line.endswith('\r') else line for line in text.split('\n')]


def _section(text, heading):
    """Yield (line index, line) for each line under `heading`, up to the next `##` or `###` heading."""
    inside = False
    for i, line in enumerate(_lines(text)):
        if line.startswith(heading):
            inside = True
        elif SECTION_END.match(line):
            inside = False
        elif inside:
            yield i, line


def _criteria(text):
    """Yield (line index, line, criterion text) for each checkbox item under Acceptance criteria."""
    for i, line in _section(text, '### Acceptance criteria'):
        m = CRITERION.match(line)
        if m:
            yield i, line, m.group(1)


def _hashed_lines(text):
    for _, line in _section(text, '### How to build'):
        if line.strip():
            yield line.rstrip()
    yield ''  # separates the two sections
    for _, line in _section(text, '### Acceptance criteria'):
        m = CRITERION.match(line)
        if line.strip() and not NOTE.match(line) and not (m and HASH_ITEM in line):
            yield (m.group(1) if m else line).rstrip()


def _digest(lines):
    body = ''.join(line + '\n' for line in lines)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()[:8]


def criteria_hash(text):
    return _digest(_hashed_lines(text))


def _checkbox_texts(text):
    return [c for _, line, c in _criteria(text) if HASH_ITEM not in line]


def _build_lines(text, stop=None):
    lines = []
    for _, line in _section(text, '### How to build'):
        if stop and stop.match(line):
            break
        if line.strip():
            lines.append(line.rstrip())
    return lines


# Earlier recipes, newest first, from this file's git history. rehash accepts a test case only when one of
# them reproduces its stored hash from its current text. ponytail: code fences are ignored, so a fenced
# heading-like line makes 893ed2f miss, which refuses (safe).
OLD_RECIPES = (
    # c6b7176: every How to build line, then the checkbox criteria texts
    lambda text: _build_lines(text) + [''] + _checkbox_texts(text),
    # 893ed2f: How to build lines up to its Test file rules block, then the checkbox criteria texts
    lambda text: _build_lines(text, re.compile(r'^(#(\s|$)|\s*([-*+]\s+)?\*\*Test file:\*\*)'))
    + [''] + _checkbox_texts(text),
    # 8be808e: the checkbox criteria texts only
    _checkbox_texts,
)


def stored_hash(text):
    for _, line, _ in _criteria(text):
        if HASH_ITEM in line:
            m = STORED.search(line)
            return m.group(1) if m else None
    return None


def item_id(text):
    for _, line, _ in _criteria(text):
        if HASH_ITEM in line:
            m = ITEM_ID.search(line)
            return m.group(1) if m else None
    return None


def hash_line(ticket_id, value):
    return f'// {ticket_id} criteria-hash: {value}'


def parse_hash_line(line):
    m = FIRST_LINE.match(line.removeprefix('\ufeff'))  # a BOM some editors write
    return (m.group(1).upper(), m.group(2)) if m else None


def read_text(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def read_ticket(path):
    text = read_text(path)
    m = next((m for m in map(HEADING.match, _lines(text)) if m), None)
    heading, title = (m.group(1), m.group(2).rstrip()) if m else (None, None)
    fields = {}
    for line in _lines(text):
        if line.startswith('### '):
            break
        m = ATTRIBUTE.match(line)
        if m:
            fields[m.group(1).strip().lower()] = m.group(2).strip().strip('`')
    return {
        'id': heading if heading and re.fullmatch(TICKET_ID, heading) else None,
        'heading': heading,
        'title': title,
        'projects': [x.strip().strip('`') for x in fields.get('projects', '').split(',') if x.strip()],
        'test_file': fields.get('test file'),
        'fields': fields,
        'stored_hash': stored_hash(text),
        'hash': criteria_hash(text),
    }


class NoTickets(FileNotFoundError):
    pass


def ticket_paths(paths):
    for p in map(Path, paths):
        if not p.exists():
            raise NoTickets(f'{p} does not exist')
        # file names are matched ignoring case, like every file-name check in the QA scripts
        found = sorted(x for x in p.iterdir() if x.is_file() and re.fullmatch(r'tc-.+\.md', x.name, re.I)) \
            if p.is_dir() else [p]
        if not found:
            raise NoTickets(f'no TC-*.md test cases in {p}')
        yield from found


def check(paths):
    problems = []
    for path in ticket_paths(paths):
        t = read_ticket(path)
        if not t['id'] or t['id'].upper() != path.stem.upper():
            problems.append((path.name, f"heading ID {t['heading']!r} must be a {TICKET_ID} ID equal to the filename"))
        elif not any(line.strip() for _, line in _section(read_text(path), '### How to build')):
            problems.append((path.name, 'no `### How to build` section'))
        elif item_id(read_text(path)) != t['id']:
            problems.append((path.name, f"hash criterion names {item_id(read_text(path))!r}, not {t['id']}"))
        elif t['stored_hash'] != t['hash']:
            problems.append((path.name, f"stored hash {t['stored_hash'] or 'missing'}, computed {t['hash']}"))
        placeholders = [m.group(0) for _, line in _section(read_text(path), '### How to build')
                        for m in PLACEHOLDER.finditer(line)]
        if placeholders:
            problems.append((path.name, f"How to build has a template placeholder: {', '.join(dict.fromkeys(placeholders))}"))
        for name in REQUIRED:
            value = t['fields'].get(name.lower())
            if not value:
                problems.append((path.name, f'no **{name}:**'))
            elif re.fullmatch(r'<[^<>]*>', value):
                problems.append((path.name, f'**{name}:** is a template placeholder: {value}'))
            elif name in ALLOWED and value not in ALLOWED[name]:
                problems.append((path.name, f"**{name}:** {value} is not one of {', '.join(ALLOWED[name])}"))
    for folder in (Path(p) for p in paths):
        if folder.is_dir() and not (folder / 'todo.md').is_file():
            problems.append(('todo.md', f'missing from {folder}'))
        elif folder.is_dir():
            listed = Counter(m.group(2) for m in map(TODO_LINE.match, _lines(read_text(folder / 'todo.md'))) if m)
            files = {x.stem.upper() for x in ticket_paths([folder])}
            for ticket_id in sorted(set(listed) | files):
                if ticket_id not in files:
                    problems.append(('todo.md', f'{ticket_id} has no test case file'))
                elif ticket_id not in listed:
                    problems.append(('todo.md', f'{ticket_id} is not listed'))
                elif listed[ticket_id] > 1:
                    problems.append(('todo.md', f'{ticket_id} is listed {listed[ticket_id]} times'))
    return problems


def write_hash(path, ticket_id):
    """Write `// <ID> criteria-hash: <hash>` into the hash criterion; None when that fails."""
    text = read_text(path)
    computed = criteria_hash(text)
    line_text = hash_line(ticket_id, computed)
    parts = text.split('\n')  # index-aligned with _lines
    for i, line, _ in _criteria(text):
        if HASH_ITEM in line:
            parts[i] = HASH_SPAN.sub(line_text, parts[i], count=1)
    new = '\n'.join(parts)
    if stored_hash(new) != computed or item_id(new) != ticket_id:
        return None
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(new)
    return computed


def rehash(path):
    """Move a test case whose How to build and criteria are unchanged onto the current hash recipe: write the
    computed hash into the test case and into line 1 of its test file, if that file exists. The Test file
    resolves against the test project root, the test cases folder's parent. Returns (hash, None), or
    (None, error) with nothing written when no earlier recipe reproduces the stored hash, when line 1
    doesn't carry it, or when the test case is done in todo.md but its test file is missing."""
    t = read_ticket(path)
    text = read_text(path)
    if t['stored_hash'] != t['hash'] and t['stored_hash'] not in {_digest(r(text)) for r in OLD_RECIPES}:
        return None, (f"{path.name}: no earlier hash recipe gives its stored hash {t['stored_hash'] or 'missing'}: "
                      "its How to build or criteria changed, so treat it as a changed test case")
    tickets = Path(path).resolve().parent
    test = tickets.parent / t['test_file'] if t['test_file'] else None
    if test and test.is_file():
        first, sep, rest = read_text(test).partition('\n')
        if parse_hash_line(first.rstrip('\r')) != (t['id'], t['stored_hash']):
            return None, (f"{test} line 1 isn't `{hash_line(t['id'], t['stored_hash'])}`: the test doesn't "
                          "match the test case's stored hash, so rehashing would hide a real change")
    elif test and (tickets / 'todo.md').is_file() and todo_marks(tickets / 'todo.md').get(t['id']) == 'x':
        return None, f"{path.name} is done in todo.md but its test file {test} is missing"
    value = write_hash(path, t['id'] or path.stem)
    if value is None:
        return None, f"{path.name} has no '{HASH_ITEM}' criterion with `criteria-hash:` to write into"
    if test and test.is_file():
        with open(test, 'w', encoding='utf-8', newline='') as f:
            f.write(first[:first.startswith('\ufeff')] + hash_line(t['id'], value)
                    + ('\r' if first.endswith('\r') else '') + sep + rest)
    return value, None


def todo_marks(path):
    marks = {}
    for line in _lines(read_text(path)):
        m = TODO_LINE.match(line)
        if m:
            marks[m.group(2)] = m.group(1).lower()
    return marks


def main(argv):
    if argv[:1] in (['-h'], ['--help']):
        print(__doc__.strip())
        return 0
    if len(argv) < 2 or argv[0] not in ('hash', 'check', 'write', 'rehash', 'index'):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    command, args = argv[0], argv[1:]
    try:
        paths = list(ticket_paths(args))
    except NoTickets as e:
        print(f'Error: {e}', file=sys.stderr)
        return 2
    if command == 'check':
        problems = check(args)
        for name, message in problems:
            print(f'{name}: {message}')
        return 1 if problems else 0
    if command == 'index':
        for path in paths:
            t = read_ticket(path)
            values = [t['id'] or path.stem] + [t['fields'].get(k) for k in ('feature', 'tier', 'type', 'journey')] \
                + [', '.join(t['projects']), t['title']]
            print(' | '.join(v or '-' for v in values))
        return 0
    status = 0
    for path in paths:
        t = read_ticket(path)
        if command == 'rehash':
            value, error = rehash(path)
            if error:
                print(f'Error: {error}', file=sys.stderr)
                status = 1
            else:
                print(hash_line(t['id'] or path.stem, value))
            continue
        value = t['hash'] if command == 'hash' else write_hash(path, t['id'] or path.stem)
        if value is None:
            print(f"Error: {path.name} has no '{HASH_ITEM}' criterion with `criteria-hash:` to write into",
                  file=sys.stderr)
            status = 1
        else:
            print(hash_line(t['id'] or path.stem, value))
    return status


def _self_test():
    import os
    import shutil
    import tempfile
    import unittest

    # Written per the qa-write-test-cases Test file rules block: the Test file rules block also mentions the hash item.
    TICKET = """## TC-ACT-001 - Create an activity with valid data succeeds

**Priority:** P1
**Tier:** Interaction-level
**Type:** Functional
**Feature:** Activities admin
**Projects:** admin-desktop-chrome, admin-iphone-13
**Test file:** tests/admin/TC-ACT-001.spec.ts

### How to build

**Arrange:** An admin session from the project; an activity name unique to this run.   
**Act:**
1. Open /admin/activity/create and save the activity.

**Cleanup:** Delete the activity.

**Test file rules:**
- Line 1 of the file is the comment named in the acceptance criteria's `Output test file contains comment` item.
**Projects:** not-an-attribute

### Acceptance criteria

**Assert:**
- [ ] Activity is created and appears in the activity list
- [x] Absence check: no error banner is shown   
  > 2026-09-25 a line under a criterion, excluded from the hash
- [ ] Output test file contains comment: `// TC-ACT-001 criteria-hash: 00000000` as its first line

### UX behavior

- [ ] Not a criterion: outside the Acceptance criteria section
"""
    PINNED = '918722ee'  # printf the How to build lines, a blank line, the criteria texts | shasum -a 256
    OLD = '0c857ce4'     # the checkbox-only recipe: printf the checkbox criteria texts | shasum -a 256
    BODY = 'import { test } from "@playwright/test";\r\n'

    TODO = """# QA test cases todo

## Activities admin
- [X] TC-ACT-001 — Create an activity (P1, Interaction-level)
- [?] TC-ACT-002 — Edit an activity (P2, Interaction-level)
- [ ] TC-ACT-003 — Delete an activity (P1, Interaction-level)
"""
    TODO_001 = TODO.split('- [?]')[0]   # lists TC-ACT-001 only

    class QaTicketsTest(unittest.TestCase):
        def setUp(self):
            self._tmp = tempfile.TemporaryDirectory()
            self.dir = Path(self._tmp.name)

        def tearDown(self):
            self._tmp.cleanup()

        def write(self, name, text, newline=None):
            path = self.dir / name
            with open(path, 'w', encoding='utf-8', newline=newline) as f:
                f.write(text)
            return path

        def test_hash_matches_shell_recipe(self):
            self.assertEqual(criteria_hash(TICKET), PINNED)

        def test_hash_ignores_checkbox_marks_and_line_endings(self):
            self.assertEqual(criteria_hash(TICKET.replace('- [ ] Activity', '- [x] Activity')), PINNED)
            self.assertEqual(criteria_hash(TICKET.replace('\n', '\r\n')), PINNED)

        def test_hash_changes_with_criterion_text(self):
            self.assertNotEqual(criteria_hash(TICKET.replace('activity list', 'list')), PINNED)
            # a line separator inside a criterion is part of its text, not a line break
            self.assertNotEqual(criteria_hash(TICKET.replace('activity list', 'activity list')), PINNED)

        def test_hash_changes_with_how_to_build_text(self):
            self.assertNotEqual(criteria_hash(TICKET.replace('unique to this run', 'from the fixtures')), PINNED)
            self.assertNotEqual(criteria_hash(TICKET.replace('and save the activity', 'and cancel')), PINNED)
            self.assertNotEqual(criteria_hash(TICKET.replace('Delete the activity.', 'None needed.')), PINNED)

        def test_hash_covers_the_whole_how_to_build_section(self):
            self.assertNotEqual(criteria_hash(TICKET.replace('**Projects:** not-an-attribute', '**Projects:** other')), PINNED)
            self.assertEqual(criteria_hash(TICKET.replace('the activity.\n\n**Test', 'the activity.\n\n\n**Test')), PINNED)

        def test_hash_covers_every_acceptance_criteria_line(self):
            for old, new in (('is shown   \n', 'is shown   \n  within 2 seconds\n'),
                             ('- [x] Absence', '  - and a heading "Welcome"\n- [x] Absence'),
                             ('**Assert:**', '**Assert:** on the list page'),
                             ('- [ ] Output test file', '**Cleanup:** Delete the activity.\n- [ ] Output test file')):
                with self.subTest(new=new):
                    self.assertNotEqual(criteria_hash(TICKET.replace(old, new)), PINNED)

        def test_hash_ignores_quote_notes_trailing_spaces_and_tick_case(self):
            self.assertEqual(criteria_hash(TICKET.replace('excluded from the hash', 'passed on retry')), PINNED)
            self.assertEqual(criteria_hash(TICKET.replace('banner is shown   ', 'banner is shown')), PINNED)
            self.assertEqual(criteria_hash(TICKET.replace('- [x] Absence', '- [X] Absence')), PINNED)
            self.assertEqual(stored_hash(TICKET.replace('- [ ] Output test file', '- [X] Output test file')), '00000000')

        def test_check_requires_how_to_build(self):
            good = TICKET.replace('criteria-hash: 00000000', f'criteria-hash: {PINNED}')
            path = self.write('TC-ACT-001.md', good.replace('### How to build', '### How to Build'))
            self.assertEqual(main(['write', str(path)]), 0)
            self.assertEqual(check([path]), [('TC-ACT-001.md', 'no `### How to build` section')])

        def test_how_to_build_ends_only_at_a_ticket_heading(self):
            for extra in ('#### Act detail\n', '```sh\n# a shell comment\n```\n'):
                with self.subTest(extra=extra):
                    text = TICKET.replace('**Cleanup:**', extra + '**Cleanup:**')
                    self.assertNotEqual(criteria_hash(text), criteria_hash(text.replace('Delete the activity.', 'None.')))

        def test_write_rewrites_only_the_hash_criterion(self):
            example = '- [ ] Output test file contains comment: `// TC-ACT-001 criteria-hash: 11111111` example\n'
            path = self.write('TC-ACT-001.md', TICKET.replace('**Cleanup:**', example + '**Cleanup:**'))
            self.assertEqual(main(['write', str(path)]), 0)
            self.assertIn('criteria-hash: 11111111', read_text(path))
            self.assertEqual(check([path]), [])

        def test_hash_section_ends_at_next_heading(self):
            self.assertEqual(criteria_hash(TICKET.replace('### UX behavior', '### UX notes')), PINNED)
            # a sub-heading or a shell comment inside Acceptance criteria doesn't end it
            self.assertNotEqual(criteria_hash(TICKET.replace('- [x] Absence', '#### More\n- [x] Absence')),
                                criteria_hash(TICKET.replace('- [x] Absence', '#### More\n- [x] Absent')))
            self.assertEqual(criteria_hash(TICKET.replace('### UX behavior', '## Next')), PINNED)
            self.assertEqual(criteria_hash(TICKET.replace('### UX behavior', '###')), PINNED)
            # a line that isn't a Markdown heading doesn't end the section
            self.assertNotEqual(criteria_hash(TICKET.replace('### UX behavior', 'UX behavior')), PINNED)
            self.assertNotEqual(criteria_hash(TICKET.replace('### UX behavior', '#UX behavior')), PINNED)

        def test_stored_hash_comes_from_the_criterion(self):
            self.assertEqual(stored_hash(TICKET), '00000000')
            self.assertIsNone(stored_hash(TICKET.replace('criteria-hash: 00000000', 'criteria-hash: <hash>')))

        def test_hash_line(self):
            self.assertEqual(hash_line('TC-ACT-001', PINNED), f'// TC-ACT-001 criteria-hash: {PINNED}')
            self.assertEqual(parse_hash_line(f'// tc-act-001 criteria-hash: {PINNED}'), ('TC-ACT-001', PINNED))
            self.assertEqual(parse_hash_line(f'\ufeff// TC-ACT-001 criteria-hash: {PINNED}'), ('TC-ACT-001', PINNED))
            self.assertIsNone(parse_hash_line('import { test } from "@playwright/test";'))
            self.assertIsNone(parse_hash_line('// TC-TS-001 criteria-hash: 48daea4bzz'))
            self.assertIsNone(parse_hash_line('// TC-TS-001 criteria-hash: 48DAEA4B'))
            self.assertIsNone(parse_hash_line('// TC-TS-001 criteria-hash: 48daea4'))

        def test_read_ticket_fields(self):
            t = read_ticket(self.write('TC-ACT-001.md', TICKET))
            self.assertEqual(t['id'], 'TC-ACT-001')
            self.assertEqual(t['projects'], ['admin-desktop-chrome', 'admin-iphone-13'])
            self.assertEqual(t['test_file'], 'tests/admin/TC-ACT-001.spec.ts')
            self.assertEqual((t['stored_hash'], t['hash']), ('00000000', PINNED))

        def test_read_ticket_strips_backticks(self):
            text = TICKET.replace('**Projects:** admin-desktop-chrome, admin-iphone-13',
                                  '**Projects:** `admin-desktop-chrome`, `admin-iphone-13`')
            t = read_ticket(self.write('TC-ACT-001.md', text.replace('**Test file:** tests/admin/TC-ACT-001.spec.ts',
                                                                     '**Test file:** `tests/admin/TC-ACT-001.spec.ts`')))
            self.assertEqual(t['projects'], ['admin-desktop-chrome', 'admin-iphone-13'])
            self.assertEqual(t['test_file'], 'tests/admin/TC-ACT-001.spec.ts')

        def good(self, ticket_id, text=TICKET):
            """Write a test case with a current hash."""
            path = self.write(f'{ticket_id}.md', text.replace('TC-ACT-001', ticket_id))
            write_hash(path, ticket_id)
            return path

        def test_check_compares_todo_with_the_ticket_files(self):
            for n in ('001', '002', '004'):
                self.good(f'TC-ACT-{n}')
            self.write('todo.md', TODO + '- [ ] TC-ACT-002 — Edit an activity again (P2, Interaction-level)\n')
            self.assertEqual(check([self.dir]), [
                ('todo.md', 'TC-ACT-002 is listed 2 times'),
                ('todo.md', 'TC-ACT-003 has no test case file'),
                ('todo.md', 'TC-ACT-004 is not listed')])
            self.write('todo.md', TODO.replace('TC-ACT-003', 'TC-ACT-004'))
            self.assertEqual(check([self.dir]), [])
            self.assertEqual(check([self.dir / 'TC-ACT-001.md']), [])   # a single test case: no todo.md check
            (self.dir / 'todo.md').unlink()
            self.assertEqual(check([self.dir]), [('todo.md', f'missing from {self.dir}')])
            self.assertEqual(main(['check', str(self.dir)]), 1)

        def test_check_flags_template_placeholders_only(self):
            self.write('todo.md', TODO_001)
            skip = "- The first line of every test is `test.skip(!['<project>', …].includes(test.info().project.name), '<reason>')`.\n"
            self.good('TC-ACT-001', TICKET.replace('**Cleanup:**', skip + '**Cleanup:**'))
            self.assertEqual(check([self.dir]), [('TC-ACT-001.md', 'How to build has a template placeholder: <project>, <reason>')])
            html = '1. Type `<script>alert(1)</script>` and `<img src=x onerror=alert(1)>` into the <Name> field.\n'
            self.good('TC-ACT-001', TICKET.replace('**Cleanup:**', html + '**Cleanup:**'))
            self.assertEqual(check([self.dir]), [])

        def test_check_flags_missing_attributes(self):
            self.write('todo.md', TODO_001)
            self.good('TC-ACT-001', TICKET.replace('**Tier:** Interaction-level\n', '').replace('**Feature:** Activities admin', '**Feature:**'))
            self.assertEqual(check([self.dir]), [('TC-ACT-001.md', 'no **Tier:**'), ('TC-ACT-001.md', 'no **Feature:**')])

        def test_check_flags_placeholder_and_invalid_attributes(self):
            self.write('todo.md', TODO_001)
            self.good('TC-ACT-001', TICKET.replace('**Priority:** P1', '**Priority:** <P0-P3>')
                      .replace('**Type:** Functional', '**Type:** <one or more of Functional/Boundary/Negative/Cross-cutting/Security/Performance>')
                      .replace('**Feature:** Activities admin', '**Feature:** <shared component or feature name>'))
            self.assertEqual(check([self.dir]), [
                ('TC-ACT-001.md', '**Priority:** is a template placeholder: <P0-P3>'),
                ('TC-ACT-001.md', '**Type:** is a template placeholder: <one or more of Functional/Boundary/Negative/Cross-cutting/Security/Performance>'),
                ('TC-ACT-001.md', '**Feature:** is a template placeholder: <shared component or feature name>')])
            self.good('TC-ACT-001', TICKET.replace('**Priority:** P1', '**Priority:** P4')
                      .replace('**Tier:** Interaction-level', '**Tier:** <Journey-level/Interaction-level>'))
            self.assertEqual(check([self.dir]), [
                ('TC-ACT-001.md', '**Priority:** P4 is not one of P0, P1, P2, P3'),
                ('TC-ACT-001.md', '**Tier:** is a template placeholder: <Journey-level/Interaction-level>')])
            self.good('TC-ACT-001', TICKET.replace('**Tier:** Interaction-level', '**Tier:** E2E'))
            self.assertEqual(check([self.dir]), [
                ('TC-ACT-001.md', '**Tier:** E2E is not one of Journey-level, Interaction-level')])

        def test_check_reports_stale_missing_and_bad_ids(self):
            self.write('todo.md', TODO)
            self.write('TC-ACT-001.md', TICKET)
            self.write('TC-ACT-002.md', TICKET.replace('TC-ACT-001', 'TC-ACT-002')
                       .replace('criteria-hash: 00000000', f'criteria-hash: {PINNED}'))
            self.write('TC-ACT-003.md', TICKET.replace('TC-ACT-001', 'TC-ACT-003').replace('criteria-hash: 00000000', ''))
            self.write('TC-ACT-004.md', TICKET.replace('TC-ACT-001', 'TC-ACT-04')
                       .replace('criteria-hash: 00000000', f'criteria-hash: {PINNED}'))
            problems = dict((p[0], p[1]) for p in check([self.dir]))
            self.assertEqual(sorted(problems), ['TC-ACT-001.md', 'TC-ACT-003.md', 'TC-ACT-004.md', 'todo.md'])
            self.assertIn('heading', problems['TC-ACT-004.md'])

        def test_check_cli_exit_codes(self):
            good = self.write('TC-ACT-002.md', TICKET.replace('TC-ACT-001', 'TC-ACT-002')
                              .replace('criteria-hash: 00000000', f'criteria-hash: {PINNED}'))
            self.assertEqual(main(['check', str(good)]), 0)
            self.assertEqual(main(['check', str(self.dir / 'TC-ACT-001.md')]), 2)   # missing path
            empty = self.dir / 'empty'
            empty.mkdir()
            self.assertEqual(main(['check', str(empty)]), 2)                        # no test cases to check
            self.write('TC-ACT-001.md', TICKET)
            self.assertEqual(main(['check', str(self.dir)]), 1)

        def test_write_changes_only_the_hash(self):
            for newline in ('\n', '\r\n'):
                with self.subTest(newline=newline):
                    for placeholder in ('00000000', '<hash>'):
                        original = TICKET.replace('criteria-hash: 00000000', f'criteria-hash: {placeholder}')
                        path = self.write('TC-ACT-001.md', original, newline=newline)
                        self.assertEqual(main(['write', str(path)]), 0)
                        with open(path, encoding='utf-8', newline='') as f:
                            after = f.read()
                        expected = original.replace(f'criteria-hash: {placeholder}', f'criteria-hash: {PINNED}')
                        self.assertEqual(after, expected.replace('\n', newline))

        def test_write_fixes_malformed_and_copied_hash_items(self):
            for bad in ('`criteria-hash:<hash>`', '`// TC-WEB-042 criteria-hash: <hash>`'):
                with self.subTest(bad=bad):
                    text = TICKET.replace('`// TC-ACT-001 criteria-hash: 00000000`', bad)
                    path = self.write('TC-ACT-001.md', text)
                    self.assertEqual(main(['write', str(path)]), 0)
                    after = read_text(path)
                    self.assertEqual(stored_hash(after), PINNED)
                    self.assertEqual(check([path]), [])

        def test_check_flags_copied_criterion_id_and_unrenamed_copies(self):
            copied = self.write('TC-ACT-001.md', TICKET.replace('// TC-ACT-001 criteria-hash: 00000000',
                                                                f'// TC-WEB-042 criteria-hash: {PINNED}'))
            self.assertEqual(len(check([copied])), 1)
            unrenamed = self.write('TC-ACT-005.md', TICKET.replace('criteria-hash: 00000000', f'criteria-hash: {PINNED}'))
            problems = check([unrenamed])
            self.assertEqual(len(problems), 1)
            self.assertIn('heading', problems[0][1])

        def test_empty_folder_raises_no_tickets(self):
            empty = self.dir / 'empty'
            empty.mkdir()
            with self.assertRaises(NoTickets):
                list(ticket_paths([empty]))

        def test_write_fails_without_hash_criterion(self):
            path = self.write('TC-ACT-001.md', TICKET.replace(
                '- [ ] Output test file contains comment: `// TC-ACT-001 criteria-hash: 00000000` as its first line\n', ''))
            self.assertEqual(main(['write', str(path)]), 1)

        def test_hash_command_prints_the_first_line(self):
            path = self.write('TC-ACT-001.md', TICKET)
            import io, contextlib
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(['hash', str(path)]), 0)
            self.assertEqual(out.getvalue().strip(), f'// TC-ACT-001 criteria-hash: {PINNED}')

        def test_ticket_names_ignore_case(self):
            self.write('todo.md', TODO_001)
            good = TICKET.replace('criteria-hash: 00000000', f'criteria-hash: {PINNED}')
            self.write('tc-act-001.MD', good)
            self.assertEqual([x.name for x in ticket_paths([self.dir])], ['tc-act-001.MD'])
            self.assertEqual(check([self.dir]), [])

        def project(self, stored=OLD, first=None, mark=' '):
            """A test project in self.dir: test-cases/ holds the test case and todo.md; the test case's test file
            starts with `first`, or doesn't exist when first is None."""
            (self.dir / 'test-cases').mkdir()
            ticket = self.write('test-cases/TC-ACT-001.md', TICKET.replace('00000000', stored))
            self.write('test-cases/todo.md', TODO.replace('- [X] TC-ACT-001', f'- [{mark}] TC-ACT-001'))
            spec = self.dir / 'tests/admin/TC-ACT-001.spec.ts'
            if first is not None:
                spec.parent.mkdir(parents=True)
                self.write('tests/admin/TC-ACT-001.spec.ts', first + BODY, newline='')
            return ticket, spec

        def test_rehash_rewrites_ticket_and_test_file_keeping_marks(self):
            ticket, spec = self.project(first=f'// TC-ACT-001 criteria-hash: {OLD}\r\n', mark='x')
            old = read_text(ticket)
            self.assertEqual(main(['rehash', str(self.dir / 'test-cases')]), 0)
            self.assertEqual(read_text(ticket), old.replace(OLD, PINNED))   # marks and ticks kept
            self.assertEqual(read_text(spec), f'// TC-ACT-001 criteria-hash: {PINNED}\r\n' + BODY)
            self.assertEqual(check([ticket]), [])
            self.assertEqual(main(['rehash', str(ticket)]), 0)              # already current: no change
            self.assertEqual(read_text(spec), f'// TC-ACT-001 criteria-hash: {PINNED}\r\n' + BODY)

        def test_rehash_reads_a_bom_prefixed_test_file(self):
            ticket, spec = self.project(first=f'\ufeff// TC-ACT-001 criteria-hash: {OLD}\n', mark='x')
            self.assertEqual(main(['rehash', str(ticket)]), 0)
            self.assertEqual(read_text(spec), f'\ufeff// TC-ACT-001 criteria-hash: {PINNED}\n' + BODY)

        def test_rehash_accepts_every_earlier_recipe(self):
            self.assertEqual(_digest(OLD_RECIPES[-1](TICKET)), OLD)
            for recipe in OLD_RECIPES:
                with self.subTest(recipe=recipe):
                    stored = _digest(recipe(TICKET))
                    self.assertNotEqual(stored, PINNED)
                    path = self.write('TC-ACT-001.md', TICKET.replace('00000000', stored))
                    self.assertEqual(main(['rehash', str(path)]), 0)
                    self.assertEqual(stored_hash(read_text(path)), PINNED)

        def test_rehash_refuses_hand_edited_criteria(self):
            ticket, spec = self.project(first=f'// TC-ACT-001 criteria-hash: {OLD}\n', mark='x')
            for old, new in (('activity list', 'list'), ('- [x] Absence', '- [x] Signed in as SUPERADMIN\n- [x] Absence')):
                with self.subTest(new=new):
                    edited = TICKET.replace('00000000', OLD).replace(old, new)
                    self.write('test-cases/TC-ACT-001.md', edited)
                    self.assertEqual(main(['rehash', str(ticket)]), 1)
                    self.assertEqual(read_text(ticket), edited)
                    self.assertEqual(read_text(spec), f'// TC-ACT-001 criteria-hash: {OLD}\n' + BODY)

        def test_rehash_refuses_a_test_file_behind_its_ticket(self):
            for first in ('// TC-ACT-001 criteria-hash: bbbbbbbb\n', '// TC-ACT-002 criteria-hash: ' + OLD + '\n', 'x\n'):
                with self.subTest(first=first):
                    ticket, spec = self.project(first=first)
                    old = read_text(ticket)
                    self.assertEqual(main(['rehash', str(ticket)]), 1)
                    self.assertEqual(read_text(ticket), old)
                    self.assertEqual(read_text(spec), first + BODY)
                    shutil.rmtree(self.dir / 'test-cases')
                    shutil.rmtree(self.dir / 'tests')

        def test_rehash_resolves_test_file_from_the_project_root(self):
            ticket, spec = self.project(first=f'// TC-ACT-001 criteria-hash: {OLD}\n', mark='x')
            cwd = os.getcwd()
            os.chdir(self.dir / 'test-cases')
            try:
                self.assertEqual(main(['rehash', 'TC-ACT-001.md']), 0)
            finally:
                os.chdir(cwd)
            self.assertEqual(read_text(spec), f'// TC-ACT-001 criteria-hash: {PINNED}\n' + BODY)

        def test_rehash_refuses_a_done_ticket_without_test_file(self):
            ticket, spec = self.project(mark='x')
            old = read_text(ticket)
            self.assertEqual(main(['rehash', str(ticket)]), 1)
            self.assertEqual(read_text(ticket), old)

        def test_rehash_without_test_file_rewrites_only_the_ticket(self):
            ticket, spec = self.project(mark='?')
            self.assertEqual(main(['rehash', str(ticket)]), 0)
            self.assertEqual(stored_hash(read_text(ticket)), PINNED)
            self.assertFalse(spec.exists())
            (self.dir / 'test-cases/todo.md').unlink()                      # no todo.md: not done either
            self.write('test-cases/TC-ACT-001.md', TICKET.replace('00000000', OLD))
            self.assertEqual(main(['rehash', str(ticket)]), 0)

        def test_todo_marks(self):
            marks = todo_marks(self.write('todo.md', TODO))
            self.assertEqual(marks, {'TC-ACT-001': 'x', 'TC-ACT-002': '?', 'TC-ACT-003': ' '})

        def test_unknown_command_fails(self):
            self.assertEqual(main([]), 2)
            self.assertEqual(main(['show', 'x']), 2)

        def test_help_exits_0(self):
            import io, contextlib
            for flag in ('-h', '--help'):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main([flag]), 0)
                self.assertIn('Usage:', out.getvalue())

        def test_index_prints_one_line_per_ticket(self):
            import io, contextlib
            self.good('TC-ACT-001')
            self.good('TC-ACT-002', TICKET.replace('**Feature:** Activities admin', '**Feature:** Activities admin\n**Journey:** J01'))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(['index', str(self.dir)]), 0)
            self.assertEqual(out.getvalue().splitlines(), [
                'TC-ACT-001 | Activities admin | Interaction-level | Functional | - | admin-desktop-chrome, admin-iphone-13'
                ' | Create an activity with valid data succeeds',
                'TC-ACT-002 | Activities admin | Interaction-level | Functional | J01 | admin-desktop-chrome, admin-iphone-13'
                ' | Create an activity with valid data succeeds'])

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QaTicketsTest)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    if sys.argv[1:] == ['--self-test']:
        sys.exit(_self_test())
    sys.exit(main(sys.argv[1:]))
