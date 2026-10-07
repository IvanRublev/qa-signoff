---
name: qa-review-test-cases
description: Validate a QA test case backlog is mutually exclusive and collectively exhaustive against its qa-spec.md and the app code it maps to; needs the app's source code, and writes a report file plus a transcript file next to qa-spec.md. Use after qa-write-test-cases, before treating the backlog as ready, or when asked to review, audit, or check QA test cases for coverage gaps or overlap.
copyright: Ivan Rublev 2026
license: Apache-2.0
version: 0.2.2
---

# Review QA test cases

Requires the `qa-write-spec` and `qa-write-test-cases` skills in the same parent folder as this skill.

Two-axis review, code-review style: **Coverage** (qa-spec.md → code → test cases) and **Overlap** (test case → test case), reported side by side, never merged or reranked; the report's Top 3 is the one sanctioned cross-axis view. Report-only — this skill never edits qa-spec.md, the backlog, or app code.

Read [`references/terms.md`](references/terms.md) before Step 1 — Page, Seam, Behavior, Covered, Product smell, Security test case, Named journey, Security findings, and In-scope role are used everywhere below and in every subagent prompt. Read [`references/finding-format.md`](references/finding-format.md) before emitting any finding — it defines what every finding carries and how to classify it (Step 1.9).

**Running scripts:** `<skill dir>` is this skill's base directory, the folder holding this SKILL.md (the path this file was opened from, without `SKILL.md`; when that path is unknown, the folder a file search for `qa-review-test-cases/SKILL.md` finds). Run every command from the test project root, so data paths like `qa-spec.md` resolve there.

## Inputs

- `qa-spec.md` (from `qa-write-spec`) — scope authority for seams and roles, plus the explicit requirements in its Role differences, Environment differences, Per-page test guidance, Cross-cutting checks, and Journeys sections.
- Test case backlog files (from `qa-write-test-cases`, TC-* headings) in its test cases folder — default `test-cases/` next to qa-spec.md. Only the test cases are read.
- Playwright config at the test project root; `<tests root>` for the Test file check (Step 1.2) is the `tests root:` line that Step 0.3's config check prints.
- App code path — required, explicit. The app's source may live in a different repo than the spec and test cases. Detail/ground-truth authority, scoped by qa-spec.md.

## Execution layout

Main orchestrates; everything else runs in a fresh subagent with a self-contained prompt (input paths, the run's scratch folder and this subagent's scratch file name, app code path, role mapping, the relevant slice of seams/clauses/C's seam map, E's index where needed, for A and F the `qa-write-test-cases` OWASP checklist (step 4), for D only the `qa-write-test-cases` sections its batch's findings cite, `references/terms.md`, `references/finding-format.md`, and the subagent's own rules, all pasted in full). Each subagent writes its full output to a per-run scratch directory, named by its role — `E.md` (or `E1.md`, `E2.md` per backlog batch), `C.md`, `A<n>-<area>.md`, `F.md`, `B.md` (or `B<n>.md`), `D.md` (or `D<n>.md` per batch); Main writes its clause list, every one of its own `M-` findings from Step 0 through Step 4 (OWASP TARGET MISSED and confirmed scope creep included), and its Step 4 dedup merge record and `PS-NN` assignment to `main-clauses.md` — and returns a short summary plus the file path (Step 5 gathers these files into the transcript); it never edits qa-spec.md, the backlog, or app code.

