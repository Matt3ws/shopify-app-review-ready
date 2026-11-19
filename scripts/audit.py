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
    level: str  # FAIL, WARN, INFO
    check: str
    detail: str
    where: str = ""


findings: list[Finding] = []


def add(level: str, check: str, detail: str, where: str = "") -> None:
    findings.append(Finding(level, check, detail, where))


def code_files(root: Path) -> list[Path]:
    out = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
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
        add("WARN", "app_subscriptions/update", "Production toml doesn't subscribe to app_subscriptions/update; plan changes made while the app is closed go unseen (every approved Edition app has it). Editing the prod toml needs explicit confirmation.", "shopify.app.toml")
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
    for m in re.finditer(r'redirect_urls\s*=\s*\[([^\]]*)\]', text):
        for url in re.findall(r'"([^"]+)"', m.group(1)):
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
    hits = grep(files, r"partners\.shopify\.com", root)
    if hits:
        add("WARN", "billing source", f"Partner API use ({short(hits)}). Read the plan from currentAppInstallation.activeSubscriptions instead (1.2.2).")
    if not grep(files, r"currentAppInstallation", root) and grep(files, r"planHandle|plan_handle|appSubscription", root):
        add("WARN", "billing source", "Billing code found but no currentAppInstallation query; check how the plan is read.")
    hits = grep(files, r"PLAN_SYNC_TTL|PLAN_.*TTL|planSyncedAt\s*[^=]*<\s*\w*TTL", root)
    if hits:
        add("WARN", "plan cache", f"Plan read appears to sit behind a TTL ({short(hits)}); a reinstall then shows stale state (1.2.2).")

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


def check_compliance_handlers(root: Path, files: list[Path]) -> None:
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
    check_package(root)
    check_translations(root)
    check_compliance_handlers(root, files)

    order = {"FAIL": 0, "WARN": 1, "INFO": 2}
    findings.sort(key=lambda f: order[f.level])
    print(f"Shopify review audit: {root.name} ({len(files)} code files)\n")
    if not findings:
        print("No findings. Still walk references/checklist.md and run the reviewer flows.")
    for f in findings:
        where = f" [{f.where}]" if f.where else ""
        print(f"{f.level:4}  {f.check}: {f.detail}{where}")
    counts = {lvl: sum(1 for f in findings if f.level == lvl) for lvl in order}
    print(f"\n{counts['FAIL']} fail, {counts['WARN']} warn, {counts['INFO']} info. Confirm each in the code before reporting it.")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
