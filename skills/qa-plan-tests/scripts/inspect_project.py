#!/usr/bin/env python3
"""
Read-only look at a test project, for the choices qa-plan-tests asks about. Prints one JSON object:
whether the folder is inside a git work tree, the Playwright setup (dependency, installed version, whether it meets the minimum the qa-browse-app skill sets, config file), the device profiles the installed Playwright
offers, the roles found in `.env`, in the config, in qa-spec.md and, with --app, as hints in the app's source code, the environments found in the config and
in qa-spec.md, and any example tests Playwright's setup left behind.

Usage:
    python3 inspect_project.py [<project root>] [--app <app code folder>]    default root: the current folder
    python3 inspect_project.py --self-test
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CONFIGS = ('playwright.config.ts', 'playwright.config.js', 'playwright.config.mts', 'playwright.config.mjs',
           'playwright.config.cts', 'playwright.config.cjs')
EXAMPLES = ('tests/example.spec.ts', 'tests/example.spec.js', 'e2e/example.spec.ts', 'e2e/example.spec.js',
            'tests-examples')
# The mobile profiles offered by default, when the installed Playwright has them; any other profile name is accepted.
MOBILE_SHORTLIST = ('iPhone 15', 'iPhone 14', 'iPhone 13', 'iPhone SE', 'Pixel 7', 'Pixel 5', 'Galaxy S9+', 'iPad Pro 11')
DEVICES_JS = ("const d=require('@playwright/test').devices;"
              "console.log(JSON.stringify(Object.entries(d).map(([n,v])=>[n,!!v.isMobile])))")


def find_config(root):
    return next((name for name in CONFIGS if (root / name).is_file()), None)


def _json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def dependency(root):
    package = _json(root / 'package.json')
    return (package.get('devDependencies') or {}).get('@playwright/test') \
        or (package.get('dependencies') or {}).get('@playwright/test')


def installed_version(root):
    return _json(root / 'node_modules' / '@playwright' / 'test' / 'package.json').get('version')


def env_roles(root):
    """`<ROLE>_USERNAME` with a `<ROLE>_PASSWORD` is a role: SUPER_ADMIN gives `Super admin`. Read from `.env-seed`,
    the credentials template every worktree copies to `.env`, and from `.env`."""
    roles = []
    for name in ('.env-seed', '.env'):
        try:
            keys = [line.split('=', 1)[0].strip() for line in (root / name).read_text(encoding='utf-8').splitlines()
                    if '=' in line and not line.lstrip().startswith('#')]
        except OSError:
            continue
        roles += [k[:-len('_USERNAME')].lower().replace('_', ' ').capitalize() for k in keys
                  if k.endswith('_USERNAME') and k[:-len('_USERNAME')] + '_PASSWORD' in keys]
    return list(dict.fromkeys(roles))


def env_files(root):
    """Whether the credential files exist and whether git ignores them: they hold live passwords and sessions."""
    def ignored(name):
        try:
            return subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', name], capture_output=True,
                                  timeout=10).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    return {name: {'exists': (root / name.rstrip('/')).exists(), 'ignored': ignored(name)}
            for name in ('.env-seed', '.env', '.auth/')}


def _names(text):
    return re.findall(r"['\"]([^'\"]+)['\"]", text)


def config_lists(root):
    """The `roles` and `environments` arrays of the config the qa-write-test-cases template gives."""
    config = find_config(root)
    text = (root / config).read_text(encoding='utf-8') if config else ''
    found = {name: re.search(rf'\b{name}\s*=\s*\[(.*?)\]', text, re.S) for name in ('roles', 'environments')}
    return {name: _names(m.group(1)) if m else [] for name, m in found.items()}


def spec_header(root):
    try:
        text = (root / 'qa-spec.md').read_text(encoding='utf-8')
    except OSError:
        return {'roles': [], 'environments': []}

    def listed(label):
        m = re.search(rf'{label}:\s*(.+?)(?:\.(?:\s|$)|\n)', text)
        return [x.strip() for x in m.group(1).split(',') if x.strip()] if m else []
    return {'roles': listed('Roles crawled'), 'environments': listed('Environments')}


def device_names(root):
    """[name, isMobile] pairs from the project's installed Playwright, or None when it isn't installed."""
    if not installed_version(root):
        return None
    try:
        out = subprocess.run(['node', '-e', DEVICES_JS], cwd=root, capture_output=True, text=True, timeout=30, check=True)
        return json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def group_devices(names):
    mobile = {n for n, is_mobile in names if is_mobile}
    return {'desktop': [n for n, _ in names if n.startswith('Desktop') and not n.endswith('HiDPI')],
            'mobile': [n for n in MOBILE_SHORTLIST if n in mobile]}


def at_least(version, minimum):
    """Whether `version` is `minimum` or newer, comparing the dotted numbers; False when either is missing."""
    def numbers(v):
        return tuple(int(n) for n in re.findall(r'\d+', v)[:3]) if v else None
    have, need = numbers(version), numbers(minimum)
    return bool(have and need and have >= need)


QA_BROWSE_APP = Path(__file__).resolve().parents[2] / 'qa-browse-app' / 'scripts' / 'qa-browse-app.mjs'


def minimum_playwright(script=QA_BROWSE_APP):
    """The oldest Playwright the qa-browse-app skill works with, asked from that skill, which owns the number."""
    try:
        out = subprocess.run(['node', str(script), 'min-playwright'], capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def git_state(root):
    """Whether the folder is inside a git work tree, and that tree's top folder."""
    try:
        out = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {'inside_work_tree': False, 'toplevel': None}
    return {'inside_work_tree': out.returncode == 0, 'toplevel': out.stdout.strip() or None}


