"""Doc Converter: WordPerfect, SpreadTable and PowerPresentation files to PDF and to Word / Excel / PowerPoint, and PDF back to WordPerfect.

How each file is stored (so the converters read the real thing):
  WordPerfect       an HTML string
  SpreadTable       JSON {"sheets": [{"name", "cells": {"A1": "text or =formula"}, "rows", "cols"}]}
  PowerPresentation JSON {"theme", "slides": [{"layout", "title", "body", "body2", "notes", "bg", "shapes": [{"id", "lib", "text", "x", "y", "w"}]}]}
Shapes are drawn by the browser, so the browser sends their pictures along (`shapes`: id -> {"png": data URL, "w", "h"}).
Everything is built from the file's own content and no address in the content is ever fetched."""
import base64, html as _html, io, json, re
from collections import Counter

THEMES = {"light": ("#ffffff", "#172033", "#2b62f0"), "dark": ("#172033", "#f4f6fb", "#7da2ff"), "warm": ("#fff7ed", "#3b2a1a", "#e0561f"), "green": ("#f0fbf4", "#12301f", "#1c9a5b")}


class ConvertError(Exception): pass


def esc(s) -> str: return _html.escape(str(s if s is not None else ""), quote=True)


def _pdf_from_html(doc: str) -> bytes:
    """WeasyPrint may only read pictures that are inside the file itself (data: addresses). Nothing is ever fetched from a web address or a file on the server."""
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher
    return HTML(string=doc, url_fetcher=URLFetcher(allowed_protocols={"data"})).write_pdf()


def _png(data_url: str | None) -> bytes | None:
    """A picture stored in the document (png, jpeg, gif or webp) as bytes Word can place; webp is turned into png."""
    m = re.match(r"^data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)$", data_url or "")
    if not m: return None
    try: raw = base64.b64decode(m.group(2))
    except Exception: return None
    if m.group(1) == "webp":
        try:
            from PIL import Image
            bio = io.BytesIO(); Image.open(io.BytesIO(raw)).convert("RGBA").save(bio, "PNG"); return bio.getvalue()
        except Exception: return None
    return raw


# ------------------------------------------------------------------ WordPerfect

_BAD_TAGS = re.compile(r"<\s*(script|style|iframe|object|embed|form|link|meta|base)\b[\s\S]*?(<\s*/\s*\1\s*>|$)", re.I)
_ON_ATTR = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_PAGE_CSS = """@page{size:A4;margin:20mm 18mm}
body{font:12pt/1.55 Georgia,'Times New Roman','DejaVu Serif',serif;color:#172033;overflow-wrap:anywhere}
h1{font-size:2em;margin:.6em 0 .3em}h2{font-size:1.5em;margin:.6em 0 .3em}h3{font-size:1.2em;margin:.6em 0 .3em}
p{margin:0 0 .7em}blockquote{border-left:3px solid #c8d3ea;margin:.6em 0;padding:.1em 1em;color:#4a5670}
table{border-collapse:collapse;margin:.6em 0;width:100%}td,th{border:1px solid #9aa6bf;padding:6px 10px}a{color:#2b62f0}img{max-width:100%}"""


def clean_html(html: str) -> str:
    h = _BAD_TAGS.sub("", html or "")
    h = _ON_ATTR.sub("", h)
    h = re.sub(r"(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2", "", h, flags=re.I)
    h = re.sub(r"<img\b(?![^>]*src=[\"']data:image/png;base64,)[^>]*>", "", h, flags=re.I)    # only pictures that live inside the file
    return h


_EXACT_PAGE = re.compile(r'<div style="[^"]*position:relative;width:([\d.]+)pt;height:([\d.]+)pt')

def wp_to_pdf(html: str, title: str = "") -> bytes:
    css = _PAGE_CSS
    m = _EXACT_PAGE.search(html or "")
    if m:       # a document made of exact pages (from a PDF): the PDF has the same page size, no margins, one page per page
        css = f"@page{{size:{m.group(1)}pt {m.group(2)}pt;margin:0}}body{{margin:0;font:12pt Arial,sans-serif}}body>div[style*='position:relative']{{page-break-after:always;margin:0!important}}body>div[style*='position:relative']:last-child{{page-break-after:auto}}"
    return _pdf_from_html(f"<!doctype html><meta charset='utf-8'><title>{esc(title)}</title><style>{css}</style><body>{clean_html(html) or '<p></p>'}")


