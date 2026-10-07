# Finding format and classification

Shared by every subagent (A, B, C, D, E, F) and Main. Read [`terms.md`](terms.md) first — Covered, Product smell, Security test case, Named journey, Security findings, and In-scope role are load-bearing here.

## Every finding carries

- **ID** — subagent prefix + number (e.g. `A3-012`, `C-007`), unique in the run. Main's own findings use prefix `M-`; a merged finding keeps the lowest source ID and lists the others; Product smells get `PS-NN` IDs from Main after dedup.
- **Fingerprint** — the dedup key printed verbatim: quoted code location + behavior, or test case ID + assert for test-case-level findings. Lets two runs be compared by hand.
- **Level** — Blocker / Error / Warning (below; Overlap rule findings are Errors).
- **Severity** — critical / high / medium / low = P0 / P1 / P2 / P3 of the `qa-write-test-cases` Priority scale, rated as the priority a test case for the behavior would get; always taken from the behavior, at every level.

  Findings that aren't a missing behavior: Overlap → the higher Priority of the two test cases; scope creep → low; missing page → by the page's purpose; CONTRADICTED, EXPECTATION WRONG, and HEDGED ASSERT → by the behavior the test case targets; APP FAILS SECURITY TEST CASE and INSECURE BEHAVIOR, no test case → by the security behavior; spec seam or spec role with no code → high; tier mismatch → high; CONFIG MISMATCH, PROJECTS MISMATCH and TEST FILE MISMATCH → high; smoke set incomplete → high; out-of-scope journey → low; every other non-behavior finding → medium.
- **Product smells** carry ID, Fingerprint, Confidence, Evidence, and Quote, but no Level or Severity. A deterministic conflict (Step 1.6) yields one Error plus one linked smell.
- **Confidence** — 1–10. 7+ shown normally; 5–6 shown with "verify"; 4 or lower appendix only. Subagents D re-verify only the high-stakes findings (SKILL.md Step 4); every other finding and Product smell keeps the confidence its subagent gave it, and the report labels it "not re-verified". A finding whose scope is uncertain carries a "scope?" flag instead of lowered confidence.
- **Evidence** — CODE-VERIFIED (code quoted), TEST-CASE-TEXT (test case lines quoted), SPEC-ONLY (qa-spec.md text), EDGE-CASE (edge case with no code involved), INFERRED (runtime-only).
- **Quote** — file, function/symbol, verbatim text. When a symbol is declared indirectly (routing or permission config, decorators, generated code, schema files), quote the declaring construct. For a missing guard, quote the handler and front-end code that should contain it. A whole-app absence may be proven by a documented search miss: the terms and locations searched.
- **Also matched** — other level rules this gap matched (Classify, below).

**Redaction:** never quote a secret value — write `[REDACTED]`. Never read environment/secret files; cite the setting's name only.

**Pre-emit verification gate:** a finding that claims a code fact but cannot quote the motivating code is unverified — confidence 5 (shown with "verify"). EDGE-CASE findings are exempt. Before reporting a missing test case, search the **full test case text** (not the index) for Act and assert lines covering the behavior, and list the search terms used in the finding.

## Classify (Step 1.9)

Report each gap once, under the highest level it matches, and list the other rules it matched under "Also matched". Each uncovered entry point to a destructive action (single, bulk, background call) is its own finding.

- **Blocker** — the backlog is not ready until this has a test case or, for APP FAILS SECURITY TEST CASE, until the app defect is acknowledged. Requires confidence ≥7; below that it becomes an Error marked "verify — possible Blocker".
  - an uncovered permission decision where an in-scope role gets the denied outcome, or two roles (in-scope or helper) get different outcomes. Allowed-only branches for the top role and denials based on entity state are Errors;
  - an uncovered destructive action;
  - an uncovered silent failure: the path is reachable through normal UI use, data is lost or wrong data is shown as correct, and there is no message. Intended guards, filters on by default, and triggers needing tampered input or an external outage are Errors.
