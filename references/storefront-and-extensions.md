# Storefront surfaces: theme app extensions, App Proxy, Functions

Anything that runs on the merchant's storefront or in checkout has its own
deploy-time limits (Shopify refuses the deploy, so CI never sees them) and
its own security model (the visitor is anonymous unless Shopify says
otherwise). These lessons come from our apps' extensions.

## Theme app extensions

- **100 KB Liquid cap per extension.** Shopify: "Extension Liquid content
  size exceeds 100 KB limit". The cap is the total of every `blocks/` and
  `snippets/` file, including comments and `{% schema %}`.
  `shopify theme check` doesn't flag it. Move inline `<script>` into
  `assets/*.js` and documentation out of Liquid comments.
  Check: `find extensions/<ext> -name '*.liquid' -exec cat {} + | wc -c`
  stays under 102400.
- **No `{{ '{' }}` / `{{ '}' }}` brace escapes.** The deploy tokenizer cuts the
  tag at the wrong `}}`, even inside quotes or `{% comment %}`, and
  `shopify app deploy` fails. Use `{% raw %}` or build the string in JS.
  Check: `grep -rn "{{ *'[{}]' *}}" extensions/`.
- **App snippets are wrapped in HTML comments** when Shopify renders them,
  even inside JSON. Never render an app snippet inside an opening tag's
  attributes or into a JSON blob; render a hidden element and read it from JS.
- **A block's filename is its handle.** Placed blocks are referenced as
  `shopify://apps/<app>/blocks/<file>/<uid>`. Renaming the file removes the
  block and its settings from every live theme. Treat a rename as a breaking
  change, or keep the old file as a thin wrapper.
  Check: `git log --diff-filter=R -- 'extensions/*/blocks/*.liquid'`.
- Reach the storefront only through theme app extensions (blocks, app
  embeds). No `ScriptTag`, no writing theme files, no asking merchants to
  paste code. If you need `read_themes` (e.g. to detect that a block was
  added), read only the files you need and be ready to explain the scope to a
  reviewer: write down exactly what is read and why.
- Uninstalling must leave the theme clean. Theme app extensions do that by
  design; anything else doesn't.

## App Proxy and storefront APIs

The visitor is anonymous. A storefront request can only be trusted for what
Shopify signs.

- **Never take the customer or shop from the request body.** One of our
  apps signed a JWT for any `customerId` and `shop` posted to a CORS-`*`
  endpoint, so anyone could read and change any customer's subscriptions.
  Put storefront endpoints behind the App Proxy, verify its signature, and
  take the customer from `logged_in_customer_id` and the shop from the
  signed `shop`. Anonymous requests get 401.
- **A valid signature doesn't authorize the query params.** Shopify signs
  every query param on the URL, including ones the visitor added
  (`?kk_customer=999`). Any param that picks *whose* data to show (customer,
  company, location) must be checked against `logged_in_customer_id` on every
  request, falling back to the caller's own data.
- Check ownership on every write, not just on read.
- No tokens in logs and no `Access-Control-Allow-Origin: *` on endpoints that
  touch customer data.
- Detect: in storefront routes, `customerId`/`shop` read from
  `req.json()`/`req.body`; `jwt.sign`; CORS `*`; `searchParams.get(...)` for an
  id that selects another customer's data.

## Shopify Functions

- Compiled Wasm must be at most **256 KB**. Derive-heavy Rust (e.g. serde's
  internally tagged enums) can add tens of KB; hand-written deserializers
  cut one of ours from 278 KB to 171 KB.
- Each Function's input query has a **complexity cap of 30** (about 1 point
  per leaf field, alias, inline fragment or argument field). Count before
  adding a field; the cap is per extension, so split Functions rather than
  trading fields.
- Both are deploy-time failures: validate with `shopify app dev` or deploy
  after touching the input query or dependencies.
- Function input queries that read customer or order data need protected
  customer data approval too.

## Checkout UI extensions

- `network_access = true` needs approval and an explanation; remove it if
  unused.
- Keep extension bundles small; checkout extensions have their own size limit
  at deploy.
