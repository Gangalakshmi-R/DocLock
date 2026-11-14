#!/usr/bin/env python
"""Record the README demo GIF by driving the real DocLock web UI with a headless browser.

    pip install playwright pillow
    playwright install chromium
    python docs/record_demo.py --base-url http://localhost:3000 --password "<your DocLock password>"

It signs in, uploads the sample documents from eval/corpus, captures the background-processing progress, the
deadline alerts, the extracted-facts view and a cited answer, then writes docs/demo.gif.
Run it against your own running stack so the answers in the GIF come from your real Llama 3.1 model.
(The GIF shipped in this repository was recorded against a stubbed test backend: see the README.)
"""
from __future__ import annotations

import argparse
import io
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "eval" / "corpus"
QUESTION = "What is the waiting period for pre-existing diseases?"


class Recorder:
    def __init__(self, page, width: int) -> None:
        self.page, self.width = page, width
        self.frames: list[tuple[Image.Image, int]] = []

    def snap(self, hold_ms: int = 1500) -> None:
        image = Image.open(io.BytesIO(self.page.screenshot())).convert("RGB")
        if image.width != self.width:
            image = image.resize((self.width, round(image.height * self.width / image.width)), Image.LANCZOS)
        self.frames.append((image, hold_ms))

    def save(self, path: Path) -> None:
        height = min(max(img.height for img, _ in self.frames), 900)
        prepared = []
        for img, _ in self.frames:
            canvas = Image.new("RGB", (self.width, height), "white")
            canvas.paste(img.crop((0, 0, self.width, min(img.height, height))))
            prepared.append(canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
        prepared[0].save(path, save_all=True, append_images=prepared[1:], duration=[d for _, d in self.frames],
                         loop=0, optimize=True, disposal=2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:3000")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo.gif"))
    ap.add_argument("--timeout", type=int, default=900, help="seconds to wait for processing / the answer")
    args = ap.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="doclock-demo-"))
    soon = date.today() + timedelta(days=12)
    membership = workdir / "gym_membership.txt"
    membership.write_text(f"City Fitness Club membership card\nMembership expiry date: {soon.isoformat()}\nAnnual fee: Rs. 4,500\n", encoding="utf-8")
    uploads = [CORPUS / "health_insurance_policy.txt", CORPUS / "rental_agreement.txt", CORPUS / "college_fee_circular.txt", membership]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(args.timeout * 1000)
        rec = Recorder(page, width=1000)

        page.goto(f"{args.base_url}/login")
        page.fill("input >> nth=0", args.username)
        page.fill("input[type=password]", args.password)
        rec.snap(1400)
        page.click("button[type=submit]")
        page.wait_for_selector("text=Your documents")

        for path in uploads:
            page.set_input_files("input[type=file]", str(path))
            page.click("text=Upload document")
            page.wait_for_selector(f"text={path.name}")  # the new document appears in the list once the upload is accepted
            # the button reads "Please wait…" while the request is in flight, then goes back to "Upload document"
            page.wait_for_function("() => document.querySelector('.upload button')?.innerText === 'Upload document'")

        # Capture the live progress bars while the background tasks run.
        shots, deadline = 0, time.time() + args.timeout
        while page.query_selector(".progress-wrap") and time.time() < deadline:
            if shots < 5:
                rec.snap(900)
                shots += 1
            time.sleep(0.9)
        page.wait_for_selector("text=Ready", timeout=args.timeout * 1000)
        page.wait_for_selector(".alert")
        time.sleep(0.5)
        rec.snap(3200)  # alerts panel + finished documents

        page.locator(".doc", has_text="health_insurance_policy").get_by_text("View").click()
        page.wait_for_selector(".facts")
        rec.snap(3200)  # extracted facts
        page.click("text=Close")

        page.fill("textarea", QUESTION)
        rec.snap(1200)
        page.click("text=Ask DocLock AI")
        page.wait_for_function("() => !document.querySelector('.answer').innerText.startsWith('Searching')")
        page.wait_for_selector(".citations details")
        page.locator(".citations summary").first.click()
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.4)
        rec.snap(4200)  # grounded answer with cited sources

        browser.close()

    out = Path(args.out)
    rec.save(out)
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB, {len(rec.frames)} frames)")


if __name__ == "__main__":
    main()