| Step | Runs in | Why |
|---|---|---|
| 0 — locate inputs, fail fast, lint the spec, check the Playwright config, map roles, declare unverifiable, ask about the app CLI, create the scratch folder | **Main** | Bad input must fail before any subagent spawns; role mapping feeds every subagent. |
| 1.1 — split qa-spec.md into clauses, tags, exclusions | **Main** | Cheap, and every subagent prompt needs it. |
| 1.2 — test case index | **Subagent E (fresh)** | Reads the whole backlog once; one shared mapping for A, B, F. Above ~60k tokens of backlog, one E per batch and Main concatenates the parts; a batch is a group of test case `.md` files made of whole `todo.md` Feature groups, each under ~60k tokens (a larger Feature group is a batch of its own). |
| 1.3 — seam → code resolution, and code → spec Warnings (Step 2) | **Subagent C (fresh, parallel with E)** | One owner for the page/action definition: C builds the route-to-page map, resolves each seam to its entry points, and reports pages and roles the spec lacks. A receives only the in-scope slice of the map. |
| Area assignment | **Main** | Groups seams for A using E's index and C's map. |
| 1.4–1.9 — Coverage per seam, OWASP per seam | **Subagents A (fresh, one per area)** | Heavy code reading; one area per subagent keeps each context small. |
| Cross-cutting clauses, OWASP per journey, tier check | **Subagent F (fresh)** | Concerns spanning seams or journeys get one owner. |
| 3 — Overlap axis | **Subagent B (fresh)** | Reads the backlog files plus E's index; no code, no spec prose. Above ~60k tokens of backlog, one B per batch (as for E), each reaching other files through E's index and grep. |
| Dedup pass, scope-creep confirmation | **Main** | After A and F return: merge duplicate findings and Product smells within the Coverage axis; confirm E's scope-creep candidates. |
| Verification of the high-stakes findings above confidence 4: Blockers, EXPECTATION WRONG, Security findings, CONFIG / PROJECTS / TEST FILE MISMATCH | **Subagents D (fresh, batches)** | Independent re-check where a wrong finding costs most (Step 4). |
| 5 — report | **Main** | Aggregate per axis, apply D's verdicts, levels, and confidences, label every other finding "not re-verified"; write the report file. |

**Order:** E and C in parallel → Main assigns areas → A (per area), B, F in parallel → Main dedup pass and scope-creep confirmation → D (per batch) → Main writes the report.

