"""Дикси: выбор магазина через saveStore и разбор выдачи «Скидки по карте».

Сайт пускает только после JS-челленджа, поэтому используется браузерный фетчер.
"""
import re

from scrapling.fetchers import StealthyFetcher, StealthySession

BASE = "https://dixy.ru"
LISTING = f"{BASE}/catalog/skidki-po-karte/"


def fetch_listing(shop: dict, attempts: int = 2) -> str:
    last = ""
    for attempt in range(attempts):
        html = _once(shop)
        if 'class="card bs-state' in html:
            return html
        last = html
    raise RuntimeError("Дикси отдал заглушку вместо выдачи (антибот)")


def _once(shop: dict) -> str:
    holder = {}

    def action(page):
        page.evaluate(
            """async ([sid, coords, addr]) => {
              const fd = new FormData();
              fd.append('action', 'saveStore');
              fd.append('isDelivery', 'false');
              fd.append('store_id', sid);
              fd.append('coords', coords);
              fd.append('address', addr);
              await fetch('/ajax/ajax.php', {method: 'POST', body: fd, credentials: 'include'});
            }""",
            [shop["id"], ",".join(shop["coords"]), shop["label"]],
        )
        page.goto(LISTING, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)  # товары дорисовываются после загрузки
        holder["html"] = page.content()

    StealthyFetcher.fetch(f"{BASE}/", headless=True, network_idle=True, timeout=90000,
                          page_action=action)
    return holder.get("html", "")


def parse(html: str, shop: dict, city: str) -> list[dict]:
    deals, seen = [], set()
    for card in re.finditer(r'<article class="card bs-state[^"]*"(.*?)</article>', html, re.S):
        block = card.group(1)
        title = re.search(r'class="card__title">([^<]*)<', block)
        price = re.search(r'class="card__price-num"[^>]*>(.*?)<span class="rub"', block, re.S)
        old = re.search(r'class="card__price-crossed"[^>]*>(.*?)<span class="rub"', block, re.S)
        link = re.search(r'class="card__link" href="([^"]+)"', block)
        image = re.search(r'class="card-image"[^>]*src="([^"]+)"', block)
        rating = re.search(r'class="card__rating".*?<span>([\d.,]+)</span>', block, re.S)
        category = re.search(r'data-section="([^"]*)"', block)
        badges = re.findall(r'class="badge [^"]*">\s*<span>([^<]*)</span>', block)
        if not (title and price and link):
            continue
        value = _num(price.group(1))
        if value is None:
            continue
        old_value = _num(old.group(1)) if old else None
        url = BASE + link.group(1)
        if url in seen:
            continue
        seen.add(url)
        percent = round((1 - value / old_value) * 100) if old_value and old_value > value else None
        deals.append({
            "store": "Дикси",
            "store_key": shop["key"],
            "city": city,
            "address": shop["label"],
            "title": title.group(1).strip(),
            "price": value,
            "old_price": old_value,
            "discount_percent": percent,
            "period": next((b for b in badges if b.strip().startswith("до ")), None),
            "campaign": None,
            "badges": badges,
            "category": category.group(1) if category else None,
            "rating": float(rating.group(1).replace(",", ".")) if rating else None,
            "no_discount_data": old_value is None,
            "url": url,
            "image": BASE + image.group(1) if image else None,
        })
    return deals


def _num(raw: str) -> float | None:
    clean = re.sub(r"<[^>]+>", "", raw).replace(" ", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def run(city: str, shop: dict) -> list[dict]:
    return parse(fetch_listing(shop), shop, city)


def fetch_listing_session(session: StealthySession, shop: dict, path: str = LISTING) -> str:
    """Один магазин в уже открытой сессии — без повторного запуска браузера."""
    holder = {}

    def action(page):
        page.evaluate(
            """async ([sid, coords, addr]) => {
              const fd = new FormData();
              fd.append('action', 'saveStore');
              fd.append('isDelivery', 'false');
              fd.append('store_id', sid);
              fd.append('coords', coords);
              fd.append('address', addr);
              await fetch('/ajax/ajax.php', {method: 'POST', body: fd, credentials: 'include'});
            }""",
            [shop["id"], ",".join(shop["coords"]), shop["label"]],
        )
        page.goto(BASE + path, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        holder["html"] = page.content()

    session.fetch(f"{BASE}/", network_idle=True, timeout=90000, page_action=action)
    html = holder.get("html", "")
    if 'class="card bs-state' not in html:
        raise RuntimeError(f"нет карточек на {path} (антибот или пустая выдача)")
    return html
