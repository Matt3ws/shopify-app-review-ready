# Embedded app: install, the iframe gate, links and errors

Requirement 2.1.1 fails an app for error pages ("404's, 500's, 300's"), and
2.1.2 for even minor UI bugs that partly block the review. Most of ours came from the edges of the embedded app:
requests the gate didn't expect, links that left the iframe, and URLs nothing
handled.

## Contents
- Install and session
- The iframe gate
- CSP frame-ancestors
- Links that leave the app
- Error and not-found pages
- Hanging requests
- Naming and polish

## Install and session

- Shopify-managed install (`embedded = true`, no
  `use_legacy_install_flow = true`): install lands straight in the app UI.
  There must be no login screen, no "enter your shop" form, and no OAuth
  redirect dance.
- Token exchange on first open; public apps must use **expiring offline
  tokens** (`expiring: true`) with refresh.
- Authenticate API calls with the App Bridge session token
  (`shopify.idToken()`), verified server-side. No cookies, no localStorage auth.
- Don't exchange a token on every request; it rotates the refresh token.
  Exchange on open when there's no working token, the store is marked
  uninstalled, or it needs re-auth.
- Lifecycle hooks (on open, on install) run inside the server function that
  verified the session token, against **that** shop. Never expose a Server
  Action that takes a `shop` argument (Shopify's security check flags it as
  `REQUEST_DERIVED_SHOP_SCOPE`).
- If session setup fails, show an error with a retry button, not a blank page
  or a spinner forever.
- `redirect_urls` in the production toml must be on the same host as
  `application_url`: Shopify validates against it if a flow ever falls back
  to OAuth, and a different host is an install failure. Pointing it at a path
  the app actually serves avoids a 404 in that fallback.

## The iframe gate

Many of our apps 404 anything that doesn't look like it came from the Shopify
Admin (`proxy.ts`). That's a UX gate, not security, and it must let through
every way Shopify legitimately reaches the app:

| Signal | Covers |
|---|---|
| `sec-fetch-dest: iframe` | normal load inside the Admin |
| `sec-fetch-site: same-origin` | the app's own fetches, RSC, server actions |
| request's own `?shop=` is a valid myshopify domain | **top-level redirects from Shopify, e.g. after plan approval** |
| referer host `admin.shopify.com` or `<store>.myshopify.com` (https) | redirects from the Admin with no `shop` param |
| referer carries a valid `?shop=` | direct visits from a Shopify URL |

Missing the third and fourth rows is the Super Siblings rejection
("selecting a paid plan results into an error 404 page"). Validate every
shop value with `^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$` and parse the
referer defensively: a malformed one must give 404, not a 500. Exclude
webhooks, health checks and public pages (e.g. `/privacy`) from the matcher.

Test it with unit tests that send each header combination, including a
cross-site document load to the confirm page.

## CSP frame-ancestors

`frame-ancestors https://<shop> https://admin.shopify.com;` with `<shop>`
validated as above, on **every HTML route** (missing it is a rejection;
a value that ignores the shop is flagged as `STATIC_FRAME_ANCESTORS`). Without a valid shop, allow `admin.shopify.com` only.
Never fall back to `*.myshopify.com`, and never interpolate an unchecked
param (a space or `;` adds sources or whole directives).

## Links that leave the app

- External, `mailto:` and `tel:` links: `target="_blank"`. Without it the
  iframe navigates, and the Admin replaces the app with "This content is
  blocked".
- Shopify-hosted flows that should take over the Admin (plan selection):
  `target="_top"`.
- Downloads: a `window.open` after an `await` can be blocked as a popup in
  Safari and Firefox. Open the tab synchronously in the click handler and set
  its location when the URL is ready, or use an `<a>` with the URL.

## Error and not-found pages

- Next.js 16 uses only the **root** `app/not-found.tsx` for URLs that match
  no route. A not-found inside a route group never catches them, and the
  merchant sees Next's bare 404. Add the root one, rendering the app's own
  page with a way back.
- `error.tsx` for route errors and ideally `global-error.tsx` for the root.
- Every data view handles loading, error (with retry) and empty states. A
  fresh install with no data must show a first-run state that says what to do,
  not zeros or a blank table.
- Every route in the nav has a page; every link target exists.

## Hanging requests

A spinner that never ends fails review like an error page does.

- If the app depends on Redis or workers, a request that enqueues work must
  fail fast when Redis is down (e.g. `enableOfflineQueue: false` on the web
  process's connection) and show an error toast, instead of hanging on
  `maxRetriesPerRequest: null`.
- Make sure workers are running and monitored in production during review;
  background work that never starts looks like a broken core feature.
- Tell reviewers in the testing notes how long background work takes.

## Naming and polish

- No developer-sounding pages in the nav (`/debug`, "Test", "Admin").
- Remove template debris: placeholder names in `package.json` and page
  titles, stray `shopify.app-content.toml`, unused mutations and scopes,
  console.log noise.
- Translations complete for every listed language (same keys in every
  catalog); no hardcoded strings in one language.
- Reviews: 1.3.1 bans incentives, withholding features and non-neutral
  wording; asking inside admin extensions or Sidekick is banned too (2.2.6,
  2.2.9). Our practice: ask only via `shopify.reviews.request()`.
- App Bridge (2.2.3): the CDN script, plus `@shopify/app-bridge-react` if you
  use React. The legacy `@shopify/app-bridge` npm package fails the
  self-review.
- No pop-up windows for OAuth or charge approval.
- Reviewers' ad blockers can stall the automated session-token check; the
  first ID token fetch must not depend on anything an ad blocker would
  block.
