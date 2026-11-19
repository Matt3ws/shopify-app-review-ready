# Security: what Shopify checks, and what it expects

Shopify reviews security three ways: the **automated app security check**
(run it yourself first), the **review team** (OWASP, TLS, an open-port scan,
token handling), and, for apps holding customer data, a possible **data
protection review**. Our own audits found several of these issues in our apps
before Shopify did; see [rejections.md](rejections.md).

Sources:
https://shopify.dev/docs/apps/build/security/app-store-requirements,
https://shopify.dev/docs/apps/build/security/app-security-checks,
https://shopify.dev/docs/apps/launch/protected-customer-data,
https://shopify.dev/docs/apps/build/security/credentials-and-data/restrict-api-access-to-your-ip-addresses

## Contents
- Deadlines that block installs
- Run Shopify's own checks
- What the review team tests
- Authentication and tenant isolation
- Webhooks
- Tokens, secrets and the browser
- Infrastructure
- Protected customer data obligations
- Incidents

## Deadlines that block installs

**IP allowlist (required for public apps):**

| Date | What happens without one |
|---|---|
| 2026-11-12 | Bulk queries and bulk mutations are blocked |
| 2026-11-20 | Delisted from the App Store and **blocked from new installs** (so a reviewer can't install) |
| 2027-01-15 | Merchants see a warning |
| 2027-04-01 | All Admin API requests are rejected |

Custom apps installed on stores **outside your organization** (client
stores) need one from 2026-11-20, and every existing such install by
2027-01-01.

Set it up in the Dev Dashboard → app → Settings → IP allowlist:

1. Add your servers' public IPv4 **and IPv6** addresses as CIDR ranges
   (behind NAT, use the gateway's). Use ASNs only for dynamic hosting, and
   limit them to the countries you run in.
2. Click **Test against recent traffic** to see the addresses your app really
   used in the last 30 days.
3. Turn on enforcement.
4. Confirm a request from outside the list gets 403.

Every app needs its own allowlist, even when apps share a server.

**Expiring offline tokens (required):** apps that haven't moved are delisted
on 2027-01-01, and Shopify rejects their API requests from 2027-04-01.

- Access tokens last an hour; the refresh token **rotates on every use**.
- Refresh dormant stores before the refresh token's **90-day** expiry, or
  webhooks and jobs stop until the merchant reinstalls.
- Never exchange or refresh for the same store concurrently, and never
  exchange on every request.

## Run Shopify's own checks

- **App security check:** `shopify app security check`. It looks for:
  - Tenant isolation and authentication: `MISSING_TENANT_ISOLATION`,
    `UNAUTHENTICATED_ENDPOINT`, `REQUEST_DERIVED_SHOP_SCOPE`,
    `REQUEST_CONTROLLED_ADMIN_CONTEXT`, `UNSCOPED_SHOP_CONFIG_WRITE`.
  - Credential leaks: `CREDENTIAL_LOG_LEAKAGE`,
    `CREDENTIAL_BROWSER_LEAKAGE`, `COMMITTED_SECRET`.
  - Shop and request validation: `WEAK_SHOP_VALIDATION`, `OPEN_REDIRECT`,
    `SSRF_REQUEST_FORGERY`, `INSECURE_WEBHOOK_URL`.
  - Embedding: `MISSING_EMBEDDED_CSP`, `STATIC_FRAME_ANCESTORS`.
  - Platform requirements: `EXPIRING_OFFLINE_TOKEN`,
    `MISSING_COMPLIANCE_WEBHOOKS`, `EOL_API_VERSION`.
  - Sessions and data access: `SESSION_LIFECYCLE_AND_REPLAY`,
    `CSRF_MISSING_PROTECTION`, `OVERBROAD_DATA_ACCESS`, `SCOPE_OVER_REQUEST`.
  - Dependencies: `DEPENDENCY_REACHABILITY`,
    `MISSING_DEPENDENCY_SECURITY_AUTOMATION` (it wants Dependabot or Renovate).
  - Injection: `UNSAFE_INNERHTML`, `CROSS_SITE_SCRIPTING`, `SQL_INJECTION`.

  Some deterministic checks only cover the React Router template. On our
  Next.js apps 11 of 15 came back "unresolved" and the other 35 checks are
  only **agent prompts** in `.shopify/app-security/<config>/agent-checks.json`.
  A clean summary is not a pass. How to run it properly:
  1. `shopify app security check --no-input -c shopify.app.toml --exclude 'types/**'`.
     Generated GraphQL types are too large for the scanner and silently block
     COMMITTED_SECRET, EOL_API_VERSION and STATIC_FRAME_ANCESTORS.
  2. Run the relevant agent checks: give each `prompt` to a subagent, grouped
     (auth/tenant, credentials/data), with the file's `instructions`. Skip the
     theme, Liquid, ScriptTag and App Proxy checks if the app has none.
  3. Merge the findings into one document and pipe it to
     `shopify app security record -c shopify.app.toml` (it takes no
     `--exclude`; the scope comes from the document), then
     `shopify app security review -c shopify.app.toml`. Backup Hero's first
     full run: 30 checks, 0 findings, 2 unresolved (App Proxy, not used).
- **Self-review:**
  `shopify doc fetch --url https://shopify.dev/docs/apps/launch/app-store-review/app-store-ai-self-review-requirements`
  gives the requirement list with "verification guidance" for each item.
  Work through it with the code open.

## What the review team tests

- **OWASP Top 10.** Any vulnerability found means rejection.
- **TLS** with a certificate that validates; self-signed is rejected.
- **Open ports (Nmap scan).** Redis, Postgres/MySQL, Memcached,
  Elasticsearch, admin panels (Dokploy, Grafana) and staging must not be
  publicly reachable. Check from outside:
  `nc -z -w 2 <ip> <port>` for 5432, 6379, 6432, 3000, 3001, 8080, 9000,
  9200, 11211, 27017, 3306. Restrict SSH to known addresses if you can.
- **Tokens:**
  - Any token that authenticates a user needs 128 bits of entropy.
  - A token in a URL (download links, magic links) must expire within
    7 days, the page must be `noindex`, and it must be served with
    `Referrer-Policy: no-referrer` (or `origin-when-cross-origin`).
  - No URL shorteners on URLs carrying tokens or personal data.

## Authentication and tenant isolation

- Verify the session token (ID token) on every request: signature, `exp`,
  `nbf`, `aud` equal to the client ID, and the `iss`/`dest` hosts matching.
  ID tokens live a minute; never send them to third parties.
- **Look up every record by shop and id together**, including jobs, exports,
  downloads, restores and anything else addressed by id. An id alone from
  the client is `MISSING_TENANT_ISOLATION`.
- The shop comes from the verified token, never from the request. Anchor
  shop regexes at both ends (`^…\.myshopify\.com$`).
- Debug, test and legacy routes need the same authentication, or must not
  exist in production.
- No Server Actions or public endpoints that take a `shop`.
- Send `frame-ancestors https://<shop> https://admin.shopify.com` on **every
  HTML route**. Missing it is a rejection. A static value that ignores the
  shop is flagged as `STATIC_FRAME_ANCESTORS`. Check the document response in
  DevTools.
- Validate redirect targets (no open redirects) and never fetch a URL the
  client supplied without an allowlist (SSRF).

## Webhooks

- Verify the HMAC on the **raw** body with a timing-safe compare, **before**
  anything else. Topic and shop headers are untrusted until it passes.
- Bad HMAC: answer 401. Shopify's own library sample answers 400; don't copy
  that for compliance topics.
- Be idempotent, keyed on `X-Shopify-Webhook-Id`, and release a dedup claim if
  processing fails, or Shopify's retry gets answered "duplicate".
- Delivery limits: 1 second to connect, 5 seconds total. Any 3xx counts as a
  failure. Shopify retries 8 times over 4 hours, so run a reconcile job for
  anything that must not be missed.
- Webhook URLs must be HTTPS (`INSECURE_WEBHOOK_URL`).
- **Your own writes echo back.** Writing a product (a metafield included)
  fires `products/update` for it; the same goes for other `*/update` topics.
  An app that subscribes to the topic of a resource it writes must drop its
  own echoes (a Redis key per record with the expected `updated_at` and a hash
  of what was written), or it floods itself (Super Siblings).
- **Plan for bursts.** Bulk edits, imports and your own restores send one
  delivery per record. Debounce per record and coalesce per shop; keep the
  route to one cheap idempotent write or an enqueue.
- **Bound every wait in the webhook path.** Give each Redis or database call
  its own deadline and fail open (process without dedup) on timeout. A
  client with `maxRetriesPerRequest: null` waits forever while Redis is down,
  and the delivery overruns the 5-second limit.

## Tokens, secrets and the browser

- Never send access or refresh tokens to the browser: select or omit secret
  columns on every query whose result reaches a response, and test it.
- Never log tokens (session tokens included: some JWT errors embed the whole
  token in their message).
- Secrets live in the environment, never in the repo (`COMMITTED_SECRET`).
  Use separate secrets and OAuth clients per environment.
- Encrypt access tokens and customer data at rest; require the key at boot.

## Infrastructure

- One hardened ingress. Databases, queues, admin panels and staging stay
  private.
- Authenticated TLS between your own services when they cross a network.
- Encrypt at rest, **backups included**, and test restores.
- Passkeys or MFA on Partner, hosting, DNS, Git, registry and email accounts.
- Dependabot or Renovate on every repo, and act on what they raise.
- Keep the framework on a patched version, and the API version at least 90
  days from deprecation (apps can't be submitted otherwise).

## Protected customer data obligations

Request access in the **Dev Dashboard → app → Settings → Access requests**
(choose a distribution method first). An unapproved field doesn't fail the
request: it comes back `null` with HTTP 200 and an `errors` entry ("This app
is not approved to use the phoneNumber field…"). Handle that as well as
`ACCESS_DENIED`. See [data-and-compliance.md](data-and-compliance.md) for
the review traps.

**Level 1** (any protected customer data):
- [ ] Process only the minimum data needed
- [ ] Tell merchants what you process and why
- [ ] Use data only for the stated purposes
- [ ] Respect customer consent decisions
- [ ] Respect opt-outs of data sale or sharing
- [ ] Let customers opt out of automated decisions with legal or significant effects
- [ ] Have privacy and data protection agreements with merchants
- [ ] Apply retention periods, and delete when they end
- [ ] Encrypt at rest and in transit

**Level 2** (name, email, phone, address), in addition:
- [ ] Encrypt backups
- [ ] Keep test and production data separate
- [ ] Have a data-loss-prevention strategy
- [ ] Limit staff access to the data
- [ ] Require strong staff passwords
- [ ] Keep an access log of who reads the data
- [ ] Have a security incident response policy

Shopify may run a **data protection review**, focused on apps with many
installs, many customer records, many approved fields, or **long
retention**. That profile fits a backup app. Have the retention, encryption
and access-log answers written down.

## Incidents

Email security@shopify.com. The Dev Dashboard keeps 30 days of API logs
(shop, IP, user agent) for the investigation; review them on a schedule
anyway, looking for addresses you don't expect.
