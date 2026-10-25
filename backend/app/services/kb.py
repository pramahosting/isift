"""The assistant's reading material: pieces of the manuals, website, workspace, meeting tools and guides (app/knowledge/kb.json, built by tools/build_knowledge.py).
Finds the few pieces that best match a question, so the assistant answers from the real documentation and the answer is always current."""
import json, math, re
from collections import Counter
from pathlib import Path

_FILE = Path(__file__).resolve().parents[1] / "knowledge" / "kb.json"
STOP = set("a an the and or of to in on for with is are was were be do does did how what when where which who why can could should would i you we my your our it this that these those at by as from if not no yes me us any all about into than then there so up out".split())
_DOCS: list[dict] = []; _DF: Counter = Counter(); _AVG = 1.0

def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf): return w[: -len(suf)]
    return w

def tokens(text: str) -> list[str]: return [_stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 1]

def load() -> list[dict]:
    global _DOCS, _DF, _AVG
    if _DOCS: return _DOCS
    try: raw = json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError): raw = []
    for d in raw:
        d["_t"] = Counter(tokens(d["title"] + " " + d["title"] + " " + d["text"])); d["_n"] = sum(d["_t"].values()) or 1
        _DF.update(d["_t"].keys())
    _DOCS = raw; _AVG = (sum(d["_n"] for d in raw) / len(raw)) if raw else 1.0
    return _DOCS

def search(query: str, admin: bool = False, k: int = 5) -> list[tuple[float, dict]]:
    """Best pieces for a question (BM25). Pieces marked admin are only returned to an administrator."""
    docs = load(); q = tokens(query)
    if not q or not docs: return []
    N = len(docs); out = []
    for d in docs:
        if d["aud"] == "admin" and not admin: continue
        s = 0.0
        for w in set(q):
            f = d["_t"].get(w, 0)
            if not f: continue
            idf = math.log(1 + (N - _DF[w] + 0.5) / (_DF[w] + 0.5)); s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * d["_n"] / _AVG))
        if s: out.append((s, d))
    out.sort(key=lambda x: -x[0]); return out[:k]

def excerpts(query: str, admin: bool = False, k: int = 5, limit: int = 4200) -> str:
    """Text to put in front of the language model."""
    parts, used = [], 0
    for s, d in search(query, admin, k):
        t = f"[{d['source']} / {d['title']}] {d['text']}"[:900]
        if used + len(t) > limit: break
        parts.append(t); used += len(t)
    return "\n".join(parts)

def best_answer(query: str, admin: bool = False, min_score: float = 4.0) -> str | None:
    """A plain answer when no language model is available: the best matching piece of documentation."""
    hit = search(query, admin, 1)
    if not hit or hit[0][0] < min_score: return None
    d = hit[0][1]; text = d["text"]
    if len(text) > 520: text = text[:520].rsplit(" ", 1)[0] + "…"
    src = "the website" if d["source"].startswith("Website") else "the iSift " + ("manual" if d["source"].startswith("Manual") else "guide")
    return f"From {src}: {text}"
