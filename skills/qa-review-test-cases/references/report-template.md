# Report template (Step 5)

Write `qa-review-test-cases-<date>-<HHMM>.md` next to qa-spec.md, and the transcript `qa-review-test-cases-transcript-<date>-<HHMM>.md` next to it (SKILL.md Step 5). Chat shows only the completion summary and both paths. Every axis and step reports a result; an empty one says "No issues found".

**OWASP applicability** (Main): the full seam×category table, merged verbatim from every area subagent's (and F's) own OWASP table — never summarized-away or left as "see subagent output"; each row cites its evidence test case(s). Sits as its own top-level section right after Completion summary, so security posture is visible immediately.

**Security Blockers / Security Errors** (Main): the Security findings (Terms), Blockers and Errors respectively, copied verbatim as `###` subsections of OWASP applicability, right after its Summary bullets and before the Flag count table. These duplicate entries that also stay in Blockers/Errors below — duplication is intentional, not an error.

**Not re-verified** (Main): Subagents D re-verify only the high-stakes findings (SKILL.md Step 4). Every other finding and Product smell carries the label `not re-verified` on every line that lists it — Top 3, Errors, Warnings, Overlap, and Product smells.

**Top 3 findings by category** is a fixed sort: all Blockers and Errors from both axes by level, then severity, then confidence; ties keep axis order (Coverage first). Split by category into two lists of 3 by the same sort: **Security** (Security Blockers/Errors pool, listed first) and **Regular** (non-security findings). Sits first, right after "How to apply these findings", before Completion summary.

