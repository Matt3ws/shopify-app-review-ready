---
name: shopify-app-review-ready
description: Get a Shopify app through App Store review the first time, using the rejections and near-misses our own apps have actually hit. Use this whenever a Shopify app (public, embedded, managed pricing or Billing API) is being prepared for submission or resubmission, when Shopify sends a review back (requirement numbers like 1.2.2 or 2.1.1, "your app submission has been paused", a reviewer screencast), or when work touches the areas reviews fail on - billing and plans, install/uninstall/reinstall, the iframe gate or CSP, compliance (GDPR) webhooks, protected customer data, access scopes, error pages, or the listing and testing instructions. Use it even when the user only says "make it ready for review", "submit the app", "Shopify sent it back" or "is anything missing before we resubmit", and before building any feature in those areas.
---

# Shopify app: ready for review

A rejection costs weeks. After repeated failures on a core requirement Shopify
pauses the submission entirely (Backup Hero was paused until 2026-11-20 for
"multiple failures to resolve a core requirement issue"). Reviewers install the
app on a development store, choose a plan, use the core features exactly as the
listing describes them, uninstall and reinstall, and fail anything that errors,
404s, or shows the wrong state. They don't read your code, and they don't
give partial credit.

This skill is the team's memory of what Shopify has actually sent back. The
references hold the detail; this file is the workflow.

## Pick the mode

- **Pre-submission audit**: "make it ready", "anything missing before we
  submit", or just before a (re)submission. Do the whole audit below.
