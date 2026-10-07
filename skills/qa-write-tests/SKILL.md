---
name: qa-write-tests
description: Turn the test cases in test-cases/ into Playwright tests, one test file per test case, in one of three modes - sequential in this session, parallel with this agent's subagents, or, in Claude Code, parallel with a Kaizero fleet of Claude Code instances in tmux. The parallel modes run each agent on its own isolated app environment, which the qa-signoff-pro pack prepares; the skill checks for the pack, offers to get it, and falls back to sequential. Use when asked to write, implement, build or automate the tests for the QA test cases, or after qa-write-test-cases or qa-plan-tests produced a backlog.
copyright: Ivan Rublev 2026
license: Apache-2.0
version: 0.1.21
---

# Write tests: from test cases to Playwright tests

Output is one Playwright test file per test case, plus ticked acceptance criteria and a mark in `todo.md`. The test case is the spec: its Test file rules block, Projects and acceptance criteria say what to build. Test cases come from `qa-write-test-cases`.

Requires the `qa-write-test-cases` and `qa-browse-app` skills in the same parent folder as this skill.

**Running scripts:** `<skill dir>` is this skill's base directory, the folder holding this SKILL.md (the path this file was opened from, without `SKILL.md`; when that path is unknown, the folder a file search for `qa-write-tests/SKILL.md` finds). `$B` stands for `node <skill dir>/../qa-browse-app/scripts/qa-browse-app.mjs`, written out in full in every command. Run every command from the test project root. `<test cases folder>` is `test-cases/` next to `qa-spec.md`, unless the user names another folder.

## Start

Done when all three hold:
- `python3 <skill dir>/../qa-write-test-cases/scripts/qa_tickets.py check <test cases folder>` and `python3 <skill dir>/../qa-write-test-cases/scripts/qa_projects.py check-test-cases --spec qa-spec.md --tests-root <tests root> <test cases folder>` exit 0, where `<tests root>` is the `tests root:` line that `python3 <skill dir>/../qa-write-test-cases/scripts/qa_projects.py check-config --spec qa-spec.md --project-dir .` prints with exit 0;
- `$B check` prints `READY`;
- the app answers at `BASE_URL` from `.env`; when it does not, start the database and the app server with the commands approved earlier in this conversation (an approval to start holds for the whole run, so ask nothing), and ask the user for the start commands once when none were approved;
- `todo.md` has at least one line marked `[ ]` or `[?]`. These lines are the **work list**. A `[?]` line is a partial test from an earlier run; Kaizero claims `[ ]` lines only, so in Kaizero mode the `[?]` lines wait for **Finish**.

When a check fails, show the printed problems and recommend `qa-write-test-cases` (or `qa-plan-tests`) to fix them, then stop.

## Choose the writing mode

When a writing mode was already chosen earlier in this conversation, with its Kaizero install settled when it is Kaizero, go straight to that mode's section; steps 1 to 3 below are skipped.

Otherwise settle the pack result by [`references/pro-detection.md`](references/pro-detection.md) and run `python3 <skill dir>/scripts/write_mode.py get --pro <result>`, with `<result>` that detection's `yes` or `no`, which reads the mode the user chose in an earlier run, saved in the test project's `.qa-signoff/` folder, and prints it only while it still works (the pack installed, the isolated-run instructions prepared, and for Kaizero its three commands installed), else `none: <cause>`; the cause names what to fix, and steps 1 to 3 below fix it. A printed mode is the chosen one: say it in one line and go straight to that mode's section; steps 1 to 3 below are skipped. The user asking to change the writing mode skips this lookup and starts at step 1.

Track two facts through steps 1 and 2: **pro** (installed or declined) and **isolated** (instructions prepared or not).

