"""Собирает сделки в data/deals.json: Магнит напрямую + всё, что накопили bulk-прогоны.

Запуск: .venv\\Scripts\\python.exe collect.py [--min 30]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import magnit
import stores

BULK = Path("data/bulk")

PYAT_FILE = Path("data/stores-pyat.json")


def pyat_stores() -> dict[str, dict]:
    """Магазины Пятёрочки, для которых уже известны адрес и координаты."""
    if not PYAT_FILE.exists():
        return {}
    return json.loads(PYAT_FILE.read_text(encoding="utf-8"))


def load_bulk() -> list[dict]:
    """Сделки из массовых прогонов. Дубликаты схлопываем, оставляя версию со старой ценой."""
    best: dict[tuple, dict] = {}
    paths = list(BULK.glob("*.jsonl")) + list(Path("data/ingest").glob("*.jsonl"))
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            key = (d.get("store_key"), d.get("title"), d.get("price"))
            prev = best.get(key)
            if prev is None or (not prev.get("old_price") and d.get("old_price")):
                best[key] = d
    return list(best.values())


def map_stores(deals: list[dict]) -> list[dict]:
    """Все известные магазины сетей в радиусе городов — для карты, даже без данных."""
    with_data = {d.get("store_key") for d in deals}
    pool: dict[str, dict] = {}
    for loader in (stores.magnit_all_stores, stores.dixy_stores, stores.auchan_stores):
        try:
            for s in loader():
                pool[s["key"]] = s
        except Exception:
            continue

    result = []
    # сети вне справочников (Пятёрочка) — берём адреса и координаты из data/stores-pyat.json
    pyat = pyat_stores()
    labels = {d.get("store_key"): d.get("address") for d in deals}
    for key, info in pyat.items():
        if key in with_data and key not in pool:
            pool[key] = {"key": key, "chain": "Пятёрочка", "label": info.get("label") or labels.get(key),
                         "lat": info.get("lat"), "lon": info.get("lon")}

    for s in pool.values():
        city = None
        for name, (lat, lon) in stores.CITIES.items():
            if stores.haversine(lat, lon, s["lat"], s["lon"]) <= 50:
                city = name
                break
        if not city:
            continue
        result.append({"key": s["key"], "chain": s["chain"], "label": s["label"], "city": city,
                       "lat": s["lat"], "lon": s["lon"], "has_data": s["key"] in with_data})
    return result


def main():
    args = sys.argv[1:]
    min_discount = int(args[args.index("--min") + 1]) if "--min" in args else 30

    deals, errors = [], []
    # Магнит: данные одинаковы для всех магазинов города, берём один на город
    for city, center in stores.CITIES.items():
        try:
            shops = stores.magnit_stores(*center)
            if not shops:
                continue
            deals.extend(magnit.parse(city, shops[0]))
        except Exception as exc:
            errors.append(f"{city} / Магнит: {type(exc).__name__}: {exc}"[:200])

    deals.extend(load_bulk())

    shown = [d for d in deals if (d.get("discount_percent") or 0) >= min_discount]
    shown.sort(key=lambda d: d.get("discount_percent") or 0, reverse=True)
    card_only = [d for d in deals if d.get("no_discount_data")]

    cities = []
    for name, (lat, lon) in stores.CITIES.items():
        cities.append({"name": name, "slug": stores.SLUGS.get(name, name.lower()),
                       "lat": lat, "lon": lon,
                       "count": sum(1 for d in shown if d["city"] == name)})

    used, seen = [], set()
    try:
        index = {s["key"]: s for s in stores.magnit_all_stores()}
    except Exception as exc:
        errors.append(f"Магнит: список магазинов недоступен: {exc}"[:160])
        index = {}
    try:
        index.update({s["key"]: s for s in stores.dixy_stores()})
    except Exception as exc:
        # Дикси периодически режет список магазинов — берём координаты из прошлой сборки
        errors.append(f"Дикси: список магазинов недоступен: {exc}"[:160])
        old = Path("data/deals.json")
        if old.exists():
            for s in json.loads(old.read_text(encoding="utf-8")).get("stores", []):
                index.setdefault(s["key"], s)
    for d in shown + card_only:
        key = d.get("store_key")
        if key and key not in seen:
            seen.add(key)
            shop = index.get(key) or {}
            lat, lon = shop.get("lat"), shop.get("lon")
            if (lat is None or lon is None) and key in pyat_stores():
                info = pyat_stores()[key]
                lat, lon = info.get("lat"), info.get("lon")
            used.append({"key": key, "chain": d["store"], "label": d.get("address") or shop.get("label"),
                         "city": d["city"], "lat": lat, "lon": lon})

    payload = {
        "min_discount": min_discount,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "errors": errors,
        "found": len(deals),
        "cities": cities,
        "stores": used,
        "map_stores": map_stores(deals),
        "deals": shown,
        "card_deals": card_only,
    }
    Path("data/deals.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # копия для клиентского приложения
    public = Path("public/data")
    public.mkdir(parents=True, exist_ok=True)
    (public / "deals.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"найдено {len(deals)}, от {min_discount}% — {len(shown)}, магазинов {len(used)}, ошибок {len(errors)}")
    for err in errors:
        print("  !", err)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