def _css_color(s: str | None):
    if not s: return None
    s = s.strip().lower()
    m = re.match(r"^#([0-9a-f]{6})$", s)
    if m: return m.group(1)
    m = re.match(r"^#([0-9a-f]{3})$", s)
    if m: return "".join(c * 2 for c in m.group(1))
    m = re.match(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", s)
    if m: return "".join(f"{min(255, int(x)):02x}" for x in m.groups())
    return {"black": "000000", "white": "ffffff", "red": "ff0000", "blue": "0000ff", "green": "008000", "gray": "808080", "grey": "808080", "orange": "ffa500", "purple": "800080", "yellow": "ffff00"}.get(s)


def wp_to_docx(html: str, title: str = "") -> bytes:
    """Headings, paragraphs, bold / italic / underline / strike, text colour and size, links, bullet and numbered lists, tables, pictures and alignment carry over as real Word content."""
    from bs4 import BeautifulSoup
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor, Emu

    soup = BeautifulSoup(clean_html(html), "html.parser")
    doc = Document()
    doc.core_properties.title = title[:200]
    st = doc.styles["Normal"]; st.font.name = "Georgia"; st.font.size = Pt(12)
    ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}

    def style_of(el) -> dict:
        out = {}
        for part in (el.get("style") or "").split(";"):
            if ":" in part:
                k, v = part.split(":", 1); out[k.strip().lower()] = v.strip()
        return out

    def css_fmt(css, f):
        """Colours, fonts, sizes and shading from an element's style, carried onto the text inside it."""
        if css.get("font-weight") in ("bold", "700", "800", "900"): f["b"] = True
        if css.get("font-style") == "italic": f["i"] = True
        if "underline" in css.get("text-decoration", ""): f["u"] = True
        if "line-through" in css.get("text-decoration", ""): f["s"] = True
        col = _css_color(css.get("color"))
        if col: f["color"] = col
        bg = _css_color(css.get("background-color") or css.get("background"))
        if bg: f["bg"] = bg
        m = re.match(r"^([\d.]+)(px|pt)$", css.get("font-size", ""))
        if m: f["size"] = round(float(m.group(1)) * (0.75 if m.group(2) == "px" else 1), 1)
        fam = (css.get("font-family") or "").split(",")[0].strip().strip("'\"")
        if fam: f["font"] = fam
        return f

    def shade(el_pr, hexcol):
        shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hexcol.upper()); el_pr.append(shd)

    def para_fmt(par, css):
        a = css.get("text-align")
        if a in ALIGN: par.alignment = ALIGN[a]
        m = re.match(r"^([\d.]+)(px|pt)$", css.get("margin-left", ""))
        if m: par.paragraph_format.left_indent = Pt(float(m.group(1)) * (0.75 if m.group(2) == "px" else 1))
        bg = _css_color(css.get("background-color") or css.get("background"))
        if bg: shade(par._p.get_or_add_pPr(), bg)

    def add_link(par, text, url, fmt):
        rid = par.part.relate_to(url, RT.HYPERLINK, is_external=True)
        h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), rid)
        r = OxmlElement("w:r"); rpr = OxmlElement("w:rPr")
        c = OxmlElement("w:color"); c.set(qn("w:val"), "2B62F0"); rpr.append(c)
        u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rpr.append(u)
        if fmt.get("b"): rpr.append(OxmlElement("w:b"))
        if fmt.get("i"): rpr.append(OxmlElement("w:i"))
        r.append(rpr); t = OxmlElement("w:t"); t.text = text; t.set(qn("xml:space"), "preserve"); r.append(t); h.append(r); par._p.append(h)

    def runs(par, node, fmt):
        from bs4 import NavigableString, Tag
        for ch in node.children:
            if isinstance(ch, NavigableString):
                txt = re.sub(r"\s+", " ", str(ch))
                if not txt: continue
                if fmt.get("href"): add_link(par, txt, fmt["href"], fmt); continue
                r = par.add_run(txt)
                r.bold = fmt.get("b") or None; r.italic = fmt.get("i") or None; r.underline = fmt.get("u") or None; r.font.strike = fmt.get("s") or None
                if fmt.get("color"): r.font.color.rgb = RGBColor.from_string(fmt["color"].upper())
                if fmt.get("size"): r.font.size = Pt(fmt["size"])
                if fmt.get("font"): r.font.name = fmt["font"]; r._r.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), fmt["font"])
                if fmt.get("bg"): shade(r._r.get_or_add_rPr(), fmt["bg"])
            elif isinstance(ch, Tag):
                n = ch.name; f = dict(fmt); css = style_of(ch)
                if n in ("b", "strong") or css.get("font-weight") in ("bold", "700", "800", "900"): f["b"] = True
                if n in ("i", "em") or css.get("font-style") == "italic": f["i"] = True
                if n == "u" or "underline" in css.get("text-decoration", ""): f["u"] = True
                if n in ("s", "strike", "del") or "line-through" in css.get("text-decoration", ""): f["s"] = True
                col = _css_color(css.get("color") or (ch.get("color") if n == "font" else None))
                if col: f["color"] = col
                css_fmt(css, f)
                if n == "a" and re.match(r"^(https?:|mailto:)", ch.get("href", ""), re.I): f["href"] = ch["href"]
                if n == "br": par.add_run().add_break(); continue
                if n == "img":
                    png = _png(ch.get("src"))
                    if png:
                        try:
                            w = int(float(ch.get("width") or 0)) or None
                            par.add_run().add_picture(io.BytesIO(png), width=Emu(w * 9525) if w else None)
                        except Exception: pass
                    continue
                if n in ("ul", "ol", "table", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"): continue      # handled as blocks
                runs(par, ch, f)

    def block(node, list_kind=None, level=0):
        from bs4 import NavigableString, Tag
        loose = None
        for ch in list(node.children):
            if isinstance(ch, NavigableString):
                if str(ch).strip():
                    if loose is None: loose = doc.add_paragraph()
                    loose.add_run(re.sub(r"\s+", " ", str(ch)))
                continue
            if not isinstance(ch, Tag): continue
            n = ch.name
            if n in ("ul", "ol"):
                loose = None
                for li in ch.find_all("li", recursive=False):
                    p = doc.add_paragraph(style="List Bullet" if n == "ul" else "List Number")
                    runs(p, li, css_fmt(style_of(li), {})); para_fmt(p, {k: v for k, v in style_of(li).items() if k != "margin-left"})
                    for sub in li.find_all(["ul", "ol"], recursive=False): block(li, None, level + 1); break
                continue
            if n in ("h1", "h2", "h3", "h4", "h5", "h6"):
                loose = None
                p = doc.add_heading(level=min(int(n[1]), 3)); cf = css_fmt(style_of(ch), {}); runs(p, ch, cf)
                for r in p.runs:
                    if not cf.get("font"): r.font.name = "Georgia"
                    if r.font.color is None or r.font.color.rgb is None: r.font.color.rgb = RGBColor.from_string("172033")
                css0 = style_of(ch)
                if not css0.get("text-align") and ch.get("align") in ALIGN: css0["text-align"] = ch["align"]
                para_fmt(p, css0)
                continue
            if n in ("p", "div", "blockquote") and not ch.find(["p", "div", "ul", "ol", "table", "h1", "h2", "h3", "blockquote"]):
                loose = None
                p = doc.add_paragraph(style="Quote" if n == "blockquote" else None); runs(p, ch, css_fmt(style_of(ch), {}))
                css0 = style_of(ch)
                if not css0.get("text-align") and ch.get("align") in ALIGN: css0["text-align"] = ch["align"]
                para_fmt(p, css0)
                continue
            if n == "table":
                loose = None
                rows = ch.find_all("tr")
                if not rows: continue
                ncols = max(sum(int(c.get("colspan") or 1) for c in r.find_all(["td", "th"], recursive=False)) for r in rows) or 1
                t = doc.add_table(rows=len(rows), cols=ncols); t.style = "Table Grid"
                for ri, r in enumerate(rows):
                    ci = 0
                    for c in r.find_all(["td", "th"], recursive=False):
                        if ci >= ncols: break
                        cell = t.cell(ri, ci); cp = cell.paragraphs[0]; ccss = style_of(c); cf = css_fmt(ccss, {"b": True} if c.name == "th" else {}); runs(cp, c, cf); para_fmt(cp, {k: v for k, v in ccss.items() if k == "text-align"})
                        if cf.get("bg"): shade(cell._tc.get_or_add_tcPr(), cf["bg"])
                        span = int(c.get("colspan") or 1)
                        if span > 1 and ci + span <= ncols: cell.merge(t.cell(ri, ci + span - 1))
                        ci += span
                doc.add_paragraph()
                continue
            if n in ("div", "section", "article", "blockquote", "span", "font", "b", "strong", "i", "em", "u", "a"):
                if n in ("span", "font", "b", "strong", "i", "em", "u", "a"):
                    if loose is None: loose = doc.add_paragraph()
                    runs(loose, type("W", (), {"children": [ch]})(), {})
                else: loose = None; block(ch)
                continue
            if n == "br": loose = None; continue
            if n == "hr": loose = None; doc.add_paragraph("―" * 20); continue
            if n == "img":
                loose = None; p = doc.add_paragraph(); runs(p, type("W", (), {"children": [ch]})(), {})
    pages_ = [d for d in soup.find_all("div") if re.search(r"position:relative", d.get("style") or "") and re.search(r"width:[\d.]+pt", d.get("style") or "") and re.search(r"background-image:url\(data:image", d.get("style") or "")]
    if pages_: _exact_docx(doc, pages_, style_of, css_fmt, runs)
    else: block(soup)
    bio = io.BytesIO(); doc.save(bio); return bio.getvalue()


def _exact_docx(doc, pages, style_of, css_fmt, runs) -> None:
    """Exact pages (from a PDF) as Word pages: the page graphics are a picture behind the text, and every line of text is a positioned text frame."""
    import copy
    from docx.enum.section import WD_SECTION
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import qn, nsdecls
    from docx.shared import Pt, Emu
    first = True
    for n, pg in enumerate(pages):
        css = style_of(pg)
        pw = float(re.match(r"([\d.]+)", css.get("width", "595")).group(1)); ph = float(re.match(r"([\d.]+)", css.get("height", "842")).group(1))
        sec = doc.sections[0] if first else doc.add_section(WD_SECTION.NEW_PAGE)
        first = False
        sec.page_width, sec.page_height = Pt(pw), Pt(ph)
        sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Pt(0); sec.header_distance = sec.footer_distance = Pt(0)
        m = re.search(r"background-image:url\(data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)\)", pg.get("style") or "")
        par0 = doc.add_paragraph(); par0.paragraph_format.space_after = Pt(0); par0.paragraph_format.space_before = Pt(0)
        par0.paragraph_format.line_spacing = Pt(1)
        if m:
            try:
                inline = doc.part.new_pic_inline(io.BytesIO(base64.b64decode(m.group(2))), Emu(int(pw * 12700)), Emu(int(ph * 12700)))
                graphic = copy.deepcopy(inline.find(qn("a:graphic")))
                anchor = parse_xml(f'<w:drawing {nsdecls("w", "wp", "a", "pic", "r")}><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="0" behindDoc="1" locked="1" layoutInCell="1" allowOverlap="1">'
                                   f'<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionH><wp:positionV relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionV>'
                                   f'<wp:extent cx="{int(pw * 12700)}" cy="{int(ph * 12700)}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/><wp:docPr id="{100 + n}" name="Page {n + 1}"/><wp:cNvGraphicFramePr/></wp:anchor></w:drawing>')
                anchor.find(qn("wp:anchor")).append(graphic)
                par0.add_run()._r.append(anchor)
            except Exception: pass
        for ln in pg.find_all("div", recursive=False):
            lc = style_of(ln)
            try: x = float(re.match(r"-?([\d.]+)", lc.get("left", "0")).group(0)); y = float(re.match(r"-?([\d.]+)", lc.get("top", "0")).group(0))
            except Exception: continue
            w = float(re.match(r"([\d.]+)", lc.get("width", "60")).group(1)); lh = float(re.match(r"([\d.]+)", lc.get("line-height", "12")).group(1))
            if not ln.get_text().strip(): continue
            p = doc.add_paragraph()
            pf = p.paragraph_format; pf.space_after = Pt(0); pf.space_before = Pt(0)
            from docx.enum.text import WD_LINE_SPACING
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY; pf.line_spacing = Pt(lh)
            fp = OxmlElement("w:framePr")
            for k, v in (("w:w", int((w * 1.12 + 6) * 20)), ("w:hSpace", 0), ("w:wrap", "around"), ("w:vAnchor", "page"), ("w:hAnchor", "page"), ("w:x", int(x * 20)), ("w:y", int(y * 20))): fp.set(qn(k), str(v))
            p._p.get_or_add_pPr().insert(0, fp)
            runs(p, ln, css_fmt(lc, {}))


# ------------------------------------------------------------------ SpreadTable

def _book(content: str) -> list[dict]:
    try:
        v = json.loads(content)
        if isinstance(v, dict) and isinstance(v.get("sheets"), list) and v["sheets"]:
            return [{"name": str(s.get("name") or "Sheet")[:40], "cells": {str(k): str(x) for k, x in (s.get("cells") or {}).items()}} for s in v["sheets"][:50]]
    except Exception: pass
    return [{"name": "Sheet1", "cells": {}}]


def _ref(k: str):
    m = re.match(r"^([A-Z]{1,3})(\d{1,5})$", k)
    if not m: return None
    return int(m.group(2)), sum((ord(c) - 64) * 26 ** i for i, c in enumerate(reversed(m.group(1))))


def sheet_to_xlsx(content: str, title: str = "") -> bytes:
    """Numbers stay numbers and formulas stay live formulas, one worksheet per sheet."""
    from openpyxl import Workbook
    wb = Workbook(); wb.remove(wb.active); used = set()
    for s in _book(content):
        name = re.sub(r"[\[\]\*\?/\\:]", "", s["name"])[:31] or "Sheet"
        base, n = name, 2
        while name.lower() in used: name = f"{base[:28]}{n}"; n += 1
        used.add(name.lower()); ws = wb.create_sheet(name)
        for k, raw in s["cells"].items():
            rc = _ref(k)
            if not rc or raw == "": continue
            cell = ws.cell(row=rc[0], column=rc[1])
            if raw.startswith("="):
                cell.value = re.sub(r"\bCONCAT\(", "_xlfn.CONCAT(", raw, flags=re.I)
            else:
                t = raw.strip()
                if re.match(r"^-?(0|[1-9]\d*)(\.\d+)?$", t): cell.value = float(t) if "." in t else int(t)      # a number stays a number; "007" stays text
                else: cell.value = raw
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value is not None and not str(c.value).startswith("=")), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(60, max(10, w + 2))
    if not wb.sheetnames: wb.create_sheet("Sheet1")
    wb.properties.title = title[:200]
    bio = io.BytesIO(); wb.save(bio); return bio.getvalue()


