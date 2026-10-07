#!/usr/bin/env node
/*
qa-browse-app: a headless Chromium the QA skills drive one command at a time.

The first command starts a daemon that holds the browser. Every browser command names a session
(--session <name>, anywhere in the args): its own cookies, storage, device, tabs and @e refs, which
persist between calls. Sessions run in parallel. Run every command from the test project root:
Playwright is loaded from that project's node_modules.

Usage:
    node qa-browse-app.mjs --session <name> <command> [args...]
    node qa-browse-app.mjs status         every session, one line each
    node qa-browse-app.mjs stop --all     close every session and the daemon
    node qa-browse-app.mjs check          READY (exit 0), or NEEDS_SETUP and the commands to run (exit 2)
    node qa-browse-app.mjs min-playwright  the oldest Playwright version this skill works with, e.g. 1.49.0
    node qa-browse-app.mjs devices "<Playwright profile>"...   desktop:/mobile: breakpoint lines, no daemon
    node qa-browse-app.mjs --self-test

Exit codes: 0 ok; 1 the command failed; 2 setup or usage error.
*/

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MAX_SCALE = 3; // device scale cap, as qa-write-spec has always crawled with
const MIN_PLAYWRIGHT = '1.49.0'; // locator.ariaSnapshot(), which snapshot is built on
const SELF = fileURLToPath(import.meta.url);

class SetupError extends Error {}

function versionAtLeast(v, min) {
  const a = v.split('.').map(Number), b = min.split('.').map(Number);
  for (let i = 0; i < 3; i++) if ((a[i] || 0) !== b[i]) return (a[i] || 0) > b[i];
  return true;
}

// Playwright from the project in dir: {pw, version}, or a SetupError naming the commands to run.
function loadPlaywright(dir) {
  const req = createRequire(path.join(path.resolve(dir), 'package.json'));
  for (const name of ['@playwright/test', 'playwright']) {
    let version;
    try { version = req(`${name}/package.json`).version; } catch { continue; }
    if (!versionAtLeast(version, MIN_PLAYWRIGHT)) {
      throw new SetupError(`${name} ${version} is installed; qa-browse-app needs ${MIN_PLAYWRIGHT} or newer\n` +
        'Run: npm i -D @playwright/test@latest\nThen: npx playwright install chromium');
    }
    return { pw: req(name), version };
  }
  throw new SetupError(`no Playwright installed in ${path.resolve(dir)}\n` +
    'Run: npm i -D @playwright/test@latest\nThen: npx playwright install chromium');
}

// The install that fixes a failed Chromium launch: the browser itself, or the host libraries it needs.
function chromiumFix(message) {
  return /Host system is missing dependencies|error while loading shared libraries/.test(message)
    ? 'Run: npx playwright install --with-deps chromium  (needs sudo on Linux)' : 'Run: npx playwright install chromium';
}

async function check(dir) {
  if (Number(process.versions.node.split('.')[0]) < 18) {
    throw new SetupError(`Node ${process.versions.node} is installed; qa-browse-app needs Node 18 or newer\n` +
      'Run: install Node 18 or newer from https://nodejs.org');
  }
  const { pw, version } = loadPlaywright(dir);
  try {
    const browser = await pw.chromium.launch();
    await browser.close();
  } catch (e) {
    throw new SetupError(`Playwright ${version} has no working Chromium: ${e.message.split('\n')[0]}\n${chromiumFix(e.message)}`);
  }
  return `READY: Playwright ${version}`;
}

// `devices`: the breakpoint of each profile, grouped as "desktop: A, B" / "mobile: C" lines.
function devices(dir, names) {
  if (!names.length) throw new UsageError('usage: devices "<Playwright profile>" ...');
  const { pw } = loadPlaywright(dir);
  const groups = new Map();
  for (const name of names) {
    const bp = profile(pw, name).isMobile ? 'mobile' : 'desktop';
    groups.set(bp, [...(groups.get(bp) || []), name]);
  }
  return [...groups].map(([bp, list]) => `${bp}: ${list.join(', ')}`).join('\n');
}

function profile(pw, name) {
  const d = pw.devices[name];
  if (d) return d;
  const close = closeMatches(name, Object.keys(pw.devices));
  throw new Error(`unknown Playwright profile "${name}"; close matches: ${close.join(', ') || 'none'}`);
}

class UsageError extends Error {}

// ---------------------------------------------------------------- daemon

const IDLE_MS = 30 * 60 * 1000;
const TIMEOUT_MS = Number(process.env.QA_BROWSE_TIMEOUT_MS) || 15000; // per action, wait, and js/eval

// The daemon's state file (port and token). Its lock and `state save` files sit next to it.
function statePath(dir) {
  if (process.env.QA_BROWSE_STATE) return process.env.QA_BROWSE_STATE;
  const key = ['win32', 'darwin'].includes(process.platform) ? path.resolve(dir).toLowerCase() : path.resolve(dir);
  const hash = [...key].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7).toString(16);
  return path.join(stateDir(), `${hash}.json`);
}

// A per-user 0700 directory, so another local user can't plant a state file or read a saved session or screenshot.
function stateDir() {
  const dir = path.join(os.tmpdir(), `qa-browse-app-${os.userInfo().uid}`);
  try { fs.mkdirSync(dir, { mode: 0o700 }); } catch (e) { if (e.code !== 'EEXIST') throw e; }
  if (process.platform === 'win32') return dir; // ponytail: Windows temp is per-user already; no ACL check
  const st = fs.lstatSync(dir);
  if (!st.isDirectory() || st.uid !== process.getuid() || st.mode & 0o077) {
    throw new SetupError(`${dir} must be a directory only you can access: not a symlink, owned by you, mode 700\n` +
      `Then: delete ${dir} and run the command again, or set TMPDIR to a directory only you can write`);
  }
  return dir;
}

const SESSION_NAME = /^[A-Za-z0-9_-]{1,64}$/;

// One named session: a browser context of the daemon's Chromium. Its commands (COMMANDS below) run one at a time.
class Session {
  constructor(pw, browser, name) {
    this.pw = pw;
    this.browser = browser;
    this.name = name;
    this.opts = { viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1, isMobile: false, hasTouch: false };
    this.headers = {};
    this.pages = [];
    this.active = 0;
    this.frame = null;
    this.refs = new Map();
    this.lastSnapshot = null;
    this.consoleLog = [];
    this.networkLog = [];
    this.dialogLog = [];
    this.nextDialog = null;
  }

  async start() {
    await this.newContext();
    await this.context.newPage();
  }

  close() {
    clearTimeout(this.idle);
    return this.context.close().catch(() => {});
  }

  line() {
    const v = this.opts.viewport;
    return `${this.name}: ${this.pages.length} tab(s), active ${this.pages[this.active]?.url() ?? 'none'}, ` +
      `${v.width}x${v.height}@${this.opts.deviceScaleFactor}x ${this.opts.isMobile ? 'mobile' : 'desktop'}`;
  }

  async newContext(storageState) {
    this.context = await this.browser.newContext({ ...this.opts, storageState, extraHTTPHeaders: this.headers });
    this.context.setDefaultTimeout(TIMEOUT_MS);
    this.context.on('page', (p) => this.watch(p));
  }

  watch(page) {
    if (!this.pages.includes(page)) this.pages.push(page);
    page.on('console', (m) => this.consoleLog.push(`[${m.type()}] ${m.text()}`));
    page.on('response', (r) => this.networkLog.push(`${r.status()} ${r.request().method()} ${r.url()}`));
    page.on('dialog', async (d) => {
      const next = this.nextDialog;
      this.nextDialog = null;
      this.dialogLog.push(`${d.type()}: ${d.message()} → ${next ? next.action : 'dismissed'}`);
      if (next?.action === 'accepted') await d.accept(next.text); else await d.dismiss();
    });
    page.on('close', () => {
      const was = this.pages[this.active];
      if (this.pages.indexOf(page) < this.active) this.active--;
      this.pages = this.pages.filter((p) => p !== page);
      this.active = Math.min(this.active, Math.max(this.pages.length - 1, 0));
      if (this.pages[this.active] !== was) { this.refs.clear(); this.frame = null; }
    });
    page.on('framenavigated', (f) => {
      if (f === page.mainFrame() && page === this.pages[this.active]) { this.refs.clear(); this.frame = null; }
    });
  }

  async page() {
    if (!this.pages.length) await this.context.newPage();
    return this.pages[this.active];
  }

  // Where locators resolve: the frame `frame` chose, else the active page.
  async root() { return this.frame || this.page(); }

  async locate(sel) {
    if (!sel) throw new UsageError('missing selector');
    if (/^@e\d+$/.test(sel)) {
      const loc = this.refs.get(sel);
      if (!loc) throw new Error(`${sel} is not in the last snapshot; run snapshot again`);
      return loc;
    }
    return (await this.root()).locator(sel);
  }

  // Rebuild the context with new options (device scale, user agent, device): a clean session with
  // one blank tab, or the saved {storage, urls} of `state load`. Extra headers carry over.
  async rebuild(opts, saved = {}) {
    Object.assign(this.opts, opts);
    await this.context.close();
    this.pages = [];
    this.frame = null;
    this.refs.clear();
    await this.newContext(saved.storage);
    for (const url of saved.urls?.length ? saved.urls : ['about:blank']) {
      const p = await this.context.newPage();
      if (url !== 'about:blank') await p.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => {});
    }
    this.active = 0;
  }
}