**Return formats** (the scratch file's content; every finding and Product smell in the form of `references/finding-format.md`):
- **E** — the test case index, one table row per test case: ID | Title | seam(s)×role(s) | lead/helper per role | attributes, verbatim | OWASP category (by substance, or —). Then its Errors and Warnings, and the scope-creep candidates.
- **C** — the route map, one table row per seam or sub-seam: seam | entry points (page handler, then every action it triggers) | note (served by another seam's handler, split into sub-seams, or "seam has no code" with its Error ID). Then its Warnings (Step 2), coverage-limited ones first.
- **A** — one `### <seam ID> <path>` section per seam or sub-seam of its area: behaviors, one row each: behavior | role(s) | quote | covering test cases or "none"; clauses: clause ID | covering test cases or uncovered part; depth per in-scope role and the seam's rating (Step 1.8); edge cases: edge case | applies (or reason not) | covering test cases; untraced dependencies; findings and Product smells. After the seams, its OWASP table: one row per seam, in the report's OWASP applicability shape (`references/report-template.md`).
- **F** — clauses: clause ID | covering test cases or uncovered part, Cross-cutting layout clauses covered by environment projects marked so; its OWASP table: one row per named journey, in the report's OWASP applicability shape; tier check: one line per journey in the report's Journeys shape, or the "not checkable" line; then its findings and Product smells.
- **B** — one Overlap finding per test case pair, citing the rule and quoting both test cases' asserts; then its shared-state interference Warnings.

## Step 0 — Locate inputs and set up

1. **Inputs.** Find qa-spec.md at the test project root and the backlog in `test-cases/` next to it (the `qa-write-test-cases` test cases folder); ask the user when either isn't there. Require an explicit app code path; default to the current repo only when it contains the app's source. Fail fast if any input is missing: no qa-spec.md, or one without a Site Map section → run `qa-write-spec` first; no backlog, or no `TC-*` test case in it → run `qa-write-test-cases` first; a test case without a `**Feature:**` attribute → stop, naming the test cases, and re-run `qa-write-test-cases`; any line `python3 <skill dir>/../qa-write-test-cases/scripts/qa_tickets.py check <test cases folder>` prints other than a `stored hash … computed …` or `hash criterion names …` line (a `todo.md` problem, a template placeholder, a missing or invalid attribute, a heading ID not matching its filename) → stop, quoting those lines, and re-run `qa-write-test-cases`; the two hash kinds are the grouped Warning of Step 1.2; no app code → stop, this skill needs source access.
2. **Spec lint.** Run `python3 <skill dir>/../qa-write-spec/scripts/qa_spec.py qa-spec.md`: exit 3 → stop and ask the user to fix the file; exit 1 or 2 → report each `defect` line as the spec Error **SPEC LINT**, each `excluded-page` line as EXCLUDED PAGE IN JOURNEY, and each `warning` line as the Warning **spec lint warning** (`references/finding-format.md`).
3. **Config check.** Run `python3 <skill dir>/../qa-write-test-cases/scripts/qa_projects.py check-config --spec qa-spec.md --project-dir .`. Fail fast when it prints an `Error:` line or no `tests root:` line: a header error → run `qa-write-spec` first; anything else (no `npx`, config fails to load) → stop and ask the user to fix the Playwright config. Report each `CONFIG:` line as the spec/config Error **CONFIG MISMATCH** (`references/finding-format.md`). Record the `tests root:` value; E's prompt carries it.
4. **Role mapping.** Read the app's role→permission config statically, then map each in-scope role to the lowest code role whose permissions cover every Site Map seam that spec role reached; ask when that doesn't settle it. `no-login` maps to anonymous access and needs no code role. Any other in-scope role with no code role is a spec Error; a deferred role (Terms) gets one Warning and no mapping. Record the mapping in the report header.
5. **Unverifiable.** Declared defaults — in project config or the framework — are CODE-VERIFIED. A branch on environment state (network, filesystem, run mode) is a normal behavior, CODE-VERIFIED when quoted. Only runtime overrides of declared defaults (settings or permissions changed through an admin UI or database) are unverifiable; note that caveat once in the report header. Findings that depend only on runtime-resolved facts are INFERRED and never Blockers or Errors.

6. **App CLI.** When the stack offers a resolved route listing (Step 2.1), ask the user whether running the app's CLI is allowed; C's prompt carries the answer.
7. **Scratch folder.** Create a fresh, empty folder for this run, e.g. `qa-review-test-cases-<date>-<time>/` in the session scratchpad — never a shared folder, since `transcript.py` (Step 5) rejects anything else there — other files, wrong extensions, subfolders. Every subagent prompt carries its path.

Any fail-fast stop in this Step still writes the report (Step 5) next to qa-spec.md before stopping, holding whatever findings Step 0 found so far (at minimum the one that triggered the stop) — the user fixes the input and re-runs, so Step 0's own findings aren't lost. Skip the transcript: no subagent has run yet.

## Step 1 — Coverage axis (qa-spec.md → code → test cases)

1. **Parse qa-spec.md** (Main). Split every guidance paragraph, Role-differences fact, Environment-differences fact, Cross-cutting check, and Journeys entry into atomic clauses with IDs. For each clause record:
   - its tag (an Environment-differences fact is always a **requirement**; Terms, Covered): **requirement** (asks for an outcome to be verified), **conditional** (applies only under a stated condition; "holds: yes / no / unknown"), **deferred** (the spec itself defers it), **note** (context, never checked), or **exclusion** (e.g. "do not install…", or any page, journey, or check the user marked `Excluded: <reason>`), extracted from any section;
   - its quantifier: every / one representative / named examples only. "Especially" and "e.g." lists bind only the seams they name;
   - its explicit seam list.

   A Journeys entry gets the tag **journey** instead: it is checked only by F's tier check and OWASP per journey, never by Step 1.4.

   A page marked `Excluded:` under its Per-page test guidance heading and in the chain of a named journey is the spec Error **EXCLUDED PAGE IN JOURNEY** (`references/finding-format.md`); Step 0.2's lint already reports pages marked on their Site Map route line.

   Scope (in/out) comes only from qa-spec.md — seams and roles. The report lists every clause with its tag.
2. **Index the backlog** (Subagent E; Return formats). Per test case: seam(s)×role(s) derived from its **Act and acceptance criteria**, not from Feature or What to build; the test case attributes (`qa-write-test-cases` "Write each test case self-contained") verbatim, `**Projects:**` and `**Test file:**` included; OWASP category by substance. Run `python3 <skill dir>/../qa-write-test-cases/scripts/qa_projects.py check-test-cases --spec <qa-spec.md> --tests-root <tests root> <test cases folder>`, with the tests root from Step 0.3, and report each line it prints as that Error, **PROJECTS MISMATCH** or **TEST FILE MISMATCH**. By hand, judge only a test case whose Projects lists some but not all of its lead role's environments: when that subset isn't the one the `qa-write-test-cases` Environment split gives it, report PROJECTS MISMATCH. Mark each role use as lead or helper. Flag as scope-creep candidates the test cases whose lead role is not an in-scope role; Main confirms scope creep (Warning) after A returns, for candidates no A matched to an in-scope behavior. Report as Warnings: test cases whose seam or role can't be determined (partial unmappability, stating what is undetermined); asserts whose outcome depends on the current date or time (relative-date presets, "today", time zones, throttle windows) without a pinned date/time in Arrange; one grouped Warning listing asserts that need human judgment to pass or fail ("plausible", "looks right", "doesn't break layout", "as expected") with no observable criterion, so they can't be automated as written; one grouped Warning listing test cases whose stored criteria hash (in the `Output test file contains comment` criterion) is missing or differs from the recomputed one, as `python3 <skill dir>/../qa-write-test-cases/scripts/qa_tickets.py check <test cases folder>` lists them: each `stored hash <stored or missing>, computed <hash>` line with both values, and each `hash criterion names <ID or None>, not <Test case ID>` line, for a test case whose hash criterion is missing or names another test case.
3. **Resolve seams to code** (Subagent C, see Step 2 for its Warnings; Return formats). For each Site Map seam: its entry points (page handler and every action it triggers, whatever the path), recorded in the report. A seam no handler serves → spec Error "seam has no code". A seam served by another seam's handler → note it; Main gives that handler to one area. A seam made of independent forms or tabs → split into sub-seams.

   **Area assignment** (Main): each seam or sub-seam goes to exactly one A. Area = the Feature value with the highest weighted count among the seam's test cases, each test case weighted 1/(number of seams it maps to); a seam with no test cases falls back to its first route segment. Merge the smallest areas until each has at least 3 seams or 15 test cases, with at most 8 A runs.
4. **Check clauses against test cases** (A for per-page, Role-differences, and Environment-differences clauses on the seams of its area; F for Cross-cutting clauses). Every requirement clause, and every conditional clause whose condition holds, must be covered by a test case or a set of test cases. A partly covered clause reports the uncovered part. A non-security clause the code contradicts is a Product smell (code is the truth), and coverage is then checked against the code's behavior, not the clause. A clause naming a feature the code lacks is a spec Error, like "seam has no code". A security clause the code contradicts is APP FAILS SECURITY TEST CASE when a test case asserts it, otherwise INSECURE BEHAVIOR, no test case. A Cross-cutting clause about layout across screen sizes or browsers is covered by the environment projects when every environment it names is in the spec's `Environments:` line — F lists it under Environment coverage, never as a missing test case; an environment it names that `Environments:` lacks is its uncovered part.
5. **Check the OWASP rule** (A per seam, F per named journey; `qa-write-test-cases` OWASP checklist). Use the checklist's categories, each with its "applies when" line, as the fixed category list. Record applicability **per threat** within each category (e.g. cross-site request forgery on state-changing forms), with evidence, as a seam×category table each A/F returns in full (Execution layout, Return formats). Test cases match by the substance of their Act and assertions, not their label; a mislabelled test case still counts and the report notes the label. An app-wide test case counts only for the seams its Act actually visits. A protection enabled once in config needs one test case proving it on a representative surface, not one per surface. Helper-role test cases count. Main merges every A/F table into the report's OWASP applicability section verbatim, marking every APP FAILS cell 🔴, every untested-surface cell 🟠, and every no-test-case A09 logging-gap cell 🔘, then appends a flag-count-by-category table totaling each marker (report-template.md). Under that table Main states OWASP tested coverage: tested categories over applicable categories, with A08 never applicable. A category is applicable when at least one of its cells is not n/a, and tested when at least one of its cells is ✔ or 🔴. Below the `qa-write-test-cases` OWASP target, report the Error **OWASP TARGET MISSED**, listing the applicable categories that are not tested. Section placement, the Security Blockers / Security Errors copies, the Completion summary's first bullet, and the Top 3 split follow [`references/report-template.md`](references/report-template.md).
6. **Trace each in-scope seam's code** (A; Return formats), starting from the entry points C resolved: where input comes from, what validates or transforms it (including validation declared away from the handler), where it goes, every conditional branch, permission/role check, and error path.

   **Trace boundary and budget:** trace project code only; stop at framework, vendor, and library calls — their configuration in project code is the evidence. Trace in priority order: handler → service → validation → templates. Code not traced is listed per seam as "untraced dependency" or "untraced (budget)". A feature that is off by default is not traced as if on: A lists it under NOT in scope; C owns its Warning (Step 2.3).

   If C found no code for a seam, check it against its clauses only (spec Error already raised).

   **Conflicting code paths:** when two code paths act on the same input with opposing effects (one switches an option on, another switches it off), classify the conflict:
   - **deterministic** — one path always wins (e.g. by execution order): each path needs a test case using an input that triggers it alone, plus one test case asserting the actual final outcome for the conflicting input; uncovered ones are Errors. Also a Product smell.
   - **non-deterministic** — the winner depends on timing or data order: a Product smell only; no test case is expected, since any test case would be flaky. An existing test case asserting a winner → Warning "flaky by design", listed with the smell.

   **Product smells:** A and F record every smell they find (Terms) with the code quoted, plus the spec clause or the conflicting path when the smell type has a second side, and list the test cases that pin the behavior or should.

   **Insecure behavior:** security behavior (Terms) the code gets wrong with no test case asserting the secure outcome → INSECURE BEHAVIOR, no test case (Step 1.9 in `references/finding-format.md`).
7. **Derive edge cases per seam** (A): double-submit, navigate away mid-operation, stale data / expired session, concurrent actions, empty / minimum / maximum / one-past-maximum input, user-visible error states, auth boundaries. An edge case applies only when it has an observable consequence; record non-applicable edge cases with a reason. Look for a guard only on this seam's own request path (server handler and page front-end code); a library guard counts when project code enables or configures it. A **present guard** is itself a behavior: its user-visible effect needs a test case. A **missing guard** with an observable consequence is a behavior gap, quoted as proof of absence (CODE-VERIFIED), or EDGE-CASE when no code is involved.
8. **Match and rate depth** per seam×role, taking each test case's angle from its asserted outcomes, not its Type label, and counting only test cases for in-scope roles or helper uses:
   - ★★★ — Functional + Boundary + Negative present;
   - ★★ — any two of the three;
   - ★ — any one of the three;
   - ☆ — none (zero test cases).

   A seam's rating is the lowest over its in-scope roles.

   The COVERAGE denominator counts code behaviors only; clauses, edge cases, and OWASP are counted separately.

   A reports CONTRADICTED, EXPECTATION WRONG, HEDGED ASSERT, and APP FAILS SECURITY TEST CASE for every test case it matches on its seams; F does the same for Journey-tier test cases, reading code along the journey's seams.
9. **Classify.** Read [`references/finding-format.md`](references/finding-format.md) — full Blocker / Error / Warning rules and precedence.

## Step 2 — Code → spec Warnings (Subagent C)

1. Take the framework's resolved route listing when the stack offers one and Step 0 allowed running the app's CLI; C never asks the user. Otherwise search route, permission, and role definitions statically, including routes declared only in config.
2. Fold every action into the page that triggers it (Terms). "Other mode" means only routes that no in-scope page calls.
3. Diff pages against the Site Map, role mapping, and exclusions:
   - a page missing from the Site Map → Warning, one per user flow (not per result page or wizard step); if guidance clauses name the page, the fix is "add to Site Map", otherwise "confirm intentional exclusion — mark the page `Excluded: <reason>` (`qa-write-spec` Exclusion grammar) if so";
   - an action no page triggers → Warning;
   - default-off routes → one grouped Warning noting the default;
   - dev and debug routes → excluded unless the spec mentions them;
   - global chrome present on every page (navbar widgets, favorites) → one pseudo-seam "every page";
   - other-mode routes → one grouped Warning with an approximate count and path pattern;
   - code roles no spec role maps to → the "coverage limited" Warnings (first in the list), quoting the role→permission map.
4. A page missing from the Site Map never gets A-level findings.

## Step 3 — Overlap axis (Subagent B)

Read the backlog files; use E's index only for seam identity. Compare within seam and Feature groups. Definitions:

- **Angle** — the kind of asserted outcome (functional, boundary, negative, security, performance), taken from assertions, not the Type label.
- **Arrange equivalence** — same roles, same data shape, same prior state.
- **Overlap** — checked per assert; one test case's assert set contained in another's counts.
- **Entry point** — how the user reaches a component; a render surface is not an entry point.

Rules (all Errors):
1. A Security or Performance check merged with another angle, in either direction; several OWASP categories in one test case.
2. One test case holding checks that need different Arranges, whether the angles differ or not.
3. A component reached from multiple entry points not split one test case per entry point.
4. Duplicate or subset coverage on seam + role + angle + Arrange + OWASP category (category for security test cases only, Terms).

Exemptions: parent/child journey re-checks; a control actor needed to attribute an absence check; test cases whose lead role is out of scope.

Warning: **shared-state interference** — test cases that mutate global state (settings, permissions, throttling, lockout) without a run-alone or ordering constraint, naming the test cases whose outcome they can change.

## Step 4 — Dedup and verification

**Dedup** (Main, after A and F): "no merge" governs the two axes, not duplicates within an axis. Key Coverage findings on their fingerprint (quoted code location + behavior); keep one finding listing every seam and every reporting subagent. Key priority-below-risk Warnings on test case ID. Merge Product smells on quoted code location the same way, then assign `PS-NN` IDs. Confirm scope creep for E's candidates.

**Verification** (Subagents D): re-verify only the high-stakes findings — every Blocker and every Error marked "verify — possible Blocker", every EXPECTATION WRONG, every Security finding (Terms), and every CONFIG MISMATCH, PROJECTS MISMATCH, and TEST FILE MISMATCH; skip findings at confidence ≤4. Every other finding and Product smell goes into the report unverified, labelled "not re-verified". Batches of about 30 findings. D's inputs: `references/terms.md`, `references/finding-format.md`, the clause list with tags, E's index, the full text of the test cases its batch's findings cite plus grep access to the backlog files, C's route map, the merged OWASP table when the batch holds OWASP TARGET MISSED, only the `qa-write-test-cases` sections its batch's findings cite (such as the OWASP checklist and target, the Priority scale, the Projects rule, and the Test file rule), qa-spec.md, and the app code.
- Coverage finding (a Blocker, a possible Blocker, or a missing OWASP test case): re-locate the quote, grep the backlog for covering Act/assert lines, check the level.
- EXPECTATION WRONG: try to disprove it — re-locate the code, repeat the search for another code path producing the test case's outcome, check whether the test case's Arrange sets a runtime-read setting, and check declared defaults. CONFIRMED only at confidence ≥7; otherwise it becomes the Warning "possible test case mismatch — verify at runtime".
- HEDGED ASSERT on a security test case: re-read the assert and confirm that the secure branch is the one to keep.
- APP FAILS SECURITY TEST CASE and INSECURE BEHAVIOR, no test case: re-locate the code and confirm the protection is absent on the path (including framework-level protection enabled in config); for INSECURE BEHAVIOR, also grep the backlog for a test case asserting the secure outcome.
- OWASP TARGET MISSED: recount the applicable and tested categories in the merged OWASP table (Step 1.5) and compare them with the `qa-write-test-cases` OWASP target.
- CONFIG MISMATCH: re-run Step 0.3's config check.
- PROJECTS MISMATCH, TEST FILE MISMATCH: re-read the test case's attributes and Test file rules block against qa-spec.md's header, its Environment differences, and the `qa-write-test-cases` Projects rule and Test file rule.

D returns per finding: verdict (CONFIRMED / UNCERTAIN = "D could not settle it" / REFUTED), level (kept or changed, citing the rule), final confidence. Main applies all three: CONFIRMED raises confidence to at least 7; UNCERTAIN caps it at 6; REFUTED moves the finding to the appendix. Main then re-applies the confidence gates from `references/finding-format.md`: a CONFIRMED "verify — possible Blocker" becomes a Blocker; a Blocker capped at 6 becomes an Error marked "verify — possible Blocker". Every finding and Product smell D did not see keeps the level and confidence its subagent gave it, and the report labels it "not re-verified". Finally Main recomputes the COVERAGE counts (Terms, Covered).

## Step 5 — Report

Read [`references/report-template.md`](references/report-template.md) for the exact structure and fill every section — an empty one says "No issues found" rather than being omitted. The Errors section lists every surviving Error, one line each. Never merge or rerank the two axes outside Top 3 (code-review precedent).

Then write the transcript, `qa-review-test-cases-transcript-<date>-<HHMM>.md`, next to the report: `python3 <skill dir>/scripts/transcript.py --scratch <run scratch dir> --out qa-review-test-cases-transcript-<date>-<HHMM>.md`. It puts Main's file first, then every subagent's full output, verbatim and in run order (E, C, each A, F, B, each D), one `## Subagent <letter><n> — <scope>` section each, the file verbatim inside a code fence; exit 1 names a missing, misnamed or empty scratch file and writes nothing — fix that file and run it again. The report cites it by section, never by scratch path, so both files together hold everything the run found.

Commit the two files: `git add -- <report> <transcript>`, `git commit -m "qa-review-test-cases: report"`. Add only these two paths; the skill stays report-only for qa-spec.md, the backlog and the app code.

The report's own "How to apply these findings" section carries the finding-type → action mapping, so it travels with the file. After saving, chat output ends with a **next step** proposal pointing at that section: hand the report, with its transcript, to an LLM to update the backlog. This is a proposal only — this skill stays report-only (Step 6) and never applies the fix itself.

## Step 6 — Report-only stance

Never edit qa-spec.md, the test cases, `todo.md`, or app code (qa-only precedent). Findings only. The user decides what is a deliberate exclusion versus a real gap and records exclusions in qa-spec.md (`qa-write-spec` Exclusion grammar).

## Support

If the user is stuck, hits a blocker, or finds a bug in this skill, follow [`support-banner.md`](support-banner.md).
