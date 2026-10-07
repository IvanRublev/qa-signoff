#!/usr/bin/env python3
"""
Lint qa-spec.md, including after hand edits. Read-only: it never rewrites the spec.

Critical checks (kind `defect` or `excluded-page`, exit 1). Later skills can't reliably catch these by reading:
  - no Site Map route marked `Excluded:` is on a named journey's chain (`excluded-page`);
  - journey IDs are unique (J01 and J1 are the same ID);
  - every Chain route of a named journey (one without a `Deferred:`/`Excluded:` marker under its heading)
    is in the Site Map;
  - the spec has Site Map routes and journeys at all;
  - the header has a `Roles crawled:` line (empty for an app with no login) and a non-empty `Environments:` line
    (downstream skills read them), and no two crawled roles share a slug, nor does one slug to `no-login`;
  - every role in a named journey's heading is in `Roles crawled:` or is `no-login`;
  - no `Excluded:` sits on a `/x/... <label>` Site Map line: exclusions go on exact page lines.

Warnings (kind `warning`, exit 2 when there is nothing critical). Later skills read these lines by hand:
  - a line that looks like a journey heading, a Chain or a Chain continuation but doesn't parse; a journey
    heading outside the Journeys section or without roles; a marker below the Chain; extra words in a Chain
    step; an `Excluded:` the lint can't place; a Site Map code block line holding a `/` but not starting with one
    (a tree glyph or bullet); an unclosed code fence;
  - a Site Map route `Excluded:` or a journey marker without a reason.

Known limits: a hyphen inside a heading's name (`### J1 Import - CSV`) is read as the roles separator;
`Excluded:` under Per-page guidance or on cross-cutting checks is not checked.

Exit codes: 0 clean, 1 critical defects (warnings are printed too), 2 warnings only, 3 bad input
(usage error or unreadable file). Each printed line is `<file>:<line>: <kind>: <message>`.

Usage:
    python3 qa_spec.py <qa-spec.md>
    python3 qa_spec.py --help
    python3 qa_spec.py --self-test
"""

import re
import sys

FENCE = ('```', '~~~')
JOURNEY = re.compile(r'^#{2,4}\s*(J\d+)\b\s*(.*)$')
JOURNEY_LIKE = re.compile(r'^(#+\s*|\*\*)J\s*\d', re.I)
SECTION = re.compile(r'^##\s+(.+?)\s*$')
CHAIN = re.compile(r'^(?:[-*]\s+)?[*_]*chain[*_]*:[*_]*\s*(.*)$', re.I)
MARKER = re.compile(r'^(?:[-*]\s+)?[*_]*(deferred|excluded)[*_]*:[*_]*\s*(.*)$', re.I)
INLINE_EXCLUDED = re.compile(r'\bexcluded:\s*(.*)$', re.I)
ARROW = re.compile(r'\s*(?:→|->|>)\s*')
ROLES = re.compile(r'\s[—–-]\s+\S')  # the roles after the dash must be non-empty
NOTE = re.compile(r'\([^)]*\)')
HEADING = 'journey heading not `### J<n> <name> — <roles>`'
HEADER_ERROR = "qa-spec.md header lacks a `Roles crawled:` or `Environments:` line; re-run qa-write-spec"
EMPTY_ENVIRONMENTS = "qa-spec.md header has an empty `Environments:` line; re-run qa-write-spec"
NO_LOGIN = 'no-login'


def slug(name):
    """A role or environment name as it appears in project names and test folders."""
    return name.strip().lower().replace(' ', '-')


def read_header(text):
    """Return (roles crawled, environments) from the spec header; ValueError when either line is missing,
    Environments: is empty, or two roles share a slug or a role slugs to no-login. An empty Roles crawled: is a
    no-login-only app."""
    roles = re.search(r'Roles crawled:[ \t]*(.*?)(?:\.\s+(?:Roles not crawled|Credentials)\b|\.?\s*$)', text, re.M)
    envs = re.search(r'^Environments:[ \t]*(.*?)\.?\s*$', text, re.M)
    split = lambda s: [x.strip() for x in s.split(',') if x.strip()]
    if not roles or not envs:
        raise ValueError(HEADER_ERROR)
    if not split(envs.group(1)):
        raise ValueError(EMPTY_ENVIRONMENTS)
    seen = {NO_LOGIN: NO_LOGIN}
    for role in split(roles.group(1)):
        if slug(role) in seen:
            raise ValueError(f'qa-spec.md `Roles crawled:` role {role!r} has the same slug as {seen[slug(role)]!r}; '
                             'rename one of them')
        seen[slug(role)] = role
    return split(roles.group(1)), split(envs.group(1))


