# Pre-submission checklist

Mark each line OK / RISK / UNKNOWN with evidence. "UNKNOWN" means it needs a
human: the Dev or Partner Dashboard, the production env, the listing, or a
live test. Requirement numbers follow Shopify's list
(https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements);
re-check it, because numbering and rules change.

## 0. Blockers outside the code (check first)
- [ ] **IP allowlist** enforced for the production app (Dev Dashboard), with
      IPv4 and IPv6, tested against recent traffic. Without it: no bulk
      operations since 2026-11-12, no new installs since 2026-11-20.
- [ ] Protected customer data **granted** (not "in review") for the
      production app, every personal field justified.
- [ ] `read_all_orders` and any other special scopes approved.
- [ ] Paid plans marked "free for partners and developers", so a reviewer on
      another organization's dev store can select them.
- [ ] Production env complete (billing credentials, app handle, encryption
      key); workers and monitoring green.
- [ ] `shopify app security check --exclude 'types/**'` run, and its agent
      checks executed and recorded (on Next.js most checks only exist as agent
      prompts); the self-review list has been walked.
- [ ] **Production runs the code you audited.** After deploying, repeat the key
      checks against the live URL (e.g. `curl -s -o /dev/null -w '%{http_code}'
      -H 'sec-fetch-site: cross-site' '<app>/billing/confirm?shop=x.myshopify.com&plan_handle=p'`
      must not be 404).

## 1. Install and session (2.3.x, 3.1.2)
- [ ] Shopify-managed install; install lands in the app UI with no login.
- [ ] Expiring offline tokens with refresh; dormant stores refreshed before
      90 days; no exchange on every request.
- [ ] Session token verified on every API route (`exp`, `nbf`, `aud`,
      `iss`/`dest`); no cookies.
- [ ] Every record looked up by shop **and** id; no Server Action or endpoint
      takes a `shop` from the client.
- [ ] Session failure shows an error with retry.
- [ ] Reinstall (2.3.4): updates the existing store row, no install-once
      flags; a late `app/uninstalled` is ignored; paused work resumes.
- [ ] `application_url` and `redirect_urls` are real, on the same host (not
      `shopify.dev/apps/default-app-home`).

## 2. Billing (1.2.x) - see billing.md
- [ ] App Pricing: plan read from the Partner API `activeSubscription`;
      only a confirmed plan cached, briefly; errors never read as "no plan".
- [ ] (Pre-April-2026 apps only) `app_subscriptions/update` re-reads the
      plan and handles ACTIVE/CANCELLED arriving in either order.
- [ ] Uninstall doesn't mark "no plan" as synced; reinstall during a paid
      cycle shows the paid plan (tested on production).
- [ ] Change plan opens Shopify's plan page with `target="_top"`; the app
      handle is the **production** one.
- [ ] Welcome-link path exists; return with `plan_handle` re-reads and shows
      the plan; the iframe gate lets the top-level return through.
