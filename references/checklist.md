# Pre-submission checklist

Mark each line OK / RISK / UNKNOWN with evidence. "UNKNOWN" means it needs a
human: the Partner Dashboard, the production env, the listing, or a live test.
Requirement numbers are given where Shopify has cited them to us; check the
current requirements page (shopify.dev → App Store requirements) for the
rest, because numbering changes.

## 1. Install and session
- [ ] Shopify-managed install; install lands in the app UI with no login.
- [ ] Expiring offline tokens with refresh; token exchange on first open.
- [ ] Session token auth on every API route; no cookies.
- [ ] No Server Action or public endpoint takes a `shop` from the client.
- [ ] Session failure shows an error with retry.
- [ ] Reinstall works: as an update of the existing store, a late
      `app/uninstalled` is ignored, and paused work resumes.
- [ ] Production toml: `application_url` and `redirect_urls` are real paths
      the app serves (not `shopify.dev/apps/default-app-home`, not a missing
      `/api/auth`).

## 2. Billing (1.2.x) - see billing.md
- [ ] Plan read live from `currentAppInstallation.activeSubscriptions` on
      every open; no TTL; test charges included.
- [ ] `app_subscriptions/update` subscribed (production toml) and re-reads the
      plan.
- [ ] Uninstall doesn't mark "no plan" as synced.
- [ ] Change plan opens Shopify's plan page with `target="_top"`; the app
      handle is right for **production**.
- [ ] Welcome-link path exists; return with `plan_handle` refreshes and shows
      the plan; the iframe gate lets the top-level return through.
- [ ] Upgrade, downgrade and decline all leave the app correct and usable.
- [ ] A store with no plan is pointed at the plans on first open.
- [ ] Prices, trial length and plan names match the Partner Dashboard.

## 3. Core functionality (2.1.1)
- [ ] Every feature and option the listing and UI mention works end to end
      on a fresh development store, including data round trips (e.g.
      backup → delete → restore keeps every advertised field).
- [ ] Root `app/not-found.tsx`, `error.tsx`; no route in the nav without a
      page.
- [ ] First-run empty states explain the next step.
- [ ] No request can hang: Redis or worker outages fail fast with a message.
- [ ] Workers and queues are running and monitored in production.
- [ ] External links use `target="_blank"`; plan links `_top`; downloads aren't
      popup-blocked.

## 4. Embedded app quality
- [ ] App Bridge script first in `<head>`; nav menu, page titles, back
      actions, save bar where forms are.
- [ ] Iframe gate covers iframe, same-origin, `?shop=`, admin referer, and
      referer with shop. It's unit-tested, and a malformed referer gives 404.
- [ ] CSP `frame-ancestors` validated; no `*.myshopify.com` fallback.
- [ ] GraphQL Admin API only (no REST); a supported API version.
- [ ] Every listed language has a complete catalog; no hardcoded strings.
- [ ] No dev-sounding pages, template names or debris.
- [ ] Review requests only via `shopify.reviews.request()`.

## 5. Data, scopes, compliance - see data-and-compliance.md
- [ ] Only used scopes; `read_all_orders` approved if requested.
- [ ] Protected customer data approved for the **production** app at the
      right level, every personal field justified.
- [ ] No PCD-gated webhook topic in a toml whose app isn't approved.
- [ ] `ACCESS_DENIED` on customer data handled gracefully.
- [ ] Compliance webhooks: HMAC first (401), 200 on valid, actually
      fulfilled, jobs retried for minutes.
- [ ] `shop/redact` deletes everything, including object storage.
- [ ] No theme downloads (1.1.3).

## 6. Security
- [ ] TLS on the app domain; `/api/health` reachable.
- [ ] No session tokens or secrets in logs.
- [ ] `pnpm audit --prod` has no runtime-reachable high advisories; the
      framework (Next.js) is on a patched version.
- [ ] Production refuses non-TLS connections to external services.

## 7. Listing and submission
- [ ] App name in the listing matches the toml `name` closely.
- [ ] Pricing in the listing equals the Partner Dashboard and the app.
- [ ] Privacy policy URL covers what the app stores.
- [ ] Screencast shows install, choosing a plan, and each core flow.
- [ ] Testing instructions: step by step, what to expect, how long
      background work takes, which store data the flows need.
- [ ] Emergency contact set.
- [ ] For a resubmission: a per-requirement "what changed" list, and every
      item reproduced as fixed on production.