def norm(route):
    route = re.sub(r'\{[^}]*\}', '{}', route.strip())
    return route.rstrip('/') or '/'


def parse(text):
    """Return (site_routes, excluded_routes, journeys, sections, problems); problems are (line, kind, message)."""
    site, excluded, journeys, sections, problems = set(), {}, [], set(), []
    section, fence, fence_mark, current, after_chain = None, None, None, None, False
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        run = len(line) - len(line.lstrip(line[:1])) if line.startswith(FENCE) else 0
        if not fence and run:
            fence, fence_mark = n, line[0] * run
            continue
        if fence and run >= len(fence_mark) and line == line[0] * run and line[0] == fence_mark[0]:
            fence, fence_mark = None, None  # closes only on a bare fence of the opener's kind, at least as long
            continue
        if fence:
            if section == 'site map' and line.startswith('/'):
                route = line.split()[0]
                site.add(norm(route))
                ex = INLINE_EXCLUDED.search(line)
                if ex and route.endswith('...'):
                    problems.append((n, 'defect', f'Excluded: on a `...` route line {route}; '
                                                  'exclude its exact pages on their own lines'))
                elif ex:
                    excluded[norm(route)] = n
                    if not ex.group(1).strip():
                        problems.append((n, 'warning', f'Excluded: without a reason on {route}'))
            elif section == 'site map' and '/' in line:
                problems.append((n, 'warning', f'Site Map route line must start with `/`: {line}'))
            elif section == 'site map' and INLINE_EXCLUDED.search(line):
                problems.append((n, 'warning', f'Excluded: not on a route line: {line}'))
            continue  # code blocks elsewhere (e.g. a pasted example under Journeys) are not parsed
        was_chain, after_chain = after_chain, False
        if section == 'site map' and INLINE_EXCLUDED.search(line):
            problems.append((n, 'warning', f'Excluded: outside the Site Map code block, not checked: {line}'))
            continue
        if section != 'journeys' and line.startswith('#') and JOURNEY_LIKE.match(line):
            problems.append((n, 'warning', f'journey heading outside the Journeys section: {line}'))
            continue
        if section == 'journeys' and (j := JOURNEY.match(line)):
            current = {'id': j.group(1), 'line': n, 'chain': None, 'marked': False, 'roles': []}
            journeys.append(current)
            if not (r := [*ROLES.finditer(' ' + j.group(2))]):
                problems.append((n, 'warning', f'{HEADING} (no roles): {line}'))
            else:  # roles follow the last dash; the name may hold dashes of its own
                roles = NOTE.sub('', (' ' + j.group(2))[r[-1].end() - 1:])
                current['roles'] = [x.strip() for x in roles.split(',') if x.strip()]
            continue
        if section == 'journeys' and JOURNEY_LIKE.match(line):
            problems.append((n, 'warning', f'{HEADING}: {line}'))
            current = None
            continue
        if (m := SECTION.match(line)):
            name = m.group(1).lower()
            section = next((k for k in ('site map', 'journeys') if name.startswith(k)), name)
            sections.add(section)
            current = None
            continue
        if section != 'journeys':
            continue
        if line.startswith('#'):
            problems.append((n, 'warning', f'{HEADING}: {line}'))
            current = None
        elif (c := CHAIN.match(line)):
            if current is None:
                problems.append((n, 'warning', f'Chain: outside a journey: {line}'))
                continue
            after_chain = True
            steps = ARROW.split(NOTE.sub('', c.group(1)).replace('`', '').strip())
            if current['chain'] is not None or not all(s.startswith('/') for s in steps):
                problems.append((n, 'warning', f'{current["id"]} Chain is not one line of routes: {line}'))
                current['chain'] = current['chain'] or []
            else:
                current['chain'] = [(s.split()[0], norm(s.split()[0])) for s in steps]
                if any(len(s.split()) > 1 for s in steps):
                    problems.append((n, 'warning', f'{current["id"]} Chain step has extra words, only its first route is checked: {line}'))
        elif line.startswith(('→', '->')) or (was_chain and line.startswith('/')):
            problems.append((n, 'warning', f'Chain continued on another line: {line}'))
        elif current and (mk := MARKER.match(line)):
            marker = f'{current["id"]} {mk.group(1).capitalize()}:'
            if current['chain'] is not None:
                problems.append((n, 'warning', f'{marker} below the Chain; move it right under the heading'))
                continue
            current['marked'] = True
            if not mk.group(2).strip():
                problems.append((n, 'warning', f'{marker} without a reason'))
    if fence:
        problems.append((fence, 'warning', f'unclosed code fence opened on line {fence}'))
    return site, excluded, journeys, sections, problems


