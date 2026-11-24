"""Полный обход одного магазина Дикси: раздел акций + все категории каталога.

Запуск: .venv\\Scripts\\python.exe dixy_full.py dixy:2227
Результат: data/bulk/dixy-full-<код>.jsonl (подхватывается collect.py)
"""
import json
import re
import sys
from pathlib import Path

from scrapling.fetchers import StealthySession

import dixy
import stores

OUT = Path("data/bulk")
START = "/catalog/skidki-po-karte/"


def categories(html: str) -> list[str]:
    found = sorted(set(re.findall(r'href="(/catalog/[a-z0-9-]+/)"', html)))
    return [p for p in found if p != START]


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else "dixy:2227"
    shop = next(s for s in stores.dixy_stores() if s["key"] == key)

    all_deals: dict[str, dict] = {}
    with StealthySession(headless=True, timeout=90000) as session:
        html = dixy.fetch_listing_session(session, shop, START)
        for d in dixy.parse(html, shop, "Королёв"):
            all_deals[d["url"]] = d
        paths = categories(html)
        print(f"акций: {len(all_deals)}, категорий: {len(paths)}")

        for n, path in enumerate(paths, 1):
            try:
                page = dixy.fetch_listing_session(session, shop, path)
                fresh = 0
                for d in dixy.parse(page, shop, "Королёв"):
                    if d["url"] not in all_deals:
                        all_deals[d["url"]] = d
                        fresh += 1
                print(f"  {n}/{len(paths)} {path[:45]:<45} +{fresh}, всего {len(all_deals)}")
            except Exception as exc:
                print(f"  {n}/{len(paths)} {path[:45]:<45} ошибка: {type(exc).__name__}")

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"dixy-full-{key.replace(':', '-')}.jsonl"
    with target.open("w", encoding="utf-8") as f:
        for d in all_deals.values():
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    with_discount = [d for d in all_deals.values() if d["discount_percent"]]
    print(f"итог: {len(all_deals)} товаров, со старой ценой {len(with_discount)} → {target}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
