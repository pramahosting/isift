"""Builds the user manuals (PDF) from content.py and the screenshots in shots/. Needs Node with Playwright: node print.js"""
import base64, html, json, os
from content import M
OUT = os.path.join(os.path.dirname(__file__), "html"); os.makedirs(OUT, exist_ok=True)
CSS = """
@page{size:A4;margin:16mm 14mm}
body{font:11.5pt/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#17283a;margin:0}
.cover{height:255mm;display:flex;flex-direction:column;justify-content:center;page-break-after:always}
.brand{font-weight:700;color:#2563eb;letter-spacing:.08em;font-size:12pt}.cover h1{font-size:34pt;margin:8mm 0 4mm;line-height:1.1}.cover p{font-size:14pt;color:#4a5d70;max-width:150mm}
.toc{margin-top:14mm;font-size:11pt}.toc li{margin:1.5mm 0}
.step{page-break-inside:avoid;margin:0 0 7mm}.step h2{font-size:15pt;margin:0 0 2mm;display:flex;gap:8px;align-items:center}
.n{background:#2563eb;color:#fff;border-radius:50%;width:8mm;height:8mm;display:inline-flex;align-items:center;justify-content:center;font-size:11pt;flex:none}
.step p{margin:0 0 3mm}.shot{width:80%;display:block;margin:0 auto;border:1px solid #cfd9e3;border-radius:6px}
.tip{background:#eef5ff;border-left:3px solid #2563eb;padding:2mm 3mm;margin:0 0 3mm;font-size:10.5pt}
.foot{margin-top:8mm;color:#6b7c8c;font-size:9.5pt;border-top:1px solid #dbe3ee;padding-top:3mm}
"""
def img(name):
    p = os.path.join(os.path.dirname(__file__), "shots", name + ".jpg")
    return "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()
files = []
for slug, title, intro, steps in M:
    toc = "".join(f"<li>{html.escape(h)}</li>" for h, *_ in steps)
    body = "".join(
        f'<section class="step"><h2><span class="n">{i}</span>{html.escape(h)}</h2><p>{html.escape(t)}</p>'
        + (f'<div class="tip"><b>Good to know:</b> {html.escape(tip)}</div>' if tip else "")
        + f'<img class="shot" alt="{html.escape(h)}" src="{img(shot)}"></section>'
        for i, (h, t, shot, tip) in enumerate(steps, 1))
    doc = (f'<!doctype html><meta charset="utf-8"><title>iSift manual: {html.escape(title)}</title><style>{CSS}</style>'
           f'<div class="cover"><div class="brand">iSIFT USER MANUAL</div><h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p><ol class="toc">{toc}</ol></div>{body}'
           f'<div class="foot">iSift user manual · {html.escape(title)} · isift.au</div>')
    open(os.path.join(OUT, slug + ".html"), "w", encoding="utf-8").write(doc); files.append(slug)
json.dump([[s, t, i] for s, t, i, _ in M], open(os.path.join(OUT, "index.json"), "w"))
print(files)