def site_entry(route, site):
    """The Site Map entry a route matches, or None."""
    # ponytail: `/reporting/...` Site Map lines match by prefix only; add real patterns if specs grow them.
    if route in site:
        return route
    return next((s for s in site if s.endswith('...') and (route + '/').startswith(s[:-3])), None)


def lint(text):
    site, excluded, journeys, sections, problems = parse(text)
    try:
        crawled = {slug(x) for x in read_header(text)[0]} | {NO_LOGIN}
    except ValueError as e:
        crawled = None
        problems.append((0, 'defect', str(e)))
    seen = {}
    for j in journeys:
        key = int(j['id'][1:])
        if key in seen:
            problems.append((j['line'], 'defect', f'{j["id"]} duplicates the journey ID on line {seen[key]}'))
        seen.setdefault(key, j['line'])
        for role in j['roles'] if crawled and not j['marked'] else []:
            if slug(role) not in crawled:
                problems.append((j['line'], 'defect', f'{j["id"]} role {role} is not in `Roles crawled:`; '
                                                      'mark the journey Deferred:'))
        if j['chain'] is None:
            problems.append((j['line'], 'warning', f'{j["id"]} has no parseable Chain: line'))
            continue
        for shown, route in j['chain']:
            entry = site_entry(route, site)
            if entry is None and not j['marked']:  # a deferred journey's pages may not be crawled yet
                problems.append((j['line'], 'defect', f'{j["id"]} Chain route {shown} is not in the Site Map'))
            elif entry in excluded and not j['marked']:
                problems.append((j['line'], 'excluded-page',
                                 f'{j["id"]} walks {shown}, marked Excluded: on line {excluded[entry]}'))
    if not site:
        problems.append((0, 'defect', 'no Site Map routes found (a `## Site Map` section with a code block of routes)'))
    if not journeys:
        problems.append((0, 'defect', 'no journeys found (a `## Journeys` section with `### J<n> <name> — <roles>` headings)'))
    return sorted(problems)


def main(argv):
    if argv in (['-h'], ['--help']):
        print(__doc__.strip())
        return 0
    if len(argv) != 1 or argv[0].startswith('-'):
        print('usage: qa_spec.py <qa-spec.md> | --self-test', file=sys.stderr)
        return 3
    try:
        with open(argv[0], encoding='utf-8-sig') as f:
            problems = lint(f.read())
    except (OSError, UnicodeDecodeError) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 3
    for n, kind, msg in problems:
        print(f'{argv[0]}:{n}: {kind}: {msg}')
    if any(kind != 'warning' for _, kind, _ in problems):
        return 1
    return 2 if problems else 0


