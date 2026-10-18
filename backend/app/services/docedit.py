"""Edit PDF and Word files: add text, delete text, place a drawn signature.

PDF editing uses pypdf, pypdfium2, pdfminer.six and ReportLab (all permissive licences). Deleting removes the text-drawing instructions from the file; if any text cannot be removed it is covered and the person is warned.
Word editing uses python-docx on the body paragraphs. All functions are synchronous; callers run them in a thread."""
import base64, io, logging
from docx import Document
from docx.shared import Inches

MAX_BYTES = 12 * 1024 * 1024
MAX_PAGES = 30
MAX_OPS = 500
PNG = b"\x89PNG\r\n\x1a\n"

class EditError(ValueError): pass
for _n in ("pyhanko", "pyhanko_certvalidator"): logging.getLogger(_n).setLevel(logging.CRITICAL)  # a self-signed certificate is expected, not an error to log

def b64_in(data: str, limit: int = MAX_BYTES) -> bytes:
    try: raw = base64.b64decode((data or "").split(",", 1)[-1], validate=False)
    except Exception: raise EditError("The file could not be read.")
    if not raw: raise EditError("The file is empty.")
    if len(raw) > limit: raise EditError(f"The file is larger than {limit // (1024 * 1024)} MB.")
    return raw

def kind_of(name: str, raw: bytes) -> str:
    n = (name or "").lower()
    if n.endswith(".pdf") and raw[:5] == b"%PDF-": return "pdf"
    if n.endswith(".docx") and raw[:2] == b"PK": return "docx"
    if n.endswith(".doc"): raise EditError("Old .doc files are not supported. Save the file as .docx in Word and upload that.")
    raise EditError("Upload a PDF (.pdf) or Word (.docx) file.")

def png_ok(raw: bytes) -> bytes:
    if raw[:8] != PNG or len(raw) > 400_000: raise EditError("The signature image is not valid.")
    return raw

def latin(text: str) -> str:
    try: text.encode("cp1252")
    except UnicodeEncodeError: raise EditError("PDF text can use Latin letters, digits and common punctuation only.")
    return text

# ---------- PDF ----------
# Built only from permissively licensed libraries: pypdf (BSD) edits the file, pypdfium2 (Apache/BSD) draws the page pictures,
# pdfminer.six (MIT) finds the lines of text and their positions, ReportLab (BSD) makes the added text and signature layer.
# Positions in and out of this module are PDF points measured from the TOP-LEFT of the page.
def _reader(raw: bytes):
    from pypdf import PdfReader
    try: rd = PdfReader(io.BytesIO(raw), strict=False)
    except Exception: raise EditError("This PDF could not be opened. It may be damaged.")
    if rd.is_encrypted: raise EditError("This PDF is password protected. Remove the password first.")
    if len(rd.pages) > MAX_PAGES: raise EditError(f"This PDF has {len(rd.pages)} pages. Up to {MAX_PAGES} pages can be edited at once.")
    return rd

def _box(pg):
    cb = pg.cropbox; return float(cb.left), float(cb.bottom), float(cb.right), float(cb.top)

def _normalised(raw: bytes) -> bytes:
    """Same file with any page rotation turned into real page content, so that what is drawn and what is edited line up."""
    from pypdf import PdfWriter
    rd = _reader(raw)
    if not any(int(p.get("/Rotate", 0) or 0) % 360 for p in rd.pages): return raw
    w = PdfWriter(clone_from=rd)
    for p in w.pages:
        if int(p.get("/Rotate", 0) or 0) % 360: p.transfer_rotation_to_content()
    out = io.BytesIO(); w.write(out); return out.getvalue()

