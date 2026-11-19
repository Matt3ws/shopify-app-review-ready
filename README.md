# shopify-app-review-ready

**A Claude Code skill for getting Shopify apps through App Store review the
first time.**

Every rule in here comes from something Shopify actually sent back to one of
six public apps built on the same stack: real rejections, automated security
check findings, deploy gates, and near-misses caught just before submission.
Each one is written down with what Shopify said, why it happened, how it was
fixed, and how to check your own app for it.

A rejection is expensive. Fail the same core requirement twice and Shopify
pauses your submission for weeks. This skill exists so that doesn't happen
again.

---

## What it catches

A few of the cases in the log, to show the kind of thing it knows about:

| What Shopify said | What was actually wrong |
|---|---|
| **1.2.2**: reinstalling during an active billing cycle shows the app on "Free" | The plan was cached with a 6-hour TTL, and the uninstall handler stamped "no plan" as freshly synced |
| **2.1.1**: the restored product didn't include its images | The backup captured media, but the restore never wrote it back |
| "Selecting a paid plan results into an error 404 page" | The iframe gate rejected Shopify's top-level redirect after plan approval |
| `REQUEST_DERIVED_SHOP_SCOPE` (app security check) | A Server Action took the shop from the browser |
| "Not approved to subscribe to webhook topics containing protected customer data" | Order/customer topics in the toml before protected customer data approval, which blocks the whole deploy |
| "This content is blocked" inside the Admin | A `mailto:` link without `target="_blank"` navigated the iframe |
| Compliance webhooks returning 200 and doing nothing | Logging a data request isn't fulfilling it |

The full log is in [`references/rejections.md`](references/rejections.md).

## How it works

When you're preparing a submission, answering a rejection, or building
something reviews tend to fail on (billing, install and reinstall, webhooks,
customer data, the iframe gate), the skill has Claude:

1. **Run a static audit.** `scripts/audit.py` checks the repo for the
   concrete patterns behind past rejections.
2. **Check every recorded rejection** against your app, using the "Detect"
   step each entry carries.
3. **Walk a pre-submission checklist** covering install and session, billing,
   core functionality, embedded-app quality, data and compliance, security,
   and the listing.
4. **Hand you the reviewer's flows** to run on production: install, choose a
   plan, reinstall mid-cycle, use every advertised feature, the failure paths.
5. **Write a readiness report** (blockers, risks, what needs a human to check
   in the Partner Dashboard) and **testing instructions** reviewers can follow.

For a rejection, it reproduces each requirement, looks for the root cause
rather than the symptom, checks your other apps for the same bug, and adds
the case to the log.

## Install

For all your projects:

```bash
git clone https://github.com/Matt3ws/shopify-app-review-ready ~/.claude/skills/shopify-app-review-ready
```

For one project:

```bash
git clone https://github.com/Matt3ws/shopify-app-review-ready .claude/skills/shopify-app-review-ready
```

Run `git pull` in that folder to update. The skill triggers on its own when
the work matches; you can also ask for it by name:

> Use shopify-app-review-ready. We're resubmitting tomorrow, is anything missing?

## The audit script

No dependencies, Python 3 only. It works on any app repo, and is tuned for
Next.js apps built from a Shopify app template (`proxy.ts`, App Bridge,
managed pricing).

```bash
python3 scripts/audit.py path/to/your-app
```

```text
Shopify review audit: my-app (272 code files)

FAIL  root not-found: No app/not-found.tsx. Next 16 uses only the root one for unmatched URLs, so they show a bare 404 (2.1.1). [app/]
FAIL  iframe gate: proxy.ts 404s non-iframe requests but doesn't clearly let through a top-level request with a valid ?shop= ... [proxy.ts]
WARN  app_subscriptions/update: Production toml doesn't subscribe to app_subscriptions/update ... [shopify.app.toml]
INFO  protected customer data: Scopes ['read_customers', 'read_orders']: check PCD approval (and Level 2 fields) for the PRODUCTION app.

2 fail, 1 warn, 1 info. Confirm each in the code before reporting it.
```

It exits with `1` when there's a `FAIL`, so it can run in CI. Findings are
leads, not verdicts. It can't see the Partner Dashboard, your production
environment or runtime behaviour; the checklist and the reviewer flows cover
those.

## What's inside

```
SKILL.md                           the workflow: audit, handling a rejection, report and notes templates
references/rejections.md           every rejection and near-miss, newest first
references/checklist.md            the pre-submission checklist, by area
references/billing.md              managed pricing and the Billing API, done the way that passes
references/embedded-app.md         install, the iframe gate, CSP, links, error pages, hanging requests
references/data-and-compliance.md  protected customer data, scopes, GDPR webhooks
references/reviewer-flows.md       what reviewers do, as a script to run on production
scripts/audit.py                   the static audit
```

## Contributing

The skill is only as good as its rejection log. When Shopify sends something
back, or you catch something before Shopify does:

1. Add an entry at the top of `references/rejections.md`: date, app,
   requirement, Shopify's exact words, cause, fix, and how to detect it.
2. If a grep could have caught it, add a check to `scripts/audit.py` and run
   it against a few apps to make sure it isn't noisy.
3. If it changes how something should be built, update the matching reference.

Shopify's requirements change; when a reference disagrees with
[shopify.dev](https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements),
the docs win. Open an issue or a pull request.
