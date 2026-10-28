"""Keeps only a short list of safe formatting tags from a WordPerfect document, so a document shared with someone can never run script in their browser."""
import re
from html import escape
from html.parser import HTMLParser

OK = {"p", "br", "h1", "h2", "h3", "ul", "ol", "li", "b", "strong", "i", "em", "u", "s", "strike", "a", "blockquote", "table", "thead", "tbody", "tr", "td", "th", "div", "span", "hr", "code", "pre", "sub", "sup", "img"}
VOID = {"br", "hr", "img"}
PNG_SRC = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]{16,40000000}$")   # pictures stored inside the file itself (shapes, and pictures from Word or PDF files); never a web address
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript", "textarea", "select", "form"}
ALIGN = re.compile(r"text-align\s*:\s*(left|right|center|justify)", re.I)

# Formatting that is kept: colours, fonts, sizes, spacing, borders and shading. Anything that could load a file or run code is dropped.
_COLOR = r"(#[0-9a-fA-F]{3,8}|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(,\s*[\d.]+\s*)?\)|[a-zA-Z]{3,20}|transparent)"
_LEN = r"-?\d{1,4}(\.\d{1,3})?(px|pt|em|rem|%|cm|mm|in)?"
_CSS = {
    "color": re.compile(r"^" + _COLOR + r"$"), "background-color": re.compile(r"^" + _COLOR + r"$"), "background": re.compile(r"^" + _COLOR + r"$"),
    "font-family": re.compile(r"^[A-Za-z0-9 ,'\"\-]{1,120}$"), "font-size": re.compile(r"^\d{1,3}(\.\d{1,2})?(px|pt|em|rem|%)$"),
    "font-weight": re.compile(r"^(normal|bold|bolder|lighter|[1-9]00)$"), "font-style": re.compile(r"^(normal|italic|oblique)$"),
    "text-decoration": re.compile(r"^(none|underline|line-through|overline)( (underline|line-through|overline))*$"),
    "text-align": re.compile(r"^(left|right|center|justify)$"), "text-indent": re.compile(r"^" + _LEN + r"$"), "line-height": re.compile(r"^(normal|\d{1,3}(\.\d{1,2})?(px|pt|em|%)?)$"),
    "letter-spacing": re.compile(r"^" + _LEN + r"$"), "vertical-align": re.compile(r"^(baseline|sub|super|top|middle|bottom)$"), "text-transform": re.compile(r"^(none|uppercase|lowercase|capitalize)$"),
    "width": re.compile(r"^" + _LEN + r"$"), "height": re.compile(r"^" + _LEN + r"$"), "border-collapse": re.compile(r"^(collapse|separate)$"),
    "list-style-type": re.compile(r"^(disc|circle|square|decimal|lower-alpha|upper-alpha|lower-roman|upper-roman|none)$"),
}
for _k in ("margin", "margin-top", "margin-bottom", "margin-left", "margin-right", "padding", "padding-top", "padding-bottom", "padding-left", "padding-right"):
    _CSS[_k] = re.compile(r"^(" + _LEN + r")( " + _LEN + r"){0,3}$")
for _k in ("border", "border-top", "border-bottom", "border-left", "border-right"):
    _CSS[_k] = re.compile(r"^(none|\d{1,2}(\.\d)?(px|pt)? (solid|dashed|dotted|double) " + _COLOR + r")$")

_CSS.update({
    "position": re.compile(r"^(relative|absolute)$"), "left": re.compile(r"^" + _LEN + r"$"), "top": re.compile(r"^" + _LEN + r"$"),
    "white-space": re.compile(r"^(nowrap|pre|normal|pre-wrap)$"), "overflow": re.compile(r"^(hidden|visible)$"), "background-size": re.compile(r"^(100% 100%|cover|contain)$"),
    "background-repeat": re.compile(r"^no-repeat$"), "min-height": re.compile(r"^" + _LEN + r"$"),
})
BG_IMG = re.compile(r"^url\(data:image/(png|jpeg);base64,[A-Za-z0-9+/=]{16,40000000}\)$")      # a page picture stored in the file itself; never a web address

def _split_decl(style: str):
    """Split on ; but not inside brackets (a data: address contains a semicolon)."""
    depth, cur = 0, ""
    for ch in style:
        if ch == "(": depth += 1
        elif ch == ")": depth = max(0, depth - 1)
        if ch == ";" and depth == 0: yield cur; cur = ""
        else: cur += ch
    if cur: yield cur

def safe_style(style: str) -> str:
    out = []
    for part in _split_decl(style or ""):
        if ":" not in part: continue
        k, v = part.split(":", 1); k = k.strip().lower(); v = re.sub(r"\s+", " ", v.strip())
        if k == "background-image":
            if BG_IMG.match(v): out.append(f"{k}:{v}")
            continue
        rx = _CSS.get(k)
        if rx and rx.match(v) and not re.search(r"url|expression|javascript|@|\\|<|>", v, re.I): out.append(f"{k}:{v}")
    return ";".join(out[:24])

class _S(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.out: list[str] = []; self.skip = 0; self.open: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT: self.skip += 1; return
        if self.skip or tag not in OK: return
        a = ""
        d = dict(attrs)
        if tag == "a":
            h = (d.get("href") or "").strip()
            if re.match(r"^(https?://|mailto:)", h, re.I): a = f' href="{escape(h, quote=True)}" target="_blank" rel="noopener noreferrer"'
        st = safe_style(d.get("style") or "")
        if st and tag != "img": a += f' style="{escape(st, quote=True)}"'
        if tag == "img":
            src = (d.get("src") or "").strip()
            if not PNG_SRC.match(src): return
            a = f' src="{src}"'
            if st: a += f' style="{escape(st, quote=True)}"'
            for k in ("width", "height"):
                if (d.get(k) or "").isdigit() and 0 < int(d[k]) <= 2000: a += f' {k}="{int(d[k])}"'
            a += f' alt="{escape((d.get("alt") or "Shape")[:80], quote=True)}"'
        if tag in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if (d.get(k) or "").isdigit() and int(d[k]) < 50: a += f' {k}="{int(d[k])}"'
        self.out.append(f"<{tag}{a}>")
        if tag not in VOID: self.open.append(tag)
    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT: self.skip = max(0, self.skip - 1); return
        if self.skip or tag not in OK or tag in VOID or tag not in self.open: return
        while self.open:
            t = self.open.pop(); self.out.append(f"</{t}>")
            if t == tag: break
    def handle_data(self, data):
        if not self.skip: self.out.append(escape(data, quote=False))

def clean(html: str) -> str:
    p = _S(); p.feed(html or ""); p.close()
    while p.open: p.out.append(f"</{p.open.pop()}>")
    return "".join(p.out)

def to_text(html: str) -> str:
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-3]|li|tr|blockquote)>", "\n", html or ""); t = re.sub(r"(?i)</t[dh]>", "\t", t)
    from html import unescape
    return re.sub(r"\n{3,}", "\n\n", unescape(re.sub(r"<[^>]+>", "", t))).strip()
