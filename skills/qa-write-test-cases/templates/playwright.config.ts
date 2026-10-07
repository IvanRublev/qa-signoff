// Playwright config shape required by qa-write-test-cases' config gate.
// One project per role x environment, copied from qa-spec.md's header, e.g.:
//   Roles crawled: admin, standard user
//   Environments: Desktop Chrome, Desktop Safari, iPhone 13
// Each project runs its role's folder, tests/<role>/, so a test file runs
// in every environment of its role; a test case listing only some environments
// under **Projects:** has a test that skips itself in the others.
// The artificial role `no-login` runs pages that need no login, with no session.
// The setup file goes at tests/auth.setup.ts (templates/auth.setup.ts).
// `list` keeps readable console output; `json` writes the run's
// machine-readable report to outputFile. Needs the `dotenv` package for .env.
import 'dotenv/config';
import { defineConfig, devices } from '@playwright/test';

// Names exactly as in the spec header.
export const roles = ['admin', 'standard user'];
const environments = ['Desktop Chrome', 'Desktop Safari', 'iPhone 13'];

// `standard user` -> `standard-user`, `Desktop Chrome` -> `desktop-chrome`.
export const slug = (name: string) => name.toLowerCase().replace(/ /g, '-');

// A misspelled profile would otherwise run as a default desktop browser.
// A device descriptor sets defaultBrowserType (iPhone 13 sets webkit); overriding it
// runs every environment in Chromium. Add breakpoints by adding device names to
// `environments`, e.g. 'Pixel 7', 'iPad Mini': each gets a project per role.
const profile = (env: string) => {
  if (!devices[env]) throw new Error(`Unknown Playwright profile in Environments: ${env}`);
  return { ...devices[env], defaultBrowserType: 'chromium' as const };
};

export default defineConfig({
  testDir: './tests',
  // Playwright's actionTimeout defaults to 0 (no limit): a stuck click or fill would
  // hang until the test timeout. A failed test keeps a screenshot (screenshots are off by
  // default), which a test run copies into the run's failed-<stamp>/ folder.
  use: { baseURL: process.env.BASE_URL, actionTimeout: 15_000, screenshot: 'only-on-failure' },
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/results.json' }],
  ],
  projects: [
    // Logs every role in and writes .auth/<role slug>.json.
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    ...[...roles, 'no-login'].flatMap(role =>
      environments.map(env => ({
        name: `${slug(role)}-${slug(env)}`,
        testDir: `./tests/${slug(role)}`,
        use: role === 'no-login'
          ? profile(env)
          : { ...profile(env), storageState: `.auth/${slug(role)}.json` },
        // no-login too: its tests may open a helper role's session.
        dependencies: ['setup'],
      })),
    ),
  ],
});
