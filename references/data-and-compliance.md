# Customer data, scopes and compliance webhooks

These fail in two ways: Shopify refuses to deploy or submit (protected
customer data, missing compliance webhooks), or the reviewer's store returns
denied or null data and a core feature looks broken.

## Protected customer data (PCD)

- Reading customers, orders, draft orders, or subscribing to `orders/*` or
  `customers/*` webhook topics needs **Protected customer data access**
  approved in the Partner Dashboard.
- Approval is **per app**. Dev and production are separate apps; "we're
  approved" usually means production only.
- **Level 1** covers customer data without personal fields; **Level 2**
  covers name, email, phone and address, and each field needs its own
  justification plus the data-protection questions answered. A field you
  query but weren't approved for comes back denied or null.
- Subscribing to a gated webhook topic without approval makes
  `shopify app deploy` refuse the **whole app**. CI can't see this; check the
  toml before every deploy.
- Code must survive a denial: treat `ACCESS_DENIED` on a resource as
  "skipped, here's why", not a crash. Word the message so the merchant knows
  it's the app's permission, not something they can fix.
- Before submitting, check in the Partner Dashboard, for the **production**
  app, that every personal field the app reads is requested with a reason.

## Scopes

- Request only what the app uses. Unused write scopes invite reviewer
  questions; remove dead code that needs them.
- `read_all_orders` (orders older than 60 days) needs its own approval
  request in the Partner Dashboard, and the reviewer should be able to see why
  (say it in the testing notes).
- Optional scopes requested at runtime (`shopify.scopes.request()`) are fine
  for features merchants opt into; request them at the moment of need.
- Keep the scope list in the env (`SCOPES`) equal to the toml.

## Compliance webhooks (mandatory for public apps)

All three must be subscribed in the production toml and **actually
fulfilled**:

| Topic | Obligation |
|---|---|
| `customers/data_request` | Get the customer's data to the merchant (e.g. a downloadable export in the app). Logging it isn't enough. |
| `customers/redact` | Delete that customer's personal data everywhere, including inside long-lived copies (backups, exports, undo records). |
| `shop/redact` | Arrives about 48 hours after uninstall. Delete everything for the shop, including object storage. |

Webhook handling that passes Shopify's automated checks:

- Verify the HMAC **before** anything else (dedup, parsing). Bad or missing
  HMAC returns 401.
- A valid delivery returns 200. Be careful with extra rejections: a 401 or
  400 for something other than a bad HMAC (shop header mismatch, stale
  delivery) is a risk if Shopify's test payloads trip it. Prefer "200 and do
  nothing, log a warning" for those.
- Either answer quickly and process after (`after()`), or enqueue before
  answering so a failure becomes a 500 that Shopify retries. Both are used in
  our apps; whichever you choose, it can't hang if Redis is down.
- Shopify won't resend after a 200, so the job must retry on its own for
  minutes (e.g. 5 attempts, 30s exponential backoff) and keep failures
  visible.
- A handler that catches and swallows errors can never be retried by the
  queue; let it throw.

## Data lifecycle claims

When a change affects what data is kept, for how long, or when it's deleted,
cite the platform requirement from the docs in the plan, not from memory.
Key facts we verified: `shop/redact` comes about 48 hours after uninstall;
nothing requires deleting on `app/uninstalled`; retention limits apply to
personal data, not product data.

## Policies and support

- The listing needs a privacy policy URL that covers what this app stores
  (for a backup app: customer and order data inside snapshots, how long, how
  it's deleted). If the policy is served by the app, keep that route public
  (outside the Admin providers and excluded from the iframe gate).
- A visible support contact in the app (settings or footer, `mailto:` with
  `target="_blank"`) isn't a listed requirement but helps reviewers and
  merchants.
