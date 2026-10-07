---
name: qa-plan-tests
description: Plan the test cases for a web app from start to finish. Checks the folder is a git repository and a working Playwright project, collects every choice up front (roles, desktop and mobile environments, approvals) with checkbox menus, starts the project's own database and app server from its documentation with your approval, optionally loads its sample data and takes the role logins from it, then runs qa-write-spec, qa-write-test-cases and qa-review-test-cases unattended and applies the review report to the test cases. Use when asked to build a QA backlog or reviewed test cases for a site, or to set up regression coverage from scratch.
copyright: Ivan Rublev 2026
license: Apache-2.0
version: 0.5.6
---

# Plan tests: from a live web app to reviewed test cases

This skill chains the steps and owns none of their rules; each step's rules live in its own skill. The steps take long, so this skill collects every choice first (Phases 1 and 2), then runs without asking anything (Phase 3).

**Hard rule:** work only inside a git repository. The skill writes many files (a spec, test cases, config, tests), and git is how the user reviews and undoes them. Outside a git work tree, change nothing and go no further than Phase 1 step 1.

Requires the `qa-write-spec`, `qa-write-test-cases`, `qa-review-test-cases` and `qa-browse-app` skills to be installed in the same parent folder as this skill.

**Running scripts:** `<skill dir>` is this skill's base directory, the folder holding this SKILL.md (the path this file was opened from, without `SKILL.md`; when that path is unknown, the folder a file search for `qa-plan-tests/SKILL.md` finds). `$B` stands for `node <skill dir>/../qa-browse-app/scripts/qa-browse-app.mjs`, written out in full in every command. Run every command from the test project root.

## Phase 1: the project