async function serve(dir) {
  const file = statePath(dir);
  let pw, browser;
  try {
    pw = loadPlaywright(dir).pw;
    browser = await pw.chromium.launch();
  } catch (e) {
    fs.writeFileSync(file, JSON.stringify({ error: e.message, setup: true }), { mode: 0o600 });
    return 2;
  }
  // A dead browser can't serve anything: exit, so each session's next command starts a new daemon and says so.
  browser.on('disconnected', () => shutdown());
  const crypto = await import('node:crypto');
  const token = crypto.randomBytes(24).toString('hex');
  const sessions = new Map(), queues = new Map(); // by session name; one command queue per session
  let idle, inFlight = 0, draining = false, closing = false;
  // The daemon exits with its last session, but not under a request still being answered: that one may be
  // creating a new session. Once exiting, it drops new connections unanswered, so their CLI retries elsewhere.
  const exitIfDone = () => { if (draining && !sessions.size && !inFlight) shutdown(); };
  // Close a session.
  const drop = (name) => {
    const s = sessions.get(name);
    if (!s) return;
    sessions.delete(name);
    s.close();
    draining = !sessions.size;
    exitIfDone();
  };
  // Run a command in its session, creating the session first if needed (restart: always).
  async function handle(name, args, stdin) {
    let s = sessions.get(name);
    const fresh = !s || args[0] === 'restart';
    if (fresh) {
      await s?.close();
      s = new Session(pw, browser, name);
      await s.start();
      sessions.set(name, s);
    }
    clearTimeout(s.idle);
    s.idle = setTimeout(() => drop(name), IDLE_MS);
    if (args[0] === 'restart') return { ok: true, out: `restarted session ${name}` };
    const reply = await runCommand(s, args, stdin);
    // device resets the session anyway, so a new one needs no warning there
    if (fresh && args[0] !== 'device') reply.warn = [`started a new qa-browse-app session "${name}" (cookies, device and tabs reset)`, reply.warn];
    return reply;
  }
  const server = http.createServer((req, res) => {
    inFlight++;
    res.on('close', () => { inFlight--; exitIfDone(); });
    if (closing) return res.destroy();
    if (req.headers.authorization !== `Bearer ${token}`) { req.resume(); return res.writeHead(403).end(); }
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      let session, args, stdin;
      try { ({ session, args, stdin } = JSON.parse(body)); } catch {}
      const named = typeof session === 'string' && SESSION_NAME.test(session);
      const free = ['ping', 'status', 'stop'].includes(args?.[0]); // these may go without a session
      if (!Array.isArray(args) || (session !== undefined && !named) || (!named && !free)) return res.writeHead(400).end();
      // The 200 headers go out before any work: a CLI that got them never retries, one that didn't may.
      res.writeHead(200, { 'content-type': 'application/json' }).flushHeaders();
      const reply = (r) => res.end(JSON.stringify(r));
      clearTimeout(idle);
      idle = setTimeout(shutdown, IDLE_MS);
      // ping, status and stop skip the queues, so a hung command can't block them
      if (args[0] === 'ping') return reply({ ok: true, out: 'pong' });
      if (args[0] === 'status') {
        return reply({ ok: true, out: named ? sessions.get(session)?.line() ?? `no session ${session}`
          : [...sessions.values()].map((s) => s.line()).join('\n') || 'no sessions' });
      }
      if (args[0] === 'stop') {
        if (!named) { reply({ ok: true, out: 'stopped' }); return shutdown(); }
        reply({ ok: true, out: sessions.has(session) ? `stopped session ${session}` : `no session ${session}` });
        return drop(session);
      }
      const queue = (queues.get(session) || Promise.resolve()).then(() => handle(session, args, stdin))
        .catch((e) => ({ ok: false, out: e.message.split('\n')[0] })).then(reply);
      queues.set(session, queue);
      queue.then(() => { if (queues.get(session) === queue) queues.delete(session); });
    });
  });
  async function shutdown() {
    if (closing) return;
    closing = true;
    try { if (JSON.parse(fs.readFileSync(file, 'utf8')).pid === process.pid) fs.unlinkSync(file); } catch {}
    server.close();
    // A renderer stuck in a page script can keep close() waiting; exit anyway, Chromium dies with us.
    await Promise.race([browser.close().catch(() => {}), new Promise((r) => setTimeout(r, 3000))]);
    process.exit(0);
  }
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
  server.listen(0, '127.0.0.1', () => {
    fs.writeFileSync(file, JSON.stringify({ port: server.address().port, token, pid: process.pid }), { mode: 0o600 });
    idle = setTimeout(shutdown, IDLE_MS);
  });
  return new Promise(() => {});
}

async function runCommand(session, args, stdin) {
  const [cmd, ...rest] = args;
  const spec = COMMANDS[cmd];
  session.warning = undefined;
  if (cmd === 'chain') return runChain(session, stdin);
  try {
    if (!spec) throw new UsageError(`unknown command: ${cmd} (see --help)`);
    const out = await spec.run(session, rest, stdin);
    return { ok: true, out: typeof out === 'string' ? out : JSON.stringify(out, null, 2), warn: session.warning };
  } catch (e) {
    return { ok: false, usage: e instanceof UsageError, out: e.message.split('\n')[0] };
  }
}

async function runChain(session, stdin) {
  let steps;
  try { steps = JSON.parse(stdin || ''); } catch { steps = null; }
  if (!Array.isArray(steps) || !steps.every(Array.isArray)) {
    return { ok: false, usage: true, out: 'chain: stdin must be a JSON array of [command, ...args] arrays' };
  }
  const results = [];
  for (const step of steps) {
    if (step[0] === 'chain' || step[0] === 'stop' || step[0] === 'restart') {
      results.push({ cmd: step[0], ok: false, out: `${step[0]} can't run inside chain` });
      break;
    }
    const r = await runCommand(session, step.map(String));
    results.push({ cmd: step[0], ok: r.ok, out: r.out });
    if (!r.ok) break;
  }
  return { ok: results.every((r) => r.ok), stdout: true, out: JSON.stringify(results, null, 2) };
}

// ---------------------------------------------------------------- commands