def _self_test():
    import io
    import tempfile
    from contextlib import redirect_stderr, redirect_stdout
    import unittest
    from pathlib import Path

    SPEC = """# QA Spec

Target: x. Roles crawled: Admin. Credentials in `.env`.
Environments: Desktop Chrome.

## Site Map

```
/login
/timesheet/                 (My times)
  /timesheet/{id}/edit
/admin/tags/                Excluded: plugin not installed
/reporting/... monthly report
```

## Journeys

### J1 Session lifecycle — Admin
Goal: log in and out.
Chain: /login → /timesheet/

### J2 Edit time — Admin
Chain: /timesheet → /timesheet/{entry}/edit
"""

    def kinds(text):
        return [(k, m) for _, k, m in lint(text)]

    class QaSpecTest(unittest.TestCase):
        def test_clean_spec(self):
            self.assertEqual(lint(SPEC), [])

        def test_chain_route_missing_from_site_map(self):
            probs = kinds(SPEC.replace('Chain: /login', 'Chain: /logon'))
            self.assertEqual(probs, [('defect', 'J1 Chain route /logon is not in the Site Map')])

        def test_duplicate_journey_id(self):
            probs = kinds(SPEC.replace('### J2 Edit', '### J1 Edit'))
            self.assertIn(('defect', 'J1 duplicates the journey ID on line 18'), probs)

        def test_excluded_page_on_named_journey(self):
            text = SPEC + '\n### J3 Tag time — Admin\nChain: /admin/tags → /timesheet/\n'
            self.assertIn(('excluded-page', 'J3 walks /admin/tags, marked Excluded: on line 12'), kinds(text))

        def test_excluded_page_on_deferred_or_excluded_journey_is_fine(self):
            for marker in ('Deferred: needs Teamlead', 'excluded: out of scope'):
                text = SPEC + f'\n### J3 Tag time — Admin\n{marker}\nChain: /admin/tags → /timesheet/\n'
                self.assertEqual(lint(text), [], marker)

        def test_marker_without_reason(self):
            text = SPEC.replace('Goal: log in and out.', 'Deferred:')
            self.assertEqual(kinds(text), [('warning', 'J1 Deferred: without a reason')])
            text = SPEC.replace('Excluded: plugin not installed', 'Excluded:')
            self.assertIn(('warning', 'Excluded: without a reason on /admin/tags/'), kinds(text))

        def test_hand_edited_variants_parse(self):
            edited = (SPEC.replace('### J1 Session lifecycle — Admin', '## J1 Session lifecycle – Admin')
                          .replace('Chain: /login → /timesheet/', '**Chain:** /login -> /timesheet')
                          .replace('### J2 Edit time — Admin', '#### J2 Edit time - Admin'))
            self.assertEqual(lint(edited), [])

        def test_placeholders_and_ellipsis_routes_match(self):
            text = SPEC + '\n### J3 Report — Admin\nChain: /timesheet/{x}/edit → /reporting/monthly\n'
            self.assertEqual(lint(text), [])

        def test_unparseable_lines_are_reported(self):
            probs = kinds(SPEC.replace('### J2 Edit time', '### J 2 Edit time'))
            self.assertIn('warning', [k for k, _ in probs])
            probs = kinds(SPEC.replace('Chain: /timesheet → ', 'Chain: timesheet page → '))
            self.assertEqual(probs[0][0], 'warning')
            probs = kinds(SPEC.replace('Chain: /login → /timesheet/\n', ''))
            self.assertIn(('warning', 'J1 has no parseable Chain: line'), probs)

        def assertFlagged(self, text, kind='warning'):
            self.assertIn(kind, [k for k, _ in kinds(text)], text)

        def test_unrecognised_heading_does_not_inherit_a_journey(self):
            for head in ('### Tagging (J2)', '##### J2 Edit time', '**J2 Edit time**', '### Notes'):
                self.assertFlagged(SPEC.replace('### J2 Edit time — Admin', head))
            self.assertFlagged(SPEC.replace('### J2 Edit time — Admin\n', ''))  # second Chain on J1
            self.assertFlagged(SPEC.replace('## Journeys\n', '## Journeys\nChain: /login\n'))  # Chain before any journey

        def test_spaced_journey_heading_does_not_end_the_section(self):
            text = SPEC.replace('### J1 Session', '## J 1 Session').replace('Chain: /timesheet →', 'Chain: /nope →')
            probs = kinds(text)
            self.assertIn('warning', [k for k, _ in probs])
            self.assertIn(('defect', 'J2 Chain route /nope is not in the Site Map'), probs)

        def test_section_heading_with_extra_text(self):
            text = SPEC.replace('## Journeys', '## Journeys (critical paths)').replace('/login → ', '/nope → ')
            self.assertIn(('defect', 'J1 Chain route /nope is not in the Site Map'), kinds(text))
            self.assertIn(('defect', 'J1 Chain route /nope is not in the Site Map'),
                          kinds(text.replace('## Site Map', '## Site Map (admin)')))

        def test_no_journeys(self):
            self.assertFlagged(SPEC[:SPEC.index('## Journeys')], 'defect')

        def test_wrapped_chain(self):
            self.assertFlagged(SPEC.replace('Chain: /login → /timesheet/', 'Chain: /login →\n  /timesheet/ → /nope'))
            self.assertFlagged(SPEC.replace('Chain: /login → /timesheet/', 'Chain: /login → /timesheet/\n  → /nope'))

        def test_marker_needs_a_colon(self):
            text = SPEC + '\n### J3 Tag — Admin\nExcluded pages below are fine to walk.\nChain: /admin/tags\n'
            self.assertIn(('excluded-page', 'J3 walks /admin/tags, marked Excluded: on line 12'), kinds(text))

        def test_excluded_on_ellipsis_line_is_a_defect(self):
            text = SPEC.replace('/reporting/... monthly report', '/reporting/... monthly report  Excluded: licensed')
            self.assertEqual(kinds(text), [('defect', 'Excluded: on a `...` route line /reporting/...; '
                                                      'exclude its exact pages on their own lines')])

        def test_missing_or_empty_header_is_a_defect(self):
            for old, new in (('Roles crawled: Admin. ', ''), ('Environments: Desktop Chrome.\n', '')):
                self.assertIn(('defect', HEADER_ERROR), kinds(SPEC.replace(old, new)), old)
            self.assertIn(('defect', EMPTY_ENVIRONMENTS), kinds(SPEC.replace('Environments: Desktop Chrome.', 'Environments: ')))

        def test_no_login_only_spec(self):
            text = SPEC.replace('Roles crawled: Admin.', 'Roles crawled: .').replace('— Admin', '— no-login')
            self.assertEqual(read_header(text), ([], ['Desktop Chrome']))
            self.assertEqual(lint(text), [])

        def test_journey_role_not_crawled(self):
            text = SPEC + '\n### J3 Team view — Admin, Teamlead\nChain: /login\n'
            self.assertEqual(kinds(text), [('defect', 'J3 role Teamlead is not in `Roles crawled:`; mark the journey Deferred:')])
            for heading in ('### J3 Reset — no-login', '### J3 Reset — admin, No-login'):
                self.assertEqual(lint(SPEC + f'\n{heading}\nChain: /login\n'), [], heading)
            self.assertEqual(lint(SPEC + '\n### J3 Team — Teamlead\nExcluded: out of scope\nChain: /login\n'), [])
            for heading in ('### J3 Check-in - check-out — Admin', '### J3 Reset — Admin (primary)'):
                self.assertEqual(lint(SPEC + f'\n{heading}\nChain: /login\n'), [], heading)
            text = SPEC.replace('Roles crawled: Admin.', 'Roles crawled: Admin, Standard user.')
            self.assertEqual(lint(text + '\n### J3 Reset — standard-user\nChain: /login\n'), [])

        def test_list_item_marker_and_chain(self):
            self.assertIn(('warning', 'J1 Deferred: without a reason'),
                          kinds(SPEC.replace('Goal: log in and out.', '- Deferred:')))
            self.assertEqual(lint(SPEC.replace('Chain: /login', '- Chain: /login')), [])

        def test_code_blocks_and_notes_in_journeys(self):
            for fence in ('```', '~~~'):
                pasted = f'{fence}\n### J1 Example — Admin\nChain: /nope\n{fence}\n'
                self.assertEqual(lint(SPEC.replace('### J2', pasted + '### J2')), [], fence)
            self.assertEqual(lint(SPEC.replace('Chain: /login →', 'Chain: /login (after 2FA) →')), [])

        def test_prose_starting_with_journey_id_is_not_a_heading(self):
            self.assertEqual(lint(SPEC.replace('Goal: log in and out.', 'J1 covers the login page first.')), [])

        def test_journey_heading_outside_journeys_section(self):
            self.assertFlagged(SPEC.replace('### J2 Edit time', '## Admin-only journeys\n\n### J2 Edit time'))
            self.assertFlagged(SPEC + '\n## Cross-cutting checks\n\n### J3 Tag — Admin\nChain: /nope\n')

        def test_unclosed_fence(self):
            self.assertFlagged(SPEC.replace('### J2', '```\n### J2'))

        def test_zero_padded_duplicate_id(self):
            self.assertFlagged(SPEC.replace('### J2 Edit', '### J01 Edit'), 'defect')

        def test_arrow_inside_note_and_backticks(self):
            self.assertEqual(lint(SPEC.replace('Chain: /login →', 'Chain: /login (Menu > Sign in) →')), [])
            self.assertEqual(lint(SPEC.replace('Chain: /login → /timesheet/', 'Chain: `/login` → `/timesheet/`')), [])

        def test_deferred_journey_skips_site_map_check(self):
            text = SPEC + '\n### J3 Team view — Teamlead\nDeferred: needs Teamlead credentials.\nChain: /team/timesheet/\n'
            self.assertEqual(lint(text), [])

        def test_heading_without_roles(self):
            self.assertFlagged(SPEC.replace('### J1 Session lifecycle — Admin', '### J1 Session lifecycle'))
            self.assertFlagged(SPEC.replace('### J1 Session lifecycle — Admin', '### J1'))
            self.assertEqual(lint(SPEC.replace('### J2 Edit time — Admin', '### J2 Check-in edit - Admin')), [])

        def test_excluded_on_its_own_line_in_site_map(self):
            self.assertFlagged(SPEC.replace('/timesheet/{id}/edit\n', '/timesheet/{id}/edit\n  Excluded: legacy\n'))

        def test_bare_route_list_after_journeys_is_fine(self):
            self.assertEqual(lint(SPEC + '\nSeams on no journey:\n/admin/tags/\n'), [])

        def test_continuation_right_after_chain(self):
            for cont in ('/nope', '-> /nope'):
                self.assertFlagged(SPEC.replace('Chain: /login → /timesheet/', f'Chain: /login → /timesheet/\n{cont}'))

        def test_no_site_map_routes_with_journeys(self):
            self.assertIn(('defect', 'no Site Map routes found (a `## Site Map` section with a code block of routes)'),
                          kinds(SPEC.replace('/login\n/timesheet/', 'login\ntimesheet/').replace('/admin/tags/', 'tags').replace('  /timesheet', '  timesheet').replace('/reporting', 'reporting')))

        def test_marker_under_unrecognised_heading_does_not_mark_previous_journey(self):
            text = SPEC + '\n### J3 Tag — Admin\nChain: /admin/tags\n### Notes\nDeferred: later\n'
            self.assertIn('excluded-page', [k for k, _ in kinds(text)])

        def test_italic_marker(self):
            text = SPEC + '\n### J3 Tag — Admin\n_Deferred:_ needs Teamlead\nChain: /admin/tags\n'
            self.assertEqual(lint(text), [])

        def test_non_utf8_file_is_bad_input(self):
            with tempfile.TemporaryDirectory() as d, redirect_stderr(io.StringIO()):
                p = Path(d) / 'qa-spec.md'
                p.write_bytes(SPEC.encode('utf-8').replace('—'.encode(), b'\x97'))
                self.assertEqual(main([str(p)]), 3)

        def test_critical_defects_win_the_exit_code(self):
            with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
                p = Path(d) / 'qa-spec.md'
                p.write_text(SPEC.replace('### J2', '### J 2').replace('/login →', '/logon →'), encoding='utf-8')
                self.assertEqual(main([str(p)]), 1)
                p.write_text(SPEC.replace('Excluded: plugin not installed', 'Excluded:'), encoding='utf-8')
                self.assertEqual(main([str(p)]), 2)

        def test_marker_below_chain_is_a_warning(self):
            text = SPEC + '\n### J3 Tag — Admin\nChain: /login\nDeferred:\n'
            self.assertIn(('warning', 'J3 Deferred: below the Chain; move it right under the heading'), kinds(text))

        def test_longer_fence_and_info_string(self):
            block = '````\n```\n### J9 Example — Admin\n```\n````\n'
            self.assertEqual(lint(SPEC.replace('### J2', block + '### J2')), [])
            block = '~~~~\n### J9 Example — Admin\n~~~\n~~~~\n'
            self.assertEqual(lint(SPEC.replace('### J2', block + '### J2')), [])
            block = '```\n```python\n### J9 Example — Admin\n```\n'
            self.assertEqual(lint(SPEC.replace('### J2', block + '### J2')), [])

        def test_excluded_outside_site_map_block(self):
            text = SPEC.replace('```\n\n## Journeys', '```\n- /login Excluded: SSO only\n\n## Journeys')
            self.assertFlagged(text)

        def test_extra_words_in_chain_step(self):
            self.assertFlagged(SPEC.replace('Chain: /login → /timesheet/', 'Chain: /login → /timesheet/ then /nope'))

        def test_prefix_entry_matches_its_root(self):
            self.assertEqual(lint(SPEC + '\n### J3 Report — Admin\nChain: /reporting/\n'), [])

        def test_dash_without_roles(self):
            self.assertFlagged(SPEC.replace('### J1 Session lifecycle — Admin', '### J1 Session lifecycle —'))

        def test_unrecognised_heading_resets_the_journey(self):
            for head in ('### Notes', '**J2 later**'):
                text = SPEC + f'\n{head}\nChain: /nope\n'
                self.assertIn(('warning', 'Chain: outside a journey: Chain: /nope'), kinds(text), head)

        def test_no_site_map(self):
            self.assertIn(('defect', 'no Site Map routes found (a `## Site Map` section with a code block of routes)'),
                          kinds('## Journeys\n\n### J1 Login — Admin\nChain: /login\n'))

        def test_marker_after_chain_does_not_mark(self):
            text = SPEC + '\n### J3 Tag — Admin\nChain: /nope\n\nSeams on no journey:\n- Excluded: /doctor (needs root)\n'
            self.assertIn(('defect', 'J3 Chain route /nope is not in the Site Map'), kinds(text))

        def test_arrow_continuation_after_blank_or_goal(self):
            self.assertFlagged(SPEC.replace('Chain: /login → /timesheet/', 'Chain: /login → /timesheet/\n\n→ /nope'))
            self.assertFlagged(SPEC.replace('Chain: /login → /timesheet/', 'Chain: /login → /timesheet/\nGoal: x\n-> /admin/tags'))

        def test_other_fence_inside_code_block(self):
            block = '```\n~~~\n### J9 Example — Admin\n```\n'
            self.assertEqual(lint(SPEC.replace('### J2', block + '### J2')), [])

        def test_site_map_line_not_starting_with_slash(self):
            text = SPEC.replace('/login\n/timesheet/ ', '/login\n├── /timesheet/ ').replace('/admin/tags/ ', '- /admin/tags/ ')
            self.assertEqual([p for p in kinds(text) if p[0] == 'warning'], [
                ('warning', 'Site Map route line must start with `/`: ├── /timesheet/                 (My times)'),
                ('warning', 'Site Map route line must start with `/`: - /admin/tags/                Excluded: plugin not installed')])

        def test_role_slug_collisions(self):
            for roles in ('admin, No Login', 'Admin, admin', 'admin, admin'):
                text = SPEC.replace('Roles crawled: Admin.', f'Roles crawled: {roles}.')
                with self.assertRaises(ValueError, msg=roles):
                    read_header(text)
                self.assertIn('defect', [k for k, _ in kinds(text)], roles)

        def test_help_exits_zero(self):
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(['--help']), 0)
                self.assertEqual(main(['-h']), 0)
            self.assertIn('Usage:', out.getvalue())

        def test_cli_exit_codes(self):
            with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                p = Path(d) / 'qa-spec.md'
                p.write_text(SPEC, encoding='utf-8')
                self.assertEqual(main([str(p)]), 0)
                p.write_text(SPEC.replace('/login →', '/logon →'), encoding='utf-8')
                self.assertEqual(main([str(p)]), 1)
                p.write_text(SPEC.replace('### J2', '### J 2'), encoding='utf-8')
                self.assertEqual(main([str(p)]), 2)
                self.assertEqual(main([str(Path(d) / 'missing.md')]), 3)
                self.assertEqual(main([]), 3)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QaSpecTest)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    if sys.argv[1:] == ['--self-test']:
        sys.exit(_self_test())
    sys.exit(main(sys.argv[1:]))
