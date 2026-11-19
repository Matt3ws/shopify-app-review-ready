# What Shopify has sent back

Every entry is something an Edition app actually hit: a review rejection, a
Shopify automated check, or a deploy-time gate. A few are near-misses our own
audits caught before Shopify did; those say so in **Source**. Newest first.
Add new ones at the top, in the same shape.

Each entry: **Requirement**, **Source**, what Shopify said, **Cause**, **Fix**,
**Detect** (how to check another app for the same bug).

---

## 2026-11 · Backup Hero · submission paused (cooldown)

- **Source:** App Review email.
- Shopify: "your app submission has been paused until November 20, 2026 …
  Multiple failures to resolve a core requirement issue."
- **Cause:** the two issues below were not fully fixed on an earlier round.
- **Lesson:** a resubmission that doesn't fully fix every listed requirement
  costs weeks, not days. Reproduce each one on production before
  resubmitting, and say per requirement what changed.

## 2026-11 · Backup Hero · 1.2.2 · reinstall showed "Free" over a paid plan

- **Source:** App Review rejection.
- Shopify: "Reinstalling the app during an active billing cycle causes the app
  UI to revert to the 'Free' plan, despite the Shopify admin app index
  confirming the paid subscription remains active until its expiration date.
  Apps must query Shopify's Billing API upon reinstall to honor the remaining
  duration of any active paid subscription."
- **Cause:** the plan was cached in the database and refreshed from the
  Partner API at most every 6 hours. The `app/uninstalled` handler wrote
  "no plan" **and** stamped it as freshly synced, so the first opens after a
  reinstall trusted that and never asked Shopify.