1. **Is `qa-signoff-pro` installed?** Detect it by [`references/pro-detection.md`](references/pro-detection.md).
   - Installed: go to step 2.
   - Missing: tell the user that `qa-signoff-pro` lets several agents write the backlog's test cases at the same time, up to 4.5x faster, with one example in hours: a run that takes 9 hours one test case after another finishes in about 2 hours. Name the work list's size `<N>` when it is known.

     Then ask one question: get `qa-signoff-pro` now? On a yes, open `https://go.ivanrublev.com/get-qa-signoff-pro` in the user's browser (`open` on macOS, `xdg-open` on Linux, `start` on Windows) and ask the user to say when it is installed; then check again. On a no, or when it is still missing after the user says it is installed, set pro to declined and go to **Sequential mode**.
2. **Are the isolated-run instructions prepared?** They are prepared when the instruction file in the test project root has an `## Isolated runs` section. The instruction file is the one the harness reads on its own: `CLAUDE.md` in Claude Code, `AGENTS.md`, `GEMINI.md` or `.github/copilot-instructions.md` in other harnesses.
   - Prepared: go to step 3.
   - Not prepared: congratulate the user on having `qa-signoff-pro`, say that now the isolated app environments can be prepared with the `qa-prepare-isolated-runs` skill, which puts an instruction file section, a database reset script and a database template into the project folder, and ask whether to run it. On a yes, run the skill, then check again; the section must exist now. On a no, tell the user plainly that the isolated-run instructions are missing, so parallel agents would affect each other's work through shared mutated application state, and that the run goes sequential; go to **Sequential mode**.
3. **Pick the mode.** Kaizero runs Claude Code instances only, so its option appears only when this agent is Claude Code. Ask one question:
   - in Claude Code, three options: **Kaizero in tmux** (recommended), **subagents of this agent**, **sequential**; when the user already declined the Kaizero install earlier in this conversation, only the last two;
   - in any other agent, two options: **subagents of this agent** (offered when the agent can run subagents) and **sequential**.

   Save the answer with `python3 <skill dir>/scripts/write_mode.py save kaizero|subagents|sequential`, then go to **Kaizero mode**, **Subagent mode** or **Sequential mode**
   according to the answer.

## Kaizero mode