SQL_NAME = re.compile(r'seed|sample|demo|fixture|dump|template|testdata|dataset', re.I)
SQL_DIRS = {'seeders', 'seeder', 'seeds', 'fixtures', 'fixture'}
LOADER_KEY = re.compile(r'seed|fixture|demo|sample|dummy', re.I)
DOC_HINT = re.compile(r'(?:sample|demo|seed|fixture|dummy)\s+(?:data|users?|accounts?)|reset-dev|loaddata|db:seed|db seed'
                      r'|seeders?\b|fixtures:load', re.I)


def _hints(base, label, key, doc, limit=12):
    """Lines worth reading: package.json and composer.json scripts and Makefile targets whose name matches `key`, and
    lines of the top-level and docs/ Markdown files that match `doc`. Each carries `label:file[:line]`."""
    base, hints = Path(base), []
    for name in ('package.json', 'composer.json'):
        for script, command in (_json(base / name).get('scripts') or {}).items():
            if key.search(script) and isinstance(command, str):
                hints.append({'file': f'{label}:{name}', 'text': f'{script}: {command}'})
    try:
        for number, line in enumerate((base / 'Makefile').read_text(encoding='utf-8').splitlines(), 1):
            m = re.match(r'^([A-Za-z0-9_.\-]+):', line)
            if m and key.search(m.group(1)):
                hints.append({'file': f'{label}:Makefile:{number}', 'text': f'{m.group(1)}:'})
    except OSError:
        pass
    docs = sorted(base.glob('*.md')) + sorted(base.glob('*.rst')) + sorted((base / 'docs').glob('*.md'))
    for doc_file in docs:
        try:
            lines = doc_file.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, 1):
            if doc.search(line) and len(hints) < limit * 2:
                hints.append({'file': f'{label}:{doc_file.relative_to(base).as_posix()}:{number}', 'text': line.strip()})
    return hints[:limit * 2]


def sample_data(base, label, limit=12):
    """Where an app or test project keeps sample data: SQL files that look like seeds or dumps, and the scripts, make
    targets and documented commands that load it. Hints for the agent to read, not a decision."""
    base = Path(base)
    if not base.is_dir():
        return {'sql_files': [], 'script_hints': []}
    sql = [f'{label}:{p.relative_to(base).as_posix()}' for p in sorted(base.rglob('*.sql'))
           if p.is_file() and not SKIP_DIRS & set(p.relative_to(base).parts[:-1])
           and (SQL_NAME.search(p.name) or SQL_DIRS & set(p.relative_to(base).parts[:-1]))]
    return {'sql_files': sql, 'script_hints': _hints(base, label, LOADER_KEY, DOC_HINT, limit)}


