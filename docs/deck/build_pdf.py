"""Build the deck PDF: run the layout audit, then export 16:9 pages."""
import asyncio, sys, pathlib
from playwright.async_api import async_playwright

DECK = pathlib.Path(__file__).resolve().parent / "deck.html"
OUT  = DECK.parent
SHOT = OUT / "stills"
SHOT.mkdir(exist_ok=True)

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1400, "height": 900})
        logs = []
        pg.on("console", lambda m: logs.append(m.text))
        pg.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))

        await pg.goto(DECK.as_uri(), wait_until="load")
        try:
            await pg.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            print("(fonts still loading — continuing)")
        await pg.wait_for_timeout(2500)

        # force a fresh audit now that layout has settled
        scaled = await pg.evaluate("() => window.fit ? window.fit() : []")
        bad = await pg.evaluate("() => window.audit ? window.audit() : ['audit() missing']")
        print("  AUTO-FIT:", scaled if scaled else "none needed")
        print("=== LAYOUT AUDIT ===")
        print("  OVERFLOW:", bad if bad else "none — every slide fits")

        n = await pg.evaluate("() => document.querySelectorAll('.slide').length")
        nums = await pg.evaluate(
            "() => [...document.querySelectorAll('.slide .foot .num')].map(e => e.textContent)")
        print("  slides  :", n)
        print("  footers :", nums)

        for line in logs:
            print("  console:", line)

        # stills of the slides that changed most
        for idx in (2, 4, 6, 13, 16, 18, 20):
            try:
                el = pg.locator(".slide").nth(idx - 1)
                await el.screenshot(path=str(SHOT / f"slide{idx:02d}.png"))
            except Exception as e:
                print(f"  !! shot {idx}: {e}")

        pdf = OUT / "HaemophiliaRadar_Deck.pdf"
        await pg.pdf(path=str(pdf), width="1280px", height="720px",
                     print_background=True, margin={"top":"0","bottom":"0","left":"0","right":"0"})
        print("=== PDF ===")
        print(f"  {pdf}  ({pdf.stat().st_size/1024:.0f} KB)")
        await b.close()

asyncio.run(main())
