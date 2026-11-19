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
   Deeper material for the two areas that fail most:
   - Billing: [references/billing.md](references/billing.md)
   - Embedded app, proxy gate, CSP, links, errors: [references/embedded-app.md](references/embedded-app.md)
   - Customer data, scopes, compliance webhooks: [references/data-and-compliance.md](references/data-and-compliance.md)

5. **Compare with an approved sibling app.** If the team has a public app that
   already passed review on the same stack, look at how it solves each
   requirement before inventing a solution. A difference is a lead, not proof:
   the sibling may simply never have been tested on that path.

6. **Run the reviewer's flows on production.** Follow
   [references/reviewer-flows.md](references/reviewer-flows.md) against the
   production app on a development store, not the dev app: their configs,
   handles, env and Partner Dashboard approvals differ, and the reviewer only
   sees production. If you can't run them yourself, hand the user the exact
   script.

7. **Write the report and the submission notes** (templates below).

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

- **Read lifecycle state from Shopify, live.** Plan, subscription, and
  install state change outside your app (uninstall, reinstall, upgrade on
  Shopify's page). A cached copy with a TTL is what failed 1.2.2. One cheap
  Admin API query per app open is fine.
- **Everything the listing or UI promises must round-trip.** If a backup
  includes images, a restore must put images back. Test delete-then-restore
  (or create-then-verify) for every option the UI offers, on a real store.
- **Production is a different app.** Different client ID, handle, toml,
  env, and Partner Dashboard approvals (protected customer data is approved per
  app). Verify production; never infer it from dev.
- **The reviewer's first minute matters.** Install lands in the app UI with no
  login, the app explains what to do, and no page 404s or hangs. A store with
  no plan must be pointed at the plans.
- **Fail open for merchants, never show the wrong state.** If Shopify can't
  answer, keep the last known plan. Don't downgrade, and don't claim a plan
  that isn't there.
- **Verify Shopify claims against the docs** (shopify.dev or the Shopify dev
  MCP) and write down what they said. Memory of how billing or scopes work has
  been wrong before, including in our own READMEs.
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