def sheet_to_pdf(content: str, shown: list | None, title: str = "") -> bytes:
    """`shown` is what the grid displays (formulas already worked out), one {cell: text} per sheet, sent by the browser."""
    parts = []
    for i, s in enumerate(_book(content)):
        vals = (shown[i] if shown and i < len(shown) and isinstance(shown[i], dict) else None) or {}
        cells = {k: str(vals.get(k, v)) for k, v in s["cells"].items()}
        pos = {k: _ref(k) for k in cells}
        pos = {k: p for k, p in pos.items() if p}
        if not pos:
            parts.append(f"<section><h2>{esc(s['name'])}</h2><p class=e>This sheet is empty.</p></section>"); continue
        mr, mc = max(p[0] for p in pos.values()), max(p[1] for p in pos.values())
        grid = {p: cells[k] for k, p in pos.items()}
        head = "<tr><th class=c></th>" + "".join(f"<th>{_colname(c)}</th>" for c in range(1, mc + 1)) + "</tr>"
        body = "".join(f"<tr><th class=r>{r}</th>" + "".join(_td(grid.get((r, c), "")) for c in range(1, mc + 1)) + "</tr>" for r in range(1, mr + 1))
        parts.append(f"<section><h2>{esc(s['name'])}</h2><table><thead>{head}</thead><tbody>{body}</tbody></table></section>")
    css = """@page{size:A4 landscape;margin:12mm}body{font:9pt Arial,'DejaVu Sans',sans-serif;color:#172033}h2{font-size:12pt;margin:0 0 4mm}section{page-break-after:always}section:last-child{page-break-after:auto}
table{border-collapse:collapse}th,td{border:1px solid #c9d2e3;padding:2px 6px;min-width:18mm;height:5mm}th{background:#eef2fa;font-weight:600;color:#4a5670;text-align:center}td.n{text-align:right}th.r{min-width:8mm}.e{color:#7d8aa6}"""
    return _pdf_from_html(f"<!doctype html><meta charset='utf-8'><title>{esc(title)}</title><style>{css}</style><body>{''.join(parts)}")


def _colname(i: int) -> str:
    s = ""
    while i > 0: i, m = divmod(i - 1, 26); s = chr(65 + m) + s
    return s


def _td(v: str) -> str:
    try: float(v.replace(",", "")); return f"<td class=n>{esc(v)}</td>"
    except ValueError: return f"<td>{esc(v)}</td>"


# ------------------------------------------------------------------ PowerPresentation

def _deck(content: str) -> dict:
    try:
        v = json.loads(content)
        if isinstance(v, dict) and isinstance(v.get("slides"), list) and v["slides"]:
            th = v.get("theme") if v.get("theme") in THEMES else "light"
            sl = []
            for s in v["slides"][:200]:
                if not isinstance(s, dict): continue
                shapes = []
                for q in (s.get("shapes") or [])[:60]:
                    try: shapes.append({"id": str(q["id"]), "x": float(q["x"]), "y": float(q["y"]), "w": float(q["w"])})
                    except Exception: continue
                sl.append({"layout": s.get("layout") if s.get("layout") in ("title", "content", "two", "section", "blank") else "content", "title": str(s.get("title") or ""),
                           "body": [str(x) for x in (s.get("body") or []) if str(x).strip()], "body2": [str(x) for x in (s.get("body2") or []) if str(x).strip()],
                           "notes": str(s.get("notes") or ""), "bg": s.get("bg") if re.match(r"^#[0-9a-fA-F]{6}$", str(s.get("bg") or "")) else None, "shapes": shapes})
            if sl: return {"theme": th, "slides": sl}
    except Exception: pass
    return {"theme": "light", "slides": [{"layout": "content", "title": "", "body": [], "body2": [], "notes": "", "bg": None, "shapes": []}]}


def deck_to_pdf(content: str, shapes: dict | None, title: str = "") -> bytes:
    """One 16:9 page per slide, laid out exactly as the editor draws it (960 by 540), with the real text kept as text."""
    d = _deck(content); bg0, fg, ac = THEMES[d["theme"]]; shapes = shapes or {}
    pages = []
    for s in d["slides"]:
        li = lambda a: "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in a) + "</ul>"
        inner = ""
        if s["layout"] != "blank": inner += f"<h2>{esc(s['title'])}</h2>"
        if s["layout"] == "two": inner += f"<div class=cols><div>{li(s['body'])}</div><div>{li(s['body2'])}</div></div>"
        elif s["layout"] != "blank": inner += li(s["body"])
        pics = ""
        for q in s["shapes"]:
            sh = shapes.get(q["id"]) or {}
            png = _png(sh.get("png"))
            if not png: continue
            try: ratio = float(sh["h"]) / float(sh["w"])
            except Exception: ratio = 0.6
            pics += f"<img class=sp src='data:image/png;base64,{base64.b64encode(png).decode()}' style='left:{q['x']:.1f}px;top:{q['y']:.1f}px;width:{q['w']:.1f}px;height:{q['w'] * ratio:.1f}px'>"
        pages.append(f"<div class='sl {s['layout']}' style='background:{s['bg'] or bg0};color:{fg};--ac:{ac}'><div class=in>{inner}</div>{pics}</div>")
    css = """@page{size:960px 540px;margin:0}body{margin:0;font-family:Arial,'DejaVu Sans',sans-serif}
.sl{position:relative;width:960px;height:540px;overflow:hidden;page-break-after:always}.sl:last-child{page-break-after:auto}
.in{position:absolute;left:0;top:0;width:960px;height:540px;box-sizing:border-box;padding:56px 64px}
h2{font-size:48px;line-height:1.15;margin:0 0 28px;color:var(--ac);overflow-wrap:anywhere}ul{margin:0;padding-left:34px;font-size:30px;line-height:1.4}li{margin:6px 0;overflow-wrap:anywhere}
.title .in{display:flex;flex-direction:column;justify-content:center;text-align:center}.title h2{font-size:68px}.title ul{list-style:none;padding:0;font-size:32px;opacity:.8}
.section .in{display:flex;flex-direction:column;justify-content:center}.section h2{font-size:64px;border-left:10px solid var(--ac);padding-left:24px}.section ul{list-style:none;opacity:.75}
.cols{display:flex;gap:36px}.cols>div{flex:1}.sp{position:absolute}"""
    return _pdf_from_html(f"<!doctype html><meta charset='utf-8'><title>{esc(title)}</title><style>{css}</style><body>{''.join(pages)}")