const COMMANDS = {
  status: { usage: 'status', about: 'Tabs, active URL and profile of this session, or of every session without --session',
    run: (s) => s.line() },
  stop: { usage: 'stop | stop --all', about: 'Close this session (the daemon exits with the last one); --all: every session and the daemon',
    run: () => { throw new Error('stop is answered by the daemon, outside the command queue'); } },
  goto: { usage: 'goto <url>', about: 'Open a URL in the active tab', async run(s, [url]) {
    if (!url) throw new UsageError('usage: goto <url>');
    const r = await (await s.page()).goto(url, { waitUntil: 'domcontentloaded' });
    return `Navigated to ${(await s.page()).url()} (${r ? r.status() : 'no response'})`;
  } },
  url: { usage: 'url', about: 'Print the current URL', async run(s) { return (await s.page()).url(); } },
  text: { usage: 'text', about: 'Visible page text, blank lines collapsed', async run(s) {
    return (await (await s.root()).locator('body').innerText()).replace(/\n\s*\n+/g, '\n\n').trim();
  } },
  links: { usage: 'links', about: 'Every link as "text → absolute href"', async run(s) {
    const links = await (await s.root()).locator('a[href]').evaluateAll((as) =>
      as.map((a) => `${(a.innerText || a.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ')} → ${a.href}`));
    return links.join('\n');
  } },
  wait: { usage: 'wait <sel|@ref|--networkidle|--load>', about: 'Wait for an element, network idle, or page load (15 s)',
    async run(s, [what]) {
      if (!what) throw new UsageError('usage: wait <sel|@ref|--networkidle|--load>');
      const page = await s.page();
      if (what === '--networkidle') await page.waitForLoadState('networkidle');
      else if (what === '--load') await page.waitForLoadState('load');
      else await (await s.locate(what)).first().waitFor();
      return 'ok';
    } },
  snapshot: { usage: 'snapshot [-i] [-c] [-d N] [-s sel] [-D] [-a [-o path]]',
    about: 'Accessibility tree; interactive elements get @e refs. -i interactive only, -c compact, -d depth, ' +
      '-s scope, -D diff against the previous snapshot, -a annotated screenshot (-o path)',
    run: snapshot },
  click: { usage: 'click <sel|@ref>', about: 'Click an element', async run(s, [sel]) {
    await (await s.locate(sel)).first().click();
    return `Clicked ${sel}`;
  } },
  fill: { usage: 'fill <sel|@ref> <value>', about: 'Replace an input\'s value', async run(s, [sel, ...value]) {
    await (await s.locate(sel)).first().fill(value.join(' '));
    return `Filled ${sel}`;
  } },
  press: { usage: 'press <key>', about: 'Press a key on the focused element (Enter, Tab, Escape, …)', async run(s, [key]) {
    if (!key) throw new UsageError('usage: press <key>');
    await (await s.page()).keyboard.press(key);
    return `Pressed ${key}`;
  } },
  cookies: { usage: 'cookies', about: 'Every cookie of the session as JSON', async run(s) {
    return s.context.cookies();
  } },
  device: { usage: 'device "<Playwright profile>"',
    about: `Emulate a Playwright device profile (viewport, user agent, isMobile, touch, scale up to ${MAX_SCALE}) in Chromium; starts a clean session with one blank tab`,
    async run(s, args) {
      const name = args.join(' ');
      const { defaultBrowserType, ...opts } = profile(s.pw, name); // the engine stays Chromium
      if (opts.deviceScaleFactor > MAX_SCALE) {
        s.warning = `${name} has device scale ${opts.deviceScaleFactor}; qa-browse-app uses ${MAX_SCALE}`;
        opts.deviceScaleFactor = MAX_SCALE;
      }
      await s.rebuild({ userAgent: undefined, ...opts });
      const v = s.opts.viewport;
      return `Device ${name}: ${v.width}x${v.height} @ ${s.opts.deviceScaleFactor}x, ` +
        `${s.opts.isMobile ? 'mobile' : 'desktop'}, ${s.opts.hasTouch ? 'touch' : 'no touch'}; session cleared`;
    } },
  viewport: { usage: `viewport [<WxH>] [--scale <1-${MAX_SCALE}>]`, about: 'Set the viewport size and optional device scale',
    async run(s, args) {
      const { flags, pos } = parseFlags(args, { '--scale': 'value' });
      const size = pos[0] ? pos[0].match(/^(\d+)x(\d+)$/) : null;
      if ((pos[0] && !size) || (!pos[0] && !flags['--scale'])) throw new UsageError('usage: viewport [<WxH>] [--scale <n>]');
      const viewport = size ? { width: Number(size[1]), height: Number(size[2]) } : s.opts.viewport;
      if (flags['--scale'] !== undefined) {
        const scale = Number(flags['--scale']);
        if (!(scale >= 1 && scale <= MAX_SCALE)) throw new UsageError(`viewport --scale must be between 1 and ${MAX_SCALE}`);
        await s.rebuild({ viewport, deviceScaleFactor: scale });
      } else {
        s.opts.viewport = viewport;
        for (const p of s.pages) await p.setViewportSize(viewport);
      }
      return `Viewport ${viewport.width}x${viewport.height} @ ${s.opts.deviceScaleFactor}x${flags['--scale'] ? '; session cleared' : ''}`;
    } },
  useragent: { usage: 'useragent <string>', about: 'Set the user agent; starts a clean session with one blank tab', async run(s, args) {
    if (!args.length) throw new UsageError('usage: useragent <string>');
    await s.rebuild({ userAgent: args.join(' ') });
    return `User agent: ${args.join(' ')}; session cleared`;
  } },
  js: { usage: 'js <expression> [--out <file>]', about: 'Evaluate a JavaScript expression in the page; prints the result',
    async run(s, args) {
      const { flags, pos } = parseFlags(args, { '--out': 'value' });
      if (!pos.length) throw new UsageError('usage: js <expression>');
      return evaluate(s, pos.join(' '), flags['--out']);
    } },

  // Navigation
  back: { usage: 'back', about: 'History back', async run(s) { return navigated(s, await (await s.page()).goBack()); } },
  forward: { usage: 'forward', about: 'History forward', async run(s) { return navigated(s, await (await s.page()).goForward()); } },
  reload: { usage: 'reload', about: 'Reload the page', async run(s) { return navigated(s, await (await s.page()).reload()); } },
  'load-html': { usage: 'load-html <file> [--wait-until load|domcontentloaded|networkidle]', about: 'Show a local HTML file as the page',
    async run(s, args) {
      const { flags, pos } = parseFlags(args, { '--wait-until': 'value' });
      if (!pos[0]) throw new UsageError('usage: load-html <file>');
      await (await s.page()).setContent(fs.readFileSync(pos[0], 'utf8'), { waitUntil: flags['--wait-until'] || 'load' });
      return `Loaded ${pos[0]}`;
    } },

  // Reading
  html: { usage: 'html [sel|@ref]', about: 'Outer HTML of an element, or the whole page', async run(s, [sel]) {
    return sel ? (await s.locate(sel)).first().evaluate((e) => e.outerHTML) : (await s.root()).content();
  } },
  forms: { usage: 'forms', about: 'Every form and its fields as JSON (password values hidden)', async run(s) {
    return (await s.root()).locator('form').evaluateAll((forms) => forms.map((f) => ({
      id: f.id || undefined, name: f.getAttribute('name') || undefined, action: f.action, method: f.method,
      fields: [...f.elements].filter((e) => e.name).map((e) => ({
        tag: e.tagName.toLowerCase(), name: e.name, type: e.type, required: e.required,
        value: e.type === 'password' ? (e.value ? '****' : '') : e.type === 'file' ? undefined : e.value,
      })),
    })));
  } },
  accessibility: { usage: 'accessibility', about: 'Full ARIA tree, no refs', async run(s) {
    return (await s.root()).locator('body').ariaSnapshot();
  } },
  media: { usage: 'media [--images|--videos|--audio] [sel]', about: 'Images, videos and audio as JSON', async run(s, args) {
    const { flags, pos } = parseFlags(args, { '--images': true, '--videos': true, '--audio': true });
    const all = !flags['--images'] && !flags['--videos'] && !flags['--audio'];
    const scope = pos[0] ? await s.locate(pos[0]) : (await s.root()).locator('body');
    const pick = (css) => scope.first().evaluate((root, css) => [...root.querySelectorAll(css)].map((e) => ({
      src: e.currentSrc || e.src, alt: e.alt, width: e.width || undefined, height: e.height || undefined,
    })), css);
    const out = {};
    if (all || flags['--images']) out.images = await pick('img');
    if (all || flags['--videos']) out.videos = await pick('video');
    if (all || flags['--audio']) out.audio = await pick('audio');
    return out;
  } },
  data: { usage: 'data [--jsonld|--og|--meta|--twitter]', about: 'Structured data: JSON-LD, Open Graph, meta, Twitter card',
    async run(s, args) {
      const { flags } = parseFlags(args, { '--jsonld': true, '--og': true, '--meta': true, '--twitter': true });
      const data = await (await s.root()).evaluate(() => {
        const metas = [...document.querySelectorAll('meta')].map((m) => [m.getAttribute('property') || m.name, m.content])
          .filter(([k]) => k);
        return {
          jsonld: [...document.querySelectorAll('script[type="application/ld+json"]')]
            .map((e) => { try { return JSON.parse(e.textContent); } catch { return e.textContent; } }),
          og: Object.fromEntries(metas.filter(([k]) => k.startsWith('og:'))),
          twitter: Object.fromEntries(metas.filter(([k]) => k.startsWith('twitter:'))),
          meta: Object.fromEntries(metas.filter(([k]) => !k.startsWith('og:') && !k.startsWith('twitter:'))),
        };
      });
      const keys = ['jsonld', 'og', 'meta', 'twitter'].filter((k) => flags[`--${k}`]);
      return keys.length ? Object.fromEntries(keys.map((k) => [k, data[k]])) : data;
    } },

  // Inspection
  eval: { usage: 'eval <file> [--out <file>]', about: 'Evaluate a JavaScript file in the page', async run(s, args) {
    const { flags, pos } = parseFlags(args, { '--out': 'value' });
    if (!pos[0]) throw new UsageError('usage: eval <file>');
    return evaluate(s, fs.readFileSync(pos[0], 'utf8'), flags['--out']);
  } },
  css: { usage: 'css <sel|@ref> <property>', about: 'Computed CSS value', async run(s, [sel, prop]) {
    if (!prop) throw new UsageError('usage: css <sel> <property>');
    return (await s.locate(sel)).first().evaluate((e, p) => getComputedStyle(e).getPropertyValue(p), prop);
  } },
  attrs: { usage: 'attrs <sel|@ref>', about: 'Element attributes as JSON', async run(s, [sel]) {
    return (await s.locate(sel)).first().evaluate((e) => Object.fromEntries([...e.attributes].map((a) => [a.name, a.value])));
  } },
  is: { usage: 'is <visible|hidden|enabled|disabled|checked|editable|focused> <sel|@ref>', about: 'Element state: true or false',
    async run(s, [prop, sel]) {
      const loc = (await s.locate(sel)).first();
      const checks = {
        visible: () => loc.isVisible(), hidden: () => loc.isHidden(), enabled: () => loc.isEnabled(),
        disabled: () => loc.isDisabled(), checked: () => loc.isChecked().catch(() => false), editable: () => loc.isEditable(),
        focused: () => loc.evaluate((e) => e === document.activeElement),
      };
      if (!checks[prop]) throw new UsageError(`is: unknown state ${prop}`);
      return String(await checks[prop]());
    } },
  console: { usage: 'console [--clear|--errors]', about: 'Console messages; --errors only errors and warnings', async run(s, args) {
    const { flags } = parseFlags(args, { '--clear': true, '--errors': true });
    if (flags['--clear']) { s.consoleLog = []; return 'cleared'; }
    return s.consoleLog.filter((l) => !flags['--errors'] || /^\[(error|warning)\]/.test(l)).join('\n');
  } },
  network: { usage: 'network [--clear]', about: 'Responses as "status method url"', async run(s, args) {
    if (parseFlags(args, { '--clear': true }).flags['--clear']) { s.networkLog = []; return 'cleared'; }
    return s.networkLog.join('\n');
  } },
  dialog: { usage: 'dialog [--clear]', about: 'Dialogs the page opened and how each was answered', async run(s, args) {
    if (parseFlags(args, { '--clear': true }).flags['--clear']) { s.dialogLog = []; return 'cleared'; }
    return s.dialogLog.join('\n');
  } },
  storage: { usage: 'storage | storage set <key> <value>', about: 'localStorage and sessionStorage as JSON, or set a localStorage key',
    async run(s, [sub, key, ...value]) {
      const root = await s.root();
      if (sub === 'set') {
        if (!key) throw new UsageError('usage: storage set <key> <value>');
        await root.evaluate(([k, v]) => localStorage.setItem(k, v), [key, value.join(' ')]);
        return `Set ${key}`;
      }
      return root.evaluate(() => ({ localStorage: { ...localStorage }, sessionStorage: { ...sessionStorage } }));
    } },
  perf: { usage: 'perf', about: 'Page load timings in ms', async run(s) {
    return (await s.page()).evaluate(() => {
      const n = performance.getEntriesByType('navigation')[0];
      if (!n) return {};
      const r = (v) => Math.round(v);
      return { ttfb: r(n.responseStart), domContentLoaded: r(n.domContentLoadedEventEnd), load: r(n.loadEventEnd),
        transferSize: n.transferSize, resources: performance.getEntriesByType('resource').length };
    });
  } },

  // Interaction
  select: { usage: 'select <sel|@ref> <value|label>', about: 'Choose a <select> option', async run(s, [sel, ...value]) {
    const v = value.join(' ');
    const loc = (await s.locate(sel)).first();
    await loc.selectOption(v).catch(() => loc.selectOption({ label: v }));
    return `Selected ${v}`;
  } },
  hover: { usage: 'hover <sel|@ref>', about: 'Hover an element', async run(s, [sel]) {
    await (await s.locate(sel)).first().hover();
    return `Hovered ${sel}`;
  } },
  type: { usage: 'type <text>', about: 'Type into the focused element', async run(s, args) {
    await (await s.page()).keyboard.type(args.join(' '));
    return 'Typed';
  } },
  scroll: { usage: 'scroll [sel|@ref]', about: 'Scroll an element into view, or to the page bottom', async run(s, [sel]) {
    if (sel) await (await s.locate(sel)).first().scrollIntoViewIfNeeded();
    else await (await s.root()).evaluate(() => scrollTo(0, document.body.scrollHeight));
    return 'Scrolled';
  } },
  tap: { usage: 'tap <sel|@ref>', about: 'Tap an element (needs a touch device, see device)', async run(s, [sel]) {
    await (await s.locate(sel)).first().tap();
    return `Tapped ${sel}`;
  } },
  upload: { usage: 'upload <sel|@ref> <file> [file...]', about: 'Set files on a file input', async run(s, [sel, ...files]) {
    if (!files.length) throw new UsageError('usage: upload <sel> <file> [file...]');
    for (const f of files) if (!fs.existsSync(f)) throw new Error(`file not found: ${f}`);
    await (await s.locate(sel)).first().setInputFiles(files);
    return `Uploaded ${files.length} file(s)`;
  } },
  cookie: { usage: 'cookie <name>=<value>', about: 'Set a cookie for the current page\'s site', async run(s, [pair]) {
    const eq = pair ? pair.indexOf('=') : -1;
    if (eq < 1) throw new UsageError('usage: cookie <name>=<value>');
    await s.context.addCookies([{ name: pair.slice(0, eq), value: pair.slice(eq + 1), url: (await s.page()).url() }]);
    return `Cookie set: ${pair.slice(0, eq)}`;
  } },
  'cookie-import': { usage: 'cookie-import <json file>', about: 'Add cookies from a JSON array (Playwright cookie format)',
    async run(s, [file]) {
      if (!file) throw new UsageError('usage: cookie-import <json file>');
      const url = (await s.page()).url();
      const cookies = JSON.parse(fs.readFileSync(file, 'utf8')).map((c) => (c.url || c.domain ? c : { ...c, url }));
      await s.context.addCookies(cookies);
      return `Imported ${cookies.length} cookie(s)`;
    } },
  header: { usage: 'header <name>:<value>', about: 'Send an extra HTTP header with every request', async run(s, [pair]) {
    const sep = pair ? pair.indexOf(':') : -1;
    if (sep < 1) throw new UsageError('usage: header <name>:<value>');
    s.headers[pair.slice(0, sep).trim()] = pair.slice(sep + 1).trim();
    await s.context.setExtraHTTPHeaders(s.headers);
    return `Header set: ${pair.slice(0, sep).trim()}`;
  } },
  'dialog-accept': { usage: 'dialog-accept [text]', about: 'Accept the next dialog (prompt text optional); dialogs are dismissed otherwise',
    async run(s, args) { s.nextDialog = { action: 'accepted', text: args.join(' ') || undefined }; return 'Next dialog: accept'; } },
  'dialog-dismiss': { usage: 'dialog-dismiss', about: 'Dismiss the next dialog', async run(s) {
    s.nextDialog = { action: 'dismissed' };
    return 'Next dialog: dismiss';
  } },

  // Visual
  screenshot: { usage: 'screenshot [--viewport] [--clip x,y,w,h] [--selector sel|@ref] [sel|@ref] [path]',
    about: 'PNG of the full page, the viewport, a clip, or one element; prints the path', async run(s, args) {
      const { flags, pos } = parseFlags(args, { '--viewport': true, '--clip': 'value', '--selector': 'value' });
      const isPath = (a) => /\.(png|jpe?g)$/i.test(a);
      const file = pos.find(isPath) || path.join(stateDir(), `qa-browse-app-${Date.now()}.png`);
      const sel = flags['--selector'] || pos.find((a) => !isPath(a));
      if (sel) await (await s.locate(sel)).first().screenshot({ path: file });
      else {
        const clip = flags['--clip'] && flags['--clip'].split(',').map(Number);
        await (await s.page()).screenshot({ path: file, fullPage: !flags['--viewport'] && !clip,
          clip: clip ? { x: clip[0], y: clip[1], width: clip[2], height: clip[3] } : undefined });
      }
      return `Screenshot: ${file}`;
    } },
  pdf: { usage: 'pdf [path] [--format letter|a4|legal]', about: 'Print the page to PDF', async run(s, args) {
    const { flags, pos } = parseFlags(args, { '--format': 'value' });
    const file = pos[0] || path.join(stateDir(), `qa-browse-app-${Date.now()}.pdf`);
    await (await s.page()).pdf({ path: file, format: flags['--format'] || 'letter' });
    return `PDF: ${file}`;
  } },
  responsive: { usage: 'responsive [prefix]', about: 'Full-page screenshots at 375x812, 768x1024 and 1280x720', async run(s, [prefix]) {
    const base = prefix || path.join(stateDir(), `qa-browse-app-responsive-${Date.now()}`);
    const page = await s.page();
    const out = [];
    for (const [name, width, height] of [['mobile', 375, 812], ['tablet', 768, 1024], ['desktop', 1280, 720]]) {
      await page.setViewportSize({ width, height });
      const file = `${base}-${name}.png`;
      await page.screenshot({ path: file, fullPage: true });
      out.push(`${name} ${width}x${height}: ${file}`);
    }
    await page.setViewportSize(s.opts.viewport);
    return out.join('\n');
  } },
  diff: { usage: 'diff <url1> <url2>', about: 'Line diff of two pages\' text', async run(s, [a, b]) {
    if (!b) throw new UsageError('usage: diff <url1> <url2>');
    const page = await s.context.newPage();
    try {
      const text = async (url) => { await page.goto(url, { waitUntil: 'domcontentloaded' }); return page.locator('body').innerText(); };
      return lineDiff(await text(a), await text(b));
    } finally { await page.close(); }
  } },

  // Tabs
  tabs: { usage: 'tabs', about: 'Open tabs; * marks the active one', async run(s) {
    await s.page();
    return (await Promise.all(s.pages.map(async (p, i) =>
      `${i === s.active ? '*' : ' '} ${i + 1} ${await p.title().catch(() => '')} ${p.url()}`))).join('\n');
  } },
  tab: { usage: 'tab <n>', about: 'Switch to tab n', async run(s, [n]) {
    const i = Number(n) - 1;
    if (!s.pages[i]) throw new UsageError(`no tab ${n}`);
    s.active = i;
    s.frame = null;
    s.refs.clear();
    await s.pages[i].bringToFront();
    return `Switched to tab ${n}: ${s.pages[i].url()}`;
  } },
  newtab: { usage: 'newtab [url]', about: 'Open a tab and switch to it', async run(s, [url]) {
    await s.page();
    const p = await s.context.newPage();
    s.active = s.pages.indexOf(p);
    s.frame = null;
    s.refs.clear();
    if (url) await p.goto(url, { waitUntil: 'domcontentloaded' });
    return `Opened tab ${s.active + 1}: ${p.url()}`;
  } },
  closetab: { usage: 'closetab [n]', about: 'Close tab n, or the active tab', async run(s, [n]) {
    const i = n ? Number(n) - 1 : s.active;
    if (!s.pages[i]) throw new UsageError(`no tab ${n}`);
    await s.pages[i].close();
    return `Closed tab ${i + 1}`;
  } },

  // Meta
  frame: { usage: 'frame <sel|@ref|--name n|--url pattern|main>', about: 'Run later commands inside an iframe, or back in main',
    async run(s, args) {
      const { flags, pos } = parseFlags(args, { '--name': 'value', '--url': 'value' });
      const page = await s.page();
      s.refs.clear();
      if (pos[0] === 'main') { s.frame = null; return 'Main frame'; }
      let frame;
      if (flags['--name']) frame = page.frame({ name: flags['--name'] });
      else if (flags['--url']) frame = page.frames().find((f) => f.url().includes(flags['--url']));
      else if (pos[0]) frame = await (await (await s.locate(pos[0])).first().elementHandle()).contentFrame();
      else throw new UsageError('usage: frame <sel|@ref|--name n|--url pattern|main>');
      if (!frame) throw new Error('no such frame');
      s.frame = frame;
      return `Frame: ${frame.url()}`;
    } },
  state: { usage: 'state save|load <name>', about: 'Save or restore cookies, localStorage and open tabs under a name',
    async run(s, [sub, name]) {
      if (!['save', 'load'].includes(sub) || !name || !/^[\w.-]+$/.test(name)) throw new UsageError('usage: state save|load <name>');
      const file = `${statePath(process.cwd())}.state-${name}.json`;
      if (sub === 'save') {
        fs.writeFileSync(file, JSON.stringify({ storage: await s.context.storageState(), urls: s.pages.map((p) => p.url()) }),
          { mode: 0o600 });
        return `Saved state ${name}`;
      }
      if (!fs.existsSync(file)) throw new Error(`no saved state ${name}`);
      const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
      await s.rebuild({}, saved);
      return `Loaded state ${name}`;
    } },
  chain: { usage: 'chain  (JSON on stdin)', about: 'Run [[cmd, ...args], ...] from stdin in order; prints one JSON array of results; stops at the first error',
    run: () => { throw new UsageError('chain reads its commands from stdin'); } },
  restart: { usage: 'restart', about: 'Restart this session: default desktop profile, empty storage, one blank tab',
    run: () => { throw new Error('restart is answered by the daemon, before the command runs'); } },
};

