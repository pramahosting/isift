"""Keeps only a short list of safe formatting tags from a WordPerfect document, so a document shared with someone can never run script in their browser."""
import re
from html import escape
from html.parser import HTMLParser

OK = {"p", "br", "h1", "h2", "h3", "ul", "ol", "li", "b", "strong", "i", "em", "u", "s", "strike", "a", "blockquote", "table", "thead", "tbody", "tr", "td", "th", "div", "span", "hr", "code", "pre", "sub", "sup"}
VOID = {"br", "hr"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript", "textarea", "select", "form"}
ALIGN = re.compile(r"text-align\s*:\s*(left|right|center|justify)", re.I)

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
        m = ALIGN.search(d.get("style") or "")
        if m and tag in ("p", "div", "h1", "h2", "h3", "li", "td", "th", "blockquote"): a += f' style="text-align:{m.group(1).lower()}"'
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
