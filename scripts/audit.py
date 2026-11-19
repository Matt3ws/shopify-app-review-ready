#!/usr/bin/env python3
"""Static pre-review audit for a Shopify app repo.

Greps for the concrete patterns behind rejections and near-misses recorded in
references/rejections.md. Every finding is a lead: open the file and confirm
before reporting it. It cannot see the Partner Dashboard, the production env,
or runtime behaviour.

Usage: python3 scripts/audit.py <app-dir>
Exit code: 1 if any FAIL finding, else 0.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {"node_modules", ".next", ".git", "dist", "build", "coverage", ".turbo", "vendor", "types", "generated", "__tests__", "tests", ".claude"}
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


@dataclass
class Finding:
    level: str  # FAIL, WARN, CHECK (needs a human), INFO
    check: str
    detail: str
    where: str = ""


findings: list[Finding] = []


def add(level: str, check: str, detail: str, where: str = "") -> None:
    findings.append(Finding(level, check, detail, where))


def code_files(root: Path) -> list[Path]:
    out = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS or part.startswith("__tests__") for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix in CODE_EXT:
            out.append(path)
    return out


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def grep(files: list[Path], pattern: str, root: Path, flags: int = 0) -> list[str]:
    rx = re.compile(pattern, flags)
    hits = []
    for f in files:
        for n, line in enumerate(read(f).splitlines(), 1):
            if rx.search(line):
                hits.append(f"{f.relative_to(root)}:{n}")
    return hits


def short(hits: list[str], limit: int = 5) -> str:
    more = f" (+{len(hits) - limit} more)" if len(hits) > limit else ""
    return ", ".join(hits[:limit]) + more


def check_tomls(root: Path) -> None:
    prod = root / "shopify.app.toml"
    if not prod.exists():
        add("INFO", "toml", "No shopify.app.toml at the root; skipped config checks.")
        return
    text = read(prod)

    if "default-app-home" in text:
        add("FAIL", "toml placeholder", "Production toml still points at shopify.dev/apps/default-app-home.", "shopify.app.toml")
    if re.search(r"use_legacy_install_flow\s*=\s*true", text):
        add("WARN", "legacy install", "use_legacy_install_flow = true; reviewers expect Shopify-managed install.", "shopify.app.toml")
    if "app_subscriptions/update" not in text:
        add("INFO", "app_subscriptions/update", "No app_subscriptions/update subscription. Only App Pricing apps enrolled before April 2026 (or Billing API apps) receive it; newer App Pricing apps must poll the Partner API instead.", "shopify.app.toml")
    for topic in ("customers/data_request", "customers/redact", "shop/redact"):
        if topic not in text:
            add("FAIL", "compliance webhooks", f"Compliance topic {topic} not subscribed in the production toml.", "shopify.app.toml")
    gated = re.findall(r'"((?:orders|customers)/[a-z_]+)"', text.split("compliance_topics")[0] if "compliance_topics" in text else text)
    gated = [t for t in gated if t not in ("customers/data_request", "customers/redact")]
    if gated:
        add("INFO", "protected customer data", f"Webhook topics {sorted(set(gated))} need PCD approval for THIS app, or deploy refuses the whole app.", "shopify.app.toml")
    scopes = re.search(r'scopes\s*=\s*"([^"]*)"', text)
    if scopes:
        scope_list = [s.strip() for s in scopes.group(1).split(",") if s.strip()]
        if "read_themes" in scope_list or "write_themes" in scope_list:
            add("INFO", "1.1.3 themes", "Theme scope requested. Fine for theme app extensions, but apps may not let merchants download themes (1.1.3).", "shopify.app.toml")
        if "read_all_orders" in scope_list:
            add("INFO", "read_all_orders", "read_all_orders needs its own approval in the Partner Dashboard; explain it in the testing notes.", "shopify.app.toml")
        pii = {"read_customers", "write_customers", "read_orders", "write_orders", "read_draft_orders", "write_draft_orders"} & set(scope_list)
        if pii:
            add("INFO", "protected customer data", f"Scopes {sorted(pii)}: check PCD approval (and Level 2 fields) for the PRODUCTION app.", "shopify.app.toml")
    app_url = re.search(r'application_url\s*=\s*"([^"]+)"', text)
    app_host = re.sub(r"^https?://([^/]+).*$", r"\1", app_url.group(1)) if app_url else None
    for m in re.finditer(r'redirect_urls\s*=\s*\[([^\]]*)\]', text):
        for url in re.findall(r'"([^"]+)"', m.group(1)):
            host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
            if app_host and host != app_host:
                add("FAIL", "redirect_urls", f"redirect_urls host {host} differs from application_url host {app_host}; an OAuth fallback then fails the install.", "shopify.app.toml")
            path = re.sub(r"^https?://[^/]+", "", url).strip("/")
            if path and not (root / "app" / path).exists() and not (root / "app" / "(shopify)" / path).exists():
                add("INFO", "redirect_urls", f"redirect_urls has {url}, but app/{path} doesn't exist (harmless with managed install; template leftover).", "shopify.app.toml")
    for stray in root.glob("shopify.app*.toml"):
        if stray.name == "shopify.app.toml":
            continue
        stext = read(stray)
        if "default-app-home" in stext and "dev" not in stray.name:
            add("INFO", "stray toml", f"{stray.name} looks like a template leftover; delete it if unused.", stray.name)


def check_next(root: Path, files: list[Path]) -> None:
    app = root / "app"
    if not app.is_dir():
        return
    if not any((app / f"not-found{ext}").exists() for ext in (".tsx", ".ts", ".jsx", ".js")):
        add("FAIL", "root not-found", "No app/not-found.tsx. Next 16 uses only the root one for unmatched URLs, so they show a bare 404 (2.1.1).", "app/")
    if not any((app / f"global-error{ext}").exists() for ext in (".tsx", ".jsx", ".js")):
        add("INFO", "global-error", "No app/global-error.tsx; an error in the root layout shows Next's default page.", "app/")


def check_proxy(root: Path) -> None:
    for name in ("proxy.ts", "middleware.ts", "proxy.js", "middleware.js"):
        p = root / name
        if not p.exists():
            continue
        text = read(p)
        # Comments explain past fallbacks; only code lines count for the CSP checks.
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("//", "*", "/*")))
        if "status: 404" not in text and "404" not in text:
            continue
        handles_shop_param = bool(re.search(r"hasShopParam|shop\s*!==\s*null|params\.shop|searchParams\.get\(['\"]shop['\"]\)[^\n]*(\|\||&&)", text))
        handles_admin_referer = "admin.shopify.com" in text and re.search(r"referer|Referer", text) and re.search(r"hostname", text)
        if not handles_shop_param or not handles_admin_referer:
            add("FAIL", "iframe gate", f"{name} 404s non-iframe requests but doesn't clearly let through a top-level request with a valid ?shop= and/or an admin.shopify.com referer. That is the plan-approval return; Super Siblings was rejected for it.", name)
        if re.search(r"frame-ancestors[^;\n]*\*\.myshopify\.com", code) or re.search(r"['\"`]https://\*\.myshopify\.com", code):
            add("WARN", "CSP", f"{name} uses a *.myshopify.com frame-ancestors fallback; allow admin.shopify.com only when the shop is unknown.", name)
        if "frame-ancestors" in code and not re.search(r"myshopify\\\.com\$", code):
            add("WARN", "CSP", f"{name} builds frame-ancestors without a visible myshopify-domain regex check on ?shop=.", name)


def check_code(root: Path, files: list[Path]) -> None:
    uses_partner = bool(grep(files, r"partners\.shopify\.com|activeSubscription\(", root))
    uses_admin_subs = bool(grep(files, r"activeSubscriptions", root))
    if uses_admin_subs and not uses_partner and grep(files, r"planHandle|plan_handle", root):
        add("WARN", "billing source", "Plan read from currentAppInstallation.activeSubscriptions. With Shopify App Pricing (enrolled after April 2026) status comes only from the Partner API activeSubscription; the Admin API shows nothing. Fine only for pre-April App Pricing or Billing API apps.")
    # A short cache of a confirmed plan is Shopify's own advice; hours are not.
    hits = grep([f for f in files if re.search(r"billing|subscription|plan-sync|plan-state", str(f), re.I)], r"(PLAN|plan|Plan)\w*(TTL|Ttl|_MS)\w*\s*=\s*[^;]*(3_?600_?000|60\s*\*\s*60\s*\*|86_?400|\bhour)", root)
    if hits:
        add("WARN", "plan cache", f"Plan read cached for hours ({short(hits)}); cache only a confirmed plan, for minutes, and never \"no plan\" (1.2.2).")

    hits = grep(files, r"/admin/api/[0-9-]+/[a-z_/]+\.json|clients\.Rest|new\s+Rest\(", root)
    if hits:
        add("FAIL", "REST Admin API", f"REST Admin API use ({short(hits)}); public apps must use GraphQL.")

    for f in files:
        text = read(f)
        if re.search(r"^\s*['\"]use server['\"]", text, re.M) and re.search(r"export\s+(const|async function|function)\s+\w+\s*=?\s*(async\s*)?\(\s*\{[^}]*\bshop\b", text):
            add("WARN", "security check", "A 'use server' module exports a function taking `shop`; Shopify flags this as REQUEST_DERIVED_SHOP_SCOPE.", str(f.relative_to(root)))

    hits = grep(files, r"(logger|console)\.\w+\([^)]*(sessionToken|idToken|accessToken|refreshToken)", root)
    if hits:
        add("WARN", "token logging", f"Possible token logging ({short(hits)}).")

    tsx = [f for f in files if f.suffix in (".tsx", ".jsx")]
    link_hits = []
    rx = re.compile(r"""href=\{?["'`](mailto:|tel:|https?://)""")
    for f in tsx:
        lines = read(f).splitlines()
        for n, line in enumerate(lines, 1):
            if rx.search(line):
                before = " ".join(lines[max(0, n - 4) : n])
                # <link>/<script> in <head> are not navigations.
                if re.search(r"<(link|script)\b", line) or (re.search(r"<(link|script)\b", before) and "<a" not in before + line):
                    continue
                window = " ".join(lines[max(0, n - 3) : n + 3])
                if "target" not in window:
                    link_hits.append(f"{f.relative_to(root)}:{n}")
    if link_hits:
        add("WARN", "external links", f"External/mailto links without target ({short(link_hits)}); inside the Admin they get blocked. Use target=\"_blank\" (or _top for Shopify flows).")

    hits = grep(files, r"apps\.shopify\.com/[^\"' ]*review", root)
    if hits:
        add("WARN", "1.3 reviews", f"Links to App Store reviews ({short(hits)}); ask only via shopify.reviews.request().")

    hits = grep(files, r"window\.open\(", root)
    if hits:
        add("INFO", "popups", f"window.open calls ({short(hits)}); after an await they can be popup-blocked in Safari/Firefox.")

    hits = grep(files, r"maxRetriesPerRequest:\s*null", root)
    if hits:
        add("INFO", "hanging requests", f"Redis maxRetriesPerRequest: null ({short(hits)}); make sure the web process fails fast when Redis is down instead of hanging a request.")

    debug_pages = [p for p in (root / "app").rglob("page.tsx")] if (root / "app").is_dir() else []
    dev_named = [str(p.relative_to(root)) for p in debug_pages if re.search(r"/(debug|test|playground|dev)/", "/" + str(p.relative_to(root)) )]
    if dev_named:
        add("WARN", "naming", f"Developer-sounding pages: {short(dev_named)}.")


def check_customer_data(root: Path, files: list[Path]) -> None:
    toml = read(root / "shopify.app.toml")
    scopes = re.search(r'scopes\s*=\s*"([^"]*)"', toml)
    scope_list = {s.strip() for s in scopes.group(1).split(",")} if scopes else set()
    if scope_list & {"read_orders", "read_customers", "read_draft_orders", "write_orders", "write_customers"}:
        if not grep(files, r"ACCESS_DENIED|access denied|AccessDenied", root, re.I):
            add("WARN", "protected customer data", "The app reads orders/customers but nothing handles ACCESS_DENIED. Without granted PCD a reviewer's (non-dev) store is refused and the feature shows nothing; Bundle Hero failed review 3x on this.")
    # Excluding test orders from billing usage is right; only flag it elsewhere.
    hits = grep([f for f in files if "billing" not in str(f).lower()], r"test:\s*false|-test:true|NOT\s+test|\btest\s*!==?\s*true|excludeTest|isTest\s*\?", root)
    if hits:
        add("WARN", "test orders", f"Test orders look filtered out ({short(hits)}). Reviewers place test orders; exclude them only from billing usage, never from what they look at.")


def check_extensions(root: Path) -> None:
    ext_root = root / "extensions"
    if not ext_root.is_dir():
        return
    for ext in sorted(d for d in ext_root.iterdir() if d.is_dir()):
        liquid = [f for f in ext.rglob("*.liquid") if "node_modules" not in f.parts]
        if not liquid:
            continue
        total = sum(len(read(f).encode("utf-8")) for f in liquid if f.parent.name in ("blocks", "snippets"))
        if total > 102_400:
            add("FAIL", "extension Liquid size", f"{ext.name}: blocks+snippets Liquid is {total // 1024} KB; Shopify refuses deploys over 100 KB.", str(ext.relative_to(root)))
        elif total > 90_000:
            add("WARN", "extension Liquid size", f"{ext.name}: blocks+snippets Liquid is {total // 1024} KB, close to the 100 KB deploy limit.", str(ext.relative_to(root)))
        for f in liquid:
            for n, line in enumerate(read(f).splitlines(), 1):
                if re.search(r"\{\{\s*'[{}]'\s*\}\}", line):
                    add("FAIL", "Liquid brace escape", "{{ '{' }}-style escapes break `shopify app deploy`; use {% raw %} or build the string in JS.", f"{f.relative_to(root)}:{n}")


def check_secrets_and_tokens(root: Path, files: list[Path]) -> None:
    for f in files:
        text = read(f)
        if "tokenExchange(" in text and "expiring" not in text:
            add("WARN", "expiring tokens", "tokenExchange without `expiring: true`; public apps must use expiring offline tokens.", str(f.relative_to(root)))
    api_files = [f for f in files if "/api/" in str(f) or f.name.startswith("route.")]
    leaks = []
    for f in api_files:
        lines = read(f).splitlines()
        for n, line in enumerate(lines, 1):
            if re.search(r"prisma\.store\.find(Unique|First|Many)\(", line):
                window = " ".join(lines[n - 1 : n + 4])
                if not re.search(r"\b(select|omit)\b", window):
                    leaks.append(f"{f.relative_to(root)}:{n}")
    if leaks:
        add("WARN", "credentials to browser", f"API routes read whole Store rows without select/omit ({short(leaks)}); make sure tokens never reach a response.")
    storefront = [f for f in files if re.search(r"storefront|proxy|app-proxy|apps/", str(f.relative_to(root)), re.I) and f.suffix in (".ts", ".js")]
    for f in storefront:
        text = read(f)
        if re.search(r"(req|request)\.(json|body)", text) and re.search(r"customer_?[iI]d|\bshop\b", text) and re.search(r"jwt\.sign|Access-Control-Allow-Origin['\"]?\s*[,:]\s*['\"]\*", text):
            add("FAIL", "storefront auth", "Storefront endpoint reads customer/shop from the body and signs tokens or allows any origin; take identity only from the App Proxy signature (logged_in_customer_id).", str(f.relative_to(root)))
    if grep(files, r"tokenExchange\(", root) and grep(files, r"refreshToken|refresh_token", root) and not grep(files, r"migrateToExpiringToken", root):
        add("INFO", "token migration", "No migrateToExpiringToken: installs from before expiring tokens keep a non-expiring token until they reinstall. Migrate in place on first use.")
    # Server code only: the browser declining to retry a 401/403 is correct.
    server_files = [f for f in files if not re.search(r"(^|/)(providers|components|hooks)/", str(f.relative_to(root)))]
    lumped = grep(server_files, r"(===|==)\s*401\s*\|\|[^\n]*(===|==)\s*403|(===|==)\s*403\s*\|\|[^\n]*(===|==)\s*401", root)
    if lumped:
        add("WARN", "401 vs 403", f"401 and 403 are treated alike ({short(lumped, 3)}). A 403 (missing scope, protected customer data) triggers a token refresh that can't help, and a retry into the same 403. Refresh on 401 only.")
    env = root / "env.ts"
    if env.exists() and grep(files, r"accessToken|refreshToken", root) and "ENCRYPTION" not in read(env):
        add("WARN", "encryption at rest", "env.ts has no ENCRYPTION_KEY; access tokens (and customer data) should be encrypted at rest.", "env.ts")
    trial = grep([f for f in files if f.suffix in (".tsx", ".ts")] + list((root / "translations").glob("*.json")) if (root / "translations").is_dir() else files, r"free trial|\d+-day trial|trial", root, re.I)
    if trial:
        add("INFO", "pricing copy", f"Trial mentioned in the UI ({short(trial, 3)}); check it matches the Partner Dashboard plans exactly.")


def check_platform(root: Path, files: list[Path]) -> None:
    if (root / "shopify.app.toml").exists():
        add("CHECK", "IP allowlist", "Dev Dashboard → app → Settings → IP allowlist: enforced, with IPv4 and IPv6, tested against recent traffic. Without it: no bulk operations (since 2026-11-12) and no new installs (since 2026-11-20).")
        add("CHECK", "protected customer data", "Dev Dashboard → Settings → Access requests: granted (not in review) for the PRODUCTION app, fields justified.")
        add("CHECK", "security check", "Run `shopify app security check` and the official self-review list.")
    has_bot = any((root / f).exists() for f in (".github/dependabot.yml", ".github/dependabot.yaml", "renovate.json", "renovate.json5", ".github/renovate.json", ".renovaterc"))
    if (root / "package.json").exists() and not has_bot:
        add("WARN", "dependency automation", "No Dependabot or Renovate config; Shopify's security check flags MISSING_DEPENDENCY_SECURITY_AUTOMATION.")
    pkg = read(root / "package.json")
    if re.search(r'"@shopify/app-bridge"\s*:', pkg):
        add("WARN", "2.2.3 App Bridge", "Legacy @shopify/app-bridge npm package; use the CDN script (plus @shopify/app-bridge-react if needed).", "package.json")
    if (root / "app").is_dir() or (root / "pages").is_dir():
        csp_sources = [root / n for n in ("proxy.ts", "middleware.ts", "proxy.js", "middleware.js", "next.config.js", "next.config.mjs", "next.config.ts")]
        if not any("frame-ancestors" in read(f) for f in csp_sources if f.exists()):
            add("FAIL", "frame-ancestors", "No frame-ancestors header found; Shopify rejects embedded apps without it on every HTML route (MISSING_EMBEDDED_CSP).")


def check_package(root: Path) -> None:
    pkg = root / "package.json"
    if not pkg.exists():
        return
    try:
        data = json.loads(read(pkg))
    except json.JSONDecodeError:
        return
    name = data.get("name", "")
    if re.search(r"template", name, re.I):
        add("INFO", "template debris", f"package.json name is '{name}'.", "package.json")
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if "next" in deps:
        add("INFO", "framework", f"next {deps['next']}: check it's on the latest patch (npm view next version).", "package.json")


def check_translations(root: Path) -> None:
    tdir = root / "translations"
    if not tdir.is_dir():
        return
    catalogs = {}
    for f in tdir.glob("*.json"):
        try:
            catalogs[f.name] = json.loads(read(f))
        except json.JSONDecodeError:
            add("FAIL", "translations", f"{f.name} is not valid JSON.", f"translations/{f.name}")

    def keys(obj, prefix=""):
        out = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                out |= keys(v, f"{prefix}{k}.")
        else:
            out.add(prefix.rstrip("."))
        return out

    if "en.json" in catalogs:
        base = keys(catalogs["en.json"])
        for name, cat in catalogs.items():
            if name == "en.json":
                continue
            missing = base - keys(cat)
            if missing:
                add("WARN", "translations", f"{name} is missing {len(missing)} keys from en.json (e.g. {sorted(missing)[:3]}).", f"translations/{name}")


def check_webhook_echoes(root: Path, files: list[Path]) -> None:
    subscribes = bool(grep(files, r"PRODUCTS_UPDATE|products/update", root)) or "products/update" in read(root / "shopify.app.toml")
    writes = grep(files, r"\b(productSet|productUpdate|productVariantsBulkUpdate|metafieldsSet)\b", root)
    echo_aware = grep(files, r"echo|ownWrite|own_write|isOwn", root, re.I)
    if subscribes and writes and not echo_aware:
        add("WARN", "webhook echoes", f"Subscribes to products/update and writes products ({short(writes, 3)}). Every write fires products/update; drop your own echoes or the app floods itself (Super Siblings). If the handler only logs a change, confirm a restore's burst is cheap.")


def check_compliance_handlers(root: Path, files: list[Path]) -> None:
    for f in files:
        if re.search(r"data.?request", f.name, re.I) and f.suffix in (".ts", ".js"):
            text = read(f)
            code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("//", "*", "/*")))
            produces = re.search(r"createExport|exportRequest|\.export\(|download|ComplianceDataRequest|dataRequest\w*\.(create|upsert)|sendMail|sendEmail|notify", code, re.I)
            if not produces:
                add("WARN", "customers/data_request", "The data-request handler doesn't appear to produce anything for the merchant (no export, record or notification). Logging isn't fulfilment.", str(f.relative_to(root)))
    for topic, needle in (("customers/data_request", "data.?request"), ("customers/redact", "customers.?redact"), ("shop/redact", "shop.?redact")):
        if not grep([f for f in files if re.search(needle, str(f), re.I)], r".", root):
            add("WARN", "compliance handlers", f"No handler file matching {topic}; check it is implemented and actually fulfils the obligation.")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}")
        return 2
    files = code_files(root)

    check_tomls(root)
    check_next(root, files)
    check_proxy(root)
    check_code(root, files)
    check_customer_data(root, files)
    check_extensions(root)
    check_secrets_and_tokens(root, files)
    check_platform(root, files)
    check_package(root)
    check_translations(root)
    check_compliance_handlers(root, files)
    check_webhook_echoes(root, files)

    order = {"FAIL": 0, "CHECK": 1, "WARN": 2, "INFO": 3}
    findings.sort(key=lambda f: order[f.level])
    print(f"Shopify review audit: {root.name} ({len(files)} code files)\n")
    if not findings:
        print("No findings. Still walk references/checklist.md and run the reviewer flows.")
    for f in findings:
        where = f" [{f.where}]" if f.where else ""
        print(f"{f.level:5}  {f.check}: {f.detail}{where}")
    counts = {lvl: sum(1 for f in findings if f.level == lvl) for lvl in order}
    print(f"\n{counts['FAIL']} fail, {counts['WARN']} warn, {counts['CHECK']} to check by hand, {counts['INFO']} info. Confirm each in the code before reporting it.")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
