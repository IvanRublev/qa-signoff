#!/usr/bin/env python3
"""
Playwright project rules of qa-write-test-cases' config gate.

Project names are `<role slug>-<environment slug>` for every role in qa-spec.md's
`Roles crawled:` line plus the artificial role `no-login`, and every Playwright
profile in its `Environments:` line. A slug is the name lowercased with spaces
turned into hyphens. A test case's test file is `<tests root>/<role slug>/<ID>.spec.ts`;
a test case listing some but not all of its role's projects carries a self-skip line
naming exactly its Projects.

Usage:
    python3 qa_projects.py check-test-cases --spec qa-spec.md --tests-root tests <test-case.md|dir>...
    python3 qa_projects.py check-config --spec qa-spec.md --project-dir .
    python3 qa_projects.py fix-config --spec qa-spec.md --project-dir . [--apply]
        prints the diff that makes a template-shaped config's `roles` and `environments` arrays match
        qa-spec.md (exit 1 while it differs); --apply writes it and re-runs check-config
    python3 qa_projects.py --self-test

Exit codes: 0 ok, or -h/--help; 1 problems found or unreadable input; 2 usage error or no test cases found.
"""

import argparse
import difflib
import fnmatch
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_tickets import NoTickets, read_text, read_ticket, ticket_paths  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'qa-write-spec' / 'scripts'))
from qa_spec import NO_LOGIN, read_header, slug  # noqa: E402  (the spec header's one parser)

SELF_SKIP = re.compile(
    r'test\.skip\(\s*!\s*\[([^\]]*)\]\s*\.includes\(\s*test\.info\(\)\.project\.name\s*\)', re.S)
NAME = re.compile(r"""['"`]([^'"`]+)['"`]""")


def expected_projects(roles, envs):
    return {slug(r): [f'{slug(r)}-{slug(e)}' for e in envs] for r in [*roles, NO_LOGIN]}


def test_file(tests_root, role, ticket_id):
    return posixpath.normpath(f'{tests_root}/{slug(role)}/{ticket_id}.spec.ts')


def check_ticket(path, roles, envs, tests_root):
    t = read_ticket(path)
    by_role = expected_projects(roles, envs)
    leads = [r for r, names in by_role.items() if t['projects'] and set(t['projects']) <= set(names)]
    if not leads:
        return [('PROJECTS MISMATCH', f"{t['id']}: Projects {t['projects'] or 'missing'} "
                 "aren't projects of one role in the config gate")]
    lead, problems = leads[0], []
    expected = test_file(tests_root, lead, t['id'])
    if posixpath.normpath(t['test_file'] or '').lower() != expected.lower():
        problems.append(('TEST FILE MISMATCH', f"{t['id']}: Test file {t['test_file']!r}, expected {expected!r}"))
    skip = SELF_SKIP.search(read_text(path))
    named = set(NAME.findall(skip.group(1))) if skip else None
    subset = set(t['projects']) != set(by_role[lead])
    if subset and named != set(t['projects']):
        problems.append(('TEST FILE MISMATCH', f"{t['id']}: Projects is a subset of {lead}'s projects, "
                         f"so its self-skip line must name exactly {sorted(t['projects'])}; "
                         f"found {sorted(named) if named else 'none'}"))
    if not subset and skip:
        problems.append(('TEST FILE MISMATCH', f"{t['id']}: Projects lists every environment, "
                         "so the test case must not carry a self-skip line"))
    return problems


def check_config(listing, roles, envs):
    root = listing['config']['rootDir']
    actual = {p['name']: p['testDir'] for p in listing['config']['projects']}
    expected = {name: f'{root}/{role}' for role, names in expected_projects(roles, envs).items() for name in names}
    problems = [f'missing project {name}' for name in expected if name not in actual]
    problems += [f'project {name} has testDir {actual[name]}, expected {d}'
                 for name, d in expected.items() if name in actual and actual[name].lower() != d.lower()]
    # A project in a role folder, or named after a spec environment, belongs to the matrix; others are left alone.
    role_dirs = set(expected.values())
    env_suffixes = tuple(f'-{slug(e)}' for e in envs)
    problems += [f'project {name} is not a role x environment of qa-spec.md (unknown role or environment)'
                 for name, d in actual.items()
                 if name not in expected and (d in role_dirs or name.endswith(env_suffixes))]
    # A project above the role folders runs every role's test files without that role's session.
    problems += [f'project {p["name"]} has testDir {p["testDir"]}, which holds the role folders, so it runs '
                 "every role's test files without their session; remove it"
                 for p in listing['config']['projects'] if p['name'] not in expected and runs_test_case_files(p)
                 and any(r.lower().startswith(p['testDir'].rstrip('/').lower() + '/') for r in role_dirs)]
    return problems