START_KEY = re.compile(r'(?:^|[:_\-])(?:dev|start|serve|server|run|up|db|database|docker|compose)(?:$|[:_\-])', re.I)
START_DOC = re.compile(r'docker[ -]compose (?:up|run)|\b(?:npm|yarn|pnpm) (?:run )?(?:dev|start|serve)\b|symfony serve'
                       r'|symfony server:start|php\b[^\n]*\s-S\s|artisan serve|rails s(?:erver)?\b|manage\.py runserver|flask run|uvicorn'
                       r'|gunicorn|mix phx\.server|spring-boot:run|bootRun|go run|brew services start|systemctl start'
                       r'|service \w+ start|pg_ctl|mysqld|mariadbd', re.I)
COMPOSE_FILES = ('docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml')


def start_hints(base, label, limit=12):
    """How an app and its database may be started for local development: compose files, `Procfile` lines, dev scripts
    and make targets, and documented commands. Hints for the agent to read, not commands to run."""
    base = Path(base)
    if not base.is_dir():
        return {'compose_files': [], 'script_hints': []}
    hints = _hints(base, label, START_KEY, START_DOC, limit)
    try:
        hints += [{'file': f'{label}:Procfile:{n}', 'text': line.strip()}
                  for n, line in enumerate((base / 'Procfile').read_text(encoding='utf-8').splitlines(), 1)
                  if line.strip() and not line.lstrip().startswith('#')]
    except OSError:
        pass
    return {'compose_files': [f'{label}:{name}' for name in COMPOSE_FILES if (base / name).is_file()],
            'script_hints': hints[:limit * 2]}


def merged_start_hints(root, app):
    found = [start_hints(root, 'project')] + ([start_hints(app, 'app')] if app else [])
    return {'compose_files': [f for d in found for f in d['compose_files']],
            'script_hints': [h for d in found for h in d['script_hints']]}


def merged_sample_data(root, app):
    found = [sample_data(root, 'project')] + ([sample_data(app, 'app')] if app else [])
    return {'sql_files': [f for d in found for f in d['sql_files']],
            'script_hints': [h for d in found for h in d['script_hints']]}


def examples(root):
    return [p for p in EXAMPLES if (root / p).exists()]


SKIP_DIRS = {'.git', 'node_modules', 'vendor', 'var', 'cache', 'dist', 'build', 'target', '.venv', 'venv', '__pycache__',
             'storage', '.next', 'coverage', '.claude', '.codex', '.agents', 'worktrees'}
CODE_SUFFIXES = {'.yaml', '.yml', '.php', '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.kt', '.rb', '.cs', '.go', '.rs',
                 '.ex', '.exs', '.swift', '.scala', '.sql', '.json', '.xml', '.toml', '.md'}
MANIFESTS = ('package.json', 'composer.json', 'pyproject.toml', 'requirements.txt', 'Gemfile', 'pom.xml', 'build.gradle',
             'build.gradle.kts', 'go.mod', 'Cargo.toml', 'mix.exs', 'Package.swift')
NOISE = {'error', 'name', 'none', 'null', 'undefined', 'true', 'false', 'string', 'default', 'id', 'type', 'value', 'key',
         'any', 'all'}
HOTSPOT = re.compile(r'\b(?:roles?|permissions?|rbac|acl|authori[sz]\w*|polic(?:y|ies)|abilit(?:y|ies))\b', re.I)
QUOTED = re.compile(r"""["']([^"']+)["']""")


def _members(block):
    return [m.group(1) for m in (re.match(r'\s*([A-Za-z_]\w*)', part) for part in re.split(r'[,\n;]', block)) if m]


def _py_members(block):
    return re.findall(r'^\s+([A-Za-z]\w*)\s*=', block, re.M)


def _ruby_members(block):
    return re.findall(r'\b([A-Za-z_]\w*)\s*:(?!:)', block) + re.findall(r'(?<![\w:]):([A-Za-z_]\w*)', block)


def _strip_role(name):
    return re.sub(r'^ROLE_', '', name)


