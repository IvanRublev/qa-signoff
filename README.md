# QA Signoff

Point an AI agent at your web app and get reviewed test cases and a Playwright regression suite, ready for release sign-off.

QA Signoff is for small SaaS teams, consultancies and software houses that ship UI-heavy products to paying customers or clients. It gives you a regression suite and a release sign-off without a bigger QA department. On a web app, a fleet of agents wrote the Playwright tests about 4× faster than a QA engineer and at least 2× cheaper than a Playwright test agency ([full report](https://github.com/IvanRublev/kimai-qa-playwright-report)). The suite and its sign-off record go to your client at delivery as proof of what was tested.

The agent crawls your app as each user role, drafts the test cases a QA engineer would plan, checks them for gaps and overlap, and turns them into Playwright tests you keep in your repository. You keep the judgment calls: choose the roles, devices and approvals, decide which findings matter, and sign off. The agent takes the crawling, the drafting and the repetitive test code, so QA Signoff is a speedup tool for the person who knows what matters.

## What you get

Start with `qa-signoff`. It reads where your test project stands and runs the stages that are left. After a change to the app it runs the change loop: re-crawl, update the affected test cases, rewrite their tests, run again.

[QA Signoff Pro](https://go.ivanrublev.com/get-qa-signoff-pro) steps are marked as `Pro:` in the following diagram.

```
                        ┌────────────────────────────────────────┐
                        │               qa-signoff               │
                        │    (entry point: reads the project,    │
                        │     runs the stages that are left)     │
                        └────────────────────┬───────────────────┘
                                             │
            ┌────────────────────────────────┼────────────────────────────────┐
            ▼                                ▼                                ▼
┌──────────────────────┐         ┌──────────────────────┐         ┌──────────────────────┐
│       1. PLAN        │         │       2. WRITE       │         │        3. RUN        │
│    qa-plan-tests     │         │    qa-write-tests    │         │ npx playwright test  │
├──────────────────────┤         ├──────────────────────┤         ├──────────────────────┤
│ qa-write-spec        │         │ one Playwright test  │         │ Pro: qa-run-tests    │
│ qa-write-test-cases  │         │ per test case,       │         │ report per run,      │
│ qa-review-test-cases │ ──────► │ one at a time        │ ──────► │ regressions, flaky,  │
│ qa-browse-app        │         │ Pro: in parallel     │         │ release gate         │
│ (crawls your app)    │         │                      │         │                      │
└───────────┬──────────┘         └───────────┬──────────┘         └───────────┬──────────┘
            │                                │                                │
qa-spec.md, test-cases/              tests/*.spec.ts                      sign-off

App changed? qa-signoff runs the loop again: plan (re-crawl, update) → write → run.
Pro adds isolated parallel writing, run reports, regression and flaky-test tracking.
```

| Skill | What it does |
|---|---|
| `qa-signoff` | Entry point. Picks the stages, tells you what to expect and do, and ends with what a sign-off consists of |
| `qa-plan-tests` | Collects every choice up front (roles, desktop and mobile devices, approvals), then runs the next three skills unattended |
| `qa-write-spec` | Crawls the live app per role and device and writes `qa-spec.md`, a map of the pages and journeys worth testing |
| `qa-write-test-cases` | Turns the spec into a prioritized test case backlog, with an OWASP Top 10:2025 security pass |
| `qa-review-test-cases` | Checks the backlog against the spec and your app code for coverage gaps and overlap |
| `qa-write-tests` | Writes one Playwright test per test case, one at a time |
| `qa-browse-app` | Headless browser the other skills use to look at your pages |

## What you need

- A git repository with a Playwright project (`npm init playwright@latest` sets one up).
- Your app running locally, and its source code for the review step.
- Credentials for each user role.

## Install

### Option 1: CLI install (recommended)

Use [npx skills](https://github.com/vercel-labs/skills) to install the skills:

```bash
# Install all skills
npx skills add IvanRublev/qa-signoff

# List the skills first
npx skills add IvanRublev/qa-signoff --list
```

The CLI detects which agents you have installed and asks where to install. When you run it from inside an agent session, name the agent: `npx skills add IvanRublev/qa-signoff -a claude-code`.

To update, run `npx skills update` (add `-g` for a global install).

### Option 2: Plugin, extension, or agent-specific install

#### Claude Code

```
/plugin marketplace add IvanRublev/qa-signoff
/plugin install qa-signoff@qa-signoff
```

The plugin installs all skills. To pick up new releases later, run `/plugin marketplace update qa-signoff`.

#### OpenAI Codex

```bash
codex plugin marketplace add IvanRublev/qa-signoff
```

Then open a Codex session, run `/plugins` and select `qa-signoff` to install all skills. To pick up new releases later, run `codex plugin marketplace upgrade`.

#### Gemini CLI

```bash
gemini extensions install https://github.com/IvanRublev/qa-signoff
```

To update, run `gemini extensions update qa-signoff`.

#### Antigravity

```bash
agy plugin install https://github.com/IvanRublev/qa-signoff
```

To update, run `agy plugin uninstall qa-signoff` and install again.

#### Grok

```bash
grok plugin install IvanRublev/qa-signoff --trust
grok plugin enable qa-signoff
```

Grok keeps hooks and skills inactive without `--trust`, and keeps plugins off until `grok plugin enable`. To update, run `grok plugin update qa-signoff`.

#### GitHub Copilot (VS Code and Copilot CLI)

Copilot reads the skills natively:

```bash
npx skills add IvanRublev/qa-signoff -a github-copilot        # this project
npx skills add IvanRublev/qa-signoff -a github-copilot -g     # all projects
```

To update, run `npx skills update` (add `-g` for a global install).

#### OpenCode

```bash
git clone https://github.com/IvanRublev/qa-signoff ~/.config/opencode/vendor/qa-signoff
mkdir -p ~/.config/opencode/skills
cp -R ~/.config/opencode/vendor/qa-signoff/skills/* ~/.config/opencode/skills/
```

To update, run `git -C ~/.config/opencode/vendor/qa-signoff pull` and copy the skill folders again. If `XDG_CONFIG_HOME` is set, use that directory in place of `~/.config`.

#### Zed

Clone the repository and copy the skill folders into the user skills directory:

```bash
git clone https://github.com/IvanRublev/qa-signoff
mkdir -p ~/.agents/skills
cp -R qa-signoff/skills/* ~/.agents/skills/
```

#### Hermes

Install every skill, since `qa-signoff` drives the others:

```bash
for s in qa-signoff qa-plan-tests qa-write-spec qa-write-test-cases qa-review-test-cases qa-write-tests qa-browse-app; do
  hermes skills install IvanRublev/qa-signoff/skills/$s
done
```

To update, run `hermes skills update <skill>` for each of them.

#### Kimi Code CLI

Start a Kimi Code session, then:

1. Run `/plugins`.
2. Choose **Custom**.
3. Paste `https://github.com/IvanRublev/qa-signoff` and press `Enter`.
4. Choose **Trust and install**.

To update, run `/plugins`, move the cursor to **QA Signoff** and press `R`.


#### Qwen Code

```bash
qwen extensions install IvanRublev/qa-signoff
```

To update, run `qwen extensions update qa-signoff`.


To update, run `git pull` and copy the skill folders again.

### Option 4: Clone and Copy

Clone the repository and copy the skill folders into your agent's skills folder:

```bash
git clone https://github.com/IvanRublev/qa-signoff.git
cp -r qa-signoff/skills/* .agents/skills/
```

## Use

In your test project, ask your agent to run `qa-signoff`.

## Go further with [QA Signoff Pro](https://go.ivanrublev.com/get-qa-signoff-pro)

Pro adds what turns a test suite into a sign-off:

- **Parallel writing without collisions.** Each agent builds its tests on its own copy of the app and database, so one agent's data never breaks another agent's test.
- **A report folder for every run.** Each failed test gets a screenshot and its own short report, ready to hand to a developer or attach to a client handover.
- **Regression and flaky-test tracking in one CSV.** Every test case, role and device gets a ✔ or ❌ for each run, newest first. Each regression is flagged per test, and tests that keep flipping between pass and fail are marked flaky, so you see what broke since the last release and which results you can rely on.
- **A release gate.** The test execution report says PASS or BLOCKED, with the regressions listed first.

See the output of Pro on a real project, with its tracking CSV, execution report and run logs [here](https://github.com/IvanRublev/kimai-qa-playwright-report#1-what-was-built).

Installing Pro installs both packs, this one included. [Get QA Signoff Pro](https://go.ivanrublev.com/get-qa-signoff-pro).

## Support

Stuck or blocked? Write to support@ivanrublev.com. Found a bug? [File an issue](https://github.com/IvanRublev/qa-signoff/issues).

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