- **Fix:** read `currentAppInstallation.activeSubscriptions` (Admin API, the
  shop's own token) on every app open, with no TTL. Uninstall may clear the
  stored plan but must not mark it synced. See [billing.md](billing.md).
- **Note:** a managed-pricing subscription can stay active after an
  uninstall until its period ends (the reviewer's own words). One of our
  READMEs said the opposite. Don't design around either assumption: read it
  live.
- **Detect:** a TTL or "synced at" check guarding the plan read; the plan
  being read from the Partner API; an uninstall handler that writes plan
  state with a timestamp. `scripts/audit.py` flags Partner API use and plan
  TTL constants.

## 2026-11 · Backup Hero · 2.1.1 · restored product came back without images

- **Source:** App Review rejection.
- Shopify: "we enabled product backups with variants, images, and custom
  fields selected, created a backup, deleted a product, and ran a restore;
  however, the restored product did not include its images."
- **Cause:** the backup captured media and metafields, but the restore's
  `productSet` call never sent `files` or `metafields`. Also, the diff that
  decides what needs restoring didn't compare media, so a product that only
  lost an image was never restored.
- **Fix:** write `files` (reuse existing file ids where they still exist,
  re-upload images from the captured URL otherwise; hosted video/3D need a
  staged upload so they only come back while the file exists), variant `file`,
  and `metafields`; add media (type + alt text, not URL) to the comparison.
- **Lesson:** the UI said "With variants, images and custom fields". Every
  word of that is a test the reviewer will run.
- **Detect:** for each option the UI or listing advertises, find where it is
  captured and where it is written back. A field that is only on one side is
  this bug.

## 2026-11 · Backup Hero · bare Next.js 404 for unknown URLs

- **Source:** own audit before resubmission (2.1.1 lists 404s as failures).
- **Cause:** only `app/(shopify)/not-found.tsx` existed. Next 16 uses the
  **root** `app/not-found.tsx` for unmatched URLs, so a mistyped path showed
  Next's bare "404: This page could not be found".
- **Fix:** add `app/not-found.tsx` rendering the app's own not-found page.
- **Detect:** `scripts/audit.py` checks for the root file.

## 2026-10 · Backup Hero · 1.1.3 · themes may not be downloadable

- **Source:** App Store self-review before submission.
- **Cause:** the app backed up themes and offered them as a zip download.
  Requirement 1.1.3 doesn't allow an app to let merchants download themes.
- **Fix:** removed theme capture, the download and the `read_themes` scope.
- **Detect:** `read_themes` in scopes; any theme file export.

## 2026-10 · Backup Hero, Discount Buddy · Shopify's app security check

- **Source:** Shopify's automated app security check (findings like
  `REQUEST_DERIVED_SHOP_SCOPE`).
- **Cause and fix, one per finding:**
  - Lifecycle hooks were Server Actions taking a `shop` argument from the
    browser, so anyone could make them act with another shop's stored token.
    Run them inside the session sync, against the shop verified from the
    session token; no module that takes a shop may be `'use server'`.
  - `proxy.ts` put `?shop=` into `frame-ancestors` unchecked, so any origin
    could frame the app. Validate it against
    `^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$` and fall back to
    `admin.shopify.com` alone (not `*.myshopify.com`).
  - Rejected session tokens were logged: `InvalidJwtError` embeds the whole
    token in its message. Log the error class only.
  - Dependency advisories (zod memory exhaustion). Keep `pnpm audit --prod`
    clean of anything reachable at runtime.
- **Detect:** `scripts/audit.py` flags `'use server'` files that take a
  `shop`, raw `frame-ancestors` interpolation, and logged tokens.

## 2026-10 · Discount Buddy · 1.3 · no custom review prompts

- **Source:** Shopify guidance found while building (the requirement text
  doesn't spell it out).
- **Cause:** a custom "Are you happy with the app?" modal with a feedback form
  and an App Store link.
- **Fix:** ask for reviews only through App Bridge's
  `shopify.reviews.request()`, after a success moment. No pre-question, no
  feedback form, no incentive.
- **Detect:** links to `apps.shopify.com/.../reviews` or star/feedback modals
  in the UI.

## 2026-08 · Super Siblings · "selecting a paid plan results into an error 404 page"

- **Source:** App Review rejection.
- **Cause:** after the merchant approves a plan, Shopify sends them back to
  the app as a **top-level, cross-site** page load (not inside the iframe, not
  same-origin), with `?shop=` appended and an `admin.shopify.com` referer. The
  iframe gate in `proxy.ts` only let through iframe loads, same-origin
  requests and referers carrying `shop`, so it answered 404 at the moment the
  merchant had just paid. A welcome-link path the app doesn't serve does the
  same.
- **Fix:** also let through a request whose own `?shop=` is a valid
  myshopify domain, and one whose referer host is `admin.shopify.com` or a
  `*.myshopify.com` admin (https only). Make sure every plan's welcome link
  points at a path the app serves. See [embedded-app.md](embedded-app.md).
- **Detect:** `scripts/audit.py` warns when the gate has no `?shop=` or
  admin-referer branch. Test it: request the confirm URL with
  `sec-fetch-site: cross-site` and an admin referer; expect 200.

## 2026-08 · Super Siblings · wrong app handle sends "Change plan" to a Shopify 404

- **Source:** found while fixing the rejection above.
- **Cause:** the plan-selection URL was built from an env var; dev and
  production apps have different handles.
- **Fix:** read the handle from `currentAppInstallation.app.handle`; keep the
  env var only as a fallback, and make sure it's set in production.

## 2026-08 · Hide It; Checkout · launch-readiness findings

- **Source:** own launch audit; the deploy limits are enforced by Shopify.
- Production toml was missing `app_subscriptions/update`, so a downgraded
  shop kept paid features live (a terms problem). Every public app now
  subscribes to it.
- A sidebar page named `/debug` looked unfinished to a reviewer; renamed
  `/simulator`. Name pages for merchants.
- Template debris invited reviewer questions: unused mutations (an unused
  write scope), a stale `shopify.app-content.toml`, console.log spam, the
  template name in `package.json` and README, a hardcoded Danish tab title.
- Shopify Functions: Wasm must be at most 256 KB, and each input query has
  a complexity cap of 30. Deploy rejects either; CI can't see it.

## 2026-07 / 08 · Hide It; Checkout · protected customer data blocks deploy

- **Source:** Shopify deploy-time gate.
- Shopify: "This app is not approved to subscribe to webhook topics
  containing protected customer data."
- **Cause:** subscribing to `orders/*` or `customers/*` topics (and some
  customer scopes) before protected customer data access was approved. The
  rejection blocks the whole app's deploy, not just the webhook.
- **Also:** approval is **per app**: the dev app and the production app are
  approved separately. Level 2 fields (name, email, phone, address) need
  their own justification, or they come back denied or null on the
  reviewer's store, and a feature that reads them looks broken.
- **Fix:** request access in the Partner Dashboard first; keep gated topics
  out of a toml whose app isn't approved; handle `ACCESS_DENIED` gracefully.
- **Detect:** order/customer topics in a toml, customer/order PII fields in
  queries. See [data-and-compliance.md](data-and-compliance.md).

## 2026-08 · Hide It; Checkout · external links replaced the app with "content is blocked"

- **Source:** found in testing.
- **Cause:** a `mailto:` support link with no `target` navigated the iframe,
  and the Admin's frame policy replaced the whole app with the browser's
  blocked-content page.
- **Fix:** every link leaving the app gets `target="_blank"`; Shopify-hosted
  flows that should replace the Admin (plan selection) use `target="_top"`.
- **Detect:** `scripts/audit.py` flags `href="mailto:`/`http` without a
  target.

## 2026-08 · Wishlist Automations · compliance webhooks logged and did nothing

- **Source:** own compliance pass.
- **Cause:** the three mandatory compliance webhooks returned 200 and only
  logged. `customers/data_request` must get the data to the merchant;
  `customers/redact` and `shop/redact` must actually delete.
- **Fix:** record data requests and let the merchant download them; delete on
  redact (including copies inside long-lived data such as backups); retry the
  jobs for minutes, not seconds, because Shopify won't resend after its 200.
- **Detect:** read each handler and follow the data. "It logs" isn't
  fulfilment.