[Kaizero](https://kaizero.sh) is a todo-list runner: it takes the lines of `todo.md` one at a time across several Claude Code (`claude`) instances, each in its own git worktree. It runs the harness, not the agents inside it, and supports Claude Code only.

**Install commands** (from the Kaizero README; used by install and by upgrade). Prerequisites: `git`, `claude`, a runnable `flock` and `tmux` (macOS: `brew install flock tmux`; Linux: `flock` ships in util-linux, `tmux` comes from the package manager). `gh` and `jq` are needed only without `--local-merge`.
- **Homebrew available** (`command -v brew` resolves): `brew install IvanRublev/tap/kaizero` to install, `brew upgrade IvanRublev/tap/kaizero` to upgrade. The formula installs `kaizero` and `kz-tmux` together.
- **No Homebrew** (also a manual install on Linux): download both scripts to `/usr/local/bin`; run the same lines again to upgrade:

  ```sh
  sudo curl -fsSL https://raw.githubusercontent.com/IvanRublev/kaizero/refs/heads/master/kaizero.sh -o /usr/local/bin/kaizero
  sudo chmod +x /usr/local/bin/kaizero
  sudo curl -fsSL https://raw.githubusercontent.com/IvanRublev/kaizero/refs/heads/master/kz-tmux.sh -o /usr/local/bin/kz-tmux
  sudo chmod +x /usr/local/bin/kz-tmux
  ```

  `sudo` asks for the user's password: when the agent cannot answer it, ask the user to run these lines in their own terminal and say when done.

1. **Is Kaizero installed?** Run `command -v kaizero kz-tmux tmux`; all three must resolve.
   - Missing: say this to the user:

     > Kaizero runs several Claude Code instances at once on this backlog, in one tmux window:
     > - **Each instance works in its own git worktree** of your repo, so parallel instances cannot overwrite each other's files.
     > - **A fresh Claude Code session for every test case.** Kaizero restarts the session before its context degrades, so the fiftieth test gets the same care as the first.
     > - **Merging and bookkeeping done for you.** Each finished test is merged into your main branch and ticked off in `todo.md`, so you review commits and watch the list shrink.

     Then ask one question: install Kaizero? On a yes, run the install commands above for the user's system (`https://kaizero.sh` is a short link to the repository README, the source of those commands). Done when `kaizero --version` prints a version and `command -v kz-tmux tmux` resolves. On a no, or when the install fails, ask whether to continue with the subagents of this agent; a yes goes to **Subagent mode**, a no goes to **Sequential mode**.
   - Installed: go to step 2.
2. **Is it the latest version?** Resolve the repository: `curl -sIL -o /dev/null -w '%{url_effective}' https://kaizero.sh`. The latest version is the newest tag: `git ls-remote --tags --sort=-v:refname <repository url>`, first `refs/tags/v<version>`. Compare it with `kaizero --version`. When the installed version is older, suggest the upgrade and, on a yes, run the install commands above again: `brew upgrade` for a Homebrew install, the curl lines otherwise. Done when `kaizero --version` shows the latest version.
3. **Suggest the fleet command.** `N` is `python3 <skill dir>/scripts/fleet.py cores`: the CPU cores minus 2, at least 2 (8 cores give 6). Kaizero commits on its own to the current branch and runs `claude` unattended with permissions auto-approved, so `git status --porcelain` must be empty first; when it is not, commit the pending changes without asking (`git add -A`, `git commit -m "qa-write-tests: commit spec, test cases and setup files before the parallel run"`). Ask the user to run this in another terminal, outside this session, from the test project root, to watch the fleet work, and to say when it runs:

   ```
   kz-tmux N KAIZERO_LINK=node_modules,.env-seed kaizero ./<test cases folder>/todo.md --local-merge
   ```
4. **Monitor the progress.** When the user says the fleet runs, start `python3 <skill dir>/scripts/fleet.py watch <test cases folder>/todo.md` in the background and stream its lines into the chat, from the main session the user reads (in Claude Code, a Monitor on the command with `timeout_ms` 3600000, re-armed on expiry while the run lasts). Each line shows how many test cases are done, the test cases that just landed, the rate per hour and the estimated completion time. The chat already shows each Monitor line, so a progress line ends the turn with no text of yours. The script exits when no `[ ]` line is left; then go to **Finish**.

The Claude Code sessions Kaizero starts build each test case by the **Write one test case** section, reached through the instruction file's isolated-run instructions.

## Subagent mode

Main is the agent running this skill; a subagent is a fresh agent with a self-contained prompt. Main alone writes `todo.md`, the Playwright config and the setup file; a subagent writes only its own test file and its own test case file's marks.

1. **Set the pace.** `N` is `python3 <skill dir>/scripts/fleet.py cores`: at most N subagents run at once. A worktree carries committed files only, so `git status --porcelain` must be empty first; when it is not, commit the pending changes without asking (`git add -A`, `git commit -m "qa-write-tests: commit spec, test cases and setup files before the parallel run"`).
2. **Start one subagent per work-list line**, in `todo.md` order, as slots free up. For each: `git worktree add ../<project>-wt/<ID> -b qa/<ID>` from the current branch, link `node_modules` and `.env-seed` from the main checkout into the worktree, and brief the subagent with the test case ID, the worktree path, and the instruction to read the instruction file's `## Isolated runs` section, start its own environment, and build the test case by this skill's **Write one test case** section.
3. **Take each result.** A subagent returns the files it wrote, the criteria it ticked, and each criterion left unticked with the reason. Main merges the branch into the current branch one at a time, sets the test case's `todo.md` mark by the mark rule, removes the worktree, and tells the user `Step <k> of <N>: <ID> done`.

Done when no `[ ]` line is left; go to **Finish**.

## Sequential mode

Main writes the work list one test case at a time, in `todo.md` order, in this session, on the app answering at `BASE_URL` from `.env`. One writer at a time keeps the app's state consistent. For each: build by **Write one test case**, set the mark, commit the test file, the ticked `<ID>.md` and `todo.md` (`git add -- <those paths>`, `git commit -m "qa-write-tests: <ID>"`), tell the user `Step <k> of <N>: <ID> done`. Done when no `[ ]` line is left; go to **Finish**.

## Write one test case

Done when the test file exists at the test case's `**Test file:**` path, passes twice in a row in every project its `**Projects:**` lists, every acceptance criterion it asserts is ticked, and the `todo.md` mark is set.

1. **Read `<ID>.md` in full.** Its How to build section (Arrange, Act, Cleanup, the Test file rules block) and its acceptance criteria are the whole spec.
2. **Start the app environment.** In the parallel modes, follow the `## Isolated runs` section of the instruction file: start the environment of this test case first, stop it as the last action on the test case. In sequential mode the app already runs at `BASE_URL`.
3. **Prepare the logins.** A test that uses a role needs `npx playwright test --project=setup` run once; it saves `.auth/<role>.json`. A test that starts logged out runs with `--no-deps`.
4. **Inspect the pages the Act steps visit.** Use a session named `<ID>`; a logged-in role reuses its saved session:

   ```bash
   jq .cookies .auth/<role>.json > "$TMPDIR/<ID>.cookies.json"
   $B --session <ID> goto $BASE_URL/<login path>
   $B --session <ID> cookie-import "$TMPDIR/<ID>.cookies.json"
   $B --session <ID> goto $BASE_URL/<page>
   $B --session <ID> snapshot -i
   $B --session <ID> stop
   ```

   The snapshot gives each element's role and name; write locators with `getByRole`, then `getByLabel` and `getByText`. A test case that tests the login itself logs in through the form.
5. **Write the test file** from the Test file rules block, line by line; a test file that already exists (a test case reset to `[ ]` after a change) is rewritten from the current test case. Line 1 is the output of `python3 <skill dir>/../qa-write-test-cases/scripts/qa_tickets.py hash <test-case.md>`. Every test title starts with `<ID>: `. Each acceptance criterion becomes at least one assertion; each `Absence check:` criterion becomes an assertion that the unwanted outcome is absent.
6. **Run it** in every project the test case lists: `npx playwright test <Test file> --project=<project> --repeat-each=2`. Fix the test until it passes; a failure that the scenario cannot explain is an app defect: keep the criterion unticked and report it.
7. **Tick the criteria.** Change `- [ ]` to `- [x]` in `<ID>.md` for each criterion the passing test asserts, and for the `Output test file contains comment` criterion once line 1 is in place. Ticking leaves the hash unchanged; confirm with `python3 <skill dir>/../qa-write-test-cases/scripts/qa_tickets.py check <test-case.md>`.
8. **Set the mark.** `[x]` when every criterion is ticked; `[?]` when some stay unticked (a missing credential, an app defect), with the reason named in the test case's `### Implementation notes` section. Main sets the mark in the parallel modes where it owns `todo.md`; in sequential mode the same agent sets it.

## Finish

Done when both gate commands from **Start** exit 0, `npx playwright test --list` exits 0, and no `[ ]` line is left in `todo.md`. Run `python3 <skill dir>/scripts/fleet.py audit <test cases folder>/todo.md <test cases folder>`: it lists each done test case whose criteria are not all ticked (Kaizero ticks the box on landing either way). Set each listed test case's mark to `[?]`, then run it again; done when it exits 0. Commit the changed `todo.md` (`qa-write-tests: mark incomplete test cases`). Each `[?]` line left (also every `[?]` line a Kaizero run skipped) is listed; offer to retry them one at a time in **Sequential mode**.

Summarize: the test cases written, the `[?]` ones with their missing criteria, the app defects found, and where the tests are (`<tests root>`).

When the pack detection of [`references/pro-detection.md`](references/pro-detection.md) says `yes`, propose running the suite with the `qa-run-tests` skill on a fresh context, in a subagent. On a yes, start the subagent with the instruction to apply `qa-run-tests` from the test project root and return the test execution report's summary and its release gate.

## Support

If the user is stuck, hits a blocker, or finds a bug in this skill, follow [`support-banner.md`](support-banner.md).