# (pattern, names found in a match, sure). A sure pattern names a role by itself; the others (role comparisons)
# count only when they repeat.
ROLE_PATTERNS = (
    (re.compile(r'\bROLE_([A-Z][A-Z0-9_]*)\b'), lambda m: [m.group(1)], True),
    (re.compile(r"""(?i)\broles?\b["']?\s*(?:==|===|=|:|=>|\bin\b|\bis\b)\s*[\[(\{]?\s*["']([A-Za-z][\w \-]{1,29})["']"""),
     lambda m: [m.group(1)], False),
    (re.compile(r"""(?i)\b(?:has|is|assign|check|require|with|in|remove|sync)_?(?:any_?)?role\w*\(\s*["']([^"']+)["']"""),
     lambda m: [m.group(1)], True),
    (re.compile(r'@(?:RolesAllowed|Secured|PreAuthorize|Roles|Authorize)\s*\(([^)]*)\)'),
     lambda m: [_strip_role(n) for n in QUOTED.findall(m.group(1))], True),
    (re.compile(r'\benum\s+\w*Role\w*\s*\{([^}]*)\}'), lambda m: _members(m.group(1)), True),
    (re.compile(r'class\s+\w*Role\w*\s*\([^)]*Enum[^)]*\)\s*:\s*\n((?:[ \t]+[^\n]*\n?)+)'),
     lambda m: _py_members(m.group(1)), True),
    (re.compile(r"""\btype\s+\w*Role\w*\s*=\s*((?:["'][\w \-]+["']\s*\|?\s*)+)"""),
     lambda m: QUOTED.findall(m.group(1)), True),
    (re.compile(r'\benum\s+:?role\b[:,]?\s*[\[{(]?([^\]})\n]*)'), lambda m: _ruby_members(m.group(1)), True),
    (re.compile(r"""Role::create\(\s*\[\s*["']name["']\s*=>\s*["']([^"']+)["']"""), lambda m: [m.group(1)], True),
    (re.compile(r"""\bRole\.(?:create!?|find_or_create_by)\(\s*(?::name\s*=>|name:)\s*["']([^"']+)["']"""),
     lambda m: [m.group(1)], True),
    (re.compile(r"""Group\.objects\.(?:get_or_create|create)\(\s*name\s*=\s*["']([^"']+)["']"""), lambda m: [m.group(1)], True),
    (re.compile(r"""(?is)insert\s+into\s+[`"\[]?\w*roles?[`"\]]?\s*\([^)]*\)\s*values\s*([^;]*)"""),
     lambda m: re.findall(r"""\(\s*["']([^"']+)["']""", m.group(1)), True),
    (re.compile(r'\bRole[A-Z]\w*\s*(?:string\s*)?=\s*"([^"]+)"'), lambda m: [m.group(1)], True),
)


def _display(name):
    return re.sub(r'[_\-\s]+', ' ', name.strip()).lower().capitalize()


def role_hints(app, limit=12, max_files=20000):
    """What an app's source says about its roles, for any language. `candidates` are role names matched by common
    definitions (`ROLE_*` constants, role enums, role-guard calls and annotations, role-creating calls, SQL seeds, role
    comparisons that repeat), each with the first file:line. `hotspots` are the files that talk most about roles and
    permissions; `stack` is the build manifests at the app root. A hint, not the truth: the agent reads the hotspots
    and searches the code for the app's own role definitions."""
    app = Path(app)
    empty = {'candidates': [], 'hotspots': [], 'stack': []}
    if not app.is_dir():
        return empty
    found, hotspots, files = {}, [], 0
    for path in sorted(app.rglob('*')):
        rel = path.relative_to(app)
        if (SKIP_DIRS & set(rel.parts[:-1])) or path.suffix not in CODE_SUFFIXES or not path.is_file():
            continue
        files += 1
        if files > max_files or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        talk = len(HOTSPOT.findall(text))
        if talk >= 3:
            hotspots.append({'file': rel.as_posix(), 'mentions': talk})
        for pattern, extract, sure in ROLE_PATTERNS:
            for m in pattern.finditer(text):
                for raw in extract(m):
                    name = _display(raw)
                    if len(name) < 2 or name.lower() in NOISE:
                        continue
                    entry = found.setdefault(name.lower(), {'name': name, 'source': raw, 'sure': False, 'mentions': 0,
                                                            'evidence': f"{rel.as_posix()}:{text.count(chr(10), 0, m.start()) + 1}"})
                    entry['mentions'] += 1
                    entry['sure'] = entry['sure'] or sure
    candidates = sorted((e for e in found.values() if e['sure'] or e['mentions'] >= 2),
                        key=lambda e: (-e['mentions'], e['name']))[:limit]
    stack = [m for m in MANIFESTS if (app / m).is_file()] + sorted(x.name for x in app.glob('*.csproj'))
    return {'candidates': [{k: e[k] for k in ('name', 'source', 'evidence', 'mentions')} for e in candidates],
            'hotspots': sorted(hotspots, key=lambda h: (-h['mentions'], h['file']))[:10], 'stack': stack}


