# Presentation deck

`deck.html` is the source; `HaemophiliaRadar_Deck.pdf` is the submission artifact.

## Viewing

Open `deck.html` in any browser. Arrow keys / space / PageDown navigate; Home and End jump to the ends.

The page audits its own layout on load. Open the console:

- `layout clean: all 23 slides fit` — nothing is clipped
- `AUTO-FIT -> 10:0.91` — that slide's body was scaled to fit
- `OVERFLOW -> 6:+21` — content exceeds the frame and **would be clipped in the PDF**

Any overflowing slide is also outlined in red on screen (never in print). Call `window.audit()` or `window.layout()` to re-measure by hand.

## Rebuilding the PDF

Slides are a fixed 1280×720 so the exported pages are exactly 16:9. Printing from the browser works, but `build_pdf.py` is the reproducible path — it runs the audit, captures stills, and exports with print backgrounds on:

```bash
python3 -m venv .venv && .venv/bin/pip install playwright
.venv/bin/playwright install chromium chromium-headless-shell
.venv/bin/python build_pdf.py
```

Output: `HaemophiliaRadar_Deck.pdf` (23 pages, 960×540 pt) and `stills/`.

## Structure

18 body slides plus a 5-slide appendix. The deck is **read, not spoken** — there is no pitch slot — so every slide title is a complete claim and carries its own evidence.

Two conventions hold throughout:

- **One key line per slide.** Accent-ruled, left-barred. Never two — a slide where everything is emphasised emphasises nothing.
- **A status chip on every capability.** Exactly four labels: `Built`, `Partial`, `Designed`, `Not built`. Any qualifier goes in muted text beside the chip, never inside it.

Footer numbers are generated at load from slide order, so reordering a slide cannot leave a stale number behind. Appendix slides carry `data-appendix` and keep their `A`/`A1`…`A4` labels.

The palette and type are inherited from `phase2/web/tailwind.config.ts` so the deck and the product read as one system.
