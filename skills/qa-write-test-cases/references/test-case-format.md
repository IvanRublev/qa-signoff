# Step 7 — Write each test case self-contained

7. **Write each test case self-contained** — no separate test-case document to reference; the test case is the spec. If you have a backlog test case template (the user's or the project's), read it first and keep its mandatory sections and its own rules (checkbox format, empty markers) — re-check the mapping below against whatever it currently requires. Without one, the sections below, in this order, are the whole format. Either way, this skill fixes where QA-test-case content goes:

   - **Test case ID format** — `TC-[CATEGORY]-[NUMBER]`, where CATEGORY is uppercase letters and digits and NUMBER is 3 digits, zero-padded, counted per CATEGORY from `001`:

     ```
     Examples:
     - TC-CLI-001 (CLI tests)
     - TC-WEB-042 (Web tests)
     - TC-API-103 (API tests)
     - TC-SEC-007 (Security tests)
     ```

     CATEGORY isn't limited to these four — use whichever fits the inventory item (pick a closer one when it fits) — but always use `SEC` for any test case produced by step 4's OWASP checklist regardless of surface.
   - **Heading** — `## <Test case ID> - <Title>`, where `<Title>` is an outcome-readable title. Each section from Parent to Potential Bugs is a `### <section name>` heading (e.g. `### How to build`), with no other `##` or `###` heading inside a section.
   - **Directly under the heading, before Parent** — add `**Priority:** <P0-P3>` (step 8), `**Tier:** <Journey-level/Interaction-level>` (step 5), `**Type:** <one or more of Functional/Boundary/Negative/Cross-cutting/Security/Performance>` (step 3), `**Estimated Time:** <rough manual-execution minutes>` (a backlog-sequencing aid, not a gate), and `**Feature:** <shared component or feature name>` — mandatory on every test case, not only ones isolation forced apart; lets test cases sharing a component (same entry point or split across several) be found together. A Journey-level test case that walks a named journey also carries `**Journey:** <journey ID from the spec>`. **Projects rule:** every test case also carries `**Projects:** <project>, …` — the lead role's project for every environment — or, for a test case that depends on Environment differences entries, exactly the environments the Environment split (step 6) gives it — named as in the Playwright config gate (e.g. `admin-desktop-chrome, admin-iphone-13`); the lead role is `no-login` when the test starts logged out (login page, password reset, a logged-out user's redirects). **Test file rule:** every test case also carries `**Test file:** <tests root>/<role>/<Test case ID>.spec.ts` — the exact path, directly in the role folder; the role folder makes the file run in every project of that role. When Projects lists some but not all of the role's environments, the test skips itself in every other project (Test file rules block).

     None of these fields are part of the generic template; they're specific to this skill's test cases.
   - **Write order and back-references** — write Journey-level test cases first, then Interaction-level ones, each in spec order (Backlog document). Parent, Relates to and Blocked by cite only a test case that already exists: one kept from an earlier run, or one written earlier in this run. Test case numbers can't show this order, because each CATEGORY counts separately, so this rule replaces a template's lower-number rule.
   - **Parent** — the Journey-level test case this one descends from, if this is an Interaction-level test case scoped under a named journey. Omit it when there is none (the template's omission rule, else leave the section out).
   - **What to build** — the user story: role, action, and the "so that" clause drawn from the journey or business goal (step 2) this test case serves.
   - **How to build** — Arrange-Act read as test case fields: **Arrange** (the state the world must be in before the test starts: role, data, prior step) and **Act** (what the user/tester does, as a sequence, in plain terms) and **Cleanup** (step 6), plus any constraint on how the test must be run that would otherwise let a false pass through (e.g. "use the real sandbox response, not a mock"). Arrange never lists a UI login for the lead role: the session comes from the project. Then a **Test file** block, filled in for this test case and repeated in every test case, so the implementer needs nothing beyond the test case:

     ```markdown
     **Test file rules:**
     - Write exactly one file at `<Test file>`. Every test in it belongs to this test case, and every test title starts with `<Test case ID>: `.
     - Line 1 of the file is the comment named in the acceptance criteria's `Output test file contains comment` item.
     - The Playwright project supplies the browser or device: never set a viewport, user agent, or device in the test.
     - Session: <exactly one of>
       - Starts logged in as <role>: the project injects the session. Do not log in through the UI.
       - Starts logged out (`no-login`): there is no session. Log in through the UI only where an Act step says so, with credentials from `process.env.<ROLE>_USERNAME` and `process.env.<ROLE>_PASSWORD` (`.env`, loaded by the Playwright config; `<ROLE>` is the role name uppercased, with every character other than a letter or digit turned into `_`, e.g. `ADMIN`, `CUSTOMER_RESTRICTED`), never literal values.
     - <only with a helper role: a crawled role other than the lead role> The <helper role> steps run in a second browser context: `const helper = await browser.newContext({ storageState: '<helper role's storageState path from the Playwright config>' })`, closed at the end of the test.
     - <only with logged-out steps besides the lead role's> The logged-out steps run in a second browser context with no session: `const guest = await browser.newContext({ storageState: { cookies: [], origins: [] } })`, closed at the end of the test. A plain `browser.newContext()` inherits the project's session. A UI login in it takes credentials from `process.env.<ROLE>_USERNAME` and `process.env.<ROLE>_PASSWORD`, as on the logged-out Session line.
     - <only when Projects lists some but not all of the role's environments> The first line of every test is `test.skip(!['<project>', …].includes(test.info().project.name), '<reason>')`.
     - Do not edit the Playwright config or other test cases' test files.
     ```

     Drop the lines marked "only …" when they don't apply, and replace every `<…>` with this test case's values.
   - **Acceptance criteria** — lead with **Assert:**, then one checkbox list, each item binary pass/fail, observable, no prose intent. For everything step 3's Negative/Security angles say must NOT happen or must stay unchanged, add an item to this same list prefixed `Absence check:` — a separate section is not the template's shape; a positive item announces itself when missing, an absence item doesn't unless it's written down. No overall pass/fail summary line ("PASS if all items above pass, FAIL otherwise"): the checkbox list already implies it. Name every spec-stated value the test checks (a length limit, a boundary value) in the criterion or How to build step that uses it: the other sections, UX behavior included, are outside the hash.
   - **UX behavior** — the observable states/surfaces/error paths a user would see, distinct from the pass/fail checklist. If the test case is backend/security-only with nothing a user sees, use the template's "no visible surface" marker, else `No user-facing surface` plus what the test checks instead.
   - **Relates to** — other TC test cases worth reading alongside this one for context, even outside this test case's own Feature (e.g. a Journey-level test case relating to an Interaction-level test case for a component that journey passes through), one per line, else `None`. Back-references only (write order above).
   - **Blocked by** — any already-written test case that must land first (e.g. a permission-model test case this one assumes exists), one per line, else `None — can start immediately`.
   - **Potential Bugs** (last, after Blocked by) — edge cases or security concerns adjacent to this test case that aren't already an Acceptance criteria item. Flags risk for whoever executes or automates the test case without forcing every guess into a formal checklist item.

   Example (Acceptance criteria only):
   - [ ] Payment decline shows an on-page message naming the reason, cart and shipping details intact
   - [ ] Absence check: retrying with a different card does not require re-entering shipping info
   - [ ] Absence check: no stack trace or raw processor error reaches the page
   - [ ] Output test file contains comment: `// TC-WEB-042 criteria-hash: <hash>` as its first line

   Together, this list is the whole mechanism for redoing the test later — describe outcomes, never the mechanism that produces them. The last item is the drift guard: once a test case is automated, editing this list or the How to build steps changes the hash, so the test file's first line goes stale and shows the test needs rebuilding.

   **Hash rule.** `<hash>` fingerprints what the test does and asserts: every How to build line, Test file rules block included, and every Acceptance criteria line except `>` notes; blank lines and trailing spaces don't count, and each section ends at the next `##` or `###` heading. The hashed text excludes the `Output test file contains comment` criterion itself, which breaks the circle of a hash covering its own line, and excludes checkbox marks, so ticking a criterion off leaves the hash unchanged. `<skill dir>/scripts/qa_tickets.py` owns the recipe: `python3 <skill dir>/scripts/qa_tickets.py write <test-case.md>` writes the computed value into that criterion and prints the test file's first line, `hash` prints that line, `check <test cases folder>` lists test cases whose stored hash is missing or stale, and `rehash` moves an unchanged test case and its test file onto a changed recipe (Re-run over an existing backlog). The test file carries the same value as its first line. Whenever this skill adds or changes a test case's How to build steps or acceptance criteria — in this step, in step 9's closing pass, or on a re-run — recompute the hash and rewrite it as the last edit to that test case.