def inspect(root, app=None):
    root = Path(root)
    names = device_names(root)
    minimum = minimum_playwright()
    config, spec = config_lists(root), spec_header(root)
    code = role_hints(Path(app)) if app else {'candidates': [], 'hotspots': [], 'stack': []}
    return {
        'root': str(root.resolve()),
        'git': git_state(root),
        'env_files': env_files(root),
        'playwright': {'dependency': dependency(root), 'installed': installed_version(root), 'config': find_config(root),
                       'minimum': minimum, 'meets_minimum': at_least(installed_version(root), minimum)},
        'devices': group_devices(names) if names else None,
        'roles': {'from_env': env_roles(root), 'from_config': config['roles'], 'from_spec': spec['roles'],
                  'from_code': code['candidates']},
        'environments': {'from_config': config['environments'], 'from_spec': spec['environments']},
        'examples': examples(root),
        'sample_data': merged_sample_data(root, app),
        'start': merged_start_hints(root, app),
        'code': {'hotspots': code['hotspots'], 'stack': code['stack']},
    }


def _self_test():
    class InspectTest(unittest.TestCase):
        def setUp(self):
            self._tmp = tempfile.TemporaryDirectory()
            self.root = Path(self._tmp.name)

        def tearDown(self):
            self._tmp.cleanup()

        def write(self, name, text):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')

        def test_an_empty_folder_is_not_a_playwright_project(self):
            r = inspect(self.root)
            self.assertEqual({k: r['playwright'][k] for k in ('dependency', 'installed', 'config', 'meets_minimum')},
                             {'dependency': None, 'installed': None, 'config': None, 'meets_minimum': False})
            self.assertIsNone(r['devices'])
            self.assertEqual((r['roles']['from_env'], r['examples']), ([], []))

        def test_finds_the_dependency_the_version_and_the_config(self):
            self.write('package.json', '{"devDependencies": {"@playwright/test": "^1.49.0"}}')
            self.write('node_modules/@playwright/test/package.json', '{"version": "1.49.0"}')
            self.write('playwright.config.mjs', 'export default {}')
            r = inspect(self.root)['playwright']
            self.assertEqual((r['dependency'], r['installed'], r['config']), ('^1.49.0', '1.49.0', 'playwright.config.mjs'))
            self.assertEqual(r['meets_minimum'], at_least('1.49.0', r['minimum']))

        def test_a_broken_package_json_is_not_a_crash(self):
            self.write('package.json', '{not json')
            self.assertIsNone(inspect(self.root)['playwright']['dependency'])

        def test_roles_come_from_username_and_password_pairs_in_env(self):
            self.write('.env', 'SUPER_ADMIN_USERNAME=a\nSUPER_ADMIN_PASSWORD=b\nUSER_USERNAME=c\nUSER_PASSWORD=d\n'
                               'LONELY_USERNAME=x\nBASE_URL=http://x\n# OLD_USERNAME=y\n')
            self.assertEqual(inspect(self.root)['roles']['from_env'], ['Super admin', 'User'])

        def test_roles_and_environments_from_the_config_template_shape(self):
            self.write('playwright.config.ts', "export const roles = ['Super admin', 'User'];\n"
                                               "const environments = ['Desktop Chrome', 'iPhone 13'];\n")
            r = inspect(self.root)
            self.assertEqual(r['roles']['from_config'], ['Super admin', 'User'])
            self.assertEqual(r['environments']['from_config'], ['Desktop Chrome', 'iPhone 13'])

        def test_roles_and_environments_from_the_spec_header(self):
            self.write('qa-spec.md', '# Spec\n\nTarget: http://x. Roles crawled: admin, standard user. '
                                     'Roles not crawled: teamlead (no credentials).\n'
                                     'Environments: Desktop Chrome, iPhone 13.\n\n## Site Map\n')
            r = inspect(self.root)
            self.assertEqual(r['roles']['from_spec'], ['admin', 'standard user'])
            self.assertEqual(r['environments']['from_spec'], ['Desktop Chrome', 'iPhone 13'])

        def test_example_tests_are_listed(self):
            self.write('tests/example.spec.ts', '')
            self.write('tests-examples/demo-todo-app.spec.ts', '')
            self.assertEqual(inspect(self.root)['examples'], ['tests/example.spec.ts', 'tests-examples'])

        def test_devices_split_into_desktop_and_a_mobile_shortlist(self):
            names = [('Desktop Chrome', False), ('Desktop Chrome HiDPI', False), ('Desktop Safari', False),
                     ('iPhone 13', True), ('iPhone 13 landscape', True), ('Pixel 7', True), ('Nexus 7', True)]
            self.assertEqual(group_devices(names), {'desktop': ['Desktop Chrome', 'Desktop Safari'],
                                                    'mobile': ['iPhone 13', 'Pixel 7']})


        def names(self):
            return [h['name'] for h in role_hints(self.root)['candidates']]

        def test_php_symfony_constants_are_counted_ranked_and_vendor_code_is_skipped(self):
            self.write('config/security.yaml', 'role_hierarchy:\n  ROLE_TEAMLEAD: ROLE_USER\n  ROLE_ADMIN: ROLE_TEAMLEAD\n')
            self.write('src/A.php', "#[IsGranted('ROLE_ADMIN')]\n#[IsGranted('ROLE_ADMIN')]\n")
            self.write('vendor/x.php', 'ROLE_VENDORONLY ROLE_VENDORONLY ROLE_VENDORONLY')
            self.write('var/cache/y.php', 'ROLE_CACHED ROLE_CACHED')
            hints = role_hints(self.root)['candidates']
            self.assertEqual([h['name'] for h in hints], ['Admin', 'Teamlead', 'User'])
            self.assertEqual(hints[0]['evidence'], 'config/security.yaml:3')
            self.assertEqual(hints[0]['mentions'], 3)

        def test_php_laravel_role_creation(self):
            self.write('database/seeders/R.php', "Role::create(['name' => 'editor']);\n$user->assignRole('billing');\n")
            self.assertEqual(sorted(self.names()), ['Billing', 'Editor'])

        def test_python_enum_members_and_role_comparisons(self):
            self.write('app/models.py', "class Role(Enum):\n    ADMIN = 'admin'\n    MANAGER = 'manager'\n\nx = 1\n")
            self.write('app/views.py', "if user.role == 'support':\n    pass\nelif user.role == 'support':\n    pass\n")
            self.write('app/groups.py', "Group.objects.get_or_create(name='Auditor')\n")
            self.assertEqual(sorted(self.names()), ['Admin', 'Auditor', 'Manager', 'Support'])

        def test_typescript_union_type_and_call(self):
            self.write('src/auth.ts', "type Role = 'admin' | 'editor';\nif (user.hasRole('viewer')) {}\n")
            self.assertEqual(sorted(self.names()), ['Admin', 'Editor', 'Viewer'])

        def test_java_annotation_and_enum(self):
            self.write('src/Api.java', '@RolesAllowed({"ADMIN", "CLERK"})\nclass Api {}\n')
            self.write('src/Role.java', 'public enum Role { OWNER, GUEST(1) }\n')
            self.assertEqual(sorted(self.names()), ['Admin', 'Clerk', 'Guest', 'Owner'])

        def test_ruby_enum(self):
            self.write('app/models/user.rb', "enum role: { admin: 0, member: 1 }\n")
            self.write('app/models/p.rb', "enum :role, [:owner, :guest]\n")
            self.assertEqual(sorted(self.names()), ['Admin', 'Guest', 'Member', 'Owner'])

        def test_sql_seed_and_go_constant(self):
            self.write('db/seed.sql', "INSERT INTO roles (name) VALUES ('owner'), ('viewer');\n")
            self.write('auth/roles.go', 'const RoleAdmin = "admin"\n')
            self.assertEqual(sorted(self.names()), ['Admin', 'Owner', 'Viewer'])

        def test_noise_words_and_one_off_weak_matches_are_dropped(self):
            self.write('src/a.php', "ROLE_ERROR ROLE_ERROR ROLE_NAME ROLE_NAME\n$x->role == 'oneoff';\n")
            self.assertEqual(self.names(), [])

        def test_hotspots_and_stack_help_any_language(self):
            self.write('composer.json', '{}')
            self.write('go.mod', 'module x')
            self.write('lib/policy.ex', 'permission role permission role rbac\n')
            self.write('lib/other.ex', 'nothing here\n')
            hints = role_hints(self.root)
            self.assertEqual(hints['stack'], ['composer.json', 'go.mod'])
            self.assertEqual([h['file'] for h in hints['hotspots']], ['lib/policy.ex'])

        def test_role_hints_of_a_missing_folder_are_empty(self):
            self.assertEqual(role_hints(self.root / 'nope'), {'candidates': [], 'hotspots': [], 'stack': []})

        def test_inspect_adds_the_code_findings_only_when_an_app_path_is_given(self):
            self.write('src/A.php', "ROLE_ADMIN ROLE_ADMIN")
            self.assertEqual(inspect(self.root)['roles']['from_code'], [])
            r = inspect(self.root, app=self.root)
            self.assertEqual([h['name'] for h in r['roles']['from_code']], ['Admin'])
            self.assertEqual(set(r['code']), {'hotspots', 'stack'})

        def test_git_says_whether_the_folder_is_inside_a_work_tree(self):
            self.assertEqual(inspect(self.root)['git'], {'inside_work_tree': False, 'toplevel': None})
            subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
            sub = self.root / 'app'
            sub.mkdir()
            g = inspect(sub)['git']
            self.assertTrue(g['inside_work_tree'])
            self.assertEqual(Path(g['toplevel']).resolve(), self.root.resolve())

        def test_roles_come_from_env_seed_when_there_is_no_env(self):
            self.write('.env-seed', 'ADMIN_USERNAME=a\nADMIN_PASSWORD=b\n')
            self.assertEqual(inspect(self.root)['roles']['from_env'], ['Admin'])

        def test_seed_and_env_roles_are_merged_without_repeats(self):
            self.write('.env-seed', 'ADMIN_USERNAME=a\nADMIN_PASSWORD=b\n')
            self.write('.env', 'ADMIN_USERNAME=a\nADMIN_PASSWORD=b\nUSER_USERNAME=c\nUSER_PASSWORD=d\n')
            self.assertEqual(inspect(self.root)['roles']['from_env'], ['Admin', 'User'])

        def test_env_files_report_presence_and_whether_git_ignores_them(self):
            subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
            self.write('.gitignore', '.env-seed\n')
            self.write('.env-seed', 'X=1\n')
            self.assertEqual(inspect(self.root)['env_files'], {
                '.env-seed': {'exists': True, 'ignored': True},
                '.env': {'exists': False, 'ignored': False},
                '.auth/': {'exists': False, 'ignored': False}})

        def test_at_least_compares_versions_numerically(self):
            self.assertTrue(at_least('1.49.0', '1.49.0'))
            self.assertTrue(at_least('1.100.0', '1.49.0'))
            self.assertTrue(at_least('2.0.0', '1.49.9'))
            self.assertFalse(at_least('1.45.3', '1.49.0'))
            self.assertFalse(at_least(None, '1.49.0'))
            self.assertFalse(at_least('1.49.0', None))

        def test_the_minimum_is_read_from_the_qa_browse_app_skill(self):
            fake = self.root / 'qa-browse-app.mjs'
            fake.write_text("if (process.argv[2] === 'min-playwright') console.log('9.9.9');", encoding='utf-8')
            self.assertEqual(minimum_playwright(fake), '9.9.9')
            self.assertIsNone(minimum_playwright(self.root / 'missing.mjs'))

        def test_sample_data_finds_sql_files_and_skips_vendor_and_plain_schemas(self):
            self.write('db/seed.sql', '')
            self.write('kimai-template.sql', '')
            self.write('data/demo-data.sql', '')
            self.write('seeders/users.sql', '')
            self.write('vendor/x/seed.sql', '')
            self.write('migrations/schema.sql', '')
            self.assertEqual(sample_data(self.root, 'project')['sql_files'],
                             ['project:data/demo-data.sql', 'project:db/seed.sql', 'project:kimai-template.sql',
                              'project:seeders/users.sql'])

        def test_sample_data_finds_loader_scripts_and_documented_commands(self):
            self.write('package.json', '{"scripts": {"db:seed": "prisma db seed", "build": "tsc", "reset": "node reset.js"}}')
            self.write('composer.json', '{"scripts": {"fixtures": "bin/console doctrine:fixtures:load"}}')
            self.write('Makefile', 'build:\n\tgo build\nseed:\n\tpsql -f db/seed.sql\n')
            self.write('README.md', 'Intro\nRun `bin/console kimai:reset-dev` to load demo data.\nNothing here.\n')
            hints = sample_data(self.root, 'app')['script_hints']
            texts = {h['text'] for h in hints}
            self.assertIn('db:seed: prisma db seed', texts)
            self.assertIn('fixtures: bin/console doctrine:fixtures:load', texts)
            self.assertIn('seed:', texts)
            self.assertIn('Run `bin/console kimai:reset-dev` to load demo data.', texts)
            self.assertNotIn('build: tsc', texts)
            self.assertEqual({h['file'] for h in hints if h['text'].startswith('Run')}, {'app:README.md:2'})

        def test_sample_data_of_an_empty_folder_is_empty(self):
            self.assertEqual(sample_data(self.root, 'project'), {'sql_files': [], 'script_hints': []})

        def test_inspect_reports_sample_data_of_the_project_and_the_app(self):
            self.write('proj/db/seed.sql', '')
            self.write('app/fixtures/demo.sql', '')
            r = inspect(self.root / 'proj', app=self.root / 'app')
            self.assertEqual(r['sample_data']['sql_files'], ['project:db/seed.sql', 'app:fixtures/demo.sql'])

        def test_start_hints_find_dev_scripts_compose_files_and_documented_commands(self):
            self.write('package.json', '{"scripts": {"dev": "vite", "build": "tsc", "test": "jest", "db:up": "docker compose up -d db"}}')
            self.write('composer.json', '{"scripts": {"serve": "symfony server:start", "lint": "phpcs"}}')
            self.write('Makefile', 'build:\n\tgo build\nrun:\n\tgo run .\nup:\n\tdocker compose up\n')
            self.write('docker-compose.yml', 'services: {}')
            self.write('Procfile', 'web: bundle exec rails server\n')
            self.write('README.md', 'Intro\nStart the database with `docker compose up -d db`.\nServe: php -d x=1 -S 127.0.0.1:8000 -t public\nSee the license.\n')
            hints = start_hints(self.root, 'project')
            texts = {h['text'] for h in hints['script_hints']}
            self.assertEqual(hints['compose_files'], ['project:docker-compose.yml'])
            for expected in ('dev: vite', 'db:up: docker compose up -d db', 'serve: symfony server:start', 'run:', 'up:',
                             'web: bundle exec rails server', 'Start the database with `docker compose up -d db`.',
                             'Serve: php -d x=1 -S 127.0.0.1:8000 -t public'):
                self.assertIn(expected, texts)
            for unexpected in ('build: tsc', 'test: jest', 'lint: phpcs', 'build:'):
                self.assertNotIn(unexpected, texts)

        def test_start_hints_of_an_empty_folder_are_empty(self):
            self.assertEqual(start_hints(self.root, 'app'), {'compose_files': [], 'script_hints': []})

        def test_inspect_reports_start_hints_of_the_project_and_the_app(self):
            self.write('proj/docker-compose.yml', '')
            self.write('app/package.json', '{"scripts": {"start": "node server.js"}}')
            r = inspect(self.root / 'proj', app=self.root / 'app')
            self.assertEqual(r['start']['compose_files'], ['project:docker-compose.yml'])
            self.assertEqual([h['text'] for h in r['start']['script_hints']], ['start: node server.js'])

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InspectTest)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main(argv):
    if argv[:1] in (['-h'], ['--help']):
        print(__doc__.strip())
        return 0
    if argv == ['--self-test']:
        return _self_test()
    app = None
    if '--app' in argv:
        i = argv.index('--app')
        app, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    print(json.dumps(inspect(Path(argv[0] if argv else '.'), app=app), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