def deck_to_pptx(content: str, shapes: dict | None, title: str = "") -> bytes:
    """Editable PowerPoint: real text boxes with bullets, the same colours and positions, shapes as pictures, speaker notes kept."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Pt
    from lxml import etree

    d = _deck(content); bg0, fg, ac = THEMES[d["theme"]]; shapes = shapes or {}
    prs = Presentation(); prs.slide_width = Emu(12192000); prs.slide_height = Emu(6858000)
    prs.core_properties.title = title[:200]
    K = 12700; rgb = lambda h: RGBColor.from_string(h.lstrip("#").upper())

    def tbox(sl, x, y, w, h, anchor=MSO_ANCHOR.TOP):
        tb = sl.shapes.add_textbox(Emu(int(x * K)), Emu(int(y * K)), Emu(int(w * K)), Emu(int(h * K)))
        tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        return tf

    def heading(sl, text, x, y, w, size, align=PP_ALIGN.LEFT, h=None):
        tf = tbox(sl, x, y, w, h or size * 1.3)
        p = tf.paragraphs[0]; p.alignment = align; r = p.add_run(); r.text = text
        r.font.size = Pt(size * 0.75); r.font.bold = True; r.font.color.rgb = rgb(ac); r.font.name = "Arial"

    def bullets(sl, lines, x, y, w, h, size, bullet=True, align=PP_ALIGN.LEFT, alpha=False):
        tf = tbox(sl, x, y, w, h)
        for i, t in enumerate(lines or [""]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align; p.space_after = Pt(size * 0.75 * 0.3)
            r = p.add_run(); r.text = t; r.font.size = Pt(size * 0.75); r.font.name = "Arial"
            r.font.color.rgb = rgb(fg)
            pPr = p._p.get_or_add_pPr()
            if bullet:
                pPr.set("marL", str(int(34 * K))); pPr.set("indent", str(int(-34 * K)))
                bu = etree.SubElement(pPr, qn("a:buChar")); bu.set("char", "•")
            else:
                etree.SubElement(pPr, qn("a:buNone"))

    for s in d["slides"]:
        sl = prs.slides.add_slide(prs.slide_layouts[6])
        fill = sl.background.fill; fill.solid(); fill.fore_color.rgb = rgb(s["bg"] or bg0)
        lay = s["layout"]
        if lay == "title":
            if s["title"]: heading(sl, s["title"], 64, 150, 832, 68, PP_ALIGN.CENTER, 90)
            bullets(sl, s["body"], 64, 260, 832, 220, 32, False, PP_ALIGN.CENTER)
        elif lay == "section":
            if s["title"]:
                bar = sl.shapes.add_shape(1, Emu(64 * K), Emu(200 * K), Emu(10 * K), Emu(80 * K)); bar.fill.solid(); bar.fill.fore_color.rgb = rgb(ac); bar.line.fill.background()
                heading(sl, s["title"], 98, 200, 800, 64, h=80)
            bullets(sl, s["body"], 98, 300, 800, 200, 30, False)
        elif lay == "two":
            if s["title"]: heading(sl, s["title"], 64, 56, 832, 48, h=64)
            bullets(sl, s["body"], 64, 150, 398, 340, 30)
            bullets(sl, s["body2"], 498, 150, 398, 340, 30)
        elif lay == "content":
            if s["title"]: heading(sl, s["title"], 64, 56, 832, 48, h=64)
            bullets(sl, s["body"], 64, 150, 832, 340, 30)
        for q in s["shapes"]:
            png = _png((shapes.get(q["id"]) or {}).get("png"))
            if not png: continue
            try: ratio = float(shapes[q["id"]]["h"]) / float(shapes[q["id"]]["w"])
            except Exception: ratio = 0.6
            sl.shapes.add_picture(io.BytesIO(png), Emu(int(q["x"] * K)), Emu(int(q["y"] * K)), Emu(int(q["w"] * K)), Emu(int(q["w"] * ratio * K)))
        if s["notes"]: sl.notes_slide.notes_text_frame.text = s["notes"]
    bio = io.BytesIO(); prs.save(bio); return bio.getvalue()


# ------------------------------------------------------------------ PDF to WordPerfect

def _hex(nc, dark_is_black: bool = False) -> str:
    """A PDF colour (grey, RGB or CMYK as 0..1 numbers) as #rrggbb, or "" when it cannot be read."""
    try:
        if isinstance(nc, (int, float)): nc = (nc,)
        if not isinstance(nc, (tuple, list)): return ""
        v = [float(x) for x in nc]
        if len(v) == 1: r = g = b = v[0]
        elif len(v) == 3: r, g, b = v
        elif len(v) == 4: c, m, y, k = v; r, g, b = (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
        else: return ""
        r, g, b = (max(0.0, min(1.0, x)) for x in (r, g, b))
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
    except Exception: return ""


_FAMILY = (("liberationserif", "'Times New Roman',Times,serif"), ("liberationsans", "Arial,Helvetica,sans-serif"), ("liberationmono", "'Courier New',monospace"), ("dejavuserif", "Georgia,serif"), ("dejavusans", "Verdana,sans-serif"), ("times", "'Times New Roman',Times,serif"), ("georgia", "Georgia,serif"), ("garamond", "Garamond,serif"), ("palatino", "'Palatino Linotype',serif"), ("cambria", "Cambria,serif"),
           ("courier", "'Courier New',monospace"), ("consolas", "Consolas,monospace"), ("mono", "'Courier New',monospace"), ("calibri", "Calibri,Arial,sans-serif"),
           ("helvetica", "Arial,Helvetica,sans-serif"), ("arial", "Arial,Helvetica,sans-serif"), ("verdana", "Verdana,sans-serif"), ("tahoma", "Tahoma,sans-serif"),
           ("segoe", "'Segoe UI',sans-serif"), ("trebuchet", "'Trebuchet MS',sans-serif"), ("roboto", "Roboto,Arial,sans-serif"), ("open", "'Open Sans',Arial,sans-serif"))

def _bg_behind(page_img, el) -> str:
    """The fill colour behind a block of text, read from the rendered page just outside the text (so a coloured bar or shaded cell keeps its colour)."""
    if not page_img: return ""
    img, ph, k = page_img
    pts = []
    w, h = el.x1 - el.x0, el.y1 - el.y0
    for x, y in ((el.x0 - 1.2, el.y0 + h * 0.5), (el.x1 + 1.2, el.y0 + h * 0.5), (el.x0 + w * 0.25, el.y1 + 1.2), (el.x0 + w * 0.75, el.y1 + 1.2), (el.x0 + w * 0.25, el.y0 - 1.2), (el.x0 + w * 0.75, el.y0 - 1.2)):
        px, py = int(x * k), int((ph - y) * k)
        if 0 <= px < img.width and 0 <= py < img.height: pts.append(img.getpixel((px, py))[:3])
    if len(pts) < 3: return ""
    best = Counter(pts).most_common(1)[0]
    if best[1] < 3: return ""
    r, g, b = best[0]
    return "" if min(r, g, b) >= 248 else "#%02x%02x%02x" % (r, g, b)


def _family(fontname: str) -> str:
    f = re.sub(r"[\s\-_]", "", re.sub(r"^[A-Z]{6}\+", "", fontname or "")).lower()
    for k, v in _FAMILY:
        if k in f: return v
    return "Arial,Helvetica,sans-serif" if f else ""


def pdf_to_wp_exact(data: bytes) -> dict:
    """Each PDF page rebuilt exactly as it looks: the page's graphics (backgrounds, shapes, pictures, gradients, QR codes) are drawn as the page background with the
    text taken out, and the real text is laid back on top in the same place, font, size and colour. The text stays editable."""
    import pypdfium2 as pdfium
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine
    if not data[:5] == b"%PDF-": raise ConvertError("That file is not a PDF.")
    try: pdf = pdfium.PdfDocument(data)
    except Exception: raise ConvertError("The PDF could not be opened. It may be damaged or password protected.")
    n_pages = len(pdf); out, warn, texty = [], [], 0

    def runs(lines, size, fam):
        spans = []
        for ln in lines:
            for ch in ln:
                if not isinstance(ch, LTChar): continue
                t = ch.get_text(); fn = (ch.fontname or "").lower()
                col = _hex(getattr(ch.graphicstate, "ncolor", None))
                if col and max(int(col[i:i + 2], 16) for i in (1, 3, 5)) <= 40: col = ""
                key = ("bold" in fn or "black" in fn or "heavy" in fn, "italic" in fn or "oblique" in fn, col, round(ch.size * 2) / 2, _family(ch.fontname))
                if t == "\n": continue
                if spans and spans[-1][0] == key: spans[-1][1].append(t)
                else: spans.append((key, [t]))
        html = ""
        for (b, i, c, sz, fam2), chars in spans:
            t = esc("".join(chars)).replace("  ", "&nbsp; ")
            st = []
            if c: st.append(f"color:{c}")
            if abs(sz - size) >= 0.75: st.append(f"font-size:{sz:g}pt")
            if fam2 and fam2 != fam: st.append(f"font-family:{fam2}")
            if st: t = f'<span style="{";".join(st)}">{t}</span>'
            if b: t = f"<b>{t}</b>"
            if i: t = f"<i>{t}</i>"
            html += t
        return html

    layouts = list(extract_pages(io.BytesIO(data), laparams=LAParams(line_margin=0.3, boxes_flow=0.5, char_margin=2.0)))
    for pi in range(n_pages):
        lay = layouts[pi] if pi < len(layouts) else None
        page = pdf[pi]
        pw, ph = page.get_size()
        try:
            for o in list(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_TEXT])): page.remove_obj(o)
            page.gen_content()
        except Exception: warn.append(f"Page {pi + 1}: the page text could not be separated from its graphics.")
        img = page.render(scale=1.6).to_pil().convert("RGB")
        bio = io.BytesIO(); img.save(bio, "PNG", optimize=True); mime, blob = "png", bio.getvalue()
        if len(blob) > 2_500_000:
            bio = io.BytesIO(); img.save(bio, "JPEG", quality=88, optimize=True); mime, blob = "jpeg", bio.getvalue()
        boxes = []
        for el in (lay or []):
            if isinstance(el, LTTextContainer):
                for ln in el:
                    if isinstance(ln, LTTextLine) and ln.get_text().strip(): boxes.append(ln)
        texty += len(boxes)
        items = []
        for ln in boxes:
            sz, fm = Counter(), Counter()
            for ch in ln:
                if isinstance(ch, LTChar) and ch.get_text().strip(): sz[round(ch.size * 2) / 2] += 1; fm[_family(ch.fontname)] += 1
            size = sz.most_common(1)[0][0] if sz else 11; fam = fm.most_common(1)[0][0] if fm else ""
            top = ph - ln.y1; h = max(ln.y1 - ln.y0, size)
            st = f"position:absolute;left:{ln.x0:.1f}pt;top:{top:.1f}pt;width:{max(ln.x1 - ln.x0, 4):.1f}pt;white-space:nowrap;font-size:{size:g}pt;line-height:{h:.1f}pt" + (f";font-family:{fam}" if fam else "")
            items.append(f'<div style="{st}">{runs([ln], size, fam)}</div>')
        out.append(f'<div style="position:relative;width:{pw:.1f}pt;height:{ph:.1f}pt;background-image:url(data:image/{mime};base64,{base64.b64encode(blob).decode()});background-size:100% 100%;background-repeat:no-repeat;overflow:hidden;margin:0 0 14pt 0">' + "".join(items) + "</div>")
    if not texty: warn.append("This PDF has no selectable text (a scan), so its pages are shown as pictures. Scanned pages cannot be turned into editable text here.")
    return {"html": "".join(out) or "<p><br></p>", "pages": n_pages, "notes": warn}


