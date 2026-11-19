# What Shopify has sent back

Every entry is something an Edition app actually hit: a review rejection, a
Shopify automated check, or a deploy-time gate. A few are near-misses our own
audits caught before Shopify did; those say so in **Source**. Newest first.
Add new ones at the top, in the same shape.

Each entry: **Requirement**, **Source**, what Shopify said, **Cause**, **Fix**,
**Detect** (how to check another app for the same bug).

---

## 2026-11 · All public apps · IP allowlist required (Shopify deadline)

- **Source:** Shopify requirement
  (shopify.dev/docs/apps/build/security/credentials-and-data/restrict-api-access-to-your-ip-addresses).
- Shopify: "November 12, 2026: Shopify blocks bulk queries and bulk
  mutations from public apps that don't have an IP allowlist. November 20,
  2026: Public apps without an IP allowlist are delisted from the Shopify App
  Store and blocked from new installs."
- **Why it matters for review:** without one, the reviewer can't install the
  app, and a bulk-operation app (backups, exports, syncs) has been broken
  since the 12th. Custom apps on client stores need one from 2026-11-20 for
  new installs and 2027-01-01 for all.
- **Fix:** Dev Dashboard → app → Settings → IP allowlist: the servers' IPv4
  and IPv6, test against recent traffic, enforce, confirm a 403 from outside.
  One per app, even when apps share a server. See
  [security.md](security.md#deadlines-that-block-installs).
- **Detect:** a Dev Dashboard check, not code. It's the first item in every
  readiness report.

## 2026-11 · Backup Hero · near-miss · copied the wrong billing pattern

- **Source:** own audit, the day before resubmitting.
- **Cause:** to fix 1.2.2, the plan read was moved from the Partner API to
  the Admin API's `currentAppInstallation`, copying an older approved app.
  For Shopify App Pricing after 2026-04-28 that returns nothing: the docs say
  status "comes from the Partner API, not from the GraphQL Admin API". The
  app would have shown "no plan" right after the reviewer chose one. A
  dev-store probe had already returned "none", and that was the warning.
- **Fix:** reverted to the Partner API with a short cache for confirmed
  plans only.
- **Lesson:** an approved sibling app is precedent, not proof. Platform
  behaviour changes by date; check the current docs (`shopify doc fetch`)
  before copying billing, install or security code.

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
- **Fix:** keep reading the Partner API's `activeSubscription` (with
  Shopify App Pricing that is the only source), but cache only a **confirmed**
  plan, for five minutes, and never cache "no plan". Uninstall may clear the
  stored plan but must not mark it synced. See [billing.md](billing.md).