```
# QA Test cases Review

| Field | Value |
|---|---|
| Date | ... |
| Branch / Commit | spec repo ...; app code ... |
| qa-spec.md | path (hash) |
| Backlog | path |
| App code | path |
| Role mapping | <spec role> → <code role>, …; deferred: <roles> |
| Runtime caveat | settings/permissions may be overridden at runtime; findings use declared defaults |

| Severity | Coverage Blockers | Coverage Errors | Coverage Warnings | Overlap |
|---|---|---|---|---|
| critical | N | N | N | N |
| high | N | N | N | N |
| medium | N | N | N | N |
| low | N | N | N | N |

Overlap severity rows are mapped by the higher Priority of the two test cases in each pair; note here if Overlap carries no Blockers/Errors.

## How to apply these findings
This report is read-only output — it never edited the backlog, qa-spec.md, or app code. To update the backlog from it (by hand or by handing this file and its transcript to an LLM), match each finding to an action:
- missing-test-case Blockers/Errors → write the test case for the quoted behavior;
- CONTRADICTED, EXPECTATION WRONG, HEDGED ASSERT → edit that test case's Arrange/Act/assert as the finding states;
- APP FAILS SECURITY TEST CASE, INSECURE BEHAVIOR (no test case) → the test case is correct or as proposed; file the app defect instead, don't edit the test case for it;
- Overlap findings → merge, split, or drop test cases per the cited rule;
- EXCLUDED PAGE IN JOURNEY, SPEC LINT → edit qa-spec.md, not the backlog, as the finding states;
- CONFIG MISMATCH → fix the Playwright config per `qa-write-test-cases` "Playwright config gate", then re-run `qa-write-test-cases`;
- Product smells → informational, no test case edit unless the user decides to pin the behavior;
- PROJECTS MISMATCH, TEST FILE MISMATCH → re-run `qa-write-test-cases`, which refreshes every test case's Projects, Test file, and Test file rules block; a test case that must be split per Environment differences entries needs its acceptance criteria edited and new test cases written, per `qa-write-test-cases` "Re-run over an existing backlog";
- any edit to a test case's How to build steps or acceptance criteria, and every stale criteria hash Warning → follow `qa-write-test-cases` "Re-run over an existing backlog", which says when to rehash and keep the marks and when to recompute and reset them; number new test cases and handle dropped ones by the same section;
- after all the edits are applied → commit them in one commit: `git add -- <edited paths>`, `git commit -m "qa-review-test-cases: apply review findings"`.

## Top 3 findings by category
The fixed sort above, split by category.

### Security
1. <ID> [Security level, severity, confidence] — <behavior>

### Regular
1. <ID> [level, severity, confidence<, not re-verified>] — <behavior>

## Completion summary
- Security: N APP-FAILS-SECURITY-TEST-CASE confirmed (see Security Errors); N Security Blockers, N Security Errors total   ← always first
- Product smells: N (N conflicting code paths, N non-deterministic)
- Environments: N environments; N PROJECTS MISMATCH, N TEST FILE MISMATCH; N Environment differences entries without a covering test case
- Coverage: N blockers, N errors, N warnings (N merged in dedup)
- Overlap: N findings
- Verification: N re-verified by D (N confirmed, N uncertain, N refuted, N level changes); N not re-verified
- Appendix-only (confidence ≤ 4 or refuted): N
- Worst issue per axis: Coverage — <Blockers, else Errors>; Overlap — <…>

## OWASP applicability
The seam × category table below has one row per seam (per named journey for F's rows) and one column per OWASP category; each cell lists that category's threats for the seam. Legend: 🔴 APP FAILS (test case asserts protection, code doesn't deliver it) · 🟠 untested (surface exists, no test case covers it) · 🔘 no test case (A09 logging gap). Every cell using one of these three markers must carry it — never leave a fail/gap cell as plain prose.

### Summary
- <bullet — dominant category / notable gap>

### Security Blockers
Blockers among the Security findings (Terms) — duplicated from Blockers below for visibility.
- <ID> [severity] (confidence N/10) [evidence] seam/role — insecure behavior, no test case — <file / function>: "<quote>" — fingerprint: <key>

### Security Errors
Errors among the Security findings (Terms) — duplicated from Errors below for visibility.
- <ID> [severity] (confidence N/10) [evidence] seam/role — <APP FAILS SECURITY TEST CASE / INSECURE BEHAVIOR, no test case / missing OWASP test case / OWASP TARGET MISSED / HEDGED ASSERT on a security test case> — <source> — fingerprint: <key>

### Flag count by category

| Category | 🔴 APP FAILS | 🟠 untested | 🔘 no test case |
|---|---|---|---|
| <category> | N | N | N |
| **Total** | **N** | **N** | **N** |

OWASP tested coverage: N/M applicable categories tested (N%), target per the `qa-write-test-cases` OWASP target: <met / missed — untested: <categories>>.

### Full seam × category table

| Seam | <category> | … |
|---|---|---|
| <seam> | ✔ <note> (<test case ID>) / n/a / — / 🔴 **APP FAILS** — <note> (<test case ID>) / 🟠 untested <note> / 🔘 no test case — <note> | … |

## Product smells
Current behavior the test cases pin but a user wouldn't expect. Read first; not counted toward coverage.

Total: N Product smells (N deterministic-conflict-linked, N non-deterministic).

- PS-01 (confidence N/10<, not re-verified>) [evidence] <smell type> — <behavior> — <file / function>: "<quote>" (spec: "<clause>" or conflicting path: "<quote>" when the smell has a second side) — pinned by: <test case IDs> / should be pinned by: <seam> — conflict: deterministic (linked Error <ID>) / non-deterministic (flaky by design: <test case IDs>) (conflicting paths only) — fingerprint: <key>

## Environment coverage
Environments (qa-spec.md): <profiles>. Projects per role: <role> → <projects>; `no-login` → <projects>.

- Test cases by Projects: every environment N; some but not all N
- Environment differences: <seam — role — breakpoint: environments> → <test case IDs> / none (Error <ID>)
- Cross-cutting layout clauses covered by environment projects: <clause ID> — <environments> / uncovered part: <environments missing from Environments>

## Blockers
- <ID> [severity] (confidence N/10) [evidence] seam/role — missing test case for <behavior> — <file / function>: "<quote>" — searched: <terms> — also matched: <rules> — fingerprint: <key>
- <ID> [severity] (confidence N/10) [evidence] seam/role — <test case ID, or none> — app fails security test case / insecure behavior, no test case (proposed assert: <secure outcome>) — <file / function>: "<quote>" — fingerprint: <key>

## Errors
Every Error that survives dedup and, when D re-verified it, verification, one line each, at its final level and confidence; an Error D did not see is labelled `not re-verified`. Full text and quotes are in the transcript, `qa-review-test-cases-transcript-<date>-<HHMM>.md`, in the section of whoever raised it (`## Main — clauses` for Main's `M-` findings, or `## Subagent E`, `C`, `A<n>` or `F`), findable by fingerprint; the transcript holds pre-verification levels, so this list is the one to act on.