def pdf_to_wp(data: bytes, exact: bool = False) -> dict:
    if exact: return pdf_to_wp_exact(data)
    return _pdf_to_wp_flow(data)


def _pdf_to_wp_flow(data: bytes) -> dict:
    """Rebuild a PDF as an editable WordPerfect document: headings (by type size), paragraphs, bold / italic, text colour, bullet lists, centred lines and the
    pictures inside the PDF. A PDF is a fixed page, so the page breaks and exact positions are not kept, and tables become plain paragraphs. A page with no
    selectable text (a scan) is placed as a picture so nothing is lost."""
    import pypdfium2 as pdfium
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar, LTImage, LTTextContainer, LTFigure, LTTextLine, LTRect, LTCurve
    if not data[:5] == b"%PDF-": raise ConvertError("That file is not a PDF.")
    try: pdf = pdfium.PdfDocument(data)
    except Exception: raise ConvertError("The PDF could not be opened. It may be damaged or password protected.")
    n_pages = len(pdf)
    pages = []
    sizes = Counter()
    for pi, layout in enumerate(extract_pages(io.BytesIO(data), laparams=LAParams(line_margin=0.3, boxes_flow=0.5, char_margin=1.0))):
        boxes, fills = [], []
        for el in layout:
            if isinstance(el, LTTextContainer):
                lines = [l for l in el if isinstance(l, LTTextLine)]
                if not lines: continue
                boxes.append((el, lines))
                for ln in lines:
                    for ch in ln:
                        if isinstance(ch, LTChar) and ch.get_text().strip(): sizes[round(ch.size)] += 1
        pages.append((layout.width, layout.height, boxes, fills))
    body = (sizes.most_common(1)[0][0] if sizes else 11) or 11
    out, warn, scans = [], [], 0

    def runs_html(lines, headline=False, base=None) -> str:
        """The text of some lines with its real look: bold, italic, colour, size and font (a span only where it differs from the block's own)."""
        bsize, bfam = base or (None, "")
        spans = []
        for li, ln in enumerate(lines):
            for ch in ln:
                if not isinstance(ch, LTChar): continue
                t = ch.get_text(); fn = (ch.fontname or "").lower()
                col = _hex(getattr(ch.graphicstate, "ncolor", None))
                if col and max(int(col[i:i + 2], 16) for i in (1, 3, 5)) <= 40: col = ""                  # black text is the default
                key = ("bold" in fn or "black" in fn or "heavy" in fn or "semibold" in fn, "italic" in fn or "oblique" in fn, col, round(ch.size * 2) / 2, _family(ch.fontname))
                if t in ("\n",): t = " "
                if spans and spans[-1][0] == key: spans[-1][1].append(t)
                else: spans.append((key, [t]))
            if spans and not spans[-1][1][-1].endswith((" ", "-")): spans[-1][1].append(" ")
            elif spans and spans[-1][1][-1] == "-" and li < len(lines) - 1: spans[-1][1].pop()      # a word split across two lines
        html = ""
        for (b, i, c, sz, fam), chars in spans:
            t = esc("".join(chars))
            if not t.strip(): html += t; continue
            st = []
            if c: st.append(f"color:{c}")
            if bsize is not None and abs(sz - bsize) >= 0.75: st.append(f"font-size:{sz:g}pt")
            if fam and fam != bfam: st.append(f"font-family:{fam}")
            if st: t = f'<span style="{";".join(st)}">{t}</span>'
            if b: t = f"<b>{t}</b>"
            if i: t = f"<i>{t}</i>"
            html += t
        return html.strip()

    def block_base(lines):
        sz, fm = Counter(), Counter()
        for ln in lines:
            for ch in ln:
                if isinstance(ch, LTChar) and ch.get_text().strip(): sz[round(ch.size * 2) / 2] += 1; fm[_family(ch.fontname)] += 1
        return (sz.most_common(1)[0][0] if sz else body, fm.most_common(1)[0][0] if fm else "")

    def box_style(el, lines, pw, fills, centred=False, tag="p", left0=0):
        size, fam = block_base(lines)
        st = [f"font-size:{size:g}pt"] + ([f"font-family:{fam}"] if fam else [])
        if centred: st.append("text-align:center")
        elif el.x1 > pw * 0.9 and el.x0 > pw * 0.55: st.append("text-align:right")
        elif el.x0 - left0 > 14 and tag == "p": st.append(f"margin-left:{int(el.x0 - left0)}pt")
        bg = _bg_behind(fills, el)
        if bg: st.append(f"background-color:{bg}")
        return ";".join(st), (size, fam)

    for pi, (pw, ph, boxes, fills) in enumerate(pages):
        pstart = len(out)
        left0 = min([el.x0 for el, _l in boxes] or [0])
        pagebg, fills = "", None
        try:
            pil_ = pdf[pi].render(scale=1.0).to_pil().convert("RGB"); fills = (pil_, ph, pil_.width / pw)
            cx_ = pil_.getpixel((min(pil_.width - 1, 4), min(pil_.height - 1, 4)))
            if min(cx_) < 248 and pil_.getpixel((pil_.width - 5, pil_.height - 5)) == cx_: pagebg = "#%02x%02x%02x" % cx_
        except Exception: pass
        items = []
        for el, lines in boxes:
            sz = Counter(round(ch.size) for ln in lines for ch in ln if isinstance(ch, LTChar) and ch.get_text().strip())
            size = sz.most_common(1)[0][0] if sz else body
            txt = "".join(ch.get_text() for ln in lines for ch in ln if isinstance(ch, LTChar)).strip()
            if not txt: continue
            items.append((-el.y1, el, lines, size, txt))
        images = []
        try:
            page = pdf[pi]
            for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]):
                try:
                    l, b, r, t = obj.get_pos(); pil = obj.get_bitmap(render=True).to_pil()
                    if pil.width < 24 or pil.height < 24: continue
                    bio = io.BytesIO(); pil.convert("RGB").save(bio, "PNG", optimize=True)
                    if len(bio.getvalue()) > 2_500_000: continue
                    images.append((-t, f'<p><img src="data:image/png;base64,{base64.b64encode(bio.getvalue()).decode()}" width="{int(min(700, max(40, (r - l) * 1.3)))}" alt="Picture from the PDF"></p>'))
                except Exception: continue
        except Exception: pass
        if not items and not images:
            if scans < 10:
                try:
                    bio = io.BytesIO(); pdf[pi].render(scale=1.4).to_pil().convert("RGB").save(bio, "PNG", optimize=True)
                    out.append(f'<p><img src="data:image/png;base64,{base64.b64encode(bio.getvalue()).decode()}" width="700" alt="Page {pi + 1} as a picture"></p>'); scans += 1
                except Exception: pass
            else: warn.append(f"Page {pi + 1} has no selectable text and was skipped.")
            if pi < n_pages - 1: out.append("<hr>")
            continue
        MARK = re.compile(r"^([•●▪◦‣\-–·]|\d{1,3}[.)])$")
        BUL = re.compile(r"^[•●▪◦‣\-–·]\s+")
        ent = sorted([(round(el.y1), el.x0, "t", (el, lines, size, txt)) for k, el, lines, size, txt in items] + [(round(-k), 0, "i", h) for k, h in images], key=lambda z: (-z[0], z[1]))
        # group boxes that sit on the same line into rows (a table row, or a list marker and its text)
        rows, cur = [], []
        for e in ent:
            if cur and e[2] == "t" and cur[-1][2] == "t" and abs(cur[-1][0] - e[0]) <= 4: cur.append(e)
            else:
                if cur: rows.append(cur)
                cur = [e]
        if cur: rows.append(cur)
        i2, table = 0, []
        def flush_table():
            nonlocal table
            if table:
                out.append('<table style="border-collapse:collapse;width:100%"><tbody>' + "".join("<tr>" + "".join(f'<td style="{c[1]}">{c[0]}</td>' if c[1] else f"<td>{c[0]}</td>" for c in r) + "</tr>" for r in table) + "</tbody></table><p><br></p>"); table = []
        list_kind = None
        def close_list():
            nonlocal list_kind
            if list_kind: out.append(f"</{list_kind}>"); list_kind = None
        for row in rows:
            if row[0][2] == "i":
                flush_table(); close_list(); out.append(row[0][3]); continue
            cells = [r[3] for r in row]
            if len(cells) >= 2 and MARK.match(cells[0][3]):                      # a list marker followed by its text
                kind_ = "ul" if BUL.match(cells[0][3] + " ") else "ol"
                flush_table()
                if list_kind != kind_: close_list(); out.append(f"<{kind_}>"); list_kind = kind_
                bs = box_style(cells[1][0], cells[1][1], pw, fills, left0=left0, tag="li")
                out.append(f'<li style="{bs[0]}">' + " ".join(runs_html(c[1], base=bs[1]) for c in cells[1:]) + "</li>"); continue
            if len(cells) >= 2:                                                   # several boxes on one line: a table row
                close_list(); row_ = []
                for c in cells:
                    bs = box_style(c[0], c[1], pw, fills, tag="td"); bg = re.search(r"background-color:[^;]+", bs[0])
                    row_.append((runs_html(c[1], base=bs[1]), bg.group(0) if bg else ""))
                table.append(row_); continue
            flush_table()
            el, lines, size, txt = cells[0]
            if BUL.match(txt):
                if list_kind != "ul": close_list(); out.append("<ul>"); list_kind = "ul"
                bs = box_style(el, lines, pw, fills, left0=left0, tag="li")
                out.append(f'<li style="{bs[0]}">' + re.sub(r"^[•●▪◦‣\-–·]\s*", "", runs_html(lines, base=bs[1])) + "</li>"); continue
            close_list()
            tag = "h1" if size >= body * 1.7 else "h2" if size >= body * 1.4 else "h3" if size >= body * 1.18 and len(txt) < 140 else "p"
            cx = (el.x0 + el.x1) / 2
            centred = abs(cx - pw / 2) < pw * 0.03 and el.x0 > pw * 0.12 and (el.x1 - el.x0) < pw * 0.7
            stl, bs = box_style(el, lines, pw, fills, centred=centred, tag=tag, left0=left0)
            if tag != "p" and not any(isinstance(ch, LTChar) and ch.get_text().strip() and any(w in (ch.fontname or "").lower() for w in ("bold", "black", "heavy")) for ln in lines for ch in ln): stl += ";font-weight:normal"
            out.append(f'<{tag} style="{stl}">{runs_html(lines, base=bs)}</{tag}>')
        flush_table(); close_list()
        if pagebg: out.insert(pstart, f'<div style="background-color:{pagebg}">'); out.append("</div>")
        if pi < n_pages - 1: out.append("<hr>")
    html = "".join(out) or "<p><br></p>"
    if not sizes: warn.append("This PDF has no selectable text, so its pages were placed as pictures. Scanned pages cannot be turned into editable text here.")
    return {"html": html, "pages": n_pages, "notes": warn}