- [ ] Upgrade, downgrade and decline all leave the app correct and usable.
- [ ] A store with no active subscription is **redirected to the plan
      page** on open (Shopify's documented integration; how 1.2.2's "request
      approval again on reinstall" happens), even if feature limits are off.
- [ ] Prices, trial length and plan names match the Partner Dashboard.
- [ ] Every plan card can be chosen and approved through Shopify (1.2.3):
      no "Contact us"/"book a call"/custom-quote card; enterprise deals are
      private plans plus "Description of additional charges" in the listing.
- [ ] Limits shown on plan cards and status are the ones the merchant gets
      (none of a paid plan's limits shown to a shop without a plan).
- [ ] The billing page renders per request in production (not prerendered
      at build without the runtime env); "Change plan" is visible live.

## 3. Core functionality (2.1.x)
- [ ] Every feature and option the listing and UI mention works end to end
      on a fresh development store, including data round trips (e.g.
      backup → delete → restore keeps every advertised field).
- [ ] Features that read orders or customers work on a **non-dev** store
      (dev stores skip the protected customer data gate).
- [ ] Test orders (Bogus Gateway) count in everything a reviewer sees;
      exclude them only from billing usage.
- [ ] Apps that create or restore records: what comes back matches what
      was there, end to end. Published to the same sales channels (a
      created product is unpublished by default); stock activated at every
      location before it's set; references remapped from old ids to the new
      records (menus, metaobject and collection-condition references); images
      and custom fields on every resource the UI mentions.
- [ ] Every limit the code knows about (caveats, unsupported fields) is
      **shown in the UI** where the merchant chooses or approves. A caveat in
      a code comment or an unused array discloses nothing.
- [ ] Data sync (2.1.4): Shopify is the source of truth; webhooks correct
      stored copies; writes are idempotent; a reconcile job heals missed
      webhooks.
- [ ] No 404, 500 or unexpected 3xx anywhere (2.1.1), and no minor UI bug
      that partly blocks a flow (2.1.2).
- [ ] Root `app/not-found.tsx` and `error.tsx`; every nav route has a page.
- [ ] First-run empty states explain the next step.
- [ ] No request can hang: Redis or worker outages fail fast with a message.
- [ ] External links use `target="_blank"`; plan links `_top`; downloads aren't
      popup-blocked; no pop-up windows for OAuth or charges.

## 4. Embedded app quality (2.2.x)
- [ ] App Bridge CDN script first in `<head>`; no legacy `@shopify/app-bridge`
      npm package (2.2.3). Nav menu, titles, back actions, save bar.
- [ ] Iframe gate covers iframe, same-origin, `?shop=`, admin referer, and a
      referer carrying `shop`. Unit-tested; a malformed referer gives 404.
- [ ] `frame-ancestors` with the validated shop on **every HTML route**; no
      `*.myshopify.com` fallback.
- [ ] GraphQL Admin API only (2.2.4); API version at least 90 days from
      deprecation.
- [ ] No deprecated fields or arguments in any GraphQL document: check the
      app's API health in the Partner Dashboard, and run the repo's own
      document check if it has one (`pnpm graphql:check-scripts` in our
      template). Codegen and `tsc` accept deprecated fields without a word.
- [ ] Every listed language complete in the UI (4.3.2); no hardcoded strings.
- [ ] No dev-sounding pages, template names or debris.
- [ ] Reviews: neutral, no incentives (1.3.1); only via
      `shopify.reviews.request()`; none in admin extensions or Sidekick.

## 5. Data, scopes, compliance - see data-and-compliance.md
- [ ] Only used scopes (`SCOPE_OVER_REQUEST`, `OVERBROAD_DATA_ACCESS`).
- [ ] No PCD-gated webhook topic in a toml whose app isn't approved.
- [ ] `ACCESS_DENIED` and null-with-error fields on customer data handled
      gracefully.
- [ ] Compliance webhooks: HMAC first (401 on failure), 200 on valid,
      actually fulfilled within 30 days, jobs retried for minutes.
- [ ] `shop/redact` deletes everything, including object storage and
      models without a cascade.
- [ ] Level 1 / Level 2 obligations met (security.md), including encrypted
      backups and an access log.
- [ ] No theme download, creation or upload (1.1.3).

## 6. Security - see security.md
- [ ] TLS valid; only 80/443 (and restricted SSH) open from outside.
- [ ] No tokens or secrets in logs, responses or the repo.
- [ ] Tokens in URLs: 128-bit, expire within 7 days, `noindex`,
      `Referrer-Policy: no-referrer`.
- [ ] No open redirects, SSRF, `innerHTML` with untrusted data, raw SQL.
- [ ] Dependabot or Renovate on the repo; `pnpm audit --prod` clean of
      reachable highs; framework on a patched version.
- [ ] MFA or passkeys on Partner, hosting, DNS, Git and email accounts.

## 7. Listing and submission (4.x)
- [ ] App name in the listing matches the toml `name` closely.
- [ ] Pricing only in pricing details: never in screenshots, the icon or the
      description.
- [ ] No stats, guarantees, "best/first/only" claims, or testimonials, in
      text or images.
- [ ] Screenshots: unique, no browser chrome or desktop backgrounds, no real
      customer data (1600×900, 3–6 desktop shots recommended).
- [ ] Privacy policy URL covers what the app stores and for how long.
- [ ] Screencast in English (or English subtitles) showing install, choosing
      a plan, and each core flow.
- [ ] Testing instructions: step by step, what to expect, how long
      background work takes, which store data the flows need. Any external
      login works without 2FA/OTP/SSO and keeps working after publishing.
- [ ] Emergency contact set.
- [ ] For a resubmission: a per-requirement "what changed" list, every item
      reproduced as fixed on production.
- [ ] After listing: answer quality-check emails within 7 days, and fix
      required issues within 30, or the app is demoted or unpublished.