- **Note:** a managed-pricing subscription can stay active after an
  uninstall until its period ends (the reviewer's own words). One of our
  READMEs said the opposite. Don't design around either assumption: read it
  live.
- **Detect:**
  - A long TTL, or one that also covers "no plan", guarding the plan read.
  - An uninstall handler that writes plan state with a timestamp.
  - `scripts/audit.py` flags plan TTL constants.

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

## 2026-09 → 11 · Super Siblings · `products/update` flood from the app's own writes

- **Source:** production incident and fixes (commits from 2026-09-28 to
  2026-11-03).
- **Cause:** the app writes a metafield on products, and **every write fires
  `products/update`** for that product. The app processed its own echoes as
  merchant edits, so one sync produced a webhook per product touched, queued
  more work, and flooded the queue. Merchants' bulk edits and imports add
  bursts of thousands. A Redis hang inside the webhook route then made
  deliveries overrun Shopify's 5-second limit.
- **Fix:**
  - **Echo blocker.** Before writing, record a Redis key per product with the
    expected `updated_at` window and a hash of the fields you wrote. Drop a
    delivery only if both match: timing alone would also drop a merchant edit
    made in the same seconds.
  - Debounce per product (latest payload wins) and coalesce per shop in a
    buffer, applied in one batch.
  - Answer 200 within 5 s; do the work after (`after()` or a queue).
  - Give each Redis call in the webhook path its own deadline and fail open
    on timeout (a global `commandTimeout` also hit the batch drain).
  - Compare payloads the way GraphQL returns them: REST payload image URLs
    carry query strings.
- **Detect:**
  - An app that subscribes to `products/update` (or any `*/update`) **and**
    writes that same resource (`productSet`, `productUpdate`,
    `metafieldsSet` on products) with no echo check.
  - Webhook routes that await Redis or Postgres with no deadline.
  - `scripts/audit.py` flags the first.

## 2026-11 · Heart of Wool · storefront endpoint signed tokens for anyone

- **Source:** own security fix (a custom app; the pattern is in older public code too).
- **Cause:** `/api/v1/auth/token` took `customerId` and `shop` from the
  request body behind CORS `*` and signed a JWT, so anyone could read and
  change any customer's subscriptions. An older app did the same, and picked
  the store's Admin token by the `Referer` header.
- **Fix:** storefront endpoints behind the App Proxy; the customer comes
  from the signed `logged_in_customer_id`; ownership checked on every write;
  anonymous requests get 401. See
  [storefront-and-extensions.md](storefront-and-extensions.md).
- **Detect:** storefront routes reading `customerId`/`shop` from the body;
  `jwt.sign`; `Access-Control-Allow-Origin: *`.

## 2026-10 · Backup Hero · 1.1.3 · themes may not be downloadable

- **Source:** App Store self-review before submission.
- **Cause:** the app backed up themes and offered them as a zip download.
  Requirement 1.1.3 doesn't allow an app to let merchants download themes,
  and the self-review also flags Themes API calls that **create or upload**
  themes, so restoring a theme is out too.
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

## 2026-10 · Discount Buddy · 1.3.1 · no custom review prompts

- **Source:** Shopify guidance found while building (the requirement text
  doesn't spell it out).
- **Cause:** a custom "Are you happy with the app?" modal with a feedback form
  and an App Store link.
- **Fix:** ask for reviews only through App Bridge's
  `shopify.reviews.request()`, after a success moment. No pre-question, no
  feedback form, no incentive.
- **Detect:** links to `apps.shopify.com/.../reviews` or star/feedback modals
  in the UI.

## 2026-10 · Store Sync · store credentials sent to the browser

- **Source:** own security audit of a public app.
- **Cause:** three routes returned full `Store` rows. Any merchant in a store
  network could read the other stores' access and refresh tokens in
  DevTools.
- **Fix:** omit secret columns everywhere a store is returned (a shared
  `STORE_SECRET_FIELDS` with Prisma `omit`), plus a unit test that fails if
  one comes back.
- **Detect:** API routes returning `prisma.store.find*` (or any row holding
  tokens) without `select`/`omit`.

## 2026-10 · Store Sync · `app_subscriptions/update` arrives twice on a plan switch

- **Source:** own fix after merchants reverted to their old plan.
- **Cause:** a plan switch sends one webhook for the new subscription
  (`ACTIVE`) and one for the old (`CANCELLED`), in no guaranteed order. The
  handler wrote whichever came last.
- **Fix:** let only `ACTIVE` set the plan. Better still, treat the webhook as a
  trigger and re-read `currentAppInstallation.activeSubscriptions`.
- **Detect:** a subscription webhook handler that writes the plan from the
  payload without checking the status.

## 2026-10 · Store Sync · GDPR deletion silently rolled back

- **Source:** own fix.
- **Cause:** the delete transaction for `app/uninstalled` and `shop/redact`
  hit a foreign-key violation on two models with no cascade, so nothing was
  deleted, and the webhook still got its 200.
- **Fix:** delete those models in the transaction, plus a test that reads the
  schema and fails when a new model references the shop without a cascade or
  an explicit delete.
- **Detect:** relations to the shop/store model without `onDelete: Cascade`
  that the redact code doesn't delete.

## 2026-10 · Store Sync · billing page promised a trial that doesn't exist

- **Source:** own audit.
- **Cause:** copy said "7-day free trial"; the plans had none.
- **Fix and detect:** `grep -rni 'trial' translations/ components/` and
  compare every price, trial and plan name with the Partner Dashboard.

## 2026-09 · Tropica · deploy gates on theme extensions

- **Source:** Shopify deploy refused.
- Shopify: "Extension Liquid content size exceeds 100 KB limit" (all
  `blocks/` + `snippets/` Liquid together, comments included), and a failed
  deploy on `{{ '{' }}` brace escapes. Also: renaming a block file removes it
  from every live theme, and app snippets are wrapped in HTML comments.
- **Fix and detect:** see
  [storefront-and-extensions.md](storefront-and-extensions.md).

## 2026-09 · Tropica · a valid App Proxy signature doesn't authorize the params

- **Source:** own audit.
- **Cause:** Shopify signs every query param, including ones a logged-in
  customer added (`?kk_customer=999`), so signature verification passed while
  serving another customer's data.
- **Fix:** check every param that selects whose data to show against
  `logged_in_customer_id`, on every request.
- **Detect:** App Proxy routes reading a customer, company or location id
  from `searchParams`.

## 2026-09 · Store Sync · scopes added later, and queries needing a missing scope

- **Source:** own fix.
- **Cause:** one query needed `read_locales`, which wasn't requested, and
  whole product webhooks failed. After a scope is added, existing installs
  get "Access denied" until the merchant opens the app and approves.
- **Fix:** check each query's required scopes against the toml; handle
  `ACCESS_DENIED` per resource; don't let one missing scope fail unrelated
  work.

## 2026-09 · Store Sync · production ran without an encryption key

- **Source:** own audit.
- **Cause:** encryption at rest for access tokens was dropped because
  production had no `ENCRYPTION_KEY`, so tokens were stored in plain text.
- **Fix:** require the key in the env schema (outside tests) and fail at
  boot, not at first encrypt. Shopify's protected customer data requirements
  expect encryption at rest anyway.
- **Detect:** `grep -n ENCRYPTION env.ts`.

## 2026-08 → 2026-09 · Bundle Hero · 2.1.4 · failed three rounds: orders and revenue showed zero

- **Source:** App Review rejection, three times, before approval (2026-11).
- Shopify: the app's core data (bundle orders and revenue) showed zero on the
  reviewer's store while the bundle discount visibly worked (requirement
  2.1.4, data synchronization).
- **Causes:** three, each enough on its own:
  1. **Protected customer data wasn't approved, only requested.** Development
     stores are exempt from the PCD gate, so every test on the team's own dev
     stores passed. The reviewer's store isn't a dev store; order reads there
     returned `ACCESS_DENIED`. The gate is on the `Order` object itself, not
     only on personal fields: an app that reads no names or emails still needs
     Level 1 access to read orders.
  2. **Test orders were filtered out** of the analytics on non-dev stores.
     Reviewers place test orders (Bogus Gateway); they saw a page of zeros.
  3. **A misconfigured Redis key** in production stopped the webhook
     workers.
- **Fix:**
  - Get PCD **granted** (not "in review") for the production app before
    submitting.
  - Count test orders in everything a reviewer looks at; exclude them only
    from billing usage.
  - Raise a loud alert on `ACCESS_DENIED`.
  - Verify production health (`/api/health`, worker heartbeat) before
    submitting.
  - Test on a **non-dev trial store**: a dev-store pass proves nothing about
    the gates a reviewer's store hits.
  - Document the data-sync design (webhooks that correct, idempotent
    rewrites, a nightly reconcile) for the reviewer.
- **Detect:**
  - Filters on `test` orders in features the reviewer sees.
  - Order or customer reads with no `ACCESS_DENIED` handling.
  - Any submission verified only on development stores.

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
  shop kept paid features live (a terms problem). That webhook only exists
  for App Pricing apps enrolled before April 2026; newer apps get no webhook
  and must read the Partner API (see [billing.md](billing.md)).
- A sidebar page named `/debug` looked unfinished to a reviewer; renamed
  `/simulator`. Name pages for merchants.
- Template debris invited reviewer questions: unused mutations (an unused
  write scope), a stale `shopify.app-content.toml`, console.log spam, the
  template name in `package.json` and README, a hardcoded Danish tab title.
- Shopify Functions: Wasm must be at most 256 KB, and each input query has
  a complexity cap of 30. Deploy rejects either; CI can't see it.

## 2026-06 → 08 · App template · token and webhook lifecycle

- **Source:** Shopify requirement plus own fixes; every app inherits the
  template.
- **Expiring offline tokens are required** for public apps:
  `tokenExchange({ expiring: true })`. Refresh tokens die after about 90 days
  idle, so a daily job must refresh idle shops, or webhooks stop until the
  merchant reinstalls. Never token-exchange on every request: Shopify keeps one
  active refresh token, and each exchange retires the stored one.
- **A revoked token isn't an expired one.** After an uninstall and reinstall,
  the session-sync fast path reused the dead token and every Admin call got
  401. `app/uninstalled` now marks the shop (deleting nothing until
  `shop/redact`), session sync re-exchanges for a marked shop, and scheduled
  jobs skip it.
- **Webhook dedup ran before HMAC and was never released.** A forged request
  could poison dedup, and if a handler failed after claiming the event,
  Shopify's retry was answered "Duplicate". That's fatal for compliance
  webhooks. Verify HMAC first, and release the claim on any non-2xx.
- **Detect:**
  - `tokenExchange` without `expiring: true`, or inside request
    middleware.
  - A session-sync fast path with no uninstalled check.
  - The order of the dedup and HMAC steps in the webhook middleware.

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
