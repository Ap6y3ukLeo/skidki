"""Ищет на сайтах сетей страницы акций и проверяет, лежат ли данные в HTML.

Запуск: .venv\\Scripts\\python.exe probe.py [site ...]
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from scrapling.fetchers import Fetcher

SITES = {
    "magnit": "https://magnit.ru",
    "5ka": "https://5ka.ru",
    "lenta": "https://lenta.com",
    "dixy": "https://dixy.ru",
    "globus": "https://www.globus.ru",
    "auchan": "https://www.auchan.ru",
}
# слова, по которым узнаём ссылку на акции в меню сайта
KEYS = re.compile(r"(promo|promotion|akci|akcii|skidk|special|offer|discount|vygod)", re.I)
JSON_MARKERS = ("__NEXT_DATA__", "__NUXT__", "application/ld+json", "application/json")


def get(url: str):
    return Fetcher.get(url, impersonate="chrome", timeout=30)


def find_promo_links(root_html: str, base: str) -> list[str]:
    links = re.findall(r'href="([^"#]+)"', root_html)
    seen, out = set(), []
    for href in links:
        if KEYS.search(href):
            url = urljoin(base, href)
            if url not in seen:
                seen.add(url)
                out.append(url)
    return out[:8]


def looks_like_data(html: str) -> dict:
    prices = len(re.findall(r"\d+[.,]\d{2}\s*(?:₽|руб)", html))
    return {
        "len": len(html),
        "prices": prices,
        "markers": [m for m in JSON_MARKERS if m in html],
    }


def probe(name: str, base: str) -> dict:
    try:
        root = get(base)
    except Exception as exc:
        return {"site": name, "error": f"{type(exc).__name__}: {exc}"[:160]}
    html = root.body.decode(root.encoding or "utf-8", "replace")
    links = find_promo_links(html, base)
    return {"site": name, "root_status": root.status, "promo_links": links[:5]}


def probe_page(url: str) -> dict:
    try:
        r = get(url)
    except Exception as exc:
        return {"url": url, "error": f"{type(exc).__name__}: {exc}"[:160]}
    html = r.body.decode(r.encoding or "utf-8", "replace")
    Path("out").mkdir(exist_ok=True)
    Path(f"out/{re.sub(r'[^a-z0-9]+', '-', url.lower())[:60]}.html").write_text(html, encoding="utf-8")
    return {"url": url, "status": r.status, **looks_like_data(html)}


if __name__ == "__main__":
    names = sys.argv[1:] or list(SITES)
    sites = [probe(n, SITES[n]) for n in names]
    print(json.dumps(sites, ensure_ascii=False, indent=2))
    for site in sites:
        for url in site.get("promo_links", [])[:2]:
            print(json.dumps(probe_page(url), ensure_ascii=False))
