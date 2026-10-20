"""A tiny PDF writer with no extra libraries: text pages (Helvetica, Western characters) and picture pages (JPEG). Used to email notes and
whiteboards as PDF. Notes with characters outside Western encodings are sent as pictures of the page instead (the browser draws them)."""
import re, zlib

_W = dict(zip(" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~", [
    278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,1015,
    667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611,278,278,278,469,556,333,
    556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500,334,260,334,584]))
def _tw(s: str, size: float, bold=False) -> float: return sum(_W.get(c, 556) * (1.05 if bold else 1) for c in s) * size / 1000

def encodable(text: str) -> bool:
    try: text.encode("cp1252"); return True
    except UnicodeEncodeError: return False

def _esc(s: str) -> bytes:
    out = bytearray()
    for b in s.encode("cp1252", "replace"):
        if b in (0x28, 0x29, 0x5C): out += b"\\" + bytes([b])
        elif 32 <= b < 127: out.append(b)
        else: out += b"\\%03o" % b
    return bytes(out)

def _wrap(line: str, size: float, width: float) -> list[str]:
    if not line.strip(): return [""]
    indent = len(line) - len(line.lstrip(" ")); pad = " " * min(indent, 12); words = line.strip().split(" "); out = []; cur = ""
    for w in words:
        while _tw(w, size) > width and len(w) > 1:                      # a very long word is cut
            k = max(1, int(len(w) * width / _tw(w, size)) - 1); 
            if cur: out.append(pad + cur); cur = ""
            out.append(pad + w[:k]); w = w[k:]
        t = (cur + " " + w) if cur else w
        if cur and _tw(pad + t, size) > width: out.append(pad + cur); cur = w
        else: cur = t
    out.append(pad + cur); return out

class _Doc:
    def __init__(self): self.objs: list[bytes] = []; self.pages: list[int] = []
    def add(self, body: bytes) -> int: self.objs.append(body); return len(self.objs)
    def build(self, extra_resources: dict | None = None) -> bytes:
        # object 1 catalog, 2 pages, 3 Helvetica, 4 Helvetica-Bold are reserved at the front
        head = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
        n = len(head); kids = " ".join(f"{p + n} 0 R" for p in self.pages)
        head[0] = b"<< /Type /Catalog /Pages 2 0 R >>"; head[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(self.pages)} >>".encode()
        allobjs = head + self.objs; out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offs = []
        for i, o in enumerate(allobjs, 1):
            offs.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        x = len(out); out += f"xref\n0 {len(allobjs) + 1}\n0000000000 65535 f \n".encode()
        for o in offs: out += f"{o:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(allobjs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode(); return bytes(out)
    def stream(self, data: bytes, extra: str = "") -> int:
        z = zlib.compress(data); return self.add(f"<< /Length {len(z)} /Filter /FlateDecode {extra}>>\nstream\n".encode() + z + b"\nendstream")

def text_pdf(title: str, body: str, footer: str = "") -> bytes:
    """A4 pages: the title in bold, then the text wrapped to the page. Raises UnicodeEncodeError for text Helvetica cannot show."""
    (title + body + footer).encode("cp1252")
    W, H, M = 595, 842, 56; size, lead = 11, 15.5; width = W - 2 * M
    lines: list[tuple[str, bool, float]] = []
    for l in _wrap(title or "Untitled", 18, width): lines.append((l, True, 18))
    lines.append(("", False, 11))
    for raw in body.replace("\r\n", "\n").replace("\t", "    ").split("\n"):
        for l in _wrap(raw, size, width): lines.append((l, False, size))
    d = _Doc(); pages_lines: list[list] = [[]]; y = H - M
    for ln in lines:
        step = lead if ln[2] == 11 else 26
        if y - step < M + 20: pages_lines.append([]); y = H - M
        y -= step; pages_lines[-1].append((y, ln))
    total = len(pages_lines)
    for pi, pl in enumerate(pages_lines, 1):
        c = bytearray()
        for y, (text, bold, sz) in pl:
            if text: c += f"BT /F{2 if bold else 1} {sz} Tf {M} {y:.1f} Td (".encode() + _esc(text) + b") Tj ET\n"
        foot = (footer + "   " if footer else "") + f"Page {pi} of {total}"
        c += b"BT /F1 8 Tf 0.45 g " + f"{M} 28 Td (".encode() + _esc(foot) + b") Tj ET\n"
        cs = d.stream(bytes(c)); pg = d.add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {cs + 4} 0 R >>".encode())
        d.pages.append(pg)
    return d.build()

def jpeg_size(b: bytes) -> tuple[int, int, int]:
    """(width, height, colour components) read from the JPEG header, or ValueError."""
    if not b.startswith(b"\xff\xd8"): raise ValueError("not a JPEG")
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF: i += 1; continue
        m = b[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7: i += 2; continue
        ln = int.from_bytes(b[i + 2:i + 4], "big")
        if m in (0xC0, 0xC1, 0xC2): return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big"), b[i + 9]
        i += 2 + ln
    raise ValueError("no size in JPEG")

def image_pdf(pages: list[bytes], footer: str = "") -> bytes:
    """One page per picture. The page is landscape for wide pictures, and the picture is scaled to fit inside a margin."""
    d = _Doc()
    for jb in pages:
        w, h, comps = jpeg_size(jb)
        if not (0 < w <= 8000 and 0 < h <= 8000): raise ValueError("bad picture size")
        PW, PH = (842, 595) if w >= h else (595, 842); M = 28
        sc = min((PW - 2 * M) / w, (PH - 2 * M - 14) / h); dw, dh = w * sc, h * sc; x, y = (PW - dw) / 2, PH - M - dh
        cs_name = "/DeviceGray" if comps == 1 else "/DeviceCMYK" if comps == 4 else "/DeviceRGB"
        im = d.add(f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace {cs_name} /BitsPerComponent 8 /Filter /DCTDecode /Length {len(jb)} >>\nstream\n".encode() + jb + b"\nendstream")
        c = f"q {dw:.2f} 0 0 {dh:.2f} {x:.2f} {y:.2f} cm /Im0 Do Q\n".encode()
        if footer: c += b"BT /F1 8 Tf 0.45 g " + f"{M} 18 Td (".encode() + _esc(footer) + b") Tj ET\n"
        cs = d.stream(c); pg = d.add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PW} {PH}] /Resources << /Font << /F1 3 0 R >> /XObject << /Im0 {im + 4} 0 R >> >> /Contents {cs + 4} 0 R >>".encode())
        d.pages.append(pg)
    return d.build()