# ------------------------------------------------------------------ Microsoft files into iSift (Word, Excel, PowerPoint)

def _w_hex(v) -> str:
    return "#" + str(v).lower() if v and re.match(r"^[0-9A-Fa-f]{6}$", str(v)) else ""


def docx_to_wp(data: bytes) -> dict:
    """A Word file as an editable WordPerfect document: headings, bold / italic / underline / strike, text colour, highlight, font and size, alignment, indents,
    bullet and numbered lists, links, tables (with shaded cells and merged cells) and pictures."""
    from docx import Document
    from docx.oxml.ns import qn
    try: doc = Document(io.BytesIO(data))
    except Exception: raise ConvertError("That file could not be opened as a Word document. It may be damaged, password protected or an old .doc file (save it as .docx first).")
    notes = []
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    numfmt: dict = {}
    try:
        numpart = doc.part.numbering_part.element
        absf = {}
        for an in numpart.findall(qn("w:abstractNum")):
            lv = an.find(qn("w:lvl")); f = lv.find(qn("w:numFmt")) if lv is not None else None
            absf[an.get(qn("w:abstractNumId"))] = f.get(qn("w:val")) if f is not None else "bullet"
        for n in numpart.findall(qn("w:num")):
            ab = n.find(qn("w:abstractNumId")); numfmt[n.get(qn("w:numId"))] = absf.get(ab.get(qn("w:val")) if ab is not None else "", "bullet")
    except Exception: pass
    pics = 0

    def run_style(r) -> str:
        st = []
        f = r.font
        try:
            if f.color is not None and f.color.type is not None and f.color.rgb is not None and str(f.color.rgb).upper() not in ("000000",): st.append(f"color:#{str(f.color.rgb).lower()}")
        except Exception: pass
        if f.size: st.append(f"font-size:{f.size.pt:g}pt")
        if f.name: st.append(f"font-family:'{re.sub(chr(39), '', f.name)}'")
        rpr = r._r.rPr
        if rpr is not None:
            sh = rpr.find(qn("w:shd")); hl = rpr.find(qn("w:highlight"))
            if sh is not None and _w_hex(sh.get(qn("w:fill"))): st.append(f"background-color:{_w_hex(sh.get(qn('w:fill')))}")
            elif hl is not None:
                hv = {"yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff", "magenta": "#ff00ff", "blue": "#0000ff", "red": "#ff0000", "lightGray": "#d3d3d3", "darkYellow": "#808000"}.get(hl.get(qn("w:val")))
                if hv: st.append(f"background-color:{hv}")
        return ";".join(st)

    def run_html(r) -> str:
        nonlocal pics
        out = ""
        for ch in r._r:
            tag = ch.tag
            if tag == W + "t": out += esc(ch.text or "")
            elif tag == W + "tab": out += "&emsp;"
            elif tag in (W + "br", W + "cr"): out += "<br>"
            elif tag == W + "drawing":
                for blip in ch.iter(A + "blip"):
                    rid = blip.get(R + "embed")
                    try:
                        part = r.part.related_parts[rid]; mime = part.content_type
                        if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                            from PIL import Image
                            bio = io.BytesIO(); Image.open(io.BytesIO(part.blob)).convert("RGBA").save(bio, "PNG"); blob, mime = bio.getvalue(), "image/png"
                        else: blob = part.blob
                        ext = ch.find(".//" + "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
                        wpx = int(int(ext.get("cx")) / 9525) if ext is not None else 0
                        out += f'<img src="data:{mime};base64,{base64.b64encode(blob).decode()}"' + (f' width="{min(wpx, 1000)}"' if wpx else "") + ' alt="Picture">'; pics += 1
                    except Exception: notes.append("A picture could not be brought in.")
        if not out: return ""
        f = r
        st = run_style(r)
        if st: out = f'<span style="{st}">{out}</span>'
        if r.bold: out = f"<b>{out}</b>"
        if r.italic: out = f"<i>{out}</i>"
        if r.underline: out = f"<u>{out}</u>"
        if r.font.strike: out = f"<s>{out}</s>"
        if r.font.superscript: out = f"<sup>{out}</sup>"
        elif r.font.subscript: out = f"<sub>{out}</sub>"
        return out

    def para_inner(p) -> str:
        from docx.text.run import Run
        html = ""
        for ch in p._p:
            if ch.tag == W + "r": html += run_html(Run(ch, p))
            elif ch.tag == W + "hyperlink":
                inner = "".join(run_html(Run(x, p)) for x in ch.findall(W + "r"))
                rid = ch.get(R + "id")
                try: url = p.part.rels[rid].target_ref if rid else ""
                except Exception: url = ""
                html += f'<a href="{esc(url)}">{inner}</a>' if re.match(r"^(https?://|mailto:)", url or "", re.I) else inner
        return html

    def para_css(p) -> str:
        st = []
        pf = p.paragraph_format
        al = {0: "left", 1: "center", 2: "right", 3: "justify"}.get(p.alignment if p.alignment is None else int(p.alignment))
        if al and al != "left": st.append(f"text-align:{al}")
        if pf.left_indent: st.append(f"margin-left:{pf.left_indent.pt:g}pt")
        if pf.first_line_indent and pf.first_line_indent.pt > 0: st.append(f"text-indent:{pf.first_line_indent.pt:g}pt")
        if pf.space_after is not None: st.append(f"margin-bottom:{pf.space_after.pt:g}pt")
        if pf.space_before: st.append(f"margin-top:{pf.space_before.pt:g}pt")
        ppr = p._p.pPr
        if ppr is not None:
            sh = ppr.find(qn("w:shd"))
            if sh is not None and _w_hex(sh.get(qn("w:fill"))): st.append(f"background-color:{_w_hex(sh.get(qn('w:fill')))}")
        return ";".join(st)

    def list_kind(p):
        ppr = p._p.pPr
        if ppr is not None and ppr.numPr is not None and ppr.numPr.numId is not None:
            f = numfmt.get(str(ppr.numPr.numId.val), "bullet")
            return "ol" if f not in ("bullet", "none") else "ul"
        sn = (p.style.name if p.style is not None else "") or ""
        if sn.lower().startswith("list number"): return "ol"
        if sn.lower().startswith("list"): return "ul"
        return None

    out, cur = [], None
    def close():
        nonlocal cur
        if cur: out.append(f"</{cur}>"); cur = None

    def table_html(t) -> str:
        rows = []
        for r in t.rows:
            seen, cells = set(), []
            for c in r.cells:
                if id(c._tc) in seen: continue
                seen.add(id(c._tc))
                tcpr = c._tc.tcPr; span = 1; bg = ""; vm = None
                if tcpr is not None:
                    gs = tcpr.find(qn("w:gridSpan")); span = int(gs.get(qn("w:val"))) if gs is not None else 1
                    sh = tcpr.find(qn("w:shd")); bg = _w_hex(sh.get(qn("w:fill"))) if sh is not None else ""
                    vme = tcpr.find(qn("w:vMerge")); vm = (vme.get(qn("w:val")) or "continue") if vme is not None else None
                if vm == "continue": continue
                inner = "".join(f"<p style=\"{para_css(p)}\">{para_inner(p) or '<br>'}</p>" for p in c.paragraphs)
                cells.append(f'<td{f" colspan={span}" if span > 1 else ""} style="border:1px solid #888888;padding:4px 8px' + (f";background-color:{bg}" if bg else "") + f'">{inner}</td>')
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return '<table style="border-collapse:collapse;width:100%"><tbody>' + "".join(rows) + "</tbody></table><p><br></p>"

    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for el in doc.element.body.iterchildren():
        if el.tag == W + "p":
            p = Paragraph(el, doc); inner = para_inner(p)
            lk = list_kind(p)
            if lk:
                if cur != lk: close(); out.append(f"<{lk}>"); cur = lk
                out.append(f'<li style="{para_css(p)}">{inner}</li>'); continue
            close()
            sn = ((p.style.name if p.style is not None else "") or "").lower()
            m = re.match(r"^heading (\d)", sn); tag = f"h{min(int(m.group(1)), 3)}" if m else "h1" if sn == "title" else "h2" if sn == "subtitle" else "p"
            if not inner.strip(): out.append("<p><br></p>"); continue
            out.append(f'<{tag} style="{para_css(p)}">{inner}</{tag}>')
        elif el.tag == W + "tbl":
            close(); out.append(table_html(Table(el, doc)))
    close()
    if not any(s.header.is_linked_to_previous is False for s in doc.sections[:1]) : pass
    return {"html": "".join(out) or "<p><br></p>", "notes": list(dict.fromkeys(notes)), "pictures": pics}


def xlsx_to_book(data: bytes) -> dict:
    """An Excel file as a SpreadTable workbook: every sheet, values and live formulas (up to 1000 rows by 52 columns per sheet)."""
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    try: wb = load_workbook(io.BytesIO(data), data_only=False)
    except Exception: raise ConvertError("That file could not be opened as an Excel workbook. It may be damaged, password protected or an old .xls file (save it as .xlsx first).")
    try: wbv = load_workbook(io.BytesIO(data), data_only=True)
    except Exception: wbv = None
    sheets, notes = [], []
    for ws in wb.worksheets[:50]:
        cells, mr, mc = {}, 0, 0
        wv = wbv[ws.title] if wbv is not None and ws.title in wbv.sheetnames else None
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 1000), max_col=min(ws.max_column, 52)):
            for c in row:
                v = c.value
                if v is None or v == "": continue
                if isinstance(v, str) and v.startswith("="): txt = v
                elif isinstance(v, bool): txt = "TRUE" if v else "FALSE"
                elif isinstance(v, (int, float)): txt = repr(v) if isinstance(v, float) and not float(v).is_integer() else str(int(v)) if float(v).is_integer() else str(v)
                elif hasattr(v, "isoformat"): txt = v.isoformat(sep=" ") if hasattr(v, "hour") else v.isoformat()
                else: txt = str(v)
                cells[f"{get_column_letter(c.column)}{c.row}"] = txt; mr = max(mr, c.row); mc = max(mc, c.column)
        if ws.max_row > 1000 or ws.max_column > 52: notes.append(f"Sheet “{ws.title}” is larger than 1000 rows by 52 columns; the rest was not brought in.")
        sheets.append({"name": ws.title[:40], "cells": cells, "rows": min(1000, max(20, mr + 10)), "cols": min(52, max(6, mc + 2))})
    if any(any(isinstance(c.value, str) and c.value.startswith("=") for c in row) for ws in wb.worksheets for row in ws.iter_rows(max_row=200)):
        notes.append("Formulas are kept and recalculated in iSift. Cell colours, fonts and charts are not part of SpreadTable, so they are not brought in.")
    else: notes.append("Cell colours, fonts and charts are not part of SpreadTable, so they are not brought in.")
    return {"content": json.dumps({"v": 1, "sheets": sheets or [{"name": "Sheet1", "cells": {}, "rows": 100, "cols": 26}]}), "notes": notes}