async function navigated(s, response) {
  return `Navigated to ${(await s.page()).url()} (${response ? response.status() : 'no response'})`;
}

async function evaluate(s, source, out) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`evaluate timed out after ${TIMEOUT_MS} ms`)), TIMEOUT_MS);
  });
  const result = await Promise.race([(await s.root()).evaluate(source), timeout]).finally(() => clearTimeout(timer));
  const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2) ?? 'undefined';
  if (!out) return text;
  fs.writeFileSync(out, text);
  return `Wrote ${out}`;
}

function closeMatches(name, names) {
  const dist = (a, b) => {
    let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      for (let j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
    return prev[b.length];
  };
  const q = name.toLowerCase();
  return names.map((n) => [n, dist(q, n.toLowerCase())]).filter(([, d]) => d <= Math.max(3, q.length / 2))
    .sort((a, b) => a[1] - b[1]).slice(0, 3).map(([n]) => n);
}

// Flags from args: spec maps a flag to true (boolean) or 'value' (takes the next arg).
function parseFlags(args, spec) {
  const flags = {}, pos = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (!(a in spec)) {
      if (a.startsWith('-') && a.length > 1 && !/^-\d/.test(a)) throw new UsageError(`unknown flag: ${a}`);
      pos.push(a);
    } else if (spec[a] === 'value') {
      if (i + 1 >= args.length) throw new UsageError(`${a} needs a value`);
      flags[a] = args[++i];
    } else flags[a] = true;
  }
  return { flags, pos };
}

const INTERACTIVE = new Set(['button', 'link', 'textbox', 'searchbox', 'checkbox', 'radio', 'combobox', 'listbox',
  'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'tab', 'switch', 'slider', 'spinbutton', 'treeitem']);
const STRUCTURAL = /^\s*- (generic|group|list|listitem|none|presentation|region|paragraph)(:)?$/;

async function snapshot(s, args) {
  const { flags } = parseFlags(args, { '-i': true, '-c': true, '-d': 'value', '-s': 'value', '-D': true, '-a': true, '-o': 'value' });
  const root = await s.root();
  const scope = (flags['-s'] ? await s.locate(flags['-s']) : root.locator('body')).first();
  const tree = (await scope.ariaSnapshot()).split('\n');
  s.refs.clear();
  // A ref's locator is its occurrence index among the matches of its locator, so count every line,
  // shown or filtered: a named element among same-role same-name elements, an unnamed one among
  // every element of its role (getByRole(role) matches named ones too).
  const seen = new Map();
  const lines = [], interactive = [];
  for (const raw of tree) {
    // Split the YAML key (role, name, attributes) from its value. A name with ": " or a leading quote makes
    // ariaSnapshot single-quote the whole key: unwrap it. An unquoted key ends at the first ": " or a final ":".
    const quoted = raw.match(/^(\s*- )'((?:[^']|'')*)'(.*)$/);
    const [key, value] = quoted ? [quoted[1] + quoted[2].replace(/''/g, "'"), quoted[3]] : raw.match(/^(.*?)((?:: .*|:)?)$/).slice(1);
    const line = key + value;
    const m = key.match(/^(\s*)- ([a-z]+)(?: "((?:[^"\\]|\\.)*)"| (\/(?:.*\/)?)(?=$| \[))?/);
    const isRef = m && INTERACTIVE.has(m[2]);
    // Playwright leaves a name such as /home/ unquoted: shown as its name, located by role index like an unnamed one.
    const name = !isRef ? undefined : m[3] !== undefined ? JSON.parse(`"${m[3]}"`) : m[4];
    let locator;
    if (isRef) {
      const count = (key) => { const n = seen.get(key) || 0; seen.set(key, n + 1); return n; };
      const roleIndex = count(m[2]);
      locator = m[3] === undefined ? scope.getByRole(m[2]).nth(roleIndex)
        : scope.getByRole(m[2], { name, exact: true }).nth(count(`${m[2]}\u0000${name}`));
    }
    const depth = (m ? m[1] : line.match(/^\s*/)[0]).length / 2;
    if (flags['-d'] !== undefined && depth > Number(flags['-d'])) continue;
    if (flags['-c'] && STRUCTURAL.test(line)) continue;
    if (isRef) {
      const [, indent, role] = m;
      const ref = `@e${s.refs.size + 1}`;
      s.refs.set(ref, locator);
      const label = `${ref} [${role}]${name === undefined ? '' : ` "${name}"`}`;
      interactive.push(label);
      lines.push(`${indent}- ${label}${line.slice(m[0].length)}`);
    } else lines.push(line);
  }
  const plain = tree.join('\n');
  let out = flags['-i'] ? interactive.join('\n') : lines.join('\n');
  if (flags['-D']) out = s.lastSnapshot === null ? '(first snapshot stored as the diff baseline)' : lineDiff(s.lastSnapshot, plain);
  s.lastSnapshot = plain;
  if (flags['-a']) out += `\nAnnotated screenshot: ${await annotate(s, flags['-o'])}`;
  return out;
}

// Line diff: "- " removed, "+ " added, "  " kept.
function lineDiff(before, after) {
  const a = before.split('\n'), b = after.split('\n');
  const lcs = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) { out.push(`  ${a[i++]}`); j++; }
    else if (j < b.length && (i >= a.length || lcs[i][j + 1] >= lcs[i + 1][j])) out.push(`+ ${b[j++]}`);
    else out.push(`- ${a[i++]}`);
  }
  return out.join('\n');
}

// Screenshot with a labeled box over every ref of the last snapshot.
async function annotate(s, file) {
  const page = await s.page();
  const boxes = [];
  for (const [ref, loc] of s.refs) {
    const box = await loc.boundingBox({ timeout: 1000 }).catch(() => null);
    if (box) boxes.push({ ref, ...box });
  }
  await page.evaluate((bs) => {
    const layer = document.createElement('div');
    layer.id = '__qa_browse_annotations';
    layer.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;z-index:2147483647';
    for (const b of bs) {
      const d = document.createElement('div');
      d.style.cssText = `position:absolute;left:${b.x + scrollX}px;top:${b.y + scrollY}px;width:${b.width}px;` +
        `height:${b.height}px;outline:2px solid red;font:bold 11px sans-serif;color:#fff`;
      d.innerHTML = `<span style="background:red;padding:0 2px">${b.ref}</span>`;
      layer.append(d);
    }
    document.body.append(layer);
  }, boxes);
  const out = file || path.join(stateDir(), `qa-browse-app-annotated-${Date.now()}.png`);
  await page.screenshot({ path: out, fullPage: true });
  await page.evaluate(() => document.getElementById('__qa_browse_annotations')?.remove());
  return out;
}

// ---------------------------------------------------------------- CLI

function readState(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}

// ponytail: a fixed ceiling per call (chain gets more); raise it if a legit command outlasts it.
// node:http, not fetch: fetch gives up after 300 s and can throw uncaught when a daemon drops the socket.
// An error before the daemon's response headers, other than a timeout, is marked notStarted: the command never ran.
async function post(state, payload, ms = payload.args[0] === 'chain' ? 30 * 60e3 : 5 * 60e3) {
  return new Promise((resolve, reject) => {
    let started = false;
    const req = http.request({ host: '127.0.0.1', port: state.port, method: 'POST', timeout: ms,
      headers: { authorization: `Bearer ${state.token}` } }, (res) => {
      started = true;
      let body = '';
      res.setEncoding('utf8').on('data', (c) => { body += c; }).on('error', reject).on('end', () => {
        if (res.statusCode !== 200) return reject(Object.assign(new Error(`daemon answered HTTP ${res.statusCode}`), { status: res.statusCode }));
        try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
      });
    });
    // A timed-out command may be running: count it as started, so it is never retried.
    req.on('timeout', () => { started = true; req.destroy(new Error(`no answer from the daemon within ${ms / 1000} s`)); });
    req.on('error', (e) => reject(Object.assign(e, { notStarted: !started })));
    req.end(JSON.stringify(payload));
  });
}

