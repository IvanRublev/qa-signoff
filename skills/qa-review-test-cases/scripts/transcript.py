#!/usr/bin/env python3
"""
Gather a review run's scratch files into qa-review-test-cases-transcript-<date>-<HHMM>.md (Step 5).

Scratch file names (SKILL.md, Execution layout), matched ignoring case:
    main-clauses.md                Main's clause list with tags (Step 1.1), its M- findings, dedup record
    E.md or E1.md, E2.md, ...      test case index (one per backlog batch)
    C.md                           seam -> code map and code -> spec Warnings
    A1-<area>.md, A2-<area>.md     coverage per area
    F.md                           cross-cutting clauses, OWASP per journey, tier check
    B.md or B1.md, B2.md, ...      overlap (one per backlog batch)
    D.md or D1.md, D2.md, ...      verification of the high-stakes findings (one per batch; none when no finding needs it)

Dotfiles (e.g. .DS_Store) are ignored.

Each file becomes one `## Subagent <id> — <scope>` section, in that order, holding the file verbatim
inside a code fence longer than any backtick run in it, so nothing in a file can break the sections.

Usage:
    python3 transcript.py --scratch <run scratch dir> --out qa-review-test-cases-transcript-<date>-<HHMM>.md
    python3 transcript.py --self-test

Exit codes: 0 written; 1 a required file is missing, a file has the wrong extension or an unknown
name, a folder sits in the scratch folder, a file is empty, or --out is inside --scratch (nothing
written); 2 usage error.
"""

import argparse
import re
import sys
from pathlib import Path

# Names are matched ignoring case; section IDs use upper-case role letters.
NAME = re.compile(r'^(?:(main-clauses)|([ECFB])(\d*)|(A)(\d+)-(.+)|(D)(\d*))\.md$', re.I)
ORDER = {'main': 0, 'E': 1, 'C': 2, 'A': 3, 'F': 4, 'B': 5, 'D': 6}
SCOPE = {'E': 'test case index', 'C': 'seam to code map', 'F': 'cross-cutting, OWASP per journey, tier check',
         'B': 'overlap', 'D': 'verification'}
REQUIRED = ('main', 'E', 'C', 'A', 'F', 'B')


def parse(name):
    """(order key, heading) for a scratch file name, or None when it doesn't follow the convention."""
    m = NAME.match(name)
    if not m:
        return None
    if m.group(1):
        return (0, 0), 'main', 'Main — clauses'
    letter = (m.group(2) or m.group(4) or m.group(7)).upper()
    number = m.group(3) or m.group(5) or m.group(8) or ''
    scope = m.group(6) if letter == 'A' else SCOPE[letter]
    if letter in 'CF' and number:
        return None
    return (ORDER[letter], int(number or 0)), letter, f'Subagent {letter}{number} — {scope}'


def fenced(text):
    """The file verbatim, inside a backtick fence longer than any backtick run in it, so nothing inside can
    close the fence or turn into a transcript heading."""
    longest = max((len(run) for run in re.findall(r'`+', text)), default=0)
    fence = '`' * max(3, longest + 1)
    return f'{fence}markdown\n{text.rstrip()}\n{fence}'


def build(scratch):
    scratch = Path(scratch)
    if not scratch.is_dir():
        raise ValueError(f'{scratch} is not a folder')
    parts, problems = [], []
    for path in sorted(scratch.iterdir()):
        if path.name.startswith('.'):
            continue
        if path.is_dir():
            problems.append(f'{path.name}: a folder, not a scratch file')
            continue
        if path.suffix.lower() != '.md':
            known = parse(path.stem + '.md')
            problems.append(f'{path.name}: wrong extension, expected {path.stem}.md' if known
                            else f'{path.name}: not a scratch file name (see transcript.py)')
            continue
        parsed = parse(path.name)
        if not parsed:
            problems.append(f'{path.name}: not a scratch file name (see transcript.py)')
            continue
        text = path.read_text(encoding='utf-8-sig')
        if not text.strip():
            problems.append(f'{path.name}: empty')
        parts.append((parsed, text))
    keys = [(letter, key) for (key, letter, _), _ in parts]
    problems += [f'two scratch files are {letter}{key[1] or ""}' for letter, key in set(keys) if keys.count((letter, key)) > 1]
    for letter in 'EBD':
        numbers = [key[1] for l, key in keys if l == letter]
        if 0 in numbers and len(numbers) > 1:
            problems.append(f'{letter}.md and numbered {letter}<n>.md files together; keep one naming')
    present = {letter for (_, letter, _), _ in parts}
    problems += [f'missing {"main-clauses.md" if r == "main" else r + " output"}' for r in REQUIRED if r not in present]
    if problems:
        raise ValueError('; '.join(problems))
    parts.sort(key=lambda p: p[0][0])
    return '\n\n'.join(f'## {heading}\n\n{fenced(text)}' for (_, _, heading), text in parts) + '\n'


