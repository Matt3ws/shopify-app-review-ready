# shopify-app-review-ready

**A Claude Code skill for getting Shopify apps through App Store review the
first time.**

Every rule in here comes from one of two places. The first is something
Shopify actually sent back to one of our apps (six public apps and a number of
custom ones, all built on the same stack): real rejections, automated
security check findings, deploy gates, and near-misses caught just before
submission. Each one is written down with what Shopify said, why it
happened, how it was fixed, and how to check your own app for it. The second
is Shopify's own documentation on review, security, billing and protected
customer data, as of November 2026, with links.

A rejection is expensive. Fail the same core requirement twice and Shopify
pauses your submission for weeks. This skill exists so that doesn't happen
again.

---

## What it catches

A few of the cases in the log, to show the kind of thing it knows about:

| What Shopify said | What was actually wrong |
|---|---|
| **1.2.2**: reinstalling during an active billing cycle shows the app on "Free" | The plan was cached with a 6-hour TTL, and the uninstall handler stamped "no plan" as freshly synced |
| **2.1.4**, three rounds: orders and revenue showed zero | Dev stores skip the protected customer data gate, and test orders were filtered out; the reviewer's store hit both |
| No new installs from 2026-11-20 | No IP allowlist (bulk operations were already blocked from 2026-11-12) |
| A plan chosen on Shopify's page didn't show in the app (near-miss) | Shopify App Pricing status comes from the Partner API since April 2026, not `currentAppInstallation` |
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

1. **Check the blockers outside the code**: IP allowlist, protected
   customer data, plans a reviewer can select.
2. **Run a static audit.** `scripts/audit.py` checks the repo for the
   concrete patterns behind past rejections.
3. **Check every recorded rejection** against your app, using the "Detect"
   step each entry carries.
4. **Walk a pre-submission checklist** covering install and session, billing,
   core functionality, embedded-app quality, data and compliance, security,
   and the listing, and run Shopify's own `shopify app security check` and
   self-review.
5. **Hand you the reviewer's flows** to run on production: install, choose a
   plan, reinstall mid-cycle, use every advertised feature, the failure paths,
   on a non-development store as well.
6. **Write a readiness report** (blockers, risks, what needs a human to check
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

FAIL   root not-found: No app/not-found.tsx. Next 16 uses only the root one for unmatched URLs, so they show a bare 404 (2.1.1). [app/]
FAIL   iframe gate: proxy.ts 404s non-iframe requests but doesn't clearly let through a top-level request with a valid ?shop= ... [proxy.ts]
CHECK  IP allowlist: Dev Dashboard → app → Settings → IP allowlist: enforced, with IPv4 and IPv6, tested against recent traffic ...
CHECK  protected customer data: Dev Dashboard → Settings → Access requests: granted (not in review) for the PRODUCTION app ...
WARN   billing source: Plan read from currentAppInstallation.activeSubscriptions. With Shopify App Pricing ... the Admin API shows nothing ...
WARN   dependency automation: No Dependabot or Renovate config; Shopify's security check flags MISSING_DEPENDENCY_SECURITY_AUTOMATION.

2 fail, 2 warn, 2 to check by hand, 0 info. Confirm each in the code before reporting it.
```

It exits with `1` when there's a `FAIL`, so it can run in CI. `CHECK` lines
are things code can't show (IP allowlist, protected customer data approval)
that a person has to confirm in the Dev Dashboard. Findings are leads, not
verdicts. It can't see the Partner Dashboard, your production
environment or runtime behaviour; the checklist and the reviewer flows cover
those.

## What's inside

```
SKILL.md                           the workflow: audit, handling a rejection, report and notes templates
references/rejections.md           every rejection and near-miss, newest first
references/checklist.md            the pre-submission checklist, by area
references/billing.md              Shopify App Pricing (and what changed on 2026-04-28), the Billing API
references/security.md             Shopify's security checks, IP allowlist, tokens, PCD Level 1/2 obligations
references/embedded-app.md         install, the iframe gate, CSP, links, error pages, hanging requests
references/data-and-compliance.md  protected customer data, scopes, GDPR webhooks
references/storefront-and-extensions.md  theme app extensions, App Proxy, Functions: deploy limits and auth
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
