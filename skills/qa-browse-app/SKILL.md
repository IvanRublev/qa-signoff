---
name: qa-browse-app
description: "Headless Chromium driven one command at a time, built on the test project's Playwright: open pages, snapshot the accessibility tree with clickable @e refs, log in, emulate a Playwright device, read cookies. Use when a QA skill (qa-write-spec) crawls an app, or to inspect or screenshot a live page."
copyright: Ivan Rublev 2026
license: Apache-2.0
version: 0.2.2
---

`$B` stands for `node <skill dir>/scripts/qa-browse-app.mjs`, where `<skill dir>` is this skill's base directory, the folder holding this SKILL.md (the path this file was opened from, without `SKILL.md`; when that path is unknown, the folder a file search for `qa-browse-app/SKILL.md` finds). Write it out in full in every command; it is not a shell variable to set. Run every `$B` command from the test project root: qa-browse-app loads Playwright from that project's `node_modules`. Every browser command takes `--session <name>`: `$B --session <name> <command> [args...]` (see Sessions).

## Setup check

Run `$B check` once before the first command.

- `READY: Playwright <version>` (exit 0): go on.
- `NEEDS_SETUP: <reason>` (exit 2): stop. Show the user the reason and the `Run:` / `Then:` commands it prints, and wait for them to run those commands and say so. Then run `$B check` again.

Every other command fails the same way, with `NEEDS_SETUP`, when the setup breaks later.

## Sessions

- **One session name per agent or crawl**, such as `admin-desktop`: ASCII letters, digits, `-` and `_`, up to 64 characters. Pass the same name on every command of that agent or crawl: `$B --session admin-desktop goto https://example.test/`. A command without `--session` fails (exit 2) with a message showing how to pass it.
- **Sessions are isolated and run in parallel.** Each has its own cookies, localStorage, sessionStorage, IndexedDB, device, extra headers, tabs, @e refs, frame and console, network and dialog logs. Commands in one session run in order; commands in different sessions run at the same time.
- **A new session** starts on first use with the default desktop profile (1280x720, no touch), empty storage and one blank tab.
- **Stop your session when done:** `$B --session <name> stop`.
- **New session warning.** A command that has to start its session, because it is the first use of the name or the session was lost (30 minutes idle, `stop --all`, or Chromium died), prints `Warning: started a new qa-browse-app session "<name>" (cookies, device and tabs reset)` on stderr. The device, login and tabs of earlier commands are gone: run `$B --session <name> device "<Playwright profile>"` for the current profile and log in again. `device` and `restart` start a session silently.

## How the browser behaves

- **One daemon per project.** The first command starts it; it holds one Chromium browser for that project root, and every session is a browser context in it. A session closes after 30 minutes idle or on `$B --session <name> stop`; the daemon exits with its last session, when Chromium dies, or on `$B stop --all`.
- **Changing the profile starts a clean session.** `device`, `useragent` and `viewport --scale` each leave the session with empty cookies, localStorage, sessionStorage and IndexedDB, and one blank tab; log in again after them. Other sessions are untouched. Extra headers set with `header` and the other profile settings stay. `viewport WxH` keeps the session. `state load` restores a saved session.
- **Restart.** `$B --session <name> restart` gives that session the default desktop profile (1280x720, no extra headers), empty storage and one blank tab, and prints `restarted session <name>`. A session whose commands time out twice in a row is stuck in a page script: restart it, then run `device` and log in again.
- **Refs.** `snapshot` numbers interactive elements `@e1`, `@e2`, …; pass a ref wherever a command takes a selector. Refs belong to the last snapshot of the current page: navigating, switching tab, or switching frame clears them. A stale ref fails with "not in the last snapshot"; take a new snapshot.
- **Selectors** are Playwright selectors: CSS (`input[name=u]`), `text=Sign in`, `role=button[name="Save"]`.
- **Dialogs** are dismissed unless `dialog-accept` ran just before; `dialog` lists each one and how it was answered.
- **Exit codes:** 0 ok; 1 the command failed (message on stderr); 2 setup or usage error. A `Warning:` line on stderr doesn't fail the command.

## Devices

`$B --session <name> device "<Playwright profile>"` applies the profile the way the Playwright projects do: viewport, user agent, `isMobile` (mobile layout viewport, `<meta viewport>` honored), touch, and device scale. It starts a clean session and prints `Device <name>: <W>x<H> @ <scale>x, <mobile|desktop>, <touch|no touch>; session cleared`. Two differences from a Playwright test run:

- The engine is always Chromium. A WebKit or Firefox profile (`iPhone 13`, `Desktop Safari`) gets that device's screen and user agent in Chromium; engine-specific behavior is left to the tests.
- Device scale is capped at 3: a profile above it runs at 3, with a `Warning:` naming the profile.

An unknown profile name fails with the closest Playwright profile names.