Total: N Errors (after dedup).

- <ID> [severity] (confidence N/10<, not re-verified>) [evidence] seam/role — <missing behavior / clause / OWASP threat / CONTRADICTED / EXPECTATION WRONG (code does: …) / HEDGED ASSERT (keep: …) / APP FAILS SECURITY TEST CASE / INSECURE BEHAVIOR, no test case> — <source> — fingerprint: <key>

## Warnings
Coverage-axis Warnings; the always-first item flags a spec role/tier gap.

Total: N Warnings.

- Coverage limited: <role> not in qa-spec.md — N behaviors unchecked — not re-verified   ← always first
- <other Warning> — not re-verified, unless it is D's level change

## Overlap
### Errors (N)
<list, or No issues found>
- <ID> [severity] (confidence N/10, not re-verified) <test case A> / <test case B> — <rule> — <quoted asserts> — fingerprint: <key>

### Warnings: shared-state interference (N)
- <mutating test case> can change <affected test cases> — <state mutated> — not re-verified

## Coverage

### Journey/Interaction ratio
<ratio> Journey vs. <ratio> Interaction (excluding Security/Performance-substance test cases) — vs. the `qa-write-test-cases` Tier ratio.

### Journeys
<N> named journeys (Terms) tiered with at least one P0/P1 Journey-level test case; N tier-mismatch, N smoke-set-incomplete.

- <J-ID> <name> — Journey-level: <test case IDs> / none / Deferred (<reason>) / Excluded (<reason>)
- (or) not checkable — qa-spec.md has no Journeys section

### Seam → code map
Full detail in the transcript's `## Subagent C` section; summarized here — see per-seam entries under Coverage map below for test case linkage.
- <seam ID> <path> → <handler>, actions: <…>
- <seam ID> <path> → no code (spec Error <ID>)

### Condensed coverage map
Full per-behavior detail is in the transcript's `## Subagent A<n>` sections, findable by fingerprint.

**Coverage**: seams N/N resolved (N spec Errors)

**Behaviors covered**: N/M (after D verdicts)

**Depth**
- ★★★: N
- ★★: N
- ★: N
- ☆: N

#### By area

**<area name>** (<seams covered>) — N test cases, depth <☆/★/★★/★★★ mix>
- <ID> <CONTRADICTED / EXPECTATION WRONG / HEDGED ASSERT / missing OWASP test case / uncovered behavior>: <what and why>
- <ID> [UNTRACED] — untraced dependencies: <service / library call>

### Spec clause tags
Main parsed qa-spec.md's guidance sections into atomic clauses (Step 1.1); the full list with every tag is in the transcript's `## Main — clauses` section. Notable tags:
- <clause ID> <text> — requirement / conditional (holds: yes/no/unknown) / deferred / note / exclusion / journey — quantifier

## NOT in scope
- <seam / code area> — <why: exclusion, default-off, statically unverifiable, …>

## Appendix — low-confidence and refuted findings
```