def runs_test_case_files(project):
    """Whether any testMatch pattern (`/regex/` or glob, as the JSON listing prints them) takes a `.spec.ts` file."""
    probe = f"{project['testDir']}/role/TC-X-001.spec.ts"
    for pattern in project.get('testMatch') or ['**/*.spec.ts']:
        regex = re.fullmatch(r'/(.*)/[a-z]*', pattern, re.S)
        # ponytail: an extglob or brace glob (Playwright's default is one) counts as matching; parse it if a
        # setup project ever uses one
        if regex and re.search(regex.group(1), probe) or not regex and (
                re.search(r'[@?+*!]\(|\{', pattern) or fnmatch.fnmatchcase(probe, pattern)):
            return True
    return False


ARRAY = r'((?:export\s+)?const\s+{name}\s*=\s*)\[[^\]]*\]'


STRING = re.compile(r"'((?:[^'\\\n]|\\.)*)'" + r'|"((?:[^"\\\n]|\\.)*)"')


def read_config_names(text):
    """The `roles` and `environments` arrays of a template-shaped config."""
    values = []
    for name in ('roles', 'environments'):
        m = re.search(ARRAY.format(name=name), text)
        body = text[m.end(1):m.end()] if m else ''
        if not m or '//' in body or '/*' in body:
            raise ValueError(f"the config's `const {name} = [...]` array is missing or holds comments: it doesn't "
                             "follow templates/playwright.config.ts, so fix it by hand")
        values.append([json.loads(f'"{m.group(2)}"') if m.group(2) is not None else m.group(1).replace("\\'", "'")
                       for m in STRING.finditer(body)])
    return tuple(values)


def rewrite_config(text, roles, envs):
    read_config_names(text)
    for name, values in (('roles', roles), ('environments', envs)):
        literal = '[' + ', '.join("'" + v.replace('\\', '\\\\').replace("'", "\\'") + "'" for v in values) + ']'
        text = re.sub(ARRAY.format(name=name), lambda m: m.group(1) + literal, text, count=1)
    if read_config_names(text) != (list(roles), list(envs)):
        raise ValueError("rewriting the config's arrays didn't round-trip; fix it by hand")
    return text


def find_config(project_dir):
    names = {p.name.lower(): p for p in Path(project_dir).iterdir() if p.is_file()}
    for ext in ('ts', 'js', 'mts', 'mjs', 'cts', 'cjs'):
        if f'playwright.config.{ext}' in names:
            return names[f'playwright.config.{ext}']
    raise ValueError(f'no playwright.config.(ts|js|mts|mjs|cts|cjs) in {project_dir}')


def parse_listing(returncode, stdout, stderr):
    try:
        listing = json.loads(stdout)
    except ValueError:
        listing = None
    if returncode != 0 and not (listing and 'config' in listing) or listing is None:
        raise ValueError(f"`npx playwright test --list` failed: {(stderr or stdout).strip()[:800]}")
    return listing


def load_listing(project_dir):
    out = subprocess.run(['npx', 'playwright', 'test', '--list', '--reporter=json'],
                         cwd=project_dir, capture_output=True, text=True)
    return parse_listing(out.returncode, out.stdout, out.stderr)


