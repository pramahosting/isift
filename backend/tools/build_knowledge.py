"""Builds the iSift assistant's reading material (app/knowledge/kb.json) from the whole pack:
the user manuals, the landing page, the workspace tiles, the in-meeting tools, the module list, the plan features and the user-facing docs.

Run after changing any of those:   python backend/tools/build_knowledge.py
Each piece is marked public (anyone) or admin (only for a signed-in administrator). Operator docs (setup, deployment, keys) are never included.
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs" / "manuals")); sys.path.insert(0, str(ROOT / "backend"))
chunks: list[dict] = []
def add(source: str, title: str, text: str, aud: str = "public"):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 25: chunks.append({"id": len(chunks), "source": source, "title": title.strip(), "text": text[:1600], "aud": aud})

# 1. manuals (every step of every manual)
from content import M
for slug, title, intro, steps in M:
    aud = "admin" if slug == "administration" else "public"
    add(f"Manual: {title}", f"{title} (overview)", intro, aud)
    for h, t, shot, tip in steps: add(f"Manual: {title}", f"{title}: {h}", f"{h}. {t}" + (f" Good to know: {tip}" if tip else ""), aud)

# 2. landing page text
land = (ROOT / "frontend/src/Landing.tsx").read_text(encoding="utf-8")
for m in re.finditer(r"\{i:\w+,t:'((?:[^'\\]|\\.)*)',d:'((?:[^'\\]|\\.)*)'", land): add("Website", m.group(1), m.group(2).replace("\\'", "'"))
for m in re.finditer(r"\['((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\]", land): add("Website", m.group(1), m.group(2).replace("\\'", "'"))
for m in re.finditer(r"\{label:'((?:[^'\\]|\\.)*)',cells:\[(.*?)\]\}", land):
    cols = ["iSift", "Zoom", "Zoho Meeting", "Webex", "GoTo Meeting", "Microsoft Teams", "Google Meet"]
    cells = [(q.replace("\\u2019", "'").replace("\\'", "'") if q else {"Y": "yes", "N": "no", "null": "not stated"}[w]) for q, w in re.findall(r"'((?:[^'\\]|\\.)*)'|\b(Y|N|null)\b", m.group(2))]
    add("Website: comparison with other meeting tools", "Comparison: " + m.group(1).replace("\\'", "'"), "; ".join(f"{c}: {v}" for c, v in zip(cols, cells)))
for m in re.finditer(r"\{slug:'([\w-]+)',t:'([^']*)',d:'([^']*)'", land): add("Website: manuals", f"Manual: {m.group(2)}", f"A step-by-step PDF manual with screenshots, on the website under User manuals. {m.group(3)}")

# 3. workspace tiles and in-meeting tools
home = (ROOT / "frontend/src/HomeWorkspace.tsx").read_text(encoding="utf-8")
for m in re.finditer(r"label:'([^']+)',note:'([^']+)'", home): add("Workspace", f"Workspace tile: {m.group(1)}", f"{m.group(1)}: {m.group(2)}. Add it to your workspace with More tools.")
room = (ROOT / "frontend/src/Room.tsx").read_text(encoding="utf-8")
for m in re.finditer(r"label:'([^']+)',hint:'([^']+)'", room): add("In a meeting", f"Meeting tool: {m.group(1)}", f"In a meeting, open More and choose {m.group(1)}: {m.group(2)}.")

# 4. modules and user-facing docs
from app.api.routes_modules import MODULES
for _id, label, desc in MODULES: add("Modules", f"Module: {label}", desc)
def sections(path: Path):
    parts = re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.M)
    for p in parts[1:]:
        head, _, body = p.partition("\n"); yield head.strip(), body
for head, body in sections(ROOT / "docs/WEBINARS.md"): add("Webinars guide", f"Webinars: {head}", body, "admin" if head.startswith("Setup") else "public")
PUBLIC_MAIL = ("Who can have an address", "Own domains", "Outlook, Thunderbird", "Easy setup", "What people get", "Spam control")
for head, body in sections(ROOT / "docs/ISIFTMAIL.md"):
    add("isiftmail guide", f"isiftmail: {head}", body, "public" if head.startswith(PUBLIC_MAIL) else "admin")
add("Give control", "Give control of a shared file", "Share a PDF or photo through iSift (More, Share a file), then choose Give control to and pick a participant. They can move through pages and scroll the file for everyone. The host can take control back at any time, and only the host can stop sharing. This works for files shared through iSift, not for a whole screen or for a PowerPoint or Word file on the host's computer; save those as PDF first.")
out = ROOT / "backend/app/knowledge/kb.json"; out.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
print(len(chunks), "pieces:", {a: sum(1 for c in chunks if c["aud"] == a) for a in ("public", "admin")}, "->", out)