`$B devices "<profile>" …` groups profiles by breakpoint without starting the daemon or needing `--session`: one `desktop: <profiles>` or `mobile: <profiles>` line per breakpoint, in the order given. The first profile on a line is that breakpoint's crawl profile.

## Commands

| Area | Command | What it does |
|---|---|---|
| Navigation | `goto <url>` | Open a URL; prints the final URL and status. A route that downloads a file exits 1 with `Download is starting`: the route exists |
| | `back`, `forward`, `reload` | History and reload |
| | `url` | Current URL |
| | `load-html <file> [--wait-until load\|domcontentloaded\|networkidle]` | Show a local HTML file |
| Snapshot | `snapshot [-i] [-c] [-d N] [-s sel] [-D] [-a [-o path]]` | Accessibility tree with @e refs. `-i` interactive elements only, `-c` drop unnamed structural nodes, `-d` depth limit, `-s` scope to a selector, `-D` diff against the previous snapshot, `-a` annotated screenshot of the refs |
| Reading | `text` | Visible text |
| | `links` | Every link as `text → absolute href` |
| | `html [sel]` | Outer HTML of an element, or the page |
| | `forms` | Forms and fields as JSON (password values hidden) |
| | `accessibility` | Full ARIA tree, no refs |
| | `media [--images\|--videos\|--audio] [sel]` | Media elements as JSON |
| | `data [--jsonld\|--og\|--meta\|--twitter]` | Structured data as JSON |
| Inspection | `js <expression> [--out file]` | Evaluate in the page; prints the result |
| | `eval <file> [--out file]` | Evaluate a JavaScript file |
| | `css <sel> <property>` | Computed style value |
| | `attrs <sel>` | Attributes as JSON |
| | `is <visible\|hidden\|enabled\|disabled\|checked\|editable\|focused> <sel>` | `true` or `false` |
| | `cookies` | Session cookies as JSON |
| | `storage`, `storage set <key> <value>` | localStorage and sessionStorage |
| | `console [--clear\|--errors]`, `network [--clear]`, `dialog [--clear]` | Logs since the session started |
| | `perf` | Load timings |
| Interaction | `click <sel>`, `hover <sel>`, `tap <sel>` | Pointer; `tap` needs a touch device |
| | `fill <sel> <value>`, `select <sel> <value>`, `upload <sel> <file>...` | Form input |
| | `type <text>`, `press <key>` | Keyboard on the focused element |
| | `scroll [sel]` | Scroll an element into view, or to the bottom |
| | `wait <sel\|--networkidle\|--load>` | Wait up to 15 s |
| | `dialog-accept [text]`, `dialog-dismiss` | Answer the next dialog |
| Session | `device "<profile>"`, `devices "<profile>"…` | See Devices |
| | `viewport [WxH] [--scale 1-3]`, `useragent <string>` | Set one property; `--scale` and `useragent` start a clean session |
| | `cookie <name>=<value>`, `cookie-import <json file>` | Add cookies |
| | `header <name>:<value>` | Extra header on every request |
| | `state save\|load <name>` | Save or restore cookies, localStorage and tabs |
| Visual | `screenshot [--viewport] [--clip x,y,w,h] [--selector sel] [sel] [path]` | Full-page PNG unless narrowed to the viewport, a clip, or one element (`--selector sel` or a bare `sel`); prints the path |
| | `pdf [path] [--format letter\|a4\|legal]` | Print to PDF |
| | `responsive [prefix]` | Screenshots at 375x812, 768x1024, 1280x720 |
| | `diff <url1> <url2>` | Line diff of two pages' text |
| Tabs | `tabs`, `tab <n>`, `newtab [url]`, `closetab [n]` | `tabs` marks the active tab with `*` |
| Frames | `frame <sel\|--name n\|--url part\|main>` | Later commands run inside that iframe until `frame main` |
| Batch | `chain` | Reads `[["goto","…"],["snapshot","-i"]]` on stdin, runs in order in the session, prints one JSON array with a result per command, stops at the first failure |
| Daemon | `check` | See Setup check; needs no `--session`. `check`, `devices`, `status` and `stop` never start the daemon |
| | `min-playwright` | Prints the oldest Playwright version this skill works with (`1.49.0`); other skills read the minimum from here. Needs no project and no `--session` |
| | `status` | Without `--session`: one line per session, `<name>: <n> tab(s), active <url>, <W>x<H>@<scale>x <mobile\|desktop>`, `no sessions` while the daemon has none, or `not running`. With `--session <name>`: that session's line, or `no session <name>` |
| | `stop`, `stop --all` | `--session <name> stop` closes that session (`stopped session <name>`, or `no session <name>`); the daemon exits with the last one. `stop --all` closes every session and the daemon (`stopped`, or `not running`) |
| | `restart` | `--session <name> restart`: that session restarts with the default profile; see How the browser behaves |

## Support

If the user is stuck, hits a blocker, or finds a bug in this skill, follow [`support-banner.md`](support-banner.md).
