// Setup required by qa-write-test-cases' config gate: logs in every crawled role
// from qa-spec.md's header and writes its session to .auth/<role slug>.json,
// the storageState path its Playwright projects use. The artificial role
// `no-login` needs no session of its own. Place this file at
// tests/auth.setup.ts, under the config's testDir.
// Credentials come from .env: <ROLE>_USERNAME and <ROLE>_PASSWORD, where <ROLE>
// is the role name uppercased with every character other than a letter or digit
// turned into _, e.g. ADMIN_USERNAME, CUSTOMER_RESTRICTED_PASSWORD; the app URL
// from BASE_URL. Add .auth/ to .gitignore: the session files hold live cookies.
import { test as setup, expect } from '@playwright/test';
// The crawled roles and their slugs come from the config, so both files stay in step.
import { roles, slug } from '../playwright.config';

const envKey = (name: string) => name.toUpperCase().replace(/[^A-Za-z0-9]/g, '_');

for (const role of roles) {
  // Keep this title: the test title `log in as <role>` identifies the role's login.
  setup(`log in as ${role}`, async ({ page }) => {
    const username = process.env[`${envKey(role)}_USERNAME`];
    const password = process.env[`${envKey(role)}_PASSWORD`];
    if (!username || !password) {
      throw new Error(`Set ${envKey(role)}_USERNAME and ${envKey(role)}_PASSWORD in .env`);
    }

    // Adapt the steps below to the app's login form.
    await page.goto('/login');
    await page.getByLabel(/username/i).fill(username);
    await page.getByLabel(/password/i).fill(password);
    await page.getByRole('button', { name: /log ?in|sign in/i }).click();
    await expect(page).not.toHaveURL(/\/login/);

    await page.context().storageState({ path: `.auth/${slug(role)}.json` });
  });
}
