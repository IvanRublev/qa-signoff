---
name: qa-write-spec
description: "Crawl a live app per role to produce `qa-spec.md`, a QA-facing seam map — the basis for writing test cases later. Use when asked to map an app for QA, crawl a site per role, or write a QA spec before qa-write-test-cases."
copyright: Ivan Rublev 2026
license: Apache-2.0
version: 0.3.5
---

This skill produces a QA spec.

A seam is a place you can test the app from without going through everything upstream of it. For a web app, seams are pages/routes reachable from the UI. Prefer the highest seam: a page is a better seam than a form or tab on it; map a form or tab as its own seam only when it works independently of the rest of the page. The fewer seams needed to get full product coverage, the better.

A role is a permission level the app renders and gates differently (admin, standard user, restricted user, etc). Two roles hitting the same route are not the same seam — one may see fields, nav items, or actions the other can't. Full product coverage means every seam mapped under every role that can reach it, not just the highest-privilege one.

**Running scripts:** `<skill dir>` is this skill's base directory, the folder holding this SKILL.md (the path this file was opened from, without `SKILL.md`; when that path is unknown, the folder a file search for `qa-write-spec/SKILL.md` finds). Run every command from the test project root, so data paths like `qa-spec.md` resolve there. `$B` stands for the `qa-browse-app` handle, `node <skill dir>/../qa-browse-app/scripts/qa-browse-app.mjs`, written out in full in every command; it is not a shell variable. Its SKILL.md lists the commands.

## Process

