# Step 4 — OWASP checklist

4. **OWASP checklist — run it on every input/auth/data surface, inventory items AND named journeys.** Some categories (Broken Access Control, Authentication Failures) only surface across a multi-step journey, not at single-item granularity — run the checklist against each named journey from step 2 as well as each inventory item from step 1. For each surface where a category applies, write one test case per category. A protection enabled once in config needs one test case proving it on a representative surface, not one per surface. The categories are [OWASP Top 10:2025](https://top10.owasp.org/2025/) — use this edition's IDs and names, and its category pages for what each covers; each row's "applies when" decides whether it applies to this project:

   1. **A01: Broken Access Control** — applies when roles or data ownership differ, or the app fetches a user-supplied URL: privilege escalation, another user's record by ID (IDOR), forced browsing to admin routes, CSRF, SSRF
   2. **A02: Security Misconfiguration** — applies to every deployed app: default credentials, missing security headers, permissive CORS, directory listing
   3. **A03: Software Supply Chain Failures** — applies when the UI or response headers disclose component names or versions (about page, `X-Powered-By`); dependency scanning itself is outside this backlog
   4. **A04: Cryptographic Failures** — applies when the app handles credentials or sensitive data: HTTPS and HSTS, secure cookie flags, password hashing, no secrets in URLs
   5. **A05: Injection** — applies when input reaches a query, template, or command: SQL injection, XSS, command injection
   6. **A06: Insecure Design** — applies when a flow can be abused as designed: rate limiting, anomaly detection, business-rule bypass
   7. **A07: Authentication Failures** — applies when users log in: session hijacking, session fixation, weak password or reset flow
   8. **A08: Software or Data Integrity Failures** — not in this checklist. Business data integrity (cascades, double billing, inconsistent related state) is a product flaw, not security: cover it with Functional or Negative test cases, not `SEC` test cases
   9. **A09: Security Logging and Alerting Failures** — applies when the app keeps an audit or security log a tester can inspect
   10. **A10: Mishandling of Exceptional Conditions** — applies when an error path is reachable from the UI: stack traces or system errors shown to the user, failing open when a check errors

   **OWASP target:** at least 90% of the applicable categories tested. Decide applicability per project from each row's "applies when"; A08 is never applicable. A category is tested when at least one test case covers it. `qa-review-test-cases` checks this target.