1. **Is this a git repository?** Run `python3 <skill dir>/scripts/inspect_project.py` and read `git.inside_work_tree`; a project inside a parent repository counts. When it is `true`, show `git.toplevel` and go on.
   When it is `false`, say plainly that this folder is not a git repository and that the skill will not run without one. Ask one question: run `git init` here (recommended), use another folder, or stop. Run `git init` only after a yes, then run the inspection again. When `git init` is denied (a sandbox that blocks writes to `.git` is the usual cause), give the user the commands to run in their own terminal, `cd <this folder>` then `git init`, say that the denial comes from the agent's sandbox, and wait for the user to say it is done; then run the inspection again. Other `.gitignore` lines and a first commit need their own yes. If the user does not agree to a repository, stop and write nothing.
   Inside a git work tree, create the state folder `.qa-signoff/` in the test project root, where the pack keeps what it remembers between runs (the app's source folder, the writing mode, the isolated databases), and add the line `.qa-signoff/` to `.gitignore`, creating the file when missing. Say so in one line; no question is needed. Done when `git check-ignore -q .qa-signoff/` exits 0.
2. **Is this a Playwright project?** Run `$B check` and `python3 <skill dir>/scripts/inspect_project.py`. The folder is ready when `$B check` prints `READY: Playwright <version>`, the inspection shows a `playwright.config.*`, and `playwright.meets_minimum` is `true`. The minimum version comes from the `qa-browse-app` skill (`$B min-playwright`, also shown as `playwright.minimum`), which owns it; this skill holds no version number. When the installed version is older, say which version is installed and which is the minimum, and offer `npm i -D @playwright/test@latest` (run it only after a yes, then commit `package.json` and the lockfile as `qa-plan-tests: upgrade Playwright`).
   If not, say so plainly: this folder is not a Playwright project. Suggest making it the test project root: `npm init -y` when there is no `package.json`, then the `Run:` and `Then:` commands `$B check` prints, and `npm i -D dotenv`. Ask one question (set it up here, use another folder, or stop). Run the commands only after a yes, then check again. Stop if the user declines. After the setup succeeds, commit what it changed (`package.json`, the lockfile, the Playwright config and tests the setup created): `git add -- <those paths>`, `git commit -m "qa-plan-tests: set up Playwright"`; the commit follows the first-commit rule of step 1.
3. **Does Playwright run?** All three must work:
   - `npx playwright --version` exits 0;
   - `npx playwright test --list` exits 0, or says no tests were found when the project has none yet;
   - a browser launches: `node -e "const {chromium}=require('@playwright/test');(async()=>{const b=await chromium.launch();await b.close();console.log('browser ok')})()"` prints `browser ok`.
   On a failure, show the output and the likely fix (`npx playwright install chromium` for a missing browser) and stop. Do not go on to Phase 2 with a broken Playwright.

## Phase 2: every choice, once

Playwright works, so its installed device profiles are known. Collect everything here; Phase 3 asks nothing.

1. **Ask two things as text:** the **app code path** (the folder with the app's source, for example `../kimai/`; the review step requires it) and the **base URL** the app answers on locally.
2. **Inspect.** Run `python3 <skill dir>/scripts/inspect_project.py --app <app code path>`. It prints JSON: the device profiles of the installed Playwright (`devices`), roles found in `.env`, in the config, in `qa-spec.md` and as hints in the app's source (`roles`), environments from the config and the spec (`environments`), example tests Playwright's setup left (`examples`), SQL files and loader hints for sample data in the project and the app (`sample_data`), compose files, dev scripts and documented start commands (`start`), and the app's stack and the files that talk most about roles (`code`).
3. **Find the roles in the app's code yourself.** The script's hints cover common patterns only; the app may use any language or framework. Read the files under `code.hotspots` and search the app's source with the tools you have for how it defines roles: enums, constants, permission tables, migrations and seeds, auth configuration, role-guard calls, test fixtures, an admin screen that lists roles. Keep roles with evidence, name the file and line, and drop noise. A `.env` is not needed to find roles; it only holds credentials.
4. **Find how to run the app locally.** Read `start` from the inspection and the project's and the app's documentation (README, `docs/`, `CLAUDE.md` or `AGENTS.md`, `Makefile`, scripts, compose files, `Procfile`) for how a developer starts the **database** and the **app server** for local development. For each, settle: the exact command, the folder to run it in, the environment variables it needs, its port or URL, and how to tell it is ready (usually the base URL answers). First check what already runs (does the base URL answer, is the port listening); that needs no start.
   Use only what the docs give for local development. No deploy, production, cloud or `sudo` commands, and no command that deletes data or volumes (`down -v`, `drop`). If the docs give no way to start something that is not running, or contradict each other, ask the user for the commands now, as text.
   Nothing is started without the approval in step 6.
5. **Find the sample data and the logins in it.** Many projects can fill their database with sample data: a plain `.sql` file, or a utility call. Read `sample_data` and search the project's and the app's folders and docs (README, `docs/`, `Makefile`, `package.json` and `composer.json` scripts, container init scripts, the framework's console or seed commands) for how it is loaded. Decide: the exact command (a `.sql` file needs the database client and its target), the **database target** (host and name, from the app's config or the container setup), and which services must be running.
   Then find, for each chosen role, the login that data creates: a username and a password from fixtures, from plaintext values in the SQL, or from the docs ("demo users"). A password stored only as a hash and documented nowhere is not a find. Keep the evidence, file and line.
   If no loader exists, say so and skip the rest of this step.
   Safety rules, since loading can replace the database's data:
   - the target must be local: `localhost`, `127.0.0.1`, `::1`, a local container or a local file. A remote host is loaded only when the user typed that host in the approval;
   - run the loader as found, with no extra drop or truncate commands of your own;
   - show the exact command and the target in the approvals and the summary.
6. **Show the choices as checkboxes**, in groups:
   - **Roles:** every role found, with its evidence. Pre-tick the ones already in the config or the spec. The artificial role `no-login` is added for you and is not offered.
   - **Environments:** `devices.desktop` and `devices.mobile` from the inspection, plus any in the config or spec. Pre-tick those, or `Desktop Chrome` and one mobile profile when there are none. Every environment runs on the Chromium engine.
   - **Approvals** (each holds for its operation class through the whole run and every later stage: a start, load, edit or stop approved here is carried out whenever a later step needs it, with no new question, and a question comes back only for a class never approved or a target the approval did not name, such as a remote host): start the database (`<command>` in `<folder>`); start the app server (`<command>` in `<folder>`, ready when `<url>` answers); both offered only for what step 4 found not running; stop what this run started when it finishes (pre-ticked); load the sample data (shown as `<command>` into `<database target>`, "can replace its data"; offered only when step 5 found a loader); delete the example tests listed in `examples`; apply the Playwright config fix the config gate proposes; apply review findings that edit test cases and `qa-spec.md` (hint: the written test cases in `test-cases/` and the QA map of the app's pages and behaviors they are written from); go on past 200 pages per role during the crawl; re-crawl every role when `qa-spec.md` already exists (otherwise crawl only new roles). Leave deletions of test cases unticked.
   Each group allows one more value typed by the user. Use whichever of these the agent has:
   - its multiple-choice question tool with multiple selection (split a group that has more options than it takes);
   - the terminal menu: write the groups to a JSON file as `choose.py`'s docstring describes (`python3 <skill dir>/scripts/choose.py --help`), ask the user to run `python3 <skill dir>/scripts/choose.py <groups.json> --out <answers.json>` in their own terminal (in Claude Code: type `! python3 …` in the prompt), and read the answers file;
   - a numbered checklist in chat, answered with the numbers to tick.
7. **Credentials.** Each chosen role needs `<ROLE>_USERNAME` and `<ROLE>_PASSWORD` in **`.env-seed`** (ROLE is the role name in capitals with spaces as underscores). `.env-seed` is the credentials template: it stays in the main checkout and is linked into every worktree, where each worktree copies it to `.env` and adds its own `BASE_URL`. So the seed holds credentials only, never `BASE_URL` or a port: dotenv keeps the first value it reads, and a seed `BASE_URL` would override each worktree's own. The inspection's `env_files` shows which of `.env-seed`, `.env` and `.auth/` exist and whether git ignores them.
   - **Roles whose login step 5 found, with the sample-data load approved:** ask nothing. After the load succeeds, Phase 3 writes their credentials into `.env-seed`.
   - **Every other role:** `.env-seed` missing but `.env` holds the role keys: offer to copy `.env` to `.env-seed` and remove `BASE_URL` and port lines from the copy. Neither exists, or keys are missing: offer to create `.env-seed` with those roles' keys and empty values, and ask the user to fill in the passwords and say when done. Never ask for a password in chat.
   - Git must ignore `.env-seed`, `.env` and `.auth/`; offer to add the missing lines to `.gitignore`.
   A role without working credentials is not crawled and is listed as not crawled.
8. **Confirm.** Show one summary: project root, app code path, base URL, the start commands (when approved), roles, environments, the sample-data command and database target (when approved), where each role's login comes from, the credentials file (`.env-seed`), approvals. Ask for a yes. After it, ask nothing more.

If `qa-spec.md` or `test-cases/` already exists, the approvals and the summary say what happens to them.

## Phase 3: unattended

Before the first write, run `git rev-parse --is-inside-work-tree` again; it must print `true`.

**One writer per file.** Subagents race when two of them write the same file, so each shared file has one owner for the whole run:

| File | Who writes it |
|---|---|
| `qa-spec.md` | `qa-write-spec`, run by one agent, one role and breakpoint at a time; afterwards Main alone, and only for approved edits |
| Playwright config and setup file | Main alone |
| `todo.md` | Main alone, after any subagents have returned |
| a test case file in `test-cases/` | one subagent or Main, never two |

**Commit after each step.** When a step in this phase finishes with its done condition met, Main commits the files that step wrote: `git add -- <those paths>` then `git commit -m "qa-plan-tests: <what the step did>"`. Never `git add -A`; files the user changed before the run stay out of the commits. A step that wrote no tracked file makes no commit. A failed step is not committed.

The app, the database and `.env-seed` are set up by Main before any subagent starts. Subagents that only read (the review's) return text and write nothing.

Pass the collected answers to each skill, and answer the questions it would ask from them. A decision nobody collected gets the safe default: delete nothing, edit nothing outside the approvals. List it under open decisions in the summary and go on.

1. **Prepare the project.** If approved, delete the example tests listed in `examples` (for instance `tests/example.spec.ts` and `tests-examples/`), and add the approved lines to `.gitignore`.
2. **Start the database.** If approved: run the approved command from its folder in the background, with its output going to a log file in the scratchpad, note what was started (process id or container) so it can be stopped, and wait up to 120 seconds for it to be ready. Done when it is ready. If it is not, stop and show the end of the log.
3. **Load the sample data.** If approved, check once more that the database target is the one shown and is local, make sure the services it needs are running, and run the loader exactly as approved. Done when it exits 0. If it fails, stop and show its output; do not retry with other commands.
   After a successful load, commit any tracked file the loader changed (message `qa-plan-tests: load sample data`), then write each role's login found in Phase 2 step 5 into `.env-seed` as `<ROLE>_USERNAME` and `<ROLE>_PASSWORD`: create the file if it is missing, keep every other line, never write `BASE_URL`, and overwrite only those keys. Ask nothing. A role whose login was not found keeps the credentials from Phase 2 step 7.
4. **Start the app server.** If approved, start it the same way as the database, after the sample data is loaded. Done when the base URL answers with an HTTP status below 500 within 120 seconds. If it does not, stop and show the end of the log.
5. **Create this run's `.env`** from the template: `cp .env-seed .env`, then append `BASE_URL=<base url>`.
6. **Write the spec.** Apply `qa-write-spec` with the roles, environments and base URL. Crawl one role and one breakpoint at a time, in order: no parallel crawls and no subagents for the crawl. Done when `qa-spec.md` exists with the chosen roles under `Roles crawled:`, the environments under `Environments:`, and a Journeys section.
7. **Write the test cases.** Apply `qa-write-test-cases`. Its Playwright config gate edits the config only as approved; that skill commits the config edit and the test cases itself. When the agent supports subagents and the backlog is large, follow that skill's "Parallel authoring": Main assigns every ID and writes `todo.md`, subagents write only their own test case files. Done when both last-gate commands exit 0:
   `python3 <skill dir>/../qa-write-test-cases/scripts/qa_tickets.py check test-cases`
   `python3 <skill dir>/../qa-write-test-cases/scripts/qa_projects.py check-test-cases --spec qa-spec.md --tests-root <tests root> test-cases`
   `<tests root>` is the `tests root:` line that `python3 <skill dir>/../qa-write-test-cases/scripts/qa_projects.py check-config --spec qa-spec.md --project-dir .` prints.
8. **Review the test cases.** Apply `qa-review-test-cases` with `qa-spec.md`, `test-cases/` and the app code path. It writes a report and a transcript next to `qa-spec.md` and prints the report's file name. Note the name.
9. **Improve the test cases from the report.** Carry out the actions in the report's "How to apply these findings" section:
   - Edit a test case the way the finding states, following `qa-write-test-cases` "Re-run over an existing backlog" for numbering, rehashing and the `todo.md` marks, when the review-finding edits are approved.
   - A finding that blames the app (APP FAILS SECURITY TEST CASE, INSECURE BEHAVIOR) goes to the summary as an app defect; the test case stays.
   - A finding that edits `qa-spec.md` is applied only when the review-finding edits are approved, and one that edits the config only when the config fix is approved, by Main alone and in the way `qa-write-spec` extends a spec; otherwise it goes to the summary.
   - A finding that would drop a test case goes to the summary.
   Apply these edits one at a time in Main, not in parallel. Then run the step 7 commands again. Done when both exit 0 and every Blocker and Error in the report is fixed or listed in the summary.
10. **Summarize.** Report the roles and environments covered, the sample data loaded and where each login came from, the test cases by priority, the report file name, the open decisions, the app defects and the findings left for the user. If approved, stop what this run started, the app server first and then the database, and say what was left running. End by proposing `qa-write-tests` as the next step, which turns the test cases in `test-cases/` into Playwright tests; run it only after the user agrees.

## Stop conditions

Stop and tell the user which step failed, with the printed problems, when:
- the folder is not in a git work tree, or the user declines `git init`;
- Phase 1 fails or the user declines the Playwright setup;
- an approved start command fails or its readiness check times out;
- the sample-data load fails;
- the base URL is unreachable or no chosen role has working credentials;
- a step's done condition fails after one repair attempt.

## Support

If the user is stuck, hits a blocker, or finds a bug in this skill, follow [`support-banner.md`](support-banner.md).
