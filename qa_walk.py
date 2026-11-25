"""Агент-пользователь: ходит по сайту как человек и собирает поломки.

Запуск:
    .venv\\Scripts\\python.exe qa_walk.py                     # локальный сайт
    .venv\\Scripts\\python.exe qa_walk.py https://склад.ру   # прод
    .venv\\Scripts\\python.exe qa_walk.py --stores 5         # сколько магазинов обойти

Что делает: открывает главную, ждёт список, кликает по магазинам,
в каждом проверяет шапку, карточки, поиск и категории; собирает
ошибки консоли, 404 и битые картинки.
"""
import argparse
import random
import sys

from patchright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://localhost:4321")
    ap.add_argument("--stores", type=int, default=3)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    problems: list[str] = []
    checked = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text[:160]) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("pageerror: " + str(e)[:160]))
        page.on("response", lambda r: problems.append(f"{r.status} {r.url[:110]}")
                if r.status >= 400 and not r.url.endswith("favicon.ico") else None)

        print(f"→ открываю {args.base}")
        page.goto(args.base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".store-row", timeout=45000)
        rows = page.locator(".store-row").count()
        print(f"  магазинов в списке: {rows}")
        if rows == 0:
            problems.append("главная: список магазинов пуст")

        # поиск по товару
        page.fill("#q", "молоко")
        page.wait_for_timeout(1500)
        found = page.locator(".store-row").count()
        print(f"  поиск «молоко»: магазинов {found}")
        page.fill("#q", "")
        page.wait_for_timeout(800)

        links = page.locator(".store-row").evaluate_all(
            "els => els.map(e => e.getAttribute('href')).filter(Boolean)")
        random.shuffle(links)
        for href in links[: args.stores]:
            checked += 1
            print(f"→ магазин {href}")
            resp = page.goto(args.base.rstrip("/") + href, wait_until="domcontentloaded", timeout=60000)
            if resp and resp.status >= 400:
                problems.append(f"{href}: статус {resp.status}")
                continue

            page.wait_for_timeout(1200)
            # прокрутка, чтобы подгрузились ленивые картинки
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            page.evaluate("window.scrollTo(0, 0)")

            title = page.locator("h1").first.inner_text() if page.locator("h1").count() else ""
            cards = page.locator(".card").count()
            empty = page.locator(".empty").count()
            print(f"  «{title}», карточек {cards}, пустое состояние {empty}")
            if not title:
                problems.append(f"{href}: нет заголовка магазина")

            if cards:
                # поиск внутри магазина: ищем слово из первого товара
                if page.locator("#storeSearch").count():
                    first_title = page.locator(".card h3").first.inner_text()
                    word = next((w for w in first_title.replace(",", " ").split() if len(w) >= 5), "")
                    if word:
                        page.fill("#storeSearch", word)
                        page.wait_for_timeout(900)
                        visible = page.evaluate("() => [...document.querySelectorAll('.card')].filter(c => !c.hidden).length")
                        print(f"  поиск «{word}»: видно {visible}")
                        if visible == 0:
                            problems.append(f"{href}: поиск «{word}» не находит товаров")
                        page.fill("#storeSearch", "")
                        page.wait_for_timeout(500)

                # категории
                chips = page.locator("#storeCats .chip")
                if chips.count() > 1:
                    name = chips.nth(1).inner_text()
                    chips.nth(1).click()
                    page.wait_for_timeout(700)
                    visible = page.evaluate("() => [...document.querySelectorAll('.card')].filter(c => !c.hidden).length")
                    print(f"  категория «{name}»: видно {visible}")
                    if visible == 0:
                        problems.append(f"{href}: категория показывает пусто")

            broken = page.evaluate(
                "() => [...document.images].filter(i => i.src && i.complete && i.naturalWidth === 0).map(i => i.src)")
            if broken:
                problems.append(f"{href}: битых картинок {len(broken)} — {broken[0][:90]}")

        if console_errors:
            problems.extend(f"консоль: {e}" for e in console_errors[:10])

        browser.close()

    print("\n— итог —")
    print(f"проверено магазинов: {checked}")
    if problems:
        print(f"проблем: {len(problems)}")
        for p_ in dict.fromkeys(problems):
            print("  •", p_)
    else:
        print("проблем не найдено")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