def main(argv):
    parser = argparse.ArgumentParser(prog='qa_projects.py')
    sub = parser.add_subparsers(dest='command')
    p = sub.add_parser('check-test-cases')
    p.add_argument('--spec', required=True); p.add_argument('--tests-root', required=True); p.add_argument('paths', nargs='+')
    p = sub.add_parser('check-config'); p.add_argument('--spec', required=True); p.add_argument('--project-dir', default='.')
    p = sub.add_parser('fix-config'); p.add_argument('--spec', required=True); p.add_argument('--project-dir', default='.')
    p.add_argument('--apply', action='store_true')
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code
    if not args.command:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        roles, envs = read_header(Path(args.spec).read_text(encoding='utf-8'))
        if args.command == 'fix-config':
            config = find_config(args.project_dir)
            old = config.read_text(encoding='utf-8')
            new = rewrite_config(old, roles, envs)
            if new == old:
                print(f'{config.name}: roles and environments already match qa-spec.md; '
                      'any remaining check-config problem needs a hand fix')
            else:
                sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                           str(config), f'{config} (from qa-spec.md)'))
                if not args.apply:
                    return 1
                config.write_text(new, encoding='utf-8')
                try:
                    load_listing(args.project_dir)
                except ValueError:
                    config.write_text(old, encoding='utf-8')
                    raise
            args.command = 'check-config'
        if args.command == 'check-test-cases':
            problems = [p for path in ticket_paths(args.paths) for p in check_ticket(path, roles, envs, args.tests_root)]
        else:
            listing = load_listing(args.project_dir)
            problems = [('CONFIG', p) for p in check_config(listing, roles, envs)]
            print(f"tests root: {os.path.relpath(listing['config']['rootDir'], args.project_dir)}")
    except NoTickets as e:
        print(f'Error: {e}', file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    for kind, message in problems:
        print(f'{kind}: {message}')
    return 1 if problems else 0


def _self_test():
    import tempfile
    import unittest

    SPEC = """# Kimai QA Spec

Target: http://127.0.0.1:8000. Roles crawled: admin, standard user. Roles not crawled: teamlead (no credentials). Credentials in `.env`.
Environments: Desktop Chrome, iPhone 13.

## Site Map
"""
    ALL = ['admin-desktop-chrome', 'admin-iphone-13']

    def ticket(projects, test_file, skip=None):
        block = f"- The first line of every test is `test.skip(!{skip}.includes(test.info().project.name), 'reason')`.\n" if skip else ''
        return f"""## TC-TS-031 - Timesheet list

**Feature:** Timesheet
**Projects:** {', '.join(projects)}
**Test file:** {test_file}

### How to build

**Test file rules:**
- Write exactly one file at `{test_file}`.
{block}
### Acceptance criteria

- [ ] Output test file contains comment: `// TC-TS-031 criteria-hash: 00000000` as its first line
"""

    def listing(root, names_to_dirs):
        # testMatch as `--list --reporter=json` prints it: the template's setup regex, else Playwright's default glob
        return {'config': {'rootDir': root, 'projects': [
            {'name': n, 'testDir': d,
             'testMatch': ['/auth\\.setup\\.ts/'] if n == 'setup' else ['**/*.@(spec|test).?(c|m)[jt]s?(x)']}
            for n, d in names_to_dirs.items()]}}

    class QaProjectsTest(unittest.TestCase):
        def setUp(self):
            self._tmp = tempfile.TemporaryDirectory()
            self.dir = Path(self._tmp.name)

        def tearDown(self):
            self._tmp.cleanup()

        def write(self, name, text):
            path = self.dir / name
            path.write_text(text, encoding='utf-8')
            return path

        def test_slug(self):
            self.assertEqual(slug('standard user'), 'standard-user')
            self.assertEqual(slug('Desktop Chrome'), 'desktop-chrome')
            self.assertEqual(slug('iPhone 13'), 'iphone-13')

        def test_read_header(self):
            self.assertEqual(read_header(SPEC), (['admin', 'standard user'], ['Desktop Chrome', 'iPhone 13']))

        def test_read_header_variants(self):
            spec = SPEC.replace('admin, standard user.', 'admin, Dr. Who.')
            self.assertEqual(read_header(spec)[0], ['admin', 'Dr. Who'])
            spec = SPEC.replace('Environments: Desktop Chrome, iPhone 13.', 'Environments: iPad (gen 7), Galaxy S9+')
            self.assertEqual(read_header(spec)[1], ['iPad (gen 7)', 'Galaxy S9+'])

        def test_read_header_without_environments_fails(self):
            with self.assertRaises(ValueError):
                read_header(SPEC.replace('Environments: Desktop Chrome, iPhone 13.\n', ''))

        def test_expected_projects_include_no_login(self):
            self.assertEqual(expected_projects(['admin', 'standard user'], ['Desktop Chrome', 'iPhone 13']), {
                'admin': ALL,
                'standard-user': ['standard-user-desktop-chrome', 'standard-user-iphone-13'],
                'no-login': ['no-login-desktop-chrome', 'no-login-iphone-13'],
            })

        def test_test_file(self):
            self.assertEqual(test_file('tests', 'standard user', 'TC-TS-031'), 'tests/standard-user/TC-TS-031.spec.ts')

        def check(self, text):
            return check_ticket(self.write('TC-TS-031.md', text), *read_header(SPEC), 'tests')

        def test_ticket_every_environment_passes(self):
            self.assertEqual(self.check(ticket(ALL, 'tests/admin/TC-TS-031.spec.ts')), [])

        def test_tests_root_spelling_does_not_matter(self):
            self.assertEqual(check_ticket(self.write('TC-TS-031.md', ticket(ALL, './tests/admin/TC-TS-031.spec.ts')),
                                          *read_header(SPEC), 'tests'), [])
            self.assertEqual(check_ticket(self.write('TC-TS-031.md', ticket(ALL, 'tests/admin/TC-TS-031.spec.ts')),
                                          *read_header(SPEC), './tests/'), [])

        def test_self_skip_line_variants(self):
            path = 'tests/admin/TC-TS-031.spec.ts'
            for skip in ("test.skip( ![`admin-iphone-13`].includes(test.info().project.name), 'r')",
                         "test.skip(!\n  ['admin-iphone-13']\n  .includes( test.info().project.name ), 'r')"):
                text = ticket(['admin-iphone-13'], path).replace(
                    '### Acceptance criteria', f'- The first line of every test is `{skip}`.\n\n### Acceptance criteria')
                self.assertEqual(self.check(text), [], skip)
            text = ticket(['admin-iphone-13'], path).replace(
                '### Acceptance criteria', "- `test.skip(['admin-iphone-13'].includes(test.info().project.name), 'r')`\n\n### Acceptance criteria")
            self.assertEqual([k for k, _ in self.check(text)], ['TEST FILE MISMATCH'])

        def test_ticket_subset_needs_exact_self_skip(self):
            path = 'tests/admin/TC-TS-031.spec.ts'
            self.assertEqual(self.check(ticket(['admin-iphone-13'], path, "['admin-iphone-13']")), [])
            kinds = [k for k, _ in self.check(ticket(['admin-iphone-13'], path))]
            self.assertEqual(kinds, ['TEST FILE MISMATCH'])
            kinds = [k for k, _ in self.check(ticket(['admin-iphone-13'], path, "['admin-desktop-chrome']"))]
            self.assertEqual(kinds, ['TEST FILE MISMATCH'])

        def test_ticket_all_environments_with_self_skip_fails(self):
            kinds = [k for k, _ in self.check(ticket(ALL, 'tests/admin/TC-TS-031.spec.ts', str(ALL)))]
            self.assertEqual(kinds, ['TEST FILE MISMATCH'])

        def test_ticket_wrong_path_or_projects(self):
            kinds = [k for k, _ in self.check(ticket(ALL, 'tests/admin/timesheet/TC-TS-031.spec.ts'))]
            self.assertEqual(kinds, ['TEST FILE MISMATCH'])
            kinds = [k for k, _ in self.check(ticket(['admin-desktop-chrome', 'standard-user-iphone-13'],
                                                     'tests/admin/TC-TS-031.spec.ts'))]
            self.assertEqual(kinds, ['PROJECTS MISMATCH'])
            kinds = [k for k, _ in self.check(ticket([], 'tests/admin/TC-TS-031.spec.ts'))]
            self.assertEqual(kinds, ['PROJECTS MISMATCH'])

        def test_check_config(self):
            roles, envs = read_header(SPEC)
            good = {'setup': '/p/tests', 'api': '/p/api'}  # other projects are left alone
            for role, names in expected_projects(roles, envs).items():
                for n in names:
                    good[n] = f'/p/tests/{role}'
            self.assertEqual(check_config(listing('/p/tests', good), roles, envs), [])
            bad = dict(good)
            del bad['no-login-iphone-13']
            bad['admin-desktop-chrome'] = '/p/tests'
            bad['admin-desktop-safari'] = '/p/tests/admin'
            problems = check_config(listing('/p/tests', bad), roles, envs)
            self.assertEqual(len(problems), 3)
            self.assertTrue(any('admin-desktop-safari' in p for p in problems))
            self.assertTrue(any('no-login-iphone-13' in p for p in problems))
            self.assertTrue(any('admin-desktop-chrome' in p for p in problems))

        def test_check_config_flags_a_catch_all_project(self):
            roles, envs = read_header(SPEC)
            good = {'setup': '/p/tests'}
            for role, names in expected_projects(roles, envs).items():
                for n in names:
                    good[n] = f'/p/tests/{role}'
            for name, d in (('chromium', '/p/tests'), ('legacy', '/p'), ('mixed', '/P/Tests/')):
                with self.subTest(name=name):
                    problems = check_config(listing('/p/tests', {**good, name: d}), roles, envs)
                    self.assertEqual(len(problems), 1)
                    self.assertIn(name, problems[0])
            # a setup-style project runs only its own files, wherever its testDir is
            other = listing('/p/tests', {**good, 'seed': '/p/tests'})
            other['config']['projects'][-1]['testMatch'] = ['**/*.seed.ts']
            self.assertEqual(check_config(other, roles, envs), [])

        def test_parse_listing_errors(self):
            with self.assertRaises(ValueError) as ctx:
                parse_listing(1, '', 'SyntaxError: Unexpected token in playwright.config.ts')
            self.assertIn('SyntaxError', str(ctx.exception))
            with self.assertRaises(ValueError):
                parse_listing(0, 'hello from console.log', '')
            self.assertEqual(parse_listing(0, '{"config": {}}', ''), {'config': {}})
            # a broken test file makes --list exit 1 but still print the config
            self.assertEqual(parse_listing(1, '{"config": {}, "errors": [{}]}', 'x'), {'config': {}, 'errors': [{}]})

        def test_check_config_cli(self):
            global load_listing
            spec = self.write('qa-spec.md', SPEC)
            roles, envs = read_header(SPEC)
            good = {'setup': str(self.dir / 'tests')}
            for role, names in expected_projects(roles, envs).items():
                for n in names:
                    good[n] = str(self.dir / 'tests' / role)
            real = load_listing
            try:
                load_listing = lambda d: listing(str(self.dir / 'tests'), good)
                import io, contextlib
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(['check-config', '--spec', str(spec), '--project-dir', str(self.dir)]), 0)
                self.assertIn('tests root: tests', out.getvalue())
                load_listing = lambda d: listing('/elsewhere/tests', {'setup': '/elsewhere/tests'})
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(['check-config', '--spec', str(spec), '--project-dir', str(self.dir)]), 1)
                self.assertIn('\nCONFIG: missing project admin-desktop-chrome', out.getvalue())
                def broken(d):
                    raise ValueError('config error')
                load_listing = broken
                self.assertEqual(main(['check-config', '--spec', str(spec), '--project-dir', str(self.dir)]), 1)
            finally:
                load_listing = real

        CONFIG = """import { defineConfig, devices } from '@playwright/test';

// Names exactly as in the spec header.
export const roles = ['admin', 'teamlead'];
const environments = [
  'Desktop Chrome',
  'Desktop Safari',
];
export default defineConfig({});
"""

        def test_rewrite_config_takes_spec_values(self):
            new = rewrite_config(self.CONFIG, ['admin', 'standard user'], ['Desktop Chrome', 'iPhone 13'])
            self.assertIn("export const roles = ['admin', 'standard user'];", new)
            self.assertIn("const environments = ['Desktop Chrome', 'iPhone 13'];", new)
            self.assertIn('// Names exactly as in the spec header.', new)

        def test_rewrite_config_quotes_names_and_refuses_comments(self):
            new = rewrite_config(self.CONFIG, ["manager's assistant", 'admin'], ['Desktop Chrome'])
            self.assertEqual(read_config_names(new), (["manager's assistant", 'admin'], ['Desktop Chrome']))
            commented = self.CONFIG.replace("'Desktop Safari',", "'Desktop Safari', // see [PW devices]")
            with self.assertRaises(ValueError):
                rewrite_config(commented, ['admin'], ['Desktop Chrome'])

        def test_fix_config_restores_file_when_recheck_cannot_load(self):
            global load_listing
            spec = self.write('qa-spec.md', SPEC)
            config = self.write('playwright.config.ts', self.CONFIG)
            real = load_listing
            def broken(d):
                raise ValueError('SyntaxError in playwright.config.ts')
            try:
                load_listing = broken
                self.assertEqual(main(['fix-config', '--spec', str(spec), '--project-dir', str(self.dir), '--apply']), 1)
            finally:
                load_listing = real
            self.assertEqual(config.read_text(encoding='utf-8'), self.CONFIG)

        def test_fix_config_without_changes_still_rechecks(self):
            global load_listing
            spec = self.write('qa-spec.md', SPEC)
            roles, envs = read_header(SPEC)
            config = self.write('playwright.config.ts', rewrite_config(self.CONFIG, roles, envs))
            real = load_listing
            try:
                load_listing = lambda d: listing(str(self.dir / 'tests'), {'setup': str(self.dir / 'tests')})
                for extra in ([], ['--apply']):
                    self.assertEqual(main(['fix-config', '--spec', str(spec), '--project-dir', str(self.dir)] + extra), 1)
            finally:
                load_listing = real

        def test_rewrite_config_refuses_non_template(self):
            with self.assertRaises(ValueError):
                rewrite_config("export default defineConfig({ projects: [] });", ['admin'], ['Desktop Chrome'])

        def test_fix_config_cli(self):
            global load_listing
            spec = self.write('qa-spec.md', SPEC)
            config = self.write('playwright.config.ts', self.CONFIG)
            args = ['fix-config', '--spec', str(spec), '--project-dir', str(self.dir)]
            self.assertEqual(main(args), 1)                           # diff only, nothing written
            self.assertEqual(config.read_text(encoding='utf-8'), self.CONFIG)
            roles, envs = read_header(SPEC)
            good = {'setup': str(self.dir / 'tests')}
            for role, names in expected_projects(roles, envs).items():
                for n in names:
                    good[n] = str(self.dir / 'tests' / role)
            real = load_listing
            try:
                load_listing = lambda d: listing(str(self.dir / 'tests'), good)
                self.assertEqual(main(args + ['--apply']), 0)         # written, then check-config passes
                self.assertEqual(read_config_names(config.read_text(encoding='utf-8')), (roles, envs))
                self.assertEqual(main(args), 0)                       # already matches
                load_listing = lambda d: listing(str(self.dir / 'tests'), {'setup': str(self.dir / 'tests')})
                config.write_text(self.CONFIG, encoding='utf-8')
                self.assertEqual(main(args + ['--apply']), 1)         # written, but the re-check fails
            finally:
                load_listing = real
            config.write_text('export default defineConfig({});', encoding='utf-8')
            self.assertEqual(main(args + ['--apply']), 1)             # not template-shaped: untouched
            self.assertEqual(config.read_text(encoding='utf-8'), 'export default defineConfig({});')

        def test_paths_and_config_name_ignore_case(self):
            self.assertEqual(check_ticket(self.write('TC-TS-031.md', ticket(ALL, 'Tests/Admin/TC-TS-031.spec.ts')),
                                          *read_header(SPEC), 'tests'), [])
            self.write('Playwright.Config.TS', 'x')
            self.assertEqual(find_config(self.dir).name, 'Playwright.Config.TS')
            for ext in ('mts', 'cts'):
                with self.subTest(ext=ext):
                    (self.dir / 'Playwright.Config.TS').unlink(missing_ok=True)
                    for old in self.dir.glob('playwright.config.*'):
                        old.unlink()
                    self.write(f'playwright.config.{ext}', 'x')
                    self.assertEqual(find_config(self.dir).name, f'playwright.config.{ext}')

        def test_cli_exit_codes(self):
            spec = self.write('qa-spec.md', SPEC)
            good = self.write('TC-TS-031.md', ticket(ALL, 'tests/admin/TC-TS-031.spec.ts'))
            self.assertEqual(main(['check-test-cases', '--spec', str(spec), '--tests-root', 'tests', str(good)]), 0)
            good.write_text(ticket(ALL, 'tests/admin/x/TC-TS-031.spec.ts'), encoding='utf-8')
            self.assertEqual(main(['check-test-cases', '--spec', str(spec), '--tests-root', 'tests', str(good)]), 1)
            self.assertEqual(main([]), 2)
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--help']), 0)
            empty = self.dir / 'empty'
            empty.mkdir()
            self.assertEqual(main(['check-test-cases', '--spec', str(spec), '--tests-root', 'tests', str(empty)]), 2)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QaProjectsTest)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    if sys.argv[1:] == ['--self-test']:
        sys.exit(_self_test())
    sys.exit(main(sys.argv[1:]))