def _lines(raw: bytes) -> list:
    """Per page: lines of text as {bbox:[x0,y0,x1,y1] top-left points, text, size}."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextLine, LTChar
    rd = _reader(raw); res = []
    try: pages = list(extract_pages(io.BytesIO(raw), laparams=LAParams(line_margin=0.2)))
    except Exception: pages = []
    for i, pg in enumerate(rd.pages):
        l, b, r, t = _box(pg); out = []
        if i < len(pages):
            def walk(o):
                if isinstance(o, LTTextLine):
                    txt = o.get_text().strip()
                    if txt:
                        size = max((c.size for c in o if isinstance(c, LTChar)), default=11)
                        out.append({"bbox": [round(o.x0 - l, 2), round(t - o.y1, 2), round(o.x1 - l, 2), round(t - o.y0, 2)], "text": txt, "size": round(size, 1)})
                elif hasattr(o, "__iter__"):
                    for c in o: walk(c)
            for o in pages[i]: walk(o)
        out.sort(key=lambda x: (round(x["bbox"][1]), x["bbox"][0])); res.append(out)
    return res

def pdf_inspect(raw: bytes) -> dict:
    import pypdfium2 as pdfium
    raw = _normalised(raw); _reader(raw); scale = 1.4; lines = _lines(raw); pages = []
    try:
        pdf = pdfium.PdfDocument(raw)
        try: pdf.init_forms()   # so signature stamps and form fields are drawn
        except Exception: pass
    except Exception: raise EditError("This PDF could not be opened. It may be damaged.")
    for i in range(len(pdf)):
        pg = pdf[i]; w, h = pg.get_size(); buf = io.BytesIO()
        pg.render(scale=scale, may_draw_forms=True).to_pil().convert("RGB").save(buf, "JPEG", quality=72)
        pages.append({"w": round(w, 2), "h": round(h, 2), "scale": scale, "image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), "lines": lines[i] if i < len(lines) else []})
    return {"kind": "pdf", "pages": pages}

def _color(c) -> tuple:
    try:
        c = str(c or "#000000").lstrip("#"); return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception: return (0, 0, 0)

def _mul(m, n):  # PDF matrices [a b c d e f]: result = m x n
    return [m[0]*n[0]+m[1]*n[2], m[0]*n[1]+m[1]*n[3], m[2]*n[0]+m[3]*n[2], m[2]*n[1]+m[3]*n[3], m[4]*n[0]+m[5]*n[2]+n[4], m[4]*n[1]+m[5]*n[3]+n[5]]

def _strip_text(rd, pg, rects: list) -> int:
    """Remove the text-drawing instructions that start inside any rectangle (user-space points, y up). Returns how many were removed."""
    from pypdf.generic import ContentStream, NameObject
    cs = ContentStream(pg.get_contents(), rd); ops = cs.operations
    I = [1, 0, 0, 1, 0, 0]; ctm = list(I); stack = []; tm = list(I); tlm = list(I); lead = 0.0; prev_del = False; keep = []; gone = 0
    f = lambda v: float(v)
    def inside(m):
        x, y = _mul(tm, ctm)[4:6]
        return any(r[0] - 2 <= x <= r[2] + 2 and r[1] - 1 <= y <= r[3] + 1 for r in rects)
    for operands, op in ops:
        o = op.decode() if isinstance(op, bytes) else str(op)
        try:
            if o == "q": stack.append(list(ctm))
            elif o == "Q": ctm = stack.pop() if stack else list(I)
            elif o == "cm": ctm = _mul([f(v) for v in operands], ctm)
            elif o == "BT": tm = list(I); tlm = list(I); prev_del = False
            elif o == "Tm": tm = tlm = [f(v) for v in operands]; tlm = list(tm); prev_del = False
            elif o in ("Td", "TD"):
                tx, ty = f(operands[0]), f(operands[1])
                if o == "TD": lead = -ty
                tlm = _mul([1, 0, 0, 1, tx, ty], tlm); tm = list(tlm); prev_del = False
            elif o == "TL": lead = f(operands[0])
            elif o == "T*": tlm = _mul([1, 0, 0, 1, 0, -lead], tlm); tm = list(tlm); prev_del = False
        except Exception: pass
        if o in ("Tj", "TJ"):
            hit = prev_del or inside(tm)
            prev_del = hit
            if hit: gone += 1; continue
        elif o in ("'", '"'):
            tlm = _mul([1, 0, 0, 1, 0, -lead], tlm); tm = list(tlm)
            if inside(tm): gone += 1; prev_del = True; keep.append(([], b"T*")); continue
            prev_del = False
        keep.append((operands, op))
    cs.operations = keep; pg.replace_contents(cs); return gone

def pdf_apply(raw: bytes, ops: list):
    """Returns (edited PDF bytes, warnings)."""
    from pypdf import PdfWriter, Transformation
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    raw = _normalised(raw); rd = _reader(raw); n = len(rd.pages); w = PdfWriter(clone_from=rd); warnings = []
    def page_of(o):
        try:
            i = int(o.get("page"))
            if not 0 <= i < n: raise ValueError
            return i
        except Exception: raise EditError("An edit points at a page that does not exist.")
    def rect_of(o, i):
        try: x0, y0, x1, y1 = [float(v) for v in o.get("rect")]
        except Exception: raise EditError("An edit has no valid area.")
        l, b, r, t = _box(w.pages[i]); W, H = r - l, t - b
        x0, x1 = max(0, min(x0, x1)), min(W, max(x0, x1)); y0, y1 = max(0, min(y0, y1)), min(H, max(y0, y1))
        if x1 - x0 < 2 or y1 - y0 < 2: raise EditError("An edit area is too small.")
        return [x0, y0, x1, y1]
    for o in ops:
        if o.get("t") not in ("delete", "text", "sign"): raise EditError("Unknown edit.")
        page_of(o)
    covers: dict = {}
    dels = [o for o in ops if o.get("t") == "delete"]
    for i in sorted({page_of(o) for o in dels}):
        l, b, r, t = _box(w.pages[i]); rects = [rect_of(o, i) for o in dels if page_of(o) == i]
        user = [[l + x0, t - y1, l + x1, t - y0] for x0, y0, x1, y1 in rects]
        _strip_text(w, w.pages[i], user)
    if dels:   # check that nothing readable is left in the deleted areas; anything that is gets covered, and the person is told
        mid = io.BytesIO(); w.write(mid); left = _lines(mid.getvalue())
        for o in dels:
            i = page_of(o); x0, y0, x1, y1 = rect_of(o, i)
            if any(ln["bbox"][0] < x1 and ln["bbox"][2] > x0 and ln["bbox"][1] < y1 - 1 and ln["bbox"][3] > y0 + 1 and ln["text"].strip() for ln in left[i]):
                covers.setdefault(i, []).append([x0, y0, x1, y1])
                warnings.append(f"Some text on page {i + 1} could not be removed from the file itself, so it was covered instead. It may still be found by searching the PDF.")
    layers: dict = {}
    for o in ops:
        if o.get("t") in ("text", "sign"): layers.setdefault(page_of(o), []).append(o)
    for i in sorted(set(layers) | set(covers)):
        l, b, r, t = _box(w.pages[i]); W, H = r - l, t - b; buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H))
        for x0, y0, x1, y1 in covers.get(i, []): c.setFillColorRGB(1, 1, 1); c.setStrokeColorRGB(1, 1, 1); c.rect(x0, H - y1, x1 - x0, y1 - y0, stroke=0, fill=1)
        for o in layers.get(i, []):
            if o["t"] == "text":
                text = latin(str(o.get("text") or "")[:4000])
                if not text.strip(): continue
                size = max(6.0, min(float(o.get("size") or 12), 72.0))
                try: x = float(o.get("x")); y = float(o.get("y"))
                except Exception: raise EditError("An edit has no valid position.")
                c.setFont("Helvetica", size); c.setFillColorRGB(*_color(o.get("color")))
                for k, line in enumerate(text.split("\n")): c.drawString(x, H - (y + size + k * size * 1.2), line)
            else:
                x0, y0, x1, y1 = rect_of(o, i)
                c.drawImage(ImageReader(io.BytesIO(png_ok(b64_in(o.get("png"), 400_000)))), x0, H - y1, x1 - x0, y1 - y0, mask="auto", preserveAspectRatio=True, anchor="c")
        c.save(); buf.seek(0)
        from pypdf import PdfReader
        w.pages[i].merge_transformed_page(PdfReader(buf).pages[0], Transformation().translate(l, b))
    out = io.BytesIO(); w.write(out); return out.getvalue(), sorted(set(warnings))

# ---------- Word ----------
def _open_docx(raw: bytes):
    try: return Document(io.BytesIO(raw))
    except Exception: raise EditError("This Word file could not be opened. It may be damaged or protected.")

def docx_inspect(raw: bytes) -> dict:
    d = _open_docx(raw)
    paras = [{"i": i, "text": p.text, "style": (p.style.name if p.style is not None else ""), "pic": bool(p._p.xpath(".//w:drawing"))} for i, p in enumerate(d.paragraphs)]
    if len(paras) > 3000: raise EditError("This document is too long to edit here.")
    return {"kind": "docx", "paragraphs": paras, "tables": len(d.tables)}

def docx_apply(raw: bytes, ops: list) -> bytes:
    d = _open_docx(raw); ps = list(d.paragraphs); n = len(ps)
    def idx(o, allow_end=False):
        try: i = int(o.get("i", o.get("after")))
        except Exception: raise EditError("An edit points at a paragraph that does not exist.")
        if i == -1 and allow_end: return i
        if not 0 <= i < n: raise EditError("An edit points at a paragraph that does not exist.")
        return i
    for o in ops:
        t = o.get("t")
        if t == "replace":
            p = ps[idx(o)]; text = str(o.get("text") or "")[:20000]; runs = p.runs
            if runs:
                runs[0].text = text
                for r in runs[1:]: r._r.getparent().remove(r._r)
            else: p.add_run(text)
    for o in ops:
        if o.get("t") == "add":
            text = str(o.get("text") or "")[:20000]
            if not text.strip(): continue
            i = idx(o, True); np_ = d.add_paragraph(text)
            if i >= 0: ps[i]._p.addnext(np_._p)
        elif o.get("t") == "sign":
            i = idx(o, True); np_ = d.add_paragraph(); w = max(0.6, min(float(o.get("width") or 2.0), 6.0))
            np_.add_run().add_picture(io.BytesIO(png_ok(b64_in(o.get("png"), 400_000))), width=Inches(w))
            if i >= 0: ps[i]._p.addnext(np_._p)
        elif o.get("t") not in ("replace", "delete"): raise EditError("Unknown edit.")
    for o in ops:
        if o.get("t") == "delete":
            e = ps[idx(o)]._p; e.getparent().remove(e) if e.getparent() is not None else None
    out = io.BytesIO(); d.save(out); return out.getvalue()

# ---------- Certified digital signature (PDF) ----------
# A cryptographic signature made with the person's own certificate (.p12 / .pfx). It proves who signed and that the file has not
# changed since. The certificate file and its password are used for this one request and are never stored or logged.
def make_certificate(name: str, email: str, password: str, years: int = 3) -> bytes:
    """A self-signed identity certificate, returned as a password-protected .p12. Programs such as Adobe Reader will show the
    signer as 'not verified' until the recipient chooses to trust it; a certificate from a recognised authority is shown as verified."""
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    name = (name or "").strip()[:64]
    if not name: raise EditError("Enter the name that the certificate should show.")
    if len(password or "") < 8: raise EditError("Choose a password of at least 8 characters for the certificate file.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name)]
    email = (email or "").strip()[:120]
    if email: attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    subject = x509.Name(attrs); now = datetime.now(timezone.utc) - timedelta(minutes=5)
    b = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now).not_valid_after(now + timedelta(days=365 * years))
         .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
         .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
         .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False))
    cert = b.sign(key, hashes.SHA256())
    return pkcs12.serialize_key_and_certificates(name.encode(), key, cert, None, serialization.BestAvailableEncryption(password.encode()))

def pdf_certify(raw: bytes, p12: bytes, password: str, reason: str = "", location: str = "", contact: str = "", visible: bool = True, page: int = 0, lock: bool = True) -> bytes:
    from pyhanko.sign import signers, fields
    from pyhanko.sign.fields import SigFieldSpec
    from pyhanko.stamp import TextStampStyle
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    rd = _reader(raw)
    try: signer = signers.SimpleSigner.load_pkcs12_data(p12, [], passphrase=(password or "").encode())
    except Exception: signer = None
    if signer is None or signer.signing_cert is None or signer.signing_key is None:
        raise EditError("The certificate could not be opened. Check the password and that the file is a .p12 or .pfx certificate with its private key.")
    try:
        w = IncrementalPdfFileWriter(io.BytesIO(raw), strict=False)
        meta = signers.PdfSignatureMetadata(field_name="iSiftSignature", reason=(reason or "")[:200] or None, location=(location or "")[:200] or None, contact_info=(contact or "")[:200] or None,
                                            certify=bool(lock), docmdp_permissions=fields.MDPPerm.NO_CHANGES if lock else fields.MDPPerm.FILL_FORMS,
                                            md_algorithm="sha256")
        idx = max(0, min(int(page or 0), len(rd.pages) - 1)); l, b, r, t = _box(rd.pages[idx]); pw = r - l
        if visible:
            box = (l + pw - 250, b + 30, l + pw - 30, b + 90)
            spec = SigFieldSpec("iSiftSignature", on_page=idx, box=box)
            style = TextStampStyle(stamp_text="Digitally signed by %(signer)s\nDate: %(ts)s", border_width=1)
            pdfs = signers.PdfSigner(meta, signer=signer, new_field_spec=spec, stamp_style=style)
        else:
            pdfs = signers.PdfSigner(meta, signer=signer, new_field_spec=SigFieldSpec("iSiftSignature", on_page=idx))
        out = io.BytesIO(); pdfs.sign_pdf(w, output=out); return out.getvalue()
    except EditError: raise
    except Exception as e: raise EditError("The file could not be signed: " + str(e)[:160])

def pdf_signatures(raw: bytes) -> list:
    """Digital signatures already in a PDF: who signed, whether the file is unchanged since, and whether it locks the document."""
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        r = PdfFileReader(io.BytesIO(raw), strict=False); res = []
        for s in r.embedded_regular_signatures:
            try:
                st = validate_pdf_signature(s)
                cn = s.signer_cert.subject.native.get("common_name", "") if s.signer_cert else ""
                res.append({"signer": cn, "intact": bool(st.intact and st.valid), "trusted": bool(st.trusted), "certified": s.sig_object.get("/Reference") is not None})
            except Exception: res.append({"signer": "", "intact": False, "trusted": False, "certified": False})
        return res
    except Exception: return []
