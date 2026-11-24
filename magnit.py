"""Магнит: товары со скидкой для выбранного магазина.

Магазин выбирается через stores-facade/store, после этого страница каталога
отдаёт товары с ценой и старой ценой. Данные Магнита одинаковы для всех
магазинов города (проверено), поэтому каталог тянем один раз на город.
"""
import json
import re

from scrapling.fetchers import FetcherSession

import stores

BASE = "https://magnit.ru"
HEADERS = {"Referer": f"{BASE}/", "Origin": BASE, "Accept": "application/json"}


def decode_devalue(arr: list):
    """Nuxt кладёт данные плоским массивом; объекты ссылаются на элементы по индексу."""
    wrappers = {"ShallowReactive", "Reactive", "Ref", "ShallowRef", "EmptyRef", "Set", "Map"}

    def walk(i):
        if not isinstance(i, int) or isinstance(i, bool):
            return i
        if i < 0:
            return None
        v = arr[i]
        if isinstance(v, dict):
            return {k: walk(j) for k, j in v.items()}
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in wrappers and len(v) > 1:
                return walk(v[1])
            return [walk(x) for x in v]
        return v

    return walk(0)


def to_float(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except ValueError:
        return None


def walk_dicts(node, predicate, found: list):
    if isinstance(node, dict):
        if predicate(node):
            found.append(node)
        else:
            for v in node.values():
                walk_dicts(v, predicate, found)
    elif isinstance(node, list):
        for v in node:
            walk_dicts(v, predicate, found)


def parse(city: str, shop: dict) -> list[dict]:
    with FetcherSession(impersonate="chrome") as s:
        s.get(f"{BASE}/", timeout=30)
        r = s.post(f"{BASE}/webgate/v1/stores-facade/store",
                   json={"externalId": {"owner": "OWNER_RTE", "storeCode": shop["code"]}},
                   timeout=30, headers=HEADERS)
        address = r.json().get("address") if r.status == 200 else shop["label"]

        p = s.get(f"{BASE}/catalog", timeout=40)
    html = p.body.decode("utf-8", "replace")
    m = re.search(r'id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError(f"нет __NUXT_DATA__ (статус {p.status})")

    tree = decode_devalue(json.loads(m.group(1)))
    found: list[dict] = []
    walk_dicts(tree, lambda n: n.get("price") not in (None, "") and "title" in n, found)

    deals, seen = [], set()
    for node in found:
        title = node.get("title")
        if not title or title in seen:
            continue
        seen.add(title)
        price = to_float(node.get("price"))
        old = to_float(node.get("oldPrice")) or None
        percent = to_float(node.get("salePercent"))
        percent = abs(int(percent)) if percent else (round((1 - price / old) * 100)
                                                     if old and price and old > price else None)
        deals.append({
            "store": "Магнит",
            "store_key": shop["key"],
            "city": city,
            "address": address,
            "title": title,
            "price": price,
            "old_price": old,
            "discount_percent": percent,
            "period": None,
            "campaign": None,
            "url": f"{BASE}{node.get('link')}" if node.get("link") else f"{BASE}/catalog",
            "image": node.get("image"),
        })
    return deals
