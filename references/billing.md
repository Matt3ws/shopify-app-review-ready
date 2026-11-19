# Billing that passes review

Reviewers test billing on almost every paid app: choose a plan, approve it,
come back to the app, upgrade or downgrade, decline, and uninstall and
reinstall during a paid cycle. Requirement 1.2.2 covers the whole loop:
"ensure that it can accept, decline and request approval for charges again on
reinstall."

**Shopify App Pricing (managed pricing) changed on 2026-04-28.** Several
things that worked for apps set up earlier, including our own older apps,
are wrong for apps set up after that. Check which one you are before copying a
sibling app. Source:
https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing

## Contents
- What the reviewer checks
- Reading the plan (Shopify App Pricing)
- Apps set up before April 2026
- The round trip to Shopify's plan page
- Testing plans, and the reviewer's store
- Uninstall and reinstall
- Store with no plan
- Enforcement switches

## What the reviewer checks

1. The app links to plan selection (App Pricing: Shopify's hosted page).
2. After approving, they land back in the app (no 404) and **the app shows the
   plan they chose**.
3. Upgrade and downgrade work without contacting support.
4. Declining leaves the app usable and honest about having no plan.
5. Uninstall and reinstall during a paid cycle: the app honours the paid plan
   for the rest of its period, or asks for approval again if Shopify says
   there's no subscription. It must never show "Free" over a live plan
   (Backup Hero's 1.2.2 rejection).

## Reading the plan (Shopify App Pricing)

From the docs: "With Shopify App Pricing, subscription status comes from the
Partner API, not from the GraphQL Admin API." The Admin API's
`currentAppInstallation.activeSubscriptions` doesn't list App Pricing
subscriptions, so an app reading it shows "no plan" to a merchant who just
paid. The migration guide says to replace `billing.check()` and
`currentAppInstallation` checks with Partner API queries.

```graphql
# Partner API: https://partners.shopify.com/<org-id>/api/<version>/graphql.json
query ActiveSubscription($appId: ID!, $shopId: ID!) {
  activeSubscription(appId: $appId, shopId: $shopId) {
    trialEndsAt
    cancelAtEndOfCycle
    items { handle }
  }
}
```

- Credentials: a Partner API client with the "Manage apps" permission, your
  organization id, and the app's gid. `shopId` is the shop's Admin gid
  (`shop { id }` via the Admin API, cache it). Public apps only.
- Rate limit: 4 requests a second per client. Throw on throttled or failed
  responses; **never treat an error as "no subscription"**.
- **Cache only a confirmed subscription, briefly** (Shopify suggests about
  five minutes), so a merchant who just approved a plan is checked immediately.
  **Never cache "no plan".** Backup Hero cached everything for six hours, and
  its uninstall handler stamped "no plan" as freshly synced, so a reinstall
  showed Free (1.2.2).
- Fail open, never wrong: on an error, keep the last known plan and don't mark
  it synced.
- No webhook tells you about a change: "After April 28, 2026, Shopify App
  Pricing no longer sends webhooks for subscription changes." Read the
  Partner API on app open and after the plan redirect; for background jobs,
  re-check on a schedule or use the Partner API's `events` query.
- One-time purchases from a Billing API past still come from
  `currentAppInstallation`; check both if you migrated.

## Apps set up before April 2026

Legacy behaviour still applies to apps enrolled earlier (this is why our
older apps read `currentAppInstallation` and subscribe to
`app_subscriptions/update`, and passed review that way):

- `APP_SUBSCRIPTIONS_UPDATE` webhooks were sent before 2026-04-28. Our
  experience: a plan switch sends two (new `ACTIVE`, old `CANCELLED`) in no
  guaranteed order, so only `ACTIVE` may set the plan. Better to treat it as a
  trigger and re-read.
- `charge_id` was appended to the redirect before 2026-04-28; it no longer
  is.
- Test subscriptions were created on development stores before 2026-04-28.
  Now "the `test` field on the GraphQL Admin API `AppSubscription` object is
  `false`" for no-charge subscriptions; don't use it.

If you don't know when your app was enrolled, follow the current rules: the
Partner API answers for both.

## The round trip to Shopify's plan page

- Plan selection URL:
  `https://admin.shopify.com/store/<store-handle>/charges/<app-handle>/pricing_plans`
  where `<store-handle>` is the shop domain without `.myshopify.com`.
- The app handle must be the **production** app's. Dev and production apps
  have different handles; a wrong or unset one sends "Change plan" to a
  Shopify 404 or hides the button.
- Open it with `target="_top"` (or the framework's redirect out of the
  iframe). Shopify's best practices: no pop-up windows for charge approval.
- Coming back: Shopify redirects to the plan's **welcome link** (redirection
  URL, per plan). Documented: for apps with an App Home, a relative path such
  as `/welcome` with `plan_handle` appended; `shop` is appended only for
  external URLs. Make sure:
  - The path exists in the app. If it's the app root, the root must notice
    `plan_handle` and forward or refresh.
  - The iframe gate lets the request through. **Observed by us, not
    documented:** the return can arrive as a top-level, cross-site load with
    `?shop=` and an `admin.shopify.com` referer, and a gate that only admits
    iframe loads answers 404 (the Super Siblings rejection). See
    [embedded-app.md](embedded-app.md#the-iframe-gate).
- After the redirect, query the Partner API to confirm, and show the plan
  Shopify reports rather than announcing an upgrade.

## What the plan page may show (1.2.3)

- **Only plans the merchant can choose and approve through Shopify.** No
  "Contact us", "Contact sales", "Book a call" or custom-quote card, not even
  as the last card. Shopify rejected Backup Hero's Enterprise card for this.
  Enterprise or custom deals are **private plans** you assign in the Partner
  Dashboard; describe them in the listing's "Description of additional
  charges".
- A shop on a private plan must still see it as its current plan, with its
  limits; just don't offer it to everyone.
- Upgrade and downgrade must work from the app without contacting support:
  every card's button goes to Shopify's plan page.
- The limits on a card or status line must be what the merchant actually
  gets. Don't show a paid plan's limits to a shop with no plan, and if
  enforcement is off during review, don't promise caps the app doesn't apply.
- The plan page has to work in **production**: in Next.js, render it per
  request. A billing page prerendered at build time froze "Plan changes are
  unavailable" into Backup Hero, because the build had no app handle (flagged
  under 1.2.2).

## Testing plans, and the reviewer's store

- Development stores test App Pricing **at no charge**, but which plans
  depend on who owns the app and the store. On a dev store owned by
  **another** Partner organization, which is what a reviewer uses, only free
  plans and paid plans marked **"free for partners and developers"** can be
  selected at no charge. Set that on the paid plans, or the reviewer can't
  test them.
- A no-charge subscription is the paid plan's handle with $0 prices. Don't
  show a "test charge" badge based on `test`.
- Known limitation: the plan selection page can 404 for a draft app when the
  dev store's locale differs from the listing's. Test with the listing's
  language.
- Prices, trial length and plan names in the app and listing must match the
  Partner Dashboard exactly. Show a trial end only when Shopify reports one.
  Enterprise or custom plans go in the listing's "Description of additional
  charges", not as fake plans.

## Uninstall and reinstall

- The Billing API docs say Shopify cancels the subscription on uninstall,
  and "Merchants can reinstall and use the app for the remainder of the
  billing period." The App Pricing docs don't say what `activeSubscription`
  returns after an uninstall, and our reviewer saw the paid plan "remains
  active until its expiration date". **Test it on production**; don't assume.
  If you read the Billing API, a `CANCELLED` subscription with
  `currentPeriodEnd` in the future may still entitle the merchant.
- `app/uninstalled`: mark the shop uninstalled and pause scheduled work.
  Clearing the stored plan is fine. **Don't record it as synced.**
- Don't delete merchant data on `app/uninstalled`; delete on `shop/redact`
  (about 48 hours later). A quick reinstall then finds its data.
- A reinstall updates the existing store row. "First install only" hooks
  don't run, so the plan read, resuming paused work, and webhook registration
  mustn't depend on "is new" (2.3.4: no install-once flags, no failure on a
  duplicate row).