async function alive(state) {
  if (!state?.port) return false;
  try { return (await post(state, { args: ['ping'] }, 2000)).ok; } catch { return false; }
}

const START_MS = 30e3;

// Take the spawn lock (<state>.lock holding our pid), or drop a stale one for the next try.
function takeLock(lock) {
  try { fs.writeFileSync(lock, String(process.pid), { flag: 'wx', mode: 0o600 }); return true; } catch (e) { if (e.code !== 'EEXIST') throw e; }
  try {
    let dead = false;
    try { process.kill(Number(fs.readFileSync(lock, 'utf8')), 0); } catch (e) { dead = e.code === 'ESRCH'; }
    if (dead || Date.now() - fs.statSync(lock).mtimeMs > START_MS) fs.rmSync(lock, { force: true });
  } catch {}
  return false;
}

// The running daemon, or a new one. One command spawns it; others racing it wait for its state file.
async function ensureDaemon(dir) {
  const file = statePath(dir), lock = `${file}.lock`;
  const state = readState(file);
  if (await alive(state)) return state;
  loadPlaywright(dir); // a missing or old Playwright fails here, before a daemon starts
  let owner = false;
  try {
    for (let i = 0; i < START_MS / 100; i++) {
      if (!owner && takeLock(lock)) {
        owner = true;
        const s = readState(file); // a racer may have started it before we took the lock
        if (await alive(s)) return s;
        fs.rmSync(file, { force: true });
        spawn(process.execPath, [SELF, '--server'], { cwd: dir, detached: true, stdio: 'ignore', windowsHide: true }).unref();
      }
      await new Promise((r) => setTimeout(r, 100));
      const s = readState(file);
      if (s?.setup) {
        if (owner) fs.rmSync(file, { force: true });
        throw new SetupError(`${s.error.split('\n')[0]}\n${chromiumFix(s.error)}`);
      }
      if (s?.port && await alive(s)) return s;
    }
  } finally { if (owner) fs.rmSync(lock, { force: true }); }
  throw new Error('the qa-browse-app daemon did not start within 30 s');
}

async function main(argv) {
  const at = argv.indexOf('--session'); // the first one names the session; the command never sees it
  const session = at < 0 ? undefined : argv[at + 1] ?? '';
  if (at >= 0) argv = [...argv.slice(0, at), ...argv.slice(at + 2)];
  const [cmd] = argv;
  const dir = process.cwd();
  if (!cmd || cmd === '-h' || cmd === '--help') {
    process.stdout.write(fs.readFileSync(SELF, 'utf8').split('*/')[0].replace(/^[^]*?\/\*\n/, ''));
    return cmd ? 0 : 2;
  }
  try {
    if (cmd === 'check') { console.log(await check(dir)); return 0; }
    if (cmd === 'min-playwright') { console.log(MIN_PLAYWRIGHT); return 0; }
    if (cmd === 'devices') { console.log(devices(dir, argv.slice(1))); return 0; }
    if (session !== undefined && !SESSION_NAME.test(session)) {
      throw new UsageError(`invalid session name "${session}": use ASCII letters, digits, - and _ (up to 64)`);
    }
    const all = cmd === 'stop' && argv[1] === '--all';
    if (session === undefined && !all && cmd !== 'status') {
      throw new UsageError('--session <name> is required: every qa-browse-app command runs in a named browser session ' +
        '(its own cookies, storage, device and tabs).\nPick one name per agent or crawl, e.g. admin-desktop, and pass it on ' +
        `every command:\n  node ${SELF} --session admin-desktop goto https://example.test/`);
    }
    const payload = { session: all ? undefined : session, args: argv };
    if (cmd === 'status' || cmd === 'stop') { // never start a daemon: one that is gone or exiting has nothing to show or stop
      const state = readState(statePath(dir));
      const reply = state?.port && await post(state, payload, 5000).catch(() => null);
      console.log(reply?.ok ? reply.out : session === undefined || all ? 'not running' : `no session ${session}`);
      return 0;
    }
    const state = await ensureDaemon(dir);
    payload.stdin = cmd === 'chain' ? fs.readFileSync(0, 'utf8') : undefined;
    // A daemon that exited before answering never ran the command: start one and retry. A connection lost after
    // the answer began fails instead, since the command may have run.
    const reply = await post(state, payload).catch(async (e) => {
      if (!e.notStarted) throw e;
      return post(await ensureDaemon(dir), payload);
    });
    for (const w of [reply.warn].flat()) if (w) console.error(`Warning: ${w}`);
    if (reply.ok || reply.stdout) { if (reply.out) console.log(reply.out); return reply.ok ? 0 : 1; }
    console.error(`Error: ${reply.out}`);
    return reply.usage ? 2 : 1;
  } catch (e) {
    if (e instanceof SetupError) { console.log(`NEEDS_SETUP: ${e.message}`); return 2; }
    console.error(`Error: ${e.message}`);
    return e instanceof UsageError ? 2 : 1;
  }
}

// ---------------------------------------------------------------- self-test

// The fixture app: / (links, a modal, a form), /login (sets sid), /home (needs sid), /logout.
const SET_STORAGE = `(async () => { document.cookie = 'c=1; path=/'; localStorage.setItem('l', '1');
  sessionStorage.setItem('s', '1'); await new Promise((r) => { const q = indexedDB.open('db', 1);
  q.onupgradeneeded = () => q.result.createObjectStore('s'); q.onsuccess = () => { const t = q.result.transaction('s', 'readwrite');
  t.objectStore('s').put('1', 'k'); t.oncomplete = () => { q.result.close(); r(); }; }; }); return 'set'; })()`;
const READ_STORAGE = `(async () => ({ cookie: document.cookie, l: localStorage.getItem('l'), s: sessionStorage.getItem('s'),
  idb: await new Promise((r) => { const q = indexedDB.open('db'); // an upgrade means no db: abort, don't create one
    q.onupgradeneeded = () => q.transaction.abort(); q.onerror = () => r(null); q.onsuccess = () => { const db = q.result;
    const g = db.transaction('s').objectStore('s').get('k'); g.onsuccess = () => { db.close(); r(g.result ?? null); }; }; }) }))()`;

let hits = 0; // GET /hit requests, to count how often a command really ran

function fixtureApp(http) {
  const page = (body, headers = {}) => [200, { 'content-type': 'text/html', ...headers },
    `<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Fixture</title></head><body>${body}</body></html>`];
  const routes = {
    'GET /': () => page(`<h1>Start</h1><a href="/login">Log in</a> <a href="/other">Other page</a>
      <button onclick="document.getElementById('m').hidden=false">Open modal</button>
      <div id="m" hidden><a href="/secret">Secret</a></div>`),
    'GET /other': () => page('<h1>Other</h1><p>other text</p>'),
    'GET /icons': () => page(`<button onclick="document.title='SAVE'">Save</button>
      <button onclick="document.title='ICON'"><svg width="10" height="10"></svg></button>`),
    'GET /slash': () => page('<a href="/">/</a> <a href="/home/">/home/</a> <a href="/x">/x/: y/</a>' +
      '<button aria-label="/q/">/r/</button> <button aria-label="/q2/">/r/: s/</button>'),
    'GET /hit': () => { hits++; return page('<p>hit</p>'); },
    'GET /quoted': () => page(`<button onclick="document.title='SAVE'">Save: now</button>
      <button onclick="document.title='ICON1'"><svg width="10" height="10"></svg></button>
      <button onclick="document.title='QUOTED'">It's "quoted": yes</button>
      <button onclick="document.title='ICON2'"><svg width="10" height="10"></svg></button>`),
    'GET /nested': () => page('<ul><li><a href="#deep">Edit</a></li></ul><a href="#top">Edit</a>'),
    'GET /echo': (req) => page(`<p>x-test=${req.headers['x-test']}</p>`),
    'GET /kitchen': () => page(`<h1 style="color: rgb(255, 0, 0)">Kitchen</h1>
      <script type="application/ld+json">{"@type":"Thing","name":"kitchen"}</script>
      <img src="/pic.png" alt="A picture">
      <form id="f"><select name="c"><option>red</option><option>blue</option></select>
        <input name="t" id="t" data-x="1" required><input type="file" name="up" id="up"></form>
      <button id="hov" onmouseover="this.textContent='hovered'">Hover me</button>
      <button id="tap" ontouchend="this.textContent='tapped'">Tap me</button>
      <button id="al" onclick="document.getElementById('al').textContent = confirm('Sure?') ? 'yes' : 'no'">Confirm</button>
      <button id="log" onclick="console.error('boom')">Log</button>
      <iframe name="inner" src="/other"></iframe>
      <div style="height:3000px"></div><p id="bottom">bottom</p>`,
      { }),
    'GET /login': () => page(`<form method="post" action="/login"><label>Username <input name="u"></label>
      <label>Password <input name="p" type="password"></label><button>Sign in</button></form>`),
    'POST /login': () => [303, { location: '/home', 'set-cookie': 'sid=s3cret; Path=/; HttpOnly' }, ''],
    'GET /home': (req) => /sid=s3cret/.test(req.headers.cookie || '')
      ? page('<h1>Welcome</h1><a href="/logout">Log out</a>') : [303, { location: '/login' }, ''],
    'GET /logout': () => [303, { location: '/', 'set-cookie': 'sid=; Path=/; Max-Age=0' }, ''],
  };
  return http.createServer((req, res) => {
    req.resume();
    req.on('end', () => {
      const [status, headers, body] = (routes[`${req.method} ${req.url}`] || (() => [404, {}, 'not found']))(req);
      res.writeHead(status, headers).end(body);
    });
  });
}

