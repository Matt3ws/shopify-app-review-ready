# The flows a reviewer runs

Run these on the **production** app, in a browser with third-party cookies
blocked (incognito). Watch the network tab for 4xx/5xx and the console for
errors throughout. Record a screencast; it goes with the submission.

Use two stores:

- **A fresh development store**, for the plan flows: test charges are free.
- **A non-development store**, such as a trial store, for everything that
  reads orders or customers. Development stores are **exempt** from the
  protected customer data gate, so a feature can pass every dev-store test
  and show zeros on the reviewer's store. That cost Bundle Hero three review
  rounds.

Place orders the way a reviewer does: test orders with the Bogus Gateway.
Anything that filters out test orders will look empty to them.

The reviewer's dev store belongs to **another** Partner organization. On
such a store, only free plans and paid plans marked "free for partners and
developers" can be selected at no charge, so check that setting, and test from
a store your organization doesn't own if you can. Use the listing's language
on the store: the plan page can 404 for a draft app when the locales differ.

## 1. Install and first minute
1. Install from the production app's install link.
2. Expect: lands in the app UI, no login, no 404, under a few seconds.
3. Expect: the first screen says what the app does and what to do next. With
   no plan and no free plan: a clear pointer to the plans.
4. Click every sidebar entry; each loads without errors.
5. Type a nonsense path after the app URL: the app's own not-found page, not
   a bare 404.

## 2. Plans
1. Open plans and choose a paid plan; approve the test charge.
2. Expect: back in the app (no 404, even if Shopify returns as a top-level
   page), showing the chosen plan, with a test-charge indication.
3. Upgrade, then downgrade. Expect the plan shown to follow each time.
4. Start a plan change and decline. Expect the app unchanged and usable.

## 3. Reinstall during a paid cycle (1.2.2)
1. With a paid plan active, uninstall the app.
2. Reinstall immediately (within a minute), and again after a few minutes.
3. Expect: the app shows the paid plan still active (or asks to approve
   again only if Shopify itself reports no subscription). Never "Free" over a
   live plan. Previous data is still there if the app keeps data until
   `shop/redact`.
4. Use a core feature right after reinstalling: it must work on the first
   open (no dead-token errors).

## 4. Core features, exactly as the listing says
For each feature and each option the UI offers:
1. Set it up the way a merchant would from the listing's description.
2. Run it and verify the result in the Shopify admin, not only in the app.
3. For anything that copies or restores data: change or delete the data,
   restore, and compare **every** advertised field (for products: title,
   description, variants, prices, images, variant images, custom fields).
4. Note how long background work takes; put it in the testing notes.

## 5. Failure paths
- A feature that needs data the store doesn't have shows guidance, not an
  error.
- A permission the app doesn't have (protected customer data, an optional
  scope) shows an explanation the merchant understands.
- Download and export links open (not popup-blocked) and work.
- Leave the app open past the session lifetime and keep using it: no auth
  errors.

## 6. Webhooks (automated checks run these)
```bash
shopify app webhook trigger --topic customers/data_request --address <prod-url>/api/webhooks/...
shopify app webhook trigger --topic customers/redact --address ...
shopify app webhook trigger --topic shop/redact --address ...
```
Expect 200 for valid deliveries. A request with a wrong HMAC must get 401
(`curl -X POST -H 'X-Shopify-Hmac-Sha256: bad' <url>`). `webhook trigger`
only sends a sample; confirm the subscriptions themselves in the production
toml / Dev Dashboard.

## 7. Shopify's own checks
- `shopify app security check`, and fix everything it reports.
- The self-review list (`shopify doc fetch --url https://shopify.dev/docs/apps/launch/app-store-review/app-store-ai-self-review-requirements`).
- IP allowlist enforced for the production app (Dev Dashboard), tested
  against recent traffic.
- An outside port scan shows only 80/443 (and SSH if you must).

## 8. Production health during review
- Workers running, queue not backed up, monitoring green.
- Production env has every variable the billing and plan links need.
- Nothing deployed mid-review that changes the flows above.