1. **List the roles** that need coverage (check `.env`, ask the user, infer from an existing permissions/roles admin page, or search the app's own code/config for role definitions — e.g. `security.yaml`, an ACL/role enum, a permissions table seed — using whatever code-search tool the harness has available). If the app has only one role, that's the full list — don't invent roles that don't exist. Confirm the target base URL and each role's credentials. Each role's credentials live in `.env` under the keys the `<ROLE>` rule of the `qa-write-test-cases` Test file rules block gives (e.g. `ADMIN_USERNAME` / `ADMIN_PASSWORD`); ask the user to rename any keys that differ. Install `@playwright/test` and `dotenv` in the test project if they are missing (`npm i -D @playwright/test dotenv`): `$B` runs on the test project's installed Playwright and reads the device profiles from it. Run `$B check` (the `qa-browse-app` Setup check): on `NEEDS_SETUP`, stop and show the user the reason and the commands it prints. Check that the base URL is reachable; if not, stop and tell the user. A role with no working credentials is not crawled; list it under Roles not crawled in the spec header with the reason (no credentials, login failed).

   If `qa-spec.md` already exists and a role under its "Roles not crawled" now has working credentials, ask the user before crawling: re-crawl every role, or crawl only the newly available roles and keep the existing map for the others. Proceed accordingly. In either case step 3 compares every seam the newly crawled roles reach against the other roles.

   **Ask the user which environments the product supports** — the tests later run in every one of them. Offer both kinds, and accept any combination:
   - **Desktop browsers:** Playwright profiles `Desktop Chrome`, `Desktop Firefox`, `Desktop Safari` (WebKit engine), `Desktop Edge`.
   - **Emulated mobile devices:** Playwright profiles, e.g. `iPhone 13` (WebKit engine, Mobile Safari-like) and `Pixel 7` (Chromium engine, Chrome on Android-like). Emulation sets viewport, touch, and mobile user agent; it is not a real device.

   Record the answer in the spec header's `Environments:` line, using the Playwright profile names exactly, so the Playwright config can mirror it. Step 2 crawls once per breakpoint, not once per environment: each environment belongs to the desktop or the mobile breakpoint by its installed Playwright device's `isMobile`. If `qa-spec.md` already has an `Environments:` line, show it and ask whether it still holds. When the answer adds an environment to a breakpoint already crawled, it needs no crawl: add it to that breakpoint's Environment differences entries. When the answer adds a breakpoint, ask before crawling: re-crawl both breakpoints, or crawl only the new one and keep the existing map for the other. Proceed accordingly; step 3 compares every seam the newly crawled breakpoint reaches against the other breakpoint.

2. **For each role, start from a clean browser session, then walk the app breadth-first to find every seam** reachable by that role — once per breakpoint, desktop and mobile. Run `$B devices "<profile>" …` with every profile in the `Environments:` line: it prints one `desktop:` or `mobile:` line per breakpoint the environments use, listing that breakpoint's environments, and the first environment on a line is that breakpoint's crawl profile; a breakpoint with no line isn't crawled. One crawl per breakpoint is a cost trade-off: `$B device` emulates the crawl profile's screen, user agent, `isMobile` and touch from the test project's installed Playwright, always in Chromium, so environments inside one breakpoint can still differ in screen width and engine; those differences are left to the tests. Every crawl — `no-login` and each role × breakpoint — runs in its own `qa-browse-app` session named `<role slug>-<breakpoint>`, the role name lowercased with spaces turned into `-`, and any other character outside ASCII letters, digits, `-` and `_` turned into `-` too, with the role part cut so the whole name stays within 64 characters (e.g. `no-login-desktop`, `admin-mobile`, `standard-user-desktop`), passed as `--session <name>` on every `$B` command of that crawl; `$B check` and `$B devices` take no session. Run the crawls one after another. Start every crawl with `$B --session <name> device "<that breakpoint's crawl profile>"`, which clears the session (cookies, storage, tabs), then, for a role, log in. The session keeps cookies and login state across calls until the next `$B --session <name> device`. End every crawl with `$B --session <name> stop`. For the second breakpoint, start from the routes already found and still follow every new link. Before the role crawls, crawl the logged-out state the same way as the artificial role `no-login` — an exception: never list `no-login` under `Roles crawled:` or `Roles not crawled:`, it is implied for every spec — never logged in, starting at the base URL, mapping every page reachable without logging in (login, password reset, public pages). Its seams go into the Site Map and its differences into Environment differences like any role's. Each role's crawl starts from the post-login landing page:
   - `$B --session <name> wait --networkidle` before every snapshot after a navigation; after an in-page action that doesn't navigate (a click that opens a modal or tab), `$B --session <name> wait <selector of the new content>` instead — inspecting DOM before the page settles misses JS-rendered nav items and silently truncates the seam map.
   - `$B --session <name> snapshot -i` to list interactive elements, `$B --session <name> links` to list all links on the page.
   - Follow every nav link, menu item, and sub-tab not yet visited, except the session and state changers below. Track visited vs. discovered-but-unvisited routes in a scratch list.
   - Repeat until no new routes surface. This is a graph traversal, not a fixed checklist — stop when the frontier is empty, not when you've covered "the obvious pages." At 200 pages per role × breakpoint, ask the user whether to continue.
   - Collapse parameterized instances into one seam: `/admin/project/5/edit` and `/admin/project/6/edit` are the same seam, `/admin/project/{id}/edit` — record the pattern once, not once per instance. Collapse query strings, pagination, and date segments the same way: `/timesheet/?page=2&order=date` and `/timesheet/2026-09-30` are one instance per pattern.
   - Don't follow links or click controls that end or change the session or its settings: logout, switch user or impersonation, and toggles that save state (locale, theme, timezone, 2FA). Don't click destructive actions (delete, revoke, deactivate) or submit forms either. Record each in the map as a route or action this role sees, without triggering it by link, click, direct URL or a guessed path such as `/logout`; map only routes the pages link to, and let `$B --session <name> stop` and `device` end and clear a session. When the app's source is available, read each such route's handler and permission rule and record its effect and the roles it blocks in Role differences; without the source, record the label, the page and the roles that see it, and mark the effect and blocked roles `not verified` — a breadth-first crawl that follows everything logs itself out, changes the account, or destroys data mid-crawl.
   - A `$B --session <name> goto` that exits 1 with `Download is starting` reached a route that downloads a file: record it as a download seam and don't open it again.
   - After each page, check the session is still this role's: the page isn't the login page, and the user menu shows this role's user. If the session dropped, note in the scratch list which page caused it (step 5 warns about it), log in again as this role, and don't revisit that page.
   - When a `$B` command prints `Warning: started a new qa-browse-app session "<name>" (cookies, device and tabs reset)`, the session was reset: re-run `$B --session <name> device` with the current breakpoint's crawl profile and, for a role, log in again as the current role.
   - Don't test behavior in this pass. Just map: what page, what's on it, what sub-routes/tabs/modals it exposes, and whether this role's view of it differs from another role's (fewer fields, hidden actions, read-only vs editable).

3. **Once every role is crawled, compare each seam reached by more than one role.** First probe each role against the routes the other roles found, by direct URL in that role's session, started and stopped the way step 2 starts and ends a crawl, skipping every route step 2 records without triggering (logout, switch user, destructive actions). Record each route the role can't reach (blocked) or reaches without it in the nav (hidden) in Role differences — they're evidence for that role's permission boundary. `no-login` being blocked from every protected route is recorded once, as a blanket fact. Then compare: open it under each of those roles and check the UI and the guidance you'd write for it side by side. Identical in both — merge into one Site Map entry and one Per-page test guidance entry. Differ in either — one Site Map entry, but keep the roles apart in Role differences (what differs) and in Per-page test guidance (per-role subsections). Don't merge on route match alone; this comparison is what decides it, for both sections.

   Then compare each seam across the two breakpoints, per role, the same way. A difference is a UI fact that changes what the user can see or do: navigation collapsed behind a menu, a table shown as cards, a control missing or moved behind a menu, a route unreachable. Pure reflow with the same controls and content is not a difference. Identical in both — no entry. Different — an Environment differences entry per breakpoint, naming the breakpoint and the environments it stands for, and per-breakpoint subsections in Per-page test guidance where the guidance differs.

4. **Name the journeys.** A journey is a chain of seams that delivers one business goal end to end (log in → create record → edit → delete; set up entities → use them → bill for them). Build them from the crawled Site Map, not from guesswork: every step is a seam from step 2, in the order a user walks it. Done when every business goal visible in the map has at least one journey spanning it. A journey that can't be walked yet is marked `Deferred: <reason>`; the usual reason is a role that wasn't crawled, named as the missing role (other reasons: missing test data, missing environment, feature not built). A seam on no journey is fine — say so under the Journeys section instead of inventing a chain for it.

5. **Write `qa-spec.md`** at the root of the test project (the repo the skills run in) — if one already exists there, read it first and extend it rather than restructure it; add new seams/roles/checks without discarding what's already documented:

   **Exclusion grammar.** The user marks a page, journey, or cross-cutting check as out of scope with `Excluded: <reason>`, in any of these places: inline at the end of its exact Site Map page line (not a `...` line), as a line right under its Per-page test guidance or Journeys heading, or at the start of its cross-cutting check line (`- Excluded: <reason> — <check>`). This skill never writes `Excluded:` itself, and keeps every existing `Excluded:` line when extending the spec. `qa-write-test-cases` and `qa-review-test-cases` leave excluded items out.

   When extending an existing spec:
   - Move each newly crawled role from "Roles not crawled" to "Roles crawled" in the header.
   - Drop the header warning of each cause now resolved (e.g. the role's crawl warning).
   - Remove a journey's `Deferred:` line once its reason is resolved.
   - Split a shared Per-page test guidance entry into per-role subsections when step 3 finds that it differs by role, and add the matching Role differences entry.
   - Keep every existing journey ID; give each new journey the number after the highest existing one.
   - Keep the `Environments:` line unless the user changed it in step 1.
   - Add Environment differences entries for a newly crawled breakpoint, and each added environment to its breakpoint's entries; add the section to a spec that lacks it.
   - Drop removed environments from Environment differences entries, and an entry itself when none of its environments remain.

   After a re-run, recommend the user run `qa-write-test-cases` to bring the backlog in line with the updated spec.

   **Header warnings.** Right under the `Environments:` line, write one `> ⚠️ **<what>:** <why>. <what is missing because of it>.` line for each way this crawl covers less than the full product, so the reader sees it before the Site Map. Cases, each with its own line:
   - a role under Roles not crawled (reason: no credentials, login failed) — name the journeys deferred for it;
   - a role × breakpoint crawl the user stopped at the 200-page check — name the role, the breakpoint and the page count;
   - a page skipped because it dropped the session (step 2) — name the page and the role;
   - a breakpoint the user declined to re-crawl while extending the spec — name it and the roles whose map for it is older.

   Warnings about one entry stay on that entry — a `Deferred:` line under its journey, an `Excluded:` marker — and are not repeated here. Keep `Roles not crawled:` in the header line too: later skills read it. Write no section when nothing applies; on a re-run, drop each line whose cause is resolved. Separate consecutive lines with a bare `>` line, so each warning renders as its own paragraph. The lines are plain blockquotes: the lint ignores them.

   Only the Site Map is a code block. The other sections' examples are fenced to set them apart; write their entries as plain markdown, since the lint ignores code blocks outside the Site Map.

<qa-spec-template>

# {Product} QA Spec

Target: {base URL}. Roles crawled: {role list}. Roles not crawled: {role} ({reason}), …. Credentials in `.env`.
Environments: {Playwright profile}, … (e.g. Desktop Chrome, Desktop Safari, iPhone 13).

> ⚠️ **{Role} crawl reduced:** {why — e.g. no credentials / login failed}. {What is missing from this spec because of it}.
>
> ⚠️ **{Role} — {breakpoint} crawl stopped at {N} pages:** {why}. Seams beyond that are unmapped.

## Site Map

The full seam list as a route tree, grouped by feature area, exactly as discovered in step 2 — not reorganized by guesswork. Merge seams reachable by multiple roles per step 3. Write it as a code block, one route per line, each line starting with `/` (indent to show nesting). A line `/x/... <label>` stands for a group of pages under `/x/` too many to list one by one; a Chain step anywhere under `/x/` matches it. `Excluded:` goes only on an exact page line: to exclude one page of such a group, give that page its own line. Example shape:

```
/login
/dashboard
/timesheet/                 (My times)
  /timesheet/create
  /timesheet/export/{format}
/admin/user/
  /admin/user/{id}/edit
/admin/permissions           (Roles)
/profile/{username}
  /profile/{username}/edit
  /profile/{username}/2fa
/logout
```

## Role differences

One entry per seam that renders differently across roles: which roles reach it, and what UI fact differs for each (hidden fields, disabled actions, read-only vs editable, extra/missing nav, not reachable). State only the fact, not what to test for it — that belongs in Per-page test guidance. Skip seams identical across every role that can reach them — those need no entry here. Example:

```markdown
### {Entity} CRUD page (e.g. Users, Projects) — Admin
Full CRUD, sees all records.

### {Entity} CRUD page (e.g. Users, Projects) — Standard user
Read-only, sees only own records.

### {Entity} CRUD page (e.g. Users, Projects) — Restricted user
Route not reachable, redirects to dashboard.
```

## Environment differences

One entry per seam, role, and breakpoint whose UI differs between the desktop and mobile breakpoints: the breakpoint and every environment it stands for, and what UI fact differs. State only the fact, not what to test for it. Skip seams identical in both breakpoints. Example:

```markdown
### Timesheet list — Admin — desktop: Desktop Chrome, Desktop Safari
Table with sortable columns; inline edit per row.

### Timesheet list — Admin — mobile: iPhone 13
Card list; columns folded into each card; edit behind the card menu.
```

## Per-page test guidance

One subsection per seam, split by role or breakpoint per step 3. Guidance only: what to verify, given the UI facts already stated in Role differences — don't restate those facts here, test them. No test IDs, no step-by-step scripts, no selectors — that's for the test cases built from this spec later. Example entries:

```markdown
### Login
Verify valid credentials authenticate, invalid credentials reject with error, forgot-password link works, session persists across reload, logged-out user redirected here from any protected route.

### {Entity} CRUD page (e.g. Users, Projects) — Admin
Create/edit/delete succeed on any record, required-field validation rejects bad input, deletion blocked or cascades correctly when entity in use, inactive entity not selectable elsewhere (e.g. project picker).

### {Entity} CRUD page (e.g. Users, Projects) — Standard user
Edit/delete controls absent from the UI, and rejected server-side if hit directly by URL — not just hidden.

### Roles / permissions page
Permission matrix changes apply correctly — verify with a lower-privilege account that gaining/losing a permission changes visible menu items and route access (direct URL navigation blocked, not just hidden nav).
```

## Journeys

One entry per journey from step 4, headed `### J<n> <name> — <roles>`: IDs are unique and never reused. A deferred journey carries `Deferred: <reason>` as the first line under its heading. Then the business goal and the seam chain as Site Map routes in walking order. Downstream skills read this list as the authoritative set of journeys. End with one line listing the seams on no journey. Example:

```markdown
### J1 Session lifecycle — Admin
Goal: an authenticated user works in the app and leaves it safely.
Chain: /login → /timesheet/ → /dashboard → /logout

### J2 User lifecycle — Admin, Standard user
Deferred: needs Standard user credentials.
Goal: an admin-created account can log in, have its password reset, and be deactivated.
Chain: /admin/user/ → /admin/user/{id}/edit → /login

Seams on no journey: /admin/plugins/, /doctor.
```

## Cross-cutting checks

Checks that apply to every seam rather than one page. Example set — adapt it to this app's features and environments, don't copy it verbatim:

- No JS console errors, no failed network requests.
- Permission boundaries: direct URL access by under-privileged role returns 403/redirect, not partial render.
- Layout holds in every environment in `Environments:`.
- Locale switch (at least one non-English) doesn't break layout or lose data.
- Accessibility: axe scan with zero critical/serious violations.
- Form validation: required fields, type mismatches, boundary values show inline errors, don't submit invalid state.

</qa-spec-template>

6. **Validate `qa-spec.md`** and fix every failure before finishing:
   - `python3 <skill dir>/scripts/qa_spec.py qa-spec.md` exits 0: this skill fixes its warnings too, since it wrote the spec. Exit 1 lists critical defects (a header without a `Roles crawled:` line — left empty for an app with no login — or without a non-empty `Environments:` line, two crawled roles whose names match once lowercased with spaces turned into `-`, or one that matches `no-login` that way, duplicate journey IDs, and, on a journey with no `Deferred:` or `Excluded:` marker, a Chain route missing from the Site Map, an `Excluded:` page on its Chain, or a heading role that is neither in `Roles crawled:` nor `no-login`; also an `Excluded:` on a `...` Site Map line); exit 2 lists only warnings, e.g. a line it can't parse or a marker without a reason; exit 3 means it couldn't read the file. The script's docstring lists every check.
   - Every seam has Per-page test guidance.
   - Every role under "Roles not crawled" is named with a reason.
   - Every reduced crawl from steps 1-2 has its `> ⚠️` line in the header.

7. **Commit.** Once step 6 passes, commit `qa-spec.md` and any file the step 1 install changed (`package.json`, the lockfile): `git add -- <those paths>`, `git commit -m "qa-write-spec: write qa-spec.md"` (`qa-write-spec: update qa-spec.md` on a re-run). Add only those paths; changes the user made elsewhere stay uncommitted.

## What this skill doesn't write

- User stories, acceptance criteria, "as a X I want Y" — that belongs to a spec skill or the qa-write-test-cases skill, not this one.
- Actual test case authoring (steps, expected/actual, test data) — this spec is the input to that work, not the output.
- Backend/unit test coverage — this is a live-app UI/E2E seam map.

## Support

If the user is stuck, hits a blocker, or finds a bug in this skill, follow [`support-banner.md`](support-banner.md).