async function selfTest() {
  const assert = (await import('node:assert/strict')).default;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'qa-browse-app-test-'));
  const env = { ...process.env, QA_BROWSE_STATE: path.join(tmp, 'daemon.json'), QA_BROWSE_TIMEOUT_MS: '3000' };
  // Async, so the fixture app in this process keeps answering while a command runs. sh passes args as
  // given; run and ok run in session t, okIn(name) in another.
  const sh = (args, { input, ...opts } = {}) => new Promise((resolve) => {
    const p = spawn(process.execPath, [SELF, ...args], { cwd: process.cwd(), env, ...opts });
    let out = '', err = '';
    p.stdout.on('data', (d) => { out += d; });
    p.stderr.on('data', (d) => { err += d; });
    p.on('close', (code) => resolve({ code, out, err }));
    p.stdin.end(input);
  });
  const run = (args, opts) => sh(['--session', 't', ...args], opts);
  const okIn = (name) => async (...args) => {
    const r = await sh(['--session', name, ...args]);
    assert.equal(r.code, 0, `${name}: ${args.join(' ')} exited ${r.code}: ${r.out}${r.err}`);
    return r.out;
  };
  const ok = okIn('t');
  const stopAll = () => sh(['stop', '--all']);
  const status = async (...args) => (await sh([...args, 'status'])).out;
  const app = fixtureApp(http);
  await new Promise((resolve) => app.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${app.address().port}`;
  const tests = {
    'goto and url': async () => {
      assert.match(await ok('goto', `${base}/`), /200/);
      assert.equal((await ok('url')).trim(), `${base}/`);
    },
    'the daemon keeps the page between calls': async () => {
      await ok('goto', `${base}/other`);
      assert.match(await ok('text'), /other text/);
    },
    'status and stop --all': async () => {
      assert.match(await status(), /^t: 1 tab\(s\), active .*\/other, 1280x720@1x desktop$/m);
      assert.equal((await stopAll()).out, 'stopped\n');
      assert.equal(await status(), 'not running\n');
      assert.equal((await stopAll()).out, 'not running\n');
      const r = await run(['goto', `${base}/`]); // restarts on demand, and says so
      assert.equal(r.code, 0, r.err);
      assert.match(r.err, /^Warning: started a new qa-browse-app session "t" \(cookies, device and tabs reset\)$/m);
      assert.doesNotMatch((await run(['url'])).err, /Warning/);
    },
    'a command without --session exits 2 and shows how to pass it': async () => {
      const r = await sh(['goto', `${base}/`]);
      assert.equal(r.code, 2);
      assert.equal(r.err, 'Error: --session <name> is required: every qa-browse-app command runs in a named browser session ' +
        '(its own cookies, storage, device and tabs).\nPick one name per agent or crawl, e.g. admin-desktop, and pass it on ' +
        `every command:\n  node ${SELF} --session admin-desktop goto https://example.test/\n`);
      assert.equal((await sh(['stop'])).code, 2);
      assert.equal((await sh(['fly'])).code, 2);
    },
    'a bad session name is refused; the flag works anywhere': async () => {
      for (const name of ['a b', 'x!', '', 'a'.repeat(65)]) {
        const r = await sh(['url', '--session', name]);
        assert.equal(r.code, 2, name);
        assert.equal(r.err, `Error: invalid session name "${name}": use ASCII letters, digits, - and _ (up to 64)\n`);
      }
      assert.equal((await sh(['url', '--session', 't'])).out, `${base}/\n`);
      assert.equal((await sh(['devices', 'Pixel 5', '--session', 'x!'])).out, 'mobile: Pixel 5\n'); // ignored
    },
    'two sessions keep separate cookies, storage, device and refs at once': async () => {
      const a = okIn('a'), b = okIn('b');
      await a('device', 'Pixel 5');
      await Promise.all([a('goto', `${base}/icons`), b('goto', `${base}/`)]);
      await a('js', SET_STORAGE);
      const ref = (await a('snapshot', '-i')).match(/(@e\d+) \[button\] "Save"/)?.[1];
      assert.match(await b('snapshot', '-i'), /"Log in"/); // b's snapshot leaves a's refs alone
      assert.deepEqual(JSON.parse(await b('js', READ_STORAGE)), { cookie: '', l: null, s: null, idb: null });
      assert.deepEqual(JSON.parse(await a('js', READ_STORAGE)), { cookie: 'c=1', l: '1', s: '1', idb: '1' });
      assert.equal((await a('js', 'innerWidth')).trim(), '393');
      assert.equal((await b('js', 'innerWidth')).trim(), '1280');
      await a('click', ref);
      assert.equal((await a('js', 'document.title')).trim(), 'SAVE');
      assert.equal((await b('js', 'document.title')).trim(), 'Fixture');
      assert.match((await sh(['--session', 'c', 'click', ref])).err, /not in the last snapshot/);
      await sh(['--session', 'c', 'stop']);
    },
    'status lists every session; --session x status shows one': async () => {
      await okIn('b')('goto', `${base}/other`);
      const all = await status();
      assert.match(all, /^a: 1 tab\(s\), active .*\/icons, 393x727@2\.75x mobile$/m);
      assert.match(all, new RegExp(`^b: 1 tab\\(s\\), active ${base}/other, 1280x720@1x desktop$`, 'm'));
      assert.equal(await status('--session', 'b'), `b: 1 tab(s), active ${base}/other, 1280x720@1x desktop\n`);
      assert.equal(await status('--session', 'zz'), 'no session zz\n');
    },
    'a slow command in one session does not hold up another session': async () => {
      const t0 = Date.now();
      const slow = sh(['--session', 'a', 'js', 'new Promise((r) => setTimeout(() => r("slow"), 2000))']).then((r) => ({ ...r, at: Date.now() - t0 }));
      await new Promise((r) => setTimeout(r, 300));
      assert.equal((await okIn('b')('url')).trim(), `${base}/other`);
      const fast = Date.now() - t0;
      const s = await slow;
      assert.equal(s.out, 'slow\n', s.err);
      assert.ok(fast < s.at - 1000, `b took ${fast} ms, a ${s.at} ms`);
    },
    'stopping one session keeps the others; stopping the last ends the daemon': async () => {
      assert.equal(await okIn('a')('stop'), 'stopped session a\n');
      assert.equal(await okIn('a')('stop'), 'no session a\n');
      const r = await sh(['--session', 'b', 'url']);
      assert.equal(r.out, `${base}/other\n`);
      assert.doesNotMatch(r.err, /Warning/);
      assert.doesNotMatch(await status(), /^a:/m);
      await stopAll();
      await okIn('b')('url');
      assert.match(await status(), /^b: /m);
      assert.equal(await okIn('b')('stop'), 'stopped session b\n');
      assert.equal(await status(), 'not running\n');
      assert.equal(await status('--session', 'b'), 'no session b\n');
    },
    'the new-session warning comes on first use, not on device or restart': async () => {
      const w = await sh(['--session', 'w1', 'url']);
      assert.equal(w.err, 'Warning: started a new qa-browse-app session "w1" (cookies, device and tabs reset)\n');
      assert.equal((await sh(['--session', 'w1', 'url'])).err, '');
      const d = await sh(['--session', 'w2', 'device', 'Pixel 5']);
      assert.equal(d.code, 0, d.err);
      assert.equal(d.err, '');
      const r = await sh(['--session', 'w3', 'restart']);
      assert.equal(r.out, 'restarted session w3\n');
      assert.equal(r.err, '');
      await okIn('w1')('goto', `${base}/other`);
      assert.equal(await okIn('w1')('restart'), 'restarted session w1\n');
      assert.match(await status('--session', 'w1'), /^w1: 1 tab\(s\), active about:blank, 1280x720@1x desktop\n$/);
      assert.match(await status('--session', 'w2'), /393x727@2\.75x mobile/);
      await stopAll();
    },
    'two first commands at once share one new daemon': async () => {
      await stopAll();
      const [a, b] = await Promise.all([run(['newtab', `${base}/`]), run(['newtab', `${base}/other`])]);
      assert.equal(a.code + b.code, 0, a.err + b.err);
      assert.equal([a, b].filter((r) => /Warning: started a new qa-browse-app session "t"/.test(r.err)).length, 1);
      const tabs = await ok('tabs');
      assert.match(tabs, new RegExp(`${base}/$`, 'm'));
      assert.match(tabs, /\/other$/m);
    },
    'a stale spawn lock from a dead process is removed': async () => {
      await stopAll();
      fs.writeFileSync(`${env.QA_BROWSE_STATE}.lock`, '99999999');
      const r = await run(['url']);
      assert.equal(r.code, 0, r.err);
      assert.match(r.err, /Warning: started a new qa-browse-app session/);
      assert.ok(!fs.existsSync(`${env.QA_BROWSE_STATE}.lock`));
    },
    'when Chromium dies, the next command starts a clean session with the warning': async () => {
      await ok('goto', `${base}/`);
      const { pid } = JSON.parse(fs.readFileSync(env.QA_BROWSE_STATE, 'utf8'));
      const { execFileSync } = await import('node:child_process');
      for (const kid of execFileSync('pgrep', ['-P', String(pid)]).toString().trim().split('\n')) process.kill(Number(kid), 'SIGKILL');
      for (let i = 0; i < 50 && fs.existsSync(env.QA_BROWSE_STATE); i++) await new Promise((r) => setTimeout(r, 100));
      const r = await run(['url']);
      assert.equal(r.code, 0, r.err);
      assert.equal(r.out.trim(), 'about:blank');
      assert.match(r.err, /Warning: started a new qa-browse-app session/);
    },
    'a malformed or unauthorized request is refused; the daemon stays up': async () => {
      await ok('goto', `${base}/`);
      const st = JSON.parse(fs.readFileSync(env.QA_BROWSE_STATE, 'utf8'));
      const send = (body, token = st.token) => fetch(`http://127.0.0.1:${st.port}/`,
        { method: 'POST', headers: { authorization: `Bearer ${token}` }, body }).then((r) => r.status);
      assert.equal(await send('{not json'), 400);
      assert.equal(await send('{}'), 400);
      assert.equal(await send('{"args":["url"]}', 'wrong'), 403);
      assert.equal(await send('{"args":["url"]}'), 400); // no session
      assert.equal(await send('{"session":"a b","args":["url"]}'), 400);
      assert.match(await status(), /^t: /m);
    },
    'the per-user state directory is created private; a shared or symlinked one is refused': async () => {
      const { QA_BROWSE_STATE, ...bare } = env;
      const at = (tmpdir) => sh(['status'], { env: { ...bare, TMPDIR: tmpdir } });
      const t1 = path.join(tmp, 't1'), t2 = path.join(tmp, 't2');
      fs.mkdirSync(t1);
      fs.mkdirSync(t2);
      assert.match((await at(t1)).out, /not running/);
      const dir = path.join(t1, `qa-browse-app-${process.getuid()}`);
      assert.equal(fs.statSync(dir).mode & 0o777, 0o700);
      fs.chmodSync(dir, 0o755);
      const shared = await at(t1);
      assert.equal(shared.code, 2);
      assert.match(shared.out, /^NEEDS_SETUP: .*qa-browse-app-\d+/);
      fs.chmodSync(dir, 0o700);
      fs.symlinkSync(dir, path.join(t2, `qa-browse-app-${process.getuid()}`));
      assert.equal((await at(t2)).code, 2);
    },
    'a missing-host-library launch error names the --with-deps install': async () => {
      assert.match(chromiumFix('browserType.launch:\n║ Host system is missing dependencies to run browsers. ║'),
        /^Run: npx playwright install --with-deps chromium/);
      assert.match(chromiumFix('error while loading shared libraries: libnss3.so'), /--with-deps/);
      assert.equal(chromiumFix('Executable doesn\'t exist at /x'), 'Run: npx playwright install chromium');
    },
    'devices groups profiles by breakpoint without starting a daemon': async () => {
      await stopAll();
      const r = await run(['devices', 'Desktop Chrome', 'Pixel 5', 'iPhone 13', 'Desktop Firefox']);
      assert.equal(r.code, 0, r.err);
      assert.equal(r.out, 'desktop: Desktop Chrome, Desktop Firefox\nmobile: Pixel 5, iPhone 13\n');
      assert.equal(r.err, '');
      assert.equal(await ok('devices', 'Pixel 5', 'Desktop Chrome'), 'mobile: Pixel 5\ndesktop: Desktop Chrome\n');
      assert.equal(await status(), 'not running\n');
      const bad = await run(['devices', 'Pixel 5', 'iphone 13']);
      assert.equal(bad.code, 1);
      assert.match(bad.err, /^Error: unknown Playwright profile "iphone 13"; close matches: .*iPhone 13/);
      assert.equal((await run(['devices'])).code, 2);
      const none = await run(['devices', 'Pixel 5'], { cwd: tmp });
      assert.equal(none.code, 2);
      assert.match(none.out, /^NEEDS_SETUP: no Playwright installed/);
    },
    'links lists text and absolute href': async () => {
      await ok('goto', `${base}/`);
      const out = await ok('links');
      assert.match(out, new RegExp(`Log in → ${base}/login`));
      assert.match(out, new RegExp(`Other page → ${base}/other`));
    },
    'snapshot -i gives refs; clicking one opens the modal': async () => {
      await ok('goto', `${base}/`);
      await ok('wait', '--networkidle');
      const snap = await ok('snapshot', '-i');
      assert.doesNotMatch(snap, /Secret/); // hidden until the modal opens
      const ref = snap.match(/(@e\d+) \[button\] "Open modal"/)?.[1];
      assert.ok(ref, snap);
      await ok('click', ref);
      assert.match(await ok('snapshot', '-i'), /@e\d+ \[link\] "Secret"/);
    },
    'snapshot without -i shows the tree; -D diffs against the last one': async () => {
      await ok('goto', `${base}/other`);
      assert.match(await ok('snapshot'), /heading "Other"/);
      await ok('goto', `${base}/`);
      const diff = await ok('snapshot', '-D');
      assert.match(diff, /^- .*heading "Other"/m);
      assert.match(diff, /^\+ .*heading "Start"/m);
    },
    'log in with fill and press; the session cookie shows; logout clears it': async () => {
      await ok('goto', `${base}/login`);
      await ok('fill', 'input[name=u]', 'admin');
      await ok('fill', 'input[name=p]', 'pw');
      await ok('press', 'Enter');
      await ok('wait', '--load');
      assert.equal((await ok('url')).trim(), `${base}/home`);
      assert.match(await ok('cookies'), /"name": "sid"/);
      await ok('goto', `${base}/logout`);
      assert.doesNotMatch(await ok('cookies'), /"name": "sid"/);
    },
    'a ref to an unnamed element clicks that element, not a named one of the same role': async () => {
      await ok('goto', `${base}/icons`);
      const snap = await ok('snapshot', '-i');
      const ref = snap.match(/^(@e\d+) \[button\]$/m)?.[1];
      assert.ok(ref, snap);
      await ok('click', ref);
      assert.equal((await ok('js', 'document.title')).trim(), 'ICON');
    },
    'a name with ": " gets a ref, and the unnamed refs after it click their own element': async () => {
      await ok('goto', `${base}/quoted`);
      const snap = await ok('snapshot', '-i');
      assert.match(snap, /^@e\d+ \[button\] "Save: now"$/m);
      assert.match(snap, /^@e\d+ \[button\] "It's "quoted": yes"$/m);
      const icons = [...snap.matchAll(/^(@e\d+) \[button\]$/gm)].map((m) => m[1]);
      assert.equal(icons.length, 2, snap);
      await ok('click', icons[0]);
      assert.equal((await ok('js', 'document.title')).trim(), 'ICON1');
      await ok('click', icons[1]);
      assert.equal((await ok('js', 'document.title')).trim(), 'ICON2');
    },
    'output larger than a pipe buffer reaches a piped stdout whole': async () => {
      const r = await run(['js', "'x'.repeat(200000)"]);
      assert.equal(r.code, 0, r.err);
      assert.equal(r.out.length, 200001);
    },
    'stopping the last session does not kill another session starting at that moment': async () => {
      for (let i = 0; i < 10; i++) { // stagger the stop, so one round lands while q's session is being created
        await okIn('r')('url');
        const q = sh(['--session', 'q', 'goto', `${base}/`]);
        await new Promise((res) => setTimeout(res, i * 40));
        const [qr, r] = await Promise.all([q, sh(['--session', 'r', 'stop'])]);
        assert.equal(r.code, 0, r.err);
        assert.equal(qr.code, 0, `round ${i}: ${qr.err}`);
        await sh(['--session', 'q', 'stop']);
      }
    },
    'a command the daemon already started is not sent again when the daemon dies under it': async () => {
      hits = 0;
      const chain = sh(['--session', 'k', 'chain'], { input: JSON.stringify([['goto', `${base}/hit`],
        ['js', 'new Promise((r) => setTimeout(() => r(1), 2500))']]) });
      let settled = false;
      chain.then(() => { settled = true; });
      while (!hits && !settled) await new Promise((r) => setTimeout(r, 50)); // goto done, js running
      assert.equal(hits, 1, 'the chain ended before its goto');
      process.kill(JSON.parse(fs.readFileSync(env.QA_BROWSE_STATE, 'utf8')).pid, 'SIGKILL');
      const r = await chain;
      assert.equal(r.code, 1, r.out + r.err);
      assert.equal(hits, 1);
    },
    'stop and status never start a daemon; a first command racing the last stop still runs': async () => {
      await stopAll();
      for (let i = 0; i < 20; i++) { // only q's stop races y's first command: a third request would soften it
        await okIn('q')('url');
        const [q, y] = await Promise.all([sh(['--session', 'q', 'stop']), sh(['--session', 'y', 'url'])]);
        assert.equal(q.out, 'stopped session q\n', q.err);
        assert.equal(y.code, 0, `round ${i}: ${y.err}`);
        const [x] = await Promise.all([sh(['--session', 'x', 'stop']), sh(['--session', 'y', 'stop'])]);
        assert.equal(x.out, 'no session x\n', x.err);
        assert.equal(await status(), 'not running\n', `round ${i}`);
      }
    },
    'a name Playwright leaves unquoted, such as /home/, is shown and its ref resolves': async () => {
      await ok('goto', `${base}/slash`);
      const snap = await ok('snapshot', '-i');
      const ref = snap.match(/^(@e\d+) \[link\] "\/home\/"$/m)?.[1];
      assert.ok(ref, snap);
      assert.match(snap, /^@e\d+ \[link\] "\/"$/m);
      assert.match(snap, /^@e\d+ \[link\] "\/x\/: y\/"$/m);
      assert.match(snap, /^@e\d+ \[button\] "\/q\/"$/m); // a name with different text: - button /q/: /r/
      assert.match(snap, /^@e\d+ \[button\] "\/q2\/"$/m);
      assert.match(await ok('attrs', ref), /"href": "\/home\/"/);
    },
    'snapshot -d gives a shallow element the ref of that element, not a deeper namesake': async () => {
      await ok('goto', `${base}/nested`);
      const snap = await ok('snapshot', '-i', '-d', '0');
      const refs = [...snap.matchAll(/(@e\d+) \[link\] "Edit"/g)].map((m) => m[1]);
      assert.equal(refs.length, 1, snap);
      assert.match(await ok('attrs', refs[0]), /"href": "#top"/);
    },
    'a js call that never returns times out; the daemon still answers': async () => {
      await ok('goto', `${base}/`);
      const r = await run(['js', 'new Promise(() => {})']);
      assert.equal(r.code, 1);
      assert.match(r.err, /timed out after 3000 ms/);
      assert.match(await status(), /^t: /m);
    },
    'stop works while a command hangs': async () => {
      const hang = run(['js', 'new Promise(() => {})']);
      await new Promise((r) => setTimeout(r, 500));
      const t0 = Date.now();
      assert.equal((await ok('stop')).trim(), 'stopped session t');
      assert.ok(Date.now() - t0 < 2500, `stop took ${Date.now() - t0} ms`);
      await hang;
      assert.equal(await status(), 'not running\n');
    },
    'a stale ref and a failing click exit 1 with an error': async () => {
      await ok('goto', `${base}/`);
      const r = await run(['click', '@e999']);
      assert.equal(r.code, 1);
      assert.match(r.err, /@e999 is not in the last snapshot/);
    },
    'device emulates the whole profile in Chromium in a clean session': async () => {
      await ok('goto', `${base}/login`);
      await ok('fill', 'input[name=u]', 'admin');
      await ok('press', 'Enter');
      await ok('wait', '--load');
      assert.equal((await ok('device', 'iPhone 13')).trim(), 'Device iPhone 13: 390x664 @ 3x, mobile, touch; session cleared');
      assert.equal((await ok('url')).trim(), 'about:blank');
      await ok('goto', `${base}/other`); // an about:blank tab has no <meta viewport>
      const probe = JSON.parse(await ok('js',
        '({w: innerWidth, dpr: devicePixelRatio, touch: navigator.maxTouchPoints, ua: navigator.userAgent, url: location.pathname, chrome: "userAgentData" in navigator})'));
      assert.equal(probe.w, 390);
      assert.equal(probe.dpr, 3);
      assert.ok(probe.touch > 0, 'hasTouch');
      assert.match(probe.ua, /iPhone/);
      assert.equal(probe.url, '/other');
      assert.ok(probe.chrome, 'engine stays Chromium');
      assert.equal((await ok('cookies')).trim(), '[]');
    },
    'device clears cookies and all storage, leaves one blank tab, keeps extra headers': async () => {
      await ok('goto', `${base}/`);
      await ok('js', SET_STORAGE);
      await ok('newtab', `${base}/other`);
      await ok('header', 'X-Test:kept');
      await ok('device', 'Pixel 5');
      assert.match(await ok('tabs'), /^\* 1 +about:blank\n?$/);
      await ok('goto', `${base}/`);
      assert.deepEqual(JSON.parse(await ok('js', READ_STORAGE)), { cookie: '', l: null, s: null, idb: null });
      await ok('goto', `${base}/echo`);
      assert.match(await ok('text'), /x-test=kept/);
      await ok('device', 'Desktop Chrome');
    },
    'useragent and viewport --scale start a clean session too': async () => {
      for (const cmd of [['useragent', 'QA Wipe'], ['viewport', '800x600', '--scale', '2']]) {
        await ok('goto', `${base}/`);
        await ok('js', SET_STORAGE);
        await ok('newtab', `${base}/other`);
        assert.match(await ok(...cmd), /; session cleared\n$/);
        assert.match(await ok('tabs'), /^\* 1 +about:blank\n?$/, cmd[0]);
        await ok('goto', `${base}/`);
        assert.deepEqual(JSON.parse(await ok('js', READ_STORAGE)), { cookie: '', l: null, s: null, idb: null }, cmd[0]);
      }
      await ok('device', 'Desktop Chrome');
    },
    'viewport WxH keeps the session': async () => {
      await ok('goto', `${base}/`);
      await ok('js', SET_STORAGE);
      await ok('viewport', '800x600');
      assert.deepEqual(JSON.parse(await ok('js', READ_STORAGE)), { cookie: 'c=1', l: '1', s: '1', idb: '1' });
      await ok('device', 'Desktop Chrome');
    },
    'device caps the scale at 3 with a warning': async () => {
      const r = await run(['device', 'Galaxy S9+']);
      assert.equal(r.code, 0, r.err);
      assert.match(r.err, /Warning: Galaxy S9\+ has device scale 4\.5; qa-browse-app uses 3/);
      assert.equal((await ok('js', 'devicePixelRatio')).trim(), '3');
    },
    'device with an unknown profile names close matches': async () => {
      const r = await run(['device', 'iphone 13']);
      assert.equal(r.code, 1);
      assert.match(r.err, /unknown Playwright profile "iphone 13"; close matches: .*iPhone 13/);
    },
    'viewport and useragent set one thing each': async () => {
      await ok('device', 'Desktop Chrome');
      await ok('viewport', '800x600');
      await ok('useragent', 'QA Agent 1.0');
      const probe = JSON.parse(await ok('js', '({w: innerWidth, h: innerHeight, ua: navigator.userAgent, touch: navigator.maxTouchPoints})'));
      assert.deepEqual(probe, { w: 800, h: 600, ua: 'QA Agent 1.0', touch: 0 });
      assert.equal((await run(['viewport', '800x600', '--scale', '4'])).code, 2);
    },
    'history, reload, load-html': async () => {
      await ok('goto', `${base}/`);
      await ok('goto', `${base}/other`);
      await ok('back');
      assert.equal((await ok('url')).trim(), `${base}/`);
      await ok('forward');
      assert.equal((await ok('url')).trim(), `${base}/other`);
      assert.match(await ok('reload'), /200/);
      const file = path.join(tmp, 'page.html');
      fs.writeFileSync(file, '<h1>Loaded</h1>');
      await ok('load-html', file);
      assert.match(await ok('text'), /Loaded/);
    },
    'reading: html, forms, accessibility, media, data': async () => {
      await ok('goto', `${base}/kitchen`);
      assert.match((await ok('html', 'h1')).trim(), /^<h1 [^>]*>Kitchen<\/h1>$/);
      const forms = JSON.parse(await ok('forms'));
      assert.deepEqual(forms[0].fields.map((f) => f.name), ['c', 't', 'up']);
      assert.equal(forms[0].fields[1].required, true);
      assert.match(await ok('accessibility'), /heading "Kitchen"/);
      assert.match(await ok('media', '--images'), /"alt": "A picture"/);
      assert.match(await ok('data', '--jsonld'), /"name": "kitchen"/);
    },
    'inspection: eval, css, attrs, is, storage, perf': async () => {
      await ok('goto', `${base}/kitchen`);
      const file = path.join(tmp, 'expr.js');
      fs.writeFileSync(file, 'document.title');
      assert.equal((await ok('eval', file)).trim(), 'Fixture');
      assert.equal((await ok('css', 'h1', 'color')).trim(), 'rgb(255, 0, 0)');
      assert.match(await ok('attrs', '#t'), /"data-x": "1"/);
      assert.equal((await ok('is', 'visible', 'h1')).trim(), 'true');
      assert.equal((await ok('is', 'checked', 'h1')).trim(), 'false');
      await ok('storage', 'set', 'k', 'v');
      assert.match(await ok('storage'), /"k": "v"/);
      assert.match(await ok('perf'), /"domContentLoaded"/);
    },
    'interaction: select, type, hover, scroll, upload, tap': async () => {
      await ok('goto', `${base}/kitchen`);
      await ok('select', 'select[name=c]', 'blue');
      assert.equal((await ok('js', 'document.querySelector("select").value')).trim(), 'blue');
      await ok('click', '#t');
      await ok('type', 'abc');
      assert.equal((await ok('js', 'document.querySelector("#t").value')).trim(), 'abc');
      await ok('hover', '#hov');
      assert.match(await ok('text'), /hovered/);
      await ok('scroll', '#bottom');
      assert.ok(Number(await ok('js', 'scrollY')) > 1000);
      const file = path.join(tmp, 'up.txt');
      fs.writeFileSync(file, 'x');
      await ok('upload', '#up', file);
      assert.equal((await ok('js', 'document.querySelector("#up").files[0].name')).trim(), 'up.txt');
      await ok('device', 'Pixel 5');
      await ok('goto', `${base}/kitchen`);
      await ok('tap', '#tap');
      assert.match(await ok('text'), /tapped/);
      await ok('device', 'Desktop Chrome');
    },
    'dialogs, console, network': async () => {
      await ok('goto', `${base}/kitchen`);
      await ok('click', '#al');
      assert.match(await ok('text'), /\bno\b/); // dismissed by default
      await ok('dialog-accept');
      await ok('click', '#al');
      assert.match(await ok('text'), /\byes\b/);
      assert.match(await ok('dialog'), /confirm: Sure\? → accepted/);
      await ok('console', '--clear');
      await ok('click', '#log');
      assert.match(await ok('console', '--errors'), /\[error\] boom/);
      assert.match(await ok('network'), new RegExp(`200 GET ${base}/kitchen`));
    },
    'cookie, cookie-import, header': async () => {
      await ok('goto', `${base}/`);
      await ok('cookie', 'a=1');
      const file = path.join(tmp, 'cookies.json');
      fs.writeFileSync(file, JSON.stringify([{ name: 'b', value: '2', url: base }]));
      await ok('cookie-import', file);
      const names = JSON.parse(await ok('cookies')).map((c) => c.name);
      assert.ok(names.includes('a') && names.includes('b'), names.join());
      await ok('header', 'X-Test:yes');
      await ok('goto', `${base}/echo`);
      assert.match(await ok('text'), /x-test=yes/);
    },
    'visual: screenshot, pdf, responsive, diff': async () => {
      await ok('goto', `${base}/other`);
      const shot = path.join(tmp, 's.png');
      assert.match(await ok('screenshot', shot), /s\.png/);
      assert.ok(fs.statSync(shot).size > 0);
      const el = path.join(tmp, 'h1.png');
      await ok('screenshot', 'h1', el);
      assert.ok(fs.statSync(el).size > 0);
      const pdf = path.join(tmp, 'p.pdf');
      await ok('pdf', pdf);
      assert.equal(fs.readFileSync(pdf).subarray(0, 4).toString(), '%PDF');
      const resp = await ok('responsive', path.join(tmp, 'r'));
      assert.equal(resp.trim().split('\n').length, 3);
      assert.match(await ok('diff', `${base}/`, `${base}/other`), /^\+ .*other text/m);
      // with no path, files land in the private per-user directory, not the shared temp dir
      const priv = stateDir();
      for (const [cmd, re] of [[['screenshot'], /^Screenshot: (.+)$/m], [['pdf'], /^PDF: (.+)$/m],
        [['snapshot', '-a'], /^Annotated screenshot: (.+)$/m]]) {
        const f = (await ok(...cmd)).match(re)?.[1];
        assert.equal(path.dirname(f ?? ''), priv, cmd.join(' '));
        fs.rmSync(f);
      }
      const r3 = (await ok('responsive')).trim().split('\n').map((l) => l.replace(/^.*?: /, ''));
      for (const f of r3) { assert.equal(path.dirname(f), priv, f); fs.rmSync(f); }
    },
    'tabs, frame, chain': async () => {
      await ok('goto', `${base}/`);
      assert.match(await ok('newtab', `${base}/other`), /tab 2/);
      assert.match(await ok('tabs'), /\* 2 .*\/other/);
      await ok('tab', '1');
      assert.equal((await ok('url')).trim(), `${base}/`);
      await ok('closetab', '2');
      assert.doesNotMatch(await ok('tabs'), /\/other/);
      await ok('goto', `${base}/kitchen`);
      await ok('frame', '--name', 'inner');
      assert.match(await ok('text'), /other text/);
      await ok('frame', 'main');
      assert.match(await ok('text'), /Kitchen/);
      const r = await run(['chain'], { input: JSON.stringify([['goto', `${base}/other`], ['url'], ['fly'], ['url']]) });
      assert.equal(r.code, 1);
      const results = JSON.parse(r.out);
      assert.equal(results.length, 3);
      assert.equal(results[1].out, `${base}/other`);
      assert.equal(results[2].ok, false);
    },
    'closing a tab before the active one keeps the active tab and its refs': async () => {
      await ok('goto', `${base}/`);
      await ok('newtab', `${base}/icons`);
      await ok('newtab', `${base}/other`);
      await ok('tab', '2');
      const ref = (await ok('snapshot', '-i')).match(/(@e\d+) \[button\] "Save"/)?.[1];
      await ok('closetab', '1');
      assert.equal((await ok('url')).trim(), `${base}/icons`);
      await ok('click', ref);
      assert.equal((await ok('js', 'document.title')).trim(), 'SAVE');
      await ok('closetab'); // the active one: the next tab becomes active, refs go
      assert.equal((await ok('url')).trim(), `${base}/other`);
      assert.match((await run(['click', ref])).err, /not in the last snapshot/);
    },
    'navigation in another tab keeps the active tab\'s refs': async () => {
      await ok('goto', `${base}/icons`);
      const ref = (await ok('snapshot', '-i')).match(/(@e\d+) \[button\] "Save"/)?.[1];
      await ok('diff', `${base}/`, `${base}/other`);
      await ok('click', ref);
      assert.equal((await ok('js', 'document.title')).trim(), 'SAVE');
    },
    'state save and load restore the session': async () => {
      await ok('goto', `${base}/login`);
      await ok('fill', 'input[name=u]', 'admin');
      await ok('press', 'Enter');
      await ok('wait', '--load');
      await ok('state', 'save', 'admin');
      assert.ok(fs.existsSync(`${env.QA_BROWSE_STATE}.state-admin.json`));
      await ok('goto', `${base}/logout`);
      await ok('state', 'load', 'admin');
      await ok('goto', `${base}/home`);
      assert.equal((await ok('url')).trim(), `${base}/home`);
      assert.equal(await ok('restart'), 'restarted session t\n');
      assert.match(await status(), /^t: 1 tab\(s\), active about:blank/m);
    },
    'every command is in SKILL.md': async () => {
      const skill = fs.readFileSync(path.join(path.dirname(SELF), '..', 'SKILL.md'), 'utf8');
      const missing = Object.keys(COMMANDS).filter((c) => !skill.includes(`\`${c}`));
      assert.deepEqual(missing, []);
    },
    'unknown command is a usage error': async () => {
      const r = await run(['fly']);
      assert.equal(r.code, 2);
      assert.match(r.err, /unknown command: fly/);
    },
    'check: READY in a project with Playwright': async () => {
      const r = await run(['check']);
      assert.equal(r.code, 0, r.out + r.err);
      assert.match(r.out, /^READY: Playwright \d+\.\d+\.\d+/);
    },
    'min-playwright: prints the minimum version and needs no project': async () => {
      const r = await run(['min-playwright'], { cwd: tmp });
      assert.equal(r.code, 0, r.out + r.err);
      assert.equal(r.out.trim(), MIN_PLAYWRIGHT);
    },
    'check: no Playwright names the install commands': async () => {
      const r = await run(['check'], { cwd: tmp });
      assert.equal(r.code, 2);
      assert.match(r.out, /^NEEDS_SETUP: no Playwright installed/);
      assert.match(r.out, /npm i -D @playwright\/test@latest/);
      assert.match(r.out, /npx playwright install chromium/);
    },
    'check: Playwright below the minimum names the found version': async () => {
      const old = path.join(tmp, 'old');
      fs.mkdirSync(path.join(old, 'node_modules/@playwright/test'), { recursive: true });
      fs.writeFileSync(path.join(old, 'node_modules/@playwright/test/package.json'),
        '{"name":"@playwright/test","version":"1.45.3"}');
      const r = await run(['check'], { cwd: old });
      assert.equal(r.code, 2);
      assert.match(r.out, /^NEEDS_SETUP: @playwright\/test 1\.45\.3 is installed; qa-browse-app needs 1\.49\.0/);
      assert.match(r.out, /npm i -D @playwright\/test@latest/);
    },
    'check: no Chromium names the browser install': async () => {
      const r = await run(['check'], { env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: path.join(tmp, 'none') } });
      assert.equal(r.code, 2);
      assert.match(r.out, /^NEEDS_SETUP: Playwright \S+ has no working Chromium/);
      assert.match(r.out, /Run: npx playwright install chromium/);
    },
  };
  let failed = 0;
  try {
    for (const [name, t] of Object.entries(tests)) {
      try { await t(); console.log(`ok   ${name}`); } catch (e) { failed++; console.log(`FAIL ${name}\n${e.message}`); }
    }
  } finally {
    await stopAll();
    app.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log(failed ? `${failed} failed` : 'all passed');
  return failed ? 1 : 0;
}

// Exit once stdout and stderr have drained: a pipe is written asynchronously, so exiting at once cuts it off.
const exit = (code) => process.stdout.write('', () => process.stderr.write('', () => process.exit(code)));
if (process.argv[2] === '--self-test') exit(await selfTest());
else if (process.argv[2] === '--server') process.exit(await serve(process.cwd()));
else exit(await main(process.argv.slice(2)));