- **A rejection came back**: go to [Handling a rejection](#handling-a-rejection).
- **Building in a risky area** (billing, install lifecycle, webhooks, customer
  data, the proxy gate, external links): read the matching reference before
  writing code, so the pattern is right the first time.

## Pre-submission audit

Work through these in order. Each step says why it exists.

0. **Check the blockers outside the code first.** IP allowlist enforced
   (no new installs without one since 2026-11-20), protected customer data
   granted, paid plans selectable by a reviewer from another organization.
   They're in section 0 of the checklist. A perfect app that a reviewer
   can't install still fails.

1. **Map the app.** Find the production and dev app configs
   (`shopify.app.toml` vs `shopify.app.<env>.toml`), the billing model
   (managed pricing or Billing API, free plan or not), the scopes and webhook
   topics, the production env (ask the user for it with secrets redacted), and
   what the listing promises. The listing is the contract: the reviewer tests
   what it claims.

2. **Run the static audit.** `python3 scripts/audit.py <app-dir>` (no
   dependencies). It greps for the concrete patterns behind past rejections.
   Treat every finding as a lead: open the file and confirm before reporting.
   It cannot see the Partner Dashboard, production env, or runtime behaviour.

3. **Check every past rejection against this app.** Read
   [references/rejections.md](references/rejections.md). Each entry has a
   "Detect" line; run it. These happened to apps built the same way, so they're
   the most likely to happen again.

4. **Walk the checklist.** [references/checklist.md](references/checklist.md),
   area by area. Mark each item OK / RISK / UNKNOWN with evidence
   (`path:line`, a command's output, or "needs Partner Dashboard check").
   Deeper material:
   - Billing (App Pricing changed on 2026-04-28): [references/billing.md](references/billing.md)
   - Security, Shopify's automated checks, PCD obligations, IP allowlist: [references/security.md](references/security.md)
   - Embedded app, proxy gate, CSP, links, errors: [references/embedded-app.md](references/embedded-app.md)
   - Customer data, scopes, compliance webhooks: [references/data-and-compliance.md](references/data-and-compliance.md)
   - Theme app extensions, App Proxy, Functions: [references/storefront-and-extensions.md](references/storefront-and-extensions.md)

5. **Run Shopify's own tools.** `shopify app security check`, and the
   official self-review list
   (`shopify doc fetch --url https://shopify.dev/docs/apps/launch/app-store-review/app-store-ai-self-review-requirements`).
   If the Shopify plugin skill (`shopify-plugin:shopify`) is available, use
   it to fetch current docs instead of relying on memory, including this
   skill's.

6. **Compare with an approved sibling app.** If the team has a public app that
   already passed review on the same stack, look at how it solves each
   requirement. A difference is a lead, not proof: the sibling may never have
   been tested on that path, or may run under older platform rules. (Copying
   an older app's billing read nearly re-broke 1.2.2; see the near-miss in the
   log.)

7. **Run the reviewer's flows on production.** Follow
   [references/reviewer-flows.md](references/reviewer-flows.md) against the
   production app, on a development store and a non-development store (dev
   stores skip the protected customer data gate), not the dev app: their configs,
   handles, env and Partner Dashboard approvals differ, and the reviewer only
   sees production. If you can't run them yourself, hand the user the exact
   script.

8. **Check that production runs the code you audited.** An audit of the
   working tree says nothing about what the reviewer gets. After deploying,
   repeat the decisive checks against the live URL (the plan-return URL must
   not 404, the plan shows after a reinstall). Backup Hero's audit found the
   fixed iframe gate still 404ing live because the fix wasn't deployed.

9. **Write the report and the submission notes** (templates below).

### Running it efficiently

The audit is large. Do the gathering in parallel, and keep the judging and
the report for yourself. Four independent read-only jobs worked well:

1. Walk the official self-review list against the code.
2. Check per resource or feature that what the app captures or promises is
   what it writes back and compares (for any app that copies, syncs or
   restores data).
3. and 4. Run Shopify's security agent checks, split into auth/tenant and
   credentials/data.

Confirm every finding a job reports in the code yourself before it goes in
the report: jobs report with confidence either way.

## Handling a rejection

1. Split the email into requirements. Quote each one exactly; the wording
   says what they tested ("Reinstalling the app during an active billing
   cycle…").
2. Reproduce it the way the screencast shows, on production. If you can't,
   reproduce it locally against the same code path and say what differs.
3. Find the root cause, not the symptom. Both Backup Hero failures looked
   like one-line bugs and were design gaps: a cached plan with a TTL, and a
   restore that never wrote a field the backup had.
4. Fix it, then check every **other** app on the same stack for the same bug.
   The same template produced the same bug more than once.
5. Add the case to [references/rejections.md](references/rejections.md) in
   this skill's repo (date, app, requirement, quote, cause, fix, detect), and
   if a static check could have caught it, add it to `scripts/audit.py`. This
   is how the skill stays useful.
6. In the resubmission notes, say per requirement what changed and how to see
   it.

## Principles that come out of the rejections

- **Read lifecycle state from Shopify, and never cache its absence.** Plan,
  subscription and install state change outside your app (uninstall,
  reinstall, a plan change on Shopify's page). With App Pricing the plan comes
  from the Partner API; cache only a confirmed plan, for minutes. A cached
  "no plan" is what failed 1.2.2.
- **Everything the listing or UI promises must round-trip.** If a backup
  includes images, a restore must put images back. Test delete-then-restore
  (or create-then-verify) for every option the UI offers, on a real store.
  "Comes back" includes being published to the same sales channels, stocked
  at the same locations, and linked from the same menus.
- **A limit only counts as disclosed if the merchant can see it.** Caveats
  in code comments or unused arrays protect no one; show them where the
  merchant chooses or approves.
- **Production is a different app.** Different client ID, handle, toml,
  env, and Partner Dashboard approvals (protected customer data is approved per
  app). Verify production; never infer it from dev.
- **A development store is not the reviewer's store.** Dev stores skip the
  protected customer data gate, and reviewers place test orders. Test
  order and customer features on a non-dev trial store with Bogus Gateway
  orders.
- **The reviewer's first minute matters.** Install lands in the app UI with no
  login, the app explains what to do, and no page 404s or hangs. A store with
  no plan must be pointed at the plans.
- **Fail open for merchants, never show the wrong state.** If Shopify can't
  answer, keep the last known plan. Don't downgrade, and don't claim a plan
  that isn't there.
- **Verify Shopify claims against the docs** (shopify.dev, `shopify doc
  fetch`, or the Shopify skill) and write down what they said and when.
  Billing, tokens and allowlists changed during 2026; memory and our own
  READMEs have been wrong.
- **Never edit the production `shopify.app.toml` without explicit
  confirmation.** Webhook topics and scopes there are deploy-time gates
  (protected customer data can make `shopify app deploy` refuse the whole app).

## Report template

```markdown
# <App> - App Review readiness (<date>)

Verdict: READY / NOT READY - <one line why>

## Blockers (fix before submitting)
- <requirement or area> - <what fails> - <evidence path:line or output> - <fix>

## Risks (could fail; fix or explain in the testing notes)
- ...

## Needs a human check (Partner Dashboard, production env, listing)
- [ ] <exact place to look and what it must say>

## Verified OK
- <area> - <evidence>
```

## Submission notes template

Reviewers follow testing instructions literally. Give them a path that works:

```text
Testing instructions
1. Install the app. It opens on <page>.
2. Choose a plan on Plans & billing (test charges are free on development stores).
3. <Core flow 1, step by step, with what they should see and how long it takes.>
4. <Core flow 2 ...>
Notes: <anything that runs in the background and how long it takes; features that need data on the store and how to create it; anything intentionally not available, and why.>

Changes since the last review (resubmissions)
- <requirement>: <what was wrong> -> <what changed> -> <how to see it>
```

Attach your own screencast of the same flows passing when resubmitting after a
rejection.