- **Error**
  - any other uncovered behavior, including a present guard's effect;
  - an uncovered applicable edge case;
  - an uncovered or partly covered requirement clause;
  - a missing OWASP test case for an applicable threat;
  - **OWASP TARGET MISSED** — tested OWASP categories below the `qa-write-test-cases` OWASP target (Step 1.5); lists the applicable categories that are not tested;
  - **CONTRADICTED** — a test case whose Arrange, Act, or Cleanup can't execute (missing URL, payload rejected before the check, a role that can't perform its Cleanup); quotes the test case line and the code;
  - **EXPECTATION WRONG** — an assert of a non-security test case whose expected outcome differs from what the code does; states the code-derived expected outcome so the test case can be updated. Requires CODE-VERIFIED evidence, a search showing no other code path produces the test case's outcome, and D's confirmation at confidence ≥7. A runtime-read setting defeats it only when the test case's Arrange sets that setting; otherwise the declared default is the truth and the finding adds "or set <setting> in Arrange". Without that evidence or confirmation it is a Warning "possible test case mismatch — verify at runtime";
  - **HEDGED ASSERT** — a test case whose assert accepts either of two outcomes; cites the test case and assert and states the branch to keep: the code's branch, or the secure branch for a security test case. The behavior gets this finding instead of a missing-test-case finding;
  - **APP FAILS SECURITY TEST CASE** — a security test case whose expected outcome the code doesn't meet. The test case stands; the app is at fault. A Blocker when the behavior is a permission decision or destructive action (with the ≥7 confidence rule), otherwise an Error;
  - **INSECURE BEHAVIOR, no test case** — security behavior (Terms) the code gets wrong, with no test case asserting the secure outcome. Level as for APP FAILS SECURITY TEST CASE; the proposed test case asserts the secure outcome, not the code's current one;
  - tier mismatch (F): a named journey with no Journey-level test case;
  - an Environment differences fact not covered (Terms, Covered) (A);
  - **CONFIG MISMATCH** (Main, Step 0.3) — spec/config Error: a `CONFIG:` line printed by `qa-write-test-cases`' `qa_projects.py check-config`, quoted verbatim; the user resolves it in the Playwright config or qa-spec.md's header;
  - **PROJECTS MISMATCH** and **TEST FILE MISMATCH** (E, Step 1.2): a test case that breaks the `qa-write-test-cases` Projects rule or Test file rule, so it would not run in exactly the environments its expected outcome is written for;
  - **EXCLUDED PAGE IN JOURNEY** (Main: Step 0.2's lint for Site Map route lines, Step 1.1 for Per-page guidance headings) — spec Error: a page marked `Excluded:` in the chain of a named journey, the case where `qa-write-test-cases` "Check the exclusions" stops. The user resolves it in qa-spec.md: remove the page's `Excluded:` line, change the journey's chain, or mark the journey `Excluded:` or `Deferred:`;
  - **SPEC LINT** (Main, Step 0.2) — spec Error: a `defect` line printed by `qa-write-spec`'s `qa_spec.py`, quoted with its line number; the user resolves it in qa-spec.md. An `excluded-page` line is reported as EXCLUDED PAGE IN JOURNEY instead;
  - a spec seam, spec role, or spec-named feature with no code (from C / Step 0 / Step 1.4).
- **Warning** — advisory:
  - **coverage limited by an absent role** — one per code role that no spec role maps to, stating how many behaviors it leaves unchecked; these are always listed **first** among Warnings (owned by C);
  - deferred role listed in qa-spec.md (Main, Step 0);
  - uncovered OWASP threat testable only by a role the spec defers, when no helper-role test case covers it;
  - seam at ★★, ★ or ☆ depth;
  - uncovered deferred clause; conditional clause with "holds: unknown";
  - default-off feature (one per feature), page missing from the Site Map, action no page triggers, other-mode routes (from C);
  - UNTRACED or untraced-budget seam;
  - **spec lint warning** (Main, Step 0.2): a `warning` line printed by `qa-write-spec`'s `qa_spec.py`, quoted with its line number;
  - possible test case mismatch — verify at runtime; flaky by design;
  - scope creep (Main, from E's candidates); partially unmappable test case; time-dependent assert without pinned date/time (from E); subjective assert — one grouped Warning (from E); stale criteria hash — one grouped Warning (from E);
  - Journey/Interaction ratio outside the `qa-write-test-cases` Tier ratio, over non-Security, non-Performance test cases and excluding Journey-level test cases on out-of-scope journeys; **out-of-scope journey** (F, Terms): a Journey-level test case that walks one is extra, not journey coverage; a test case parented to one keeps its per-seam coverage and gets only a note on its Parent;
  - **priority below risk**: a test case whose Priority is below the one the `qa-write-test-cases` Priority scale and its tie-breaks give it (A for the test cases it matches, security test cases included; F for Journey-level test cases); **smoke set incomplete** (F): a named journey that has a Journey-level test case but none at P0/P1.

A behavior repeated across seams is one finding listing the seams; a cross-cutting clause gap is one finding per clause with a seam list. INFERRED findings are never Blockers or Errors. Anything in an exclusion clause is suppressed.

**Tier check** (F): named journeys come from qa-spec.md's Journeys section. With no Journeys section, report the tier check as "not checkable — qa-spec.md has no Journeys section" instead of passing. A Journey-level test case walks the journey named in its `**Journey:** <J-ID>` field, comparing journey IDs numerically (`J01` = `J1`), as `qa-write-spec`'s `qa_spec.py` does; only when the field is absent, match its Act against the journey's Chain. Journey-tier security test cases (Terms) are not journeys. A journey's security test case is a Journey-tier security test case that walks the journey by the same match.
