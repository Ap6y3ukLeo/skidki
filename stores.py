"""Города и магазины сетей: списки точек и поиск ближайшей."""
import json
import re
from math import hypot
from pathlib import Path

from scrapling.fetchers import Fetcher

CITIES = {
    "Москва": (55.7558, 37.6173),
    "Королёв": (55.9142, 37.8255),
}

SLUGS = {"Москва": "moskva", "Королёв": "korolev"}

# точки опроса: у Купера магазин привязан к точке, поэтому обходим город сеткой
CITY_POINTS = {
    "Москва": [
        (55.7558, 37.6173),  # центр
        (55.6895, 37.5560),  # юго-запад
        (55.8100, 37.6400),  # север
        (55.7320, 37.7800),  # восток
        (55.8000, 37.4000),  # северо-запад
        (55.6500, 37.7400),  # юго-восток
    ],
    "Королёв": [
        (55.9142, 37.8255),
        (55.9300, 37.8600),
        (55.8900, 37.7900),
    ],
}

MAGNIT_SEARCH = "https://magnit.ru/webgate/v1/stores-facade/search"
MAGNIT_DETAIL = "https://magnit.ru/webgate/v1/stores-facade/search/detail"
MAGNIT_CITY_FIAS = "0c5b2444-70a0-4932-980c-b4dc0d3f02b5"  # Москва
DIXY_STORES = "https://dixy.ru/ajax/stores-json.php"
GLOBUS_PAGE = "https://www.globus.ru/catalog/akcii-20"  # список магазинов лежит в кэше страницы

MAGNIT_CACHE = Path("data/stores-magnit.json")


def bbox(lat: float, lon: float, deg: float = 0.09) -> tuple[dict, dict]:
    """Квадрат вокруг точки: магазины ищем только в своём городе, а не по всей стране."""
    return (
        {"latitude": lat + deg, "longitude": lon - deg},
        {"latitude": lat - deg, "longitude": lon + deg},
    )


def nearest(items: list[dict], lat: float, lon: float) -> dict | None:
    return min(items, key=lambda s: hypot(s["lat"] - lat, s["lon"] - lon)) if items else None


def magnit_stores(lat: float, lon: float, radius_km: float = 25) -> list[dict]:
    """Все магазины Магнита вокруг точки: адреса берём из search/detail по FIAS города."""
    shops = magnit_all_stores()
    near = [s for s in shops if haversine(lat, lon, s["lat"], s["lon"]) <= radius_km]
    near.sort(key=lambda s: haversine(lat, lon, s["lat"], s["lon"]))
    return near


def magnit_all_stores() -> list[dict]:
    if MAGNIT_CACHE.exists():
        return json.loads(MAGNIT_CACHE.read_text(encoding="utf-8"))

    result, page = [], 1
    while True:
        body = {"filters": {"cityFIASID": MAGNIT_CITY_FIAS},
                "pagination": {"size": 100, "page": page}}
        r = Fetcher.post(MAGNIT_DETAIL, json=body, impersonate="chrome", timeout=40,
                         headers={"Referer": "https://magnit.ru/", "Origin": "https://magnit.ru",
                                  "Accept": "application/json"})
        if r.status != 200:
            break
        data = json.loads(r.body.decode("utf-8"))
        items = data.get("data") or []
        if not items:
            break
        for it in items:
            result.append({
                "key": f"magnit:{it['externalId']['storeCode']}",
                "chain": "Магнит",
                "code": it["externalId"]["storeCode"],
                "lat": it["coordinates"]["latitude"],
                "lon": it["coordinates"]["longitude"],
                "label": it.get("address") or "Магнит",
            })
        if len(result) >= (data.get("totalCount") or 0):
            break
        page += 1
        if page > 3:  # API игнорирует номер страницы и отдаёт одно и то же — дальше смысла нет
            break

    MAGNIT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MAGNIT_CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def auchan_stores() -> list[dict]:
    """Магазины Ашана: их API отдаёт список по региону без авторизации."""
    result = []
    for region in (1, 3):  # 1 — Москва и область, 3 — Санкт-Петербург
        r = Fetcher.get(f"https://www.auchan.ru/v3/shops/?regionId={region}",
                        impersonate="chrome", timeout=30,
                        headers={"Accept": "application/json", "Referer": "https://www.auchan.ru/"})
        if r.status != 200:
            continue
        for s in json.loads(r.body.decode("utf-8")).get("shops", []):
            try:
                lat, lon = float(s["geo_lat"]), float(s["geo_lon"])
            except (TypeError, ValueError):
                continue
            result.append({
                "key": f"auchan:{s['merchant_id']}",
                "chain": "Ашан",
                "id": s["merchant_id"],
                "lat": lat,
                "lon": lon,
                "label": s.get("address_string") or s.get("name") or "Ашан",
            })
    return result


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def dixy_stores() -> list[dict]:
    cache = Path("data/stores-dixy.json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    r = Fetcher.get(DIXY_STORES, impersonate="chrome", timeout=30)
    body = r.body.decode("utf-8", "replace")
    if not body.strip().startswith("["):
        # после серии запросов обычный HTTP отбивается — берём список браузером
        from scrapling.fetchers import StealthyFetcher
        page = StealthyFetcher.fetch(DIXY_STORES, headless=True, timeout=60000)
        body = page.body.decode("utf-8", "replace")
    if not body.strip().startswith("["):
        raise RuntimeError(f"Дикси не отдал список магазинов ({r.status})")
    shops = json.loads(body)
    result = [{
        "key": f"dixy:{s['properties']['id']}",
        "chain": "Дикси",
        "id": s["properties"]["id"],
        "coords": s["geometry"]["coordinates"],
        "lat": float(s["geometry"]["coordinates"][0]),
        "lon": float(s["geometry"]["coordinates"][1]),
        "label": s["properties"]["balloonContentBody"].strip(),
    } for s in shops]

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def globus_stores() -> list[dict]:
    r = Fetcher.get(GLOBUS_PAGE, impersonate="chrome", timeout=40)
    html = r.body.decode(r.encoding or "utf-8", "replace")
    tree = json.loads(re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
    queries = tree["props"]["pageProps"]["dehydratedState"]["queries"]
    stores = next(q for q in queries if q["queryKey"] == "directories-stores")["state"]["data"]["data"]["stores"]
    return [{
        "key": f"globus:{s['id']}",
        "chain": "Глобус",
        "id": s["id"],
        "lat": s["location"]["latitude"],
        "lon": s["location"]["longitude"],
        "label": f"{s['name']}, {s['full_addr']}",
    } for s in stores]


def all_stores(lat: float, lon: float) -> dict[str, list[dict]]:
    """Списки магазинов всех сетей вокруг точки, для выбора на сайте."""
    return {
        "Магнит": magnit_stores(lat, lon),
        "Глобус": globus_stores(),
        "Дикси": dixy_stores(),
    }