def pptx_to_deck(data: bytes) -> dict:
    """A PowerPoint file as a PowerPresentation deck: each slide's title, bullet text, background colour and speaker notes."""
    from pptx import Presentation
    try: prs = Presentation(io.BytesIO(data))
    except Exception: raise ConvertError("That file could not be opened as a PowerPoint presentation. It may be damaged, password protected or an old .ppt file (save it as .pptx first).")
    slides, pic_slides = [], 0
    for sl in list(prs.slides)[:300]:
        title, bodies, picture = "", [], False
        shapes = sorted(sl.shapes, key=lambda x: (x.top or 0, x.left or 0))
        for sh in shapes:
            if sh.shape_type == 13: picture = True; continue
            if not getattr(sh, "has_text_frame", False) or not sh.text_frame.text.strip(): continue
            lines = [p.text.strip() for p in sh.text_frame.paragraphs if p.text.strip()]
            is_title = False
            try: is_title = sh.is_placeholder and sh.placeholder_format.type in (1, 3)           # TITLE, CENTER_TITLE
            except Exception: pass
            if is_title and not title: title = " ".join(lines)
            else: bodies.append(lines)
        if not title and bodies: title = bodies[0][0]; bodies[0] = bodies[0][1:]; bodies = [b for b in bodies if b]
        bg = None
        try:
            f = sl.background.fill
            if f.type == 1: bg = "#" + str(f.fore_color.rgb).lower()
        except Exception: pass
        try: notes = sl.notes_slide.notes_text_frame.text if sl.has_notes_slide else ""
        except Exception: notes = ""
        layout = "title" if not slides and title and len(bodies) <= 1 and sum(len(b) for b in bodies) <= 1 else "two" if len(bodies) == 2 else "content"
        if layout == "content" and len(bodies) > 2: bodies = [[x for b in bodies for x in b]]
        s = {"layout": layout, "title": title, "body": bodies[0] if bodies else [], "notes": notes}
        if layout == "two": s["body2"] = bodies[1]
        if bg: s["bg"] = bg
        slides.append(s); pic_slides += 1 if picture else 0
    n = ["Slide text, bullets, background colours and speaker notes are brought in. PowerPresentation does not hold pictures, charts or custom layouts from PowerPoint, so those are not brought in."]
    if pic_slides: n[0] += f" {pic_slides} slide(s) had pictures."
    return {"content": json.dumps({"v": 1, "theme": "light", "slides": slides or [{"layout": "content", "title": "", "body": [], "notes": ""}]}), "notes": n}


# ------------------------------------------------------------------ Microsoft files straight to PDF (nothing is saved in iSift)

def docx_to_pdf(data: bytes, title: str = "") -> bytes:
    return wp_to_pdf(docx_to_wp(data)["html"], title)


def _rgb_of(color) -> str:
    """A python-pptx / openpyxl colour as #rrggbb, or "" when it is a theme colour that cannot be resolved here."""
    try:
        v = str(color.rgb) if color.rgb is not None else ""
        if re.match(r"^[0-9A-Fa-f]{8}$", v): v = v[2:]                    # Excel writes ARGB
        if re.match(r"^[0-9A-Fa-f]{6}$", v): return "#" + v.lower()
    except Exception: pass
    return ""


