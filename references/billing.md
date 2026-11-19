# Billing that passes review

Reviewers test billing on almost every paid app: choose a plan, approve it,
come back to the app, upgrade or downgrade, decline, and uninstall and
reinstall during a paid cycle. Requirement 1.2.2 is about this whole loop.

## Contents
- What the reviewer checks
- Reading the plan (the pattern)
- The round trip to Shopify's plan page
- Uninstall and reinstall
- Webhook: app_subscriptions/update
- Store with no plan
- Test charges, trials, dev stores
- Enforcement switches

## What the reviewer checks

1. The app links to plan selection (managed pricing: Shopify's hosted page).
2. After approving, they land back in the app (no 404) and **the app shows the
   plan they chose**.
3. Upgrade and downgrade work without contacting support.
4. Declining leaves the app usable and honest about having no plan.
5. Uninstall and reinstall during a paid cycle: the app shows the paid plan
   still running until it ends (or asks to approve again if Shopify says
   there's no subscription). It must never show "Free" over a live plan.

## Reading the plan

Read it from the Admin API with the shop's own offline token, on every app
open. This is how our approved apps do it, and it works for managed pricing
and the Billing API alike.

```graphql
query getActiveSubscriptions {
  currentAppInstallation {
    activeSubscriptions {
      id
      status
      test
      createdAt
      trialDays
      currentPeriodEnd
      lineItems {
        plan {
          pricingDetails {
            __typename
            ... on AppRecurringPricing { planHandle }
          }
        }
      }
    }
  }
}
```

- Entitling statuses: `ACTIVE` (and `ACCEPTED`). Anything else is no plan.
- `planHandle` lives on `AppRecurringPricing` (managed pricing). Don't match
  on `name`: Shopify localizes it.
- **Don't filter out `test: true`.** Development stores and App Review use
  test charges; they're real subscriptions for the app's purposes.
- Trial end: `createdAt + trialDays`.
- An active subscription without a handle is a surprise, not "no plan":
  treat it as an error and keep the last known plan.

Rules that came from the 1.2.2 rejection:

- **No TTL on the plan read.** One cheap query per open costs nothing; a
  cache is how a reinstall showed Free for six hours.
- **Fail open, never wrong.** If the query fails (network, revoked token),
  keep the stored plan and don't mark it synced. Only a definite answer
  ("active with handle X" or "none") is written.
- **Don't use the Partner API for this.** It needs organization
  credentials in the env, answers only for listed apps, and is rate
  limited. The Admin API answers for the installation itself.
- Storing the plan for background jobs is fine, as long as every app open and
  every `app_subscriptions/update` overwrites it from Shopify.

## The round trip to Shopify's plan page

- Plan selection URL (managed pricing):
  `https://admin.shopify.com/store/<store-handle>/charges/<app-handle>/pricing_plans`
  where `<store-handle>` is the shop domain without `.myshopify.com`.
- Read `<app-handle>` from `currentAppInstallation.app.handle`. Dev and
  production apps have different handles; an env var that's wrong or unset
  sends the button to a Shopify 404 or hides it.
- Open it with `target="_top"` (or App Bridge `open(url, '_top')`); it won't
  render inside the iframe.
- Coming back: Shopify redirects to the plan's **welcome link** (Partner
  Dashboard → pricing) with `plan_handle` appended. Two things must hold:
  - The welcome-link path exists in the app. If it points at the app root,
    the root must notice `plan_handle` and forward or refresh.
  - The iframe gate lets the request through. It can arrive as a
    **top-level cross-site** load with `?shop=` and an `admin.shopify.com`
    referer. See [embedded-app.md](embedded-app.md#the-iframe-gate). This was
    a rejection ("selecting a paid plan results into an error 404 page").
- The return happens whether the merchant approved or backed out, and the
  params don't say which. Re-read the plan and show what it is; don't announce
  "upgraded".

## Uninstall and reinstall

- `app/uninstalled`: mark the shop uninstalled and pause scheduled work.
  Clearing the stored plan is fine. **Don't record it as synced**, because
  that blocks the next read.
- Don't delete merchant data on `app/uninstalled`. Delete on `shop/redact`,
  which Shopify sends about 48 hours later. A quick reinstall then finds its
  data intact.
- A reinstall is an *update* of the existing store row, not a new install, so
  "first install only" hooks don't run. Make sure the plan read, resuming
  paused work, and re-registering webhooks don't depend on "is new".
- A late `app/uninstalled` delivery can arrive after the reinstall. Compare
  its `X-Shopify-Triggered-At` with when the new token was exchanged, and
  ignore it if the reinstall is newer.
- Quick reinstall edge: a stored token can be revoked yet look valid. If the
  first Admin call on open fails with 401 and the refresh fails, exchange a
  new token in the same open rather than leaving the merchant broken until
  the next one.

## Webhook: app_subscriptions/update

Every approved Edition public app subscribes to it. On delivery, re-read the
plan with the query above (the payload doesn't carry `planHandle`). Without
it, a merchant who downgrades or cancels while the app is closed keeps paid
features until they next open the app, which our audit flagged as a terms
problem. Adding it means editing the production toml: get explicit
confirmation first.

## Store with no plan

If there's no free plan, a store with no subscription must be clearly pointed
at the plans: on first open, not only on the billing page. A reviewer who
installs and sees a working app with no hint about plans may conclude billing
isn't implemented, and one who meets a "Get a plan" wall without explanation
may conclude the app is broken. Say what to do, with one button to the plan
page.

## Test charges, trials, dev stores

- Show a "Test charge" badge when `test` is true, so it's clear no money moved.
- Show the trial end only when Shopify says there is a trial; don't advertise
  "14-day free trial" to a reinstalling shop that may already have used it.
  Keep the trial length in copy equal to the Partner Dashboard.
- Prices in the UI must match the Partner Dashboard exactly; a mismatch
  reads as bait and switch.
- `shop.plan.partnerDevelopment` tells you it's a development store, if you
  want to explain that no real charge applies.

## Enforcement switches

Some apps gate features on the plan behind an env switch. Turning
enforcement on during review adds risk (the reviewer meets plan walls) and
isn't what 1.2.2 tests: it tests that the plan shown is right. If enforcement
stays off, the UI must still show the correct plan and still point plan-less
stores at the plans. Turn it on after approval, once you've watched the plan
read work in production for a few days.