def main(argv):
    parser = argparse.ArgumentParser(prog='transcript.py')
    parser.add_argument('--scratch', required=True)
    parser.add_argument('--out', required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code
    try:
        if Path(args.out).resolve().is_relative_to(Path(args.scratch).resolve()):
            raise ValueError(f'--out {args.out} is inside --scratch; write it next to the report')
        text = build(args.scratch)
    except (OSError, ValueError) as e:
        print(f'Error: {e}; nothing written', file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf-8')
    print(f'Wrote {out}')
    return 0


def _self_test():
    import tempfile
    import unittest

    class TranscriptTest(unittest.TestCase):
        def setUp(self):
            self._tmp = tempfile.TemporaryDirectory()
            self.dir = Path(self._tmp.name)
            for name, text in {
                'main-clauses.md': '- CL-001 requirement: login rejects bad passwords\n',
                'E.md': '# Test case index\n\n| test case | seam |\n',
                'C.md': '## Seam map\n\n/login -> SecurityController\n',
                'A2-timesheet.md': '# Area timesheet\n\nA2-001 Error\n',
                'A1-auth.md': '# Area auth\n\n```md\n# not a heading inside a fence\n```\n',
                'F.md': 'cross-cutting\n',
                'B.md': 'overlap\n',
                'D10.md': 'verdicts 10\n',
                'D2.md': 'verdicts 2\n',
            }.items():
                (self.dir / name).write_text(text, encoding='utf-8')
            self._out_tmp = tempfile.TemporaryDirectory()
            self.out = Path(self._out_tmp.name) / 'out' / 'transcript.md'

        def tearDown(self):
            self._tmp.cleanup()
            self._out_tmp.cleanup()

        def run_cli(self):
            return main(['--scratch', str(self.dir), '--out', str(self.out)])

        def sections(self):
            return [l for l in self.out.read_text(encoding='utf-8').splitlines()
                    if l.startswith(('## Subagent ', '## Main — '))]

        def test_sections_in_run_order(self):
            self.assertEqual(self.run_cli(), 0)
            self.assertEqual(self.sections(), [
                '## Main — clauses',
                '## Subagent E — test case index',
                '## Subagent C — seam to code map',
                '## Subagent A1 — auth',
                '## Subagent A2 — timesheet',
                '## Subagent F — cross-cutting, OWASP per journey, tier check',
                '## Subagent B — overlap',
                '## Subagent D2 — verification',
                '## Subagent D10 — verification',
            ])

        def test_each_file_is_kept_verbatim_in_a_fence_it_cannot_escape(self):
            tricky = ('# Area auth\n\n- step\n  ```php\n  $a = 1;\n## Findings\n  ## indented\n\n'
                      'Title\n===\n\n````md\n```\nnested\n```\n````\n\n```x``` inline\n')
            (self.dir / 'A1-auth.md').write_text(tricky, encoding='utf-8')
            (self.dir / 'E.md').write_text('# Test case index\n', encoding='utf-8-sig')
            self.assertEqual(self.run_cli(), 0)
            text = self.out.read_text(encoding='utf-8')
            self.assertEqual(len(self.sections()), 9, 'every file keeps its own section')
            body = text[text.index('## Subagent A1 — auth'):text.index('## Subagent A2')]
            opener = body.splitlines()[2]
            self.assertTrue(opener.startswith('`````') and opener.endswith('markdown'), opener)
            fence = opener[:-len('markdown')]
            self.assertIn(f'\n{fence}markdown\n{tricky.rstrip()}\n{fence}\n', text)
            self.assertIn('\n```markdown\n# Test case index\n```\n', text)   # BOM dropped, shortest fence
            self.assertNotIn('\ufeff', text)

        def test_run_with_no_finding_to_re_verify_has_no_D(self):
            (self.dir / 'D10.md').unlink()
            (self.dir / 'D2.md').unlink()
            self.assertEqual(self.run_cli(), 0)
            self.assertEqual(self.sections()[-1], '## Subagent B — overlap')

        def test_batched_index_and_overlap(self):
            (self.dir / 'E.md').rename(self.dir / 'E1.md')
            (self.dir / 'E2.md').write_text('more index\n', encoding='utf-8')
            (self.dir / 'B.md').rename(self.dir / 'B1.md')
            self.assertEqual(self.run_cli(), 0)
            self.assertIn('## Subagent E2 — test case index', self.sections())
            self.assertIn('## Subagent B1 — overlap', self.sections())

        def test_missing_unknown_or_empty_files_write_nothing(self):
            for broken in ('missing C', 'no area', 'unknown name', 'empty file'):
                with self.subTest(broken=broken):
                    self.tearDown(); self.setUp()
                    if broken == 'missing C':
                        (self.dir / 'C.md').unlink()
                    elif broken == 'no area':
                        (self.dir / 'A1-auth.md').unlink(); (self.dir / 'A2-timesheet.md').unlink()
                    elif broken == 'unknown name':
                        (self.dir / 'notes.md').write_text('stray\n', encoding='utf-8')
                    else:
                        (self.dir / 'F.md').write_text('  \n', encoding='utf-8')
                    self.assertEqual(self.run_cli(), 1)
                    self.assertFalse(self.out.exists())

        def test_duplicate_and_more_missing_or_unknown_files(self):
            for broken in ('A1 twice', 'E and E1', 'missing F', 'missing B', 'C1.md'):
                with self.subTest(broken=broken):
                    self.tearDown(); self.setUp()
                    if broken == 'A1 twice':
                        (self.dir / 'A1-login.md').write_text('x\n', encoding='utf-8')
                    elif broken == 'E and E1':
                        (self.dir / 'E1.md').write_text('x\n', encoding='utf-8')
                    elif broken == 'missing F':
                        (self.dir / 'F.md').unlink()
                    elif broken == 'missing B':
                        (self.dir / 'B.md').unlink()
                    else:
                        (self.dir / 'C1.md').write_text('x\n', encoding='utf-8')
                    self.assertEqual(self.run_cli(), 1)
                    self.assertFalse(self.out.exists())

        def test_names_ignore_case(self):
            for old, new in (('E.md', 'e.MD'), ('main-clauses.md', 'MAIN-CLAUSES.md'), ('A1-auth.md', 'a1-Auth.Md')):
                (self.dir / old).rename(self.dir / new)
            self.assertEqual(self.run_cli(), 0)
            sections = self.sections()
            self.assertIn('## Main — clauses', sections)
            self.assertIn('## Subagent E — test case index', sections)
            self.assertIn('## Subagent A1 — Auth', sections)

        def test_same_name_in_two_cases_is_a_duplicate(self):
            (self.dir / 'f.md').write_text('again\n', encoding='utf-8')
            if len(list(self.dir.iterdir())) != 10:
                self.skipTest('case-insensitive file system keeps one name')
            self.assertEqual(self.run_cli(), 1)

        def test_single_unnumbered_d(self):
            (self.dir / 'D10.md').unlink()
            (self.dir / 'D2.md').rename(self.dir / 'D.md')
            self.assertEqual(self.run_cli(), 0)
            self.assertIn('## Subagent D — verification', self.sections())
            (self.dir / 'D1.md').write_text('x\n', encoding='utf-8')
            self.out.unlink()
            self.assertEqual(self.run_cli(), 1)
            self.assertFalse(self.out.exists())

        def test_dotfiles_are_ignored(self):
            (self.dir / '.DS_Store').write_bytes(b'\x00\x01')
            self.assertEqual(self.run_cli(), 0)

        def test_out_inside_scratch_is_rejected(self):
            inside = self.dir / 'transcript.md'
            self.assertEqual(main(['--scratch', str(self.dir), '--out', str(inside)]), 1)
            self.assertFalse(inside.exists())

        def test_wrong_extension_is_named(self):
            for name, expected in (('D3.txt', 'D3.txt: wrong extension, expected D3.md'),
                                   ('A3-reports.txt', 'A3-reports.txt: wrong extension, expected A3-reports.md')):
                with self.subTest(name=name):
                    self.tearDown(); self.setUp()
                    (self.dir / name).write_text('lost evidence\n', encoding='utf-8')
                    import io, contextlib
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        self.assertEqual(self.run_cli(), 1)
                    self.assertIn(expected, err.getvalue())
                    self.assertFalse(self.out.exists())

        def test_usage(self):
            self.assertEqual(main([]), 2)
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['-h']), 0)
            self.assertEqual(main(['--scratch', str(self.dir / 'absent'), '--out', str(self.out)]), 1)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TranscriptTest)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    if sys.argv[1:] == ['--self-test']:
        sys.exit(_self_test())
    sys.exit(main(sys.argv[1:]))