- A late `app/uninstalled` delivery can arrive after the reinstall: compare
  its `X-Shopify-Triggered-At` with when the new token was exchanged.

## Store with no plan

Shopify's documented App Pricing integration has three parts: check for an
active subscription, **gate access**, and **redirect merchants without an
active subscription to the hosted plan selection page**, from the app's root
so it works whichever page they arrive on
(https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing,
…/redirect-plan-selection-page). For an app with no free plan, this is how it
"requests approval for charges again on reinstall" (1.2.2): a reinstalled
shop whose subscription has ended lands on the plan page.

An app that lets a no-plan shop use everything, with only a note on the
billing page, never asks for approval. That's a 1.2.2 risk even when the plan
display is right.

## Enforcement switches

Some of our apps gate features behind an env switch that's off until
listing. Know what "off" means for the reviewer:

- If "off" also turns off the redirect to the plan page, the reviewer can use
  the whole paid app without approving a charge, which is the opposite of
  Shopify's documented integration. Keep the **redirect** on even when the
  feature limits are off.
- If enforcement is on, a reviewer who hasn't picked a plan meets plan walls.
  That's fine as long as every wall explains itself and links to the plan
  page, and the testing notes tell them to pick a plan first.

Decide this per app before submitting, and say in the testing notes which
one the reviewer will see.