def pptx_to_pdf(data: bytes, title: str = "") -> bytes:
    """Each slide as one PDF page the size of the slide: backgrounds, shapes with their fills, pictures, tables and text with its font, size, colour and bullets."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE as T
    try: prs = Presentation(io.BytesIO(data))
    except Exception: raise ConvertError("That file could not be opened as a PowerPoint presentation.")
    K = 12700.0
    W, H = prs.slide_width / K, prs.slide_height / K
    pages = []

    def run_html(r, default_size):
        t = esc(r.text or "")
        if not t: return ""
        f = r.font; st = []
        col = ""
        try: col = _rgb_of(f.color) if f.color is not None and f.color.type is not None else ""
        except Exception: pass
        if col: st.append(f"color:{col}")
        st.append(f"font-size:{(f.size.pt if f.size else default_size):g}pt")
        if f.name: st.append(f"font-family:'{re.sub(chr(39), '', f.name)}',Arial,sans-serif")
        t = f'<span style="{";".join(st)}">{t}</span>'
        if f.bold: t = f"<b>{t}</b>"
        if f.italic: t = f"<i>{t}</i>"
        if f.underline: t = f"<u>{t}</u>"
        return t

    def text_html(shape, default_size):
        out = []
        for p in shape.text_frame.paragraphs:
            inner = "".join(run_html(r, default_size) for r in p.runs)
            if not inner.strip() and not p.runs: out.append(f'<div style="height:{default_size * 1.2:g}pt"></div>'); continue
            al = {1: "left", 2: "center", 3: "right", 4: "justify"}.get(int(p.alignment) if p.alignment is not None else 1, "left")
            ppr = p._p.pPr
            bullet = ppr is not None and ppr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}buChar") is not None
            lvl = p.level or 0
            pre = '<span style="display:inline-block;width:1.1em">&#8226;</span>' if bullet else ""
            out.append(f'<div style="text-align:{al};margin-left:{lvl * 18 + (0 if not bullet else 0)}pt;margin-bottom:2pt;line-height:1.15">{pre}{inner}</div>')
        return "".join(out)

    def draw(shapes, items, dx=0.0, dy=0.0):
        for sh in shapes:
            try:
                if sh.left is None or sh.top is None or sh.width is None: continue
                x, y, w, h = sh.left / K, sh.top / K, sh.width / K, (sh.height or 0) / K
            except Exception: continue
            pos = f"position:absolute;left:{x:.1f}pt;top:{y:.1f}pt;width:{w:.1f}pt;height:{h:.1f}pt;"
            if sh.shape_type == T.GROUP:
                draw(sh.shapes, items); continue
            if sh.shape_type == T.PICTURE:
                try:
                    img = sh.image; mime = img.content_type
                    if mime not in ("image/png", "image/jpeg", "image/gif"):
                        from PIL import Image
                        bio = io.BytesIO(); Image.open(io.BytesIO(img.blob)).convert("RGBA").save(bio, "PNG"); blob, mime = bio.getvalue(), "image/png"
                    else: blob = img.blob
                    items.append(f'<img style="{pos}" src="data:{mime};base64,{base64.b64encode(blob).decode()}">')
                except Exception: pass
                continue
            if getattr(sh, "has_table", False) and sh.has_table:
                rows = []
                for ri, r in enumerate(sh.table.rows):
                    tds = ""
                    for c in r.cells:
                        if c.is_spanned: continue
                        bg = ""
                        try:
                            if c.fill.type == 1: bg = f";background:{_rgb_of(c.fill.fore_color)}"
                        except Exception: pass
                        if not bg and sh.table.first_row and ri == 0: bg = ";background:#4f81bd;color:#ffffff;font-weight:bold"        # PowerPoint's default table look
                        elif not bg and sh.table.horz_banding: bg = ";background:" + ("#d0d8e8" if ri % 2 else "#e9edf4")
                        sp = (f' colspan="{c.span_width}"' if c.is_merge_origin and c.span_width > 1 else "") + (f' rowspan="{c.span_height}"' if c.is_merge_origin and c.span_height > 1 else "")
                        tds += f'<td{sp} style="border:1px solid #888;padding:3pt 5pt{bg}">{text_html(c, 12)}</td>'
                    rows.append(f"<tr>{tds}</tr>")
                items.append(f'<table style="{pos}border-collapse:collapse;table-layout:fixed">' + "".join(rows) + "</table>"); continue
            st = pos
            try:
                if sh.fill.type == 1:
                    c = _rgb_of(sh.fill.fore_color)
                    if c: st += f"background:{c};"
            except Exception: pass
            try:
                if sh.line.fill.type == 1:
                    c = _rgb_of(sh.line.color)
                    if c: st += f"border:{max((sh.line.width or 9525) / 12700, 0.75):g}pt solid {c};"
            except Exception: pass
            try:
                ast = str(sh.auto_shape_type)
                if "OVAL" in ast or "ELLIPSE" in ast: st += "border-radius:50%;"
                elif "ROUNDED" in ast: st += f"border-radius:{min(w, h) * 0.16:.1f}pt;"
            except Exception: pass
            inner = ""
            if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip():
                dsz = 40 if (getattr(sh, "is_placeholder", False) and sh.placeholder_format.type in (1, 3)) else 18
                try:
                    va = sh.text_frame.vertical_anchor
                    anchor = {1: "top", 3: "middle", 4: "bottom"}.get(int(va), "top") if va is not None else ("middle" if sh.shape_type == T.AUTO_SHAPE else "top")
                except Exception: anchor = "top"
                jc = {"top": "flex-start", "middle": "center", "bottom": "flex-end"}[anchor]
                inner = f'<div style="display:flex;flex-direction:column;justify-content:{jc};height:100%;box-sizing:border-box;padding:3.6pt 7.2pt">{text_html(sh, dsz)}</div>'
            items.append(f'<div style="{st}box-sizing:border-box;overflow:hidden">{inner}</div>')

    for sl in prs.slides:
        items = []
        bg = "#ffffff"
        for holder in (sl, sl.slide_layout, sl.slide_layout.slide_master):
            try:
                if holder.background.fill.type == 1: bg = _rgb_of(holder.background.fill.fore_color) or bg; break
            except Exception: continue
        for layer in (sl.slide_layout.slide_master, sl.slide_layout):                # logos and bars drawn on the master / layout, behind the slide
            try: draw([x for x in layer.shapes if not x.is_placeholder], items)
            except Exception: pass
        draw(sl.shapes, items)
        pages.append(f'<section style="position:relative;width:{W:.1f}pt;height:{H:.1f}pt;background:{bg};overflow:hidden;page-break-after:always;font-family:Calibri,Arial,sans-serif">' + "".join(items) + "</section>")
    css = f"@page{{size:{W:.1f}pt {H:.1f}pt;margin:0}}body{{margin:0}}section:last-child{{page-break-after:auto}}"
    return _pdf_from_html(f"<!doctype html><meta charset='utf-8'><title>{esc(title)}</title><style>{css}</style><body>" + ("".join(pages) or "<section></section>"))


def xlsx_to_pdf(data: bytes, title: str = "") -> bytes:
    """Every sheet as PDF pages, with the worked-out values, fills, fonts, colours, borders, column widths and merged cells."""
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    try: wb = load_workbook(io.BytesIO(data), data_only=False)
    except Exception: raise ConvertError("That file could not be opened as an Excel workbook.")
    try: wbv = load_workbook(io.BytesIO(data), data_only=True)
    except Exception: wbv = None

    def fmt_value(v, nf):
        if v is None: return ""
        if isinstance(v, bool): return "TRUE" if v else "FALSE"
        if hasattr(v, "strftime"):
            try: return v.strftime("%d/%m/%Y %H:%M" if getattr(v, "hour", 0) or getattr(v, "minute", 0) else "%d/%m/%Y")
            except Exception: return str(v)
        if isinstance(v, (int, float)):
            nf = nf or "General"
            dec = len(nf.split(".")[1].split(";")[0].rstrip("%_)").replace("#", "0")) if "." in nf and "0" in nf else 0
            if "%" in nf: return f"{v * 100:,.{dec}f}%"
            if "0" in nf and nf != "General":
                s = f"{v:,.{dec}f}" if "," in nf else f"{v:.{dec}f}"
                return ("$" if "$" in nf else "") + s
            return f"{v:.10g}"
        return str(v)

    pages = []
    for ws in wb.worksheets[:50]:
        wv = wbv[ws.title] if wbv is not None and ws.title in wbv.sheetnames else ws
        maxr, maxc = min(ws.max_row, 3000), min(ws.max_column, 80)
        merged, skip = {}, set()
        for rng in ws.merged_cells.ranges:
            merged[(rng.min_row, rng.min_col)] = (rng.max_row - rng.min_row + 1, rng.max_col - rng.min_col + 1)
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    if (r, c) != (rng.min_row, rng.min_col): skip.add((r, c))
        widths = [(ws.column_dimensions[get_column_letter(c)].width or 8.43) * 7 for c in range(1, maxc + 1)]
        total = sum(widths) or 1
        rows = []
        for r in range(1, maxr + 1):
            rh = ws.row_dimensions[r].height
            tds = ""
            for c in range(1, maxc + 1):
                if (r, c) in skip: continue
                cell = ws.cell(row=r, column=c); val = wv.cell(row=r, column=c).value
                st = []
                try:
                    if cell.fill and cell.fill.fill_type == "solid":
                        bg = _rgb_of(cell.fill.fgColor)
                        if bg and bg != "#000000": st.append(f"background:{bg}")
                except Exception: pass
                f = cell.font
                if f is not None:
                    try:
                        fc = _rgb_of(f.color) if f.color is not None else ""
                        if fc: st.append(f"color:{fc}")
                    except Exception: pass
                    if f.b: st.append("font-weight:bold")
                    if f.i: st.append("font-style:italic")
                    if f.sz: st.append(f"font-size:{f.sz:g}pt")
                    if f.name: st.append(f"font-family:'{re.sub(chr(39), '', f.name)}',Arial,sans-serif")
                    if f.u: st.append("text-decoration:underline")
                al = cell.alignment.horizontal if cell.alignment is not None else None
                if al in ("left", "center", "right"): st.append(f"text-align:{al}")
                elif isinstance(val, (int, float)) and not isinstance(val, bool): st.append("text-align:right")
                b = cell.border
                for side, nm in ((b.left, "left"), (b.right, "right"), (b.top, "top"), (b.bottom, "bottom")):
                    if side is not None and side.style: st.append(f"border-{nm}:1px solid " + (_rgb_of(side.color) if side.color is not None and _rgb_of(side.color) else "#555"))
                sp = ""
                if (r, c) in merged: rs, cs = merged[(r, c)]; sp = (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
                tds += f'<td{sp} style="{";".join(st)}">{esc(fmt_value(val, cell.number_format))}</td>'
            rows.append(f'<tr{f" style=height:{rh * 1.333:.0f}px" if rh else ""}>{tds}</tr>')
        zoom = min(1.0, 1000 / total)
        grid = "<colgroup>" + "".join(f'<col style="width:{w:.0f}px">' for w in widths) + "</colgroup>"
        pages.append(f'<h2 style="font:bold 12pt Arial;margin:0 0 6pt">{esc(ws.title)}</h2><table style="border-collapse:collapse;table-layout:fixed;width:{total:.0f}px;zoom:{zoom:.3f};font:10pt Arial,sans-serif">{grid}{"".join(rows)}</table><div style="page-break-after:always"></div>')
    css = "@page{size:A4 landscape;margin:12mm}td{padding:2px 4px;overflow:hidden;white-space:nowrap;border:0.5px solid #e3e6ec;vertical-align:bottom}"
    return _pdf_from_html(f"<!doctype html><meta charset='utf-8'><title>{esc(title)}</title><style>{css}</style><body>{''.join(pages)}")
