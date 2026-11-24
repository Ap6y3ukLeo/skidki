"""Дикси по всем магазинам Москвы и области: одна браузерная сессия, докачка, JSONL.

Запуск: .venv\\Scripts\\python.exe dixy_bulk.py [--limit N]
Прогресс: data/bulk/dixy-moskva.jsonl и .done — повторный запуск продолжает с места.
"""
import argparse
import json
import time
from pathlib import Path

from scrapling.fetchers import StealthySession

import dixy
import stores

OUT = Path("data/bulk")
MSK_BOX = (55.2, 36.3, 56.3, 38.6)  # Москва и область: lat_min, lon_min, lat_max, lon_max


def moscow_stores() -> list[dict]:
    lat_min, lon_min, lat_max, lon_max = MSK_BOX
    return [s for s in stores.dixy_stores()
            if lat_min <= s["lat"] <= lat_max and lon_min <= s["lon"] <= lon_max]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    jsonl = OUT / "dixy-moskva.jsonl"
    done_path = OUT / "dixy-moskva.done"
    done = set(done_path.read_text(encoding="utf-8").split()) if done_path.exists() else set()

    shops = moscow_stores()
    todo = [s for s in shops if s["key"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"Дикси: всего {len(shops)}, в очереди {len(todo)}")

    started = time.time()
    ok = 0
    with StealthySession(headless=True, timeout=90000) as session:
        with jsonl.open("a", encoding="utf-8") as out, done_path.open("a", encoding="utf-8") as mark:
            for n, shop in enumerate(todo, 1):
                try:
                    html = dixy.fetch_listing_session(session, shop)
                    deals = dixy.parse(html, shop, "Москва")
                except Exception as exc:
                    print(f"  ! {shop['key']}: {type(exc).__name__}: {exc}"[:140])
                    continue
                for d in deals:
                    out.write(json.dumps(d, ensure_ascii=False) + "\n")
                out.flush()
                mark.write(shop["key"] + "\n")
                mark.flush()
                ok += 1
                if n % 3 == 0 or n == len(todo):
                    rate = n / max(time.time() - started, 1)
                    left = (len(todo) - n) / rate if rate else 0
                    print(f"  {n}/{len(todo)} магазинов, {len(deals)} товаров, "
                          f"~{left / 60:.0f} мин осталось")
    print(f"готово: {ok} магазинов за {(time.time() - started) / 60:.1f} мин")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    main()
