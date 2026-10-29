// Present a photo or a PDF from a phone: the picture is drawn on a canvas and the canvas is sent like a shared screen,
// so everyone gets it full-size with the same zoom and pan as a screen share. Phones cannot capture their own screen.
const W = 1920, H = 1080;
/** The picture is sent in its own shape (an upright page stays upright), so a phone held upright shows a page full-size instead of a small strip inside a wide frame. */
function fitSize(w: number, h: number) {
  const a = Math.max(0.2, Math.min(5, w / h));
  let cw = a >= 1 ? 1920 : 1920 * a, ch = a >= 1 ? 1920 / a : 1920;
  const k = Math.min(1, Math.sqrt(2.2e6 / (cw * ch)));                 // about as many pixels as the old 1920 x 1080 frame
  cw = Math.max(320, Math.round(cw * k / 2) * 2); ch = Math.max(320, Math.round(ch * k / 2) * 2);
  return { cw, ch };
}

export class FileShare {
  pages = 1;
  page = 1;
  track!: MediaStreamTrack;
  onPage?: (n: number) => void;                 // told when scrolling moves to another page
  private cv = document.createElement('canvas');
  private bmp?: ImageBitmap;
  private pdf?: any;
  private timer?: number;
  // a PDF is laid out as one long strip (pages stacked, as in any PDF viewer) and the canvas is a window onto it that scrolls
  private hs: number[] = [];                    // page heights in strip pixels (every page scaled to the canvas width)
  private tops: number[] = [];
  private total = 0;
  private y = 0;
  private cache = new Map<number, HTMLCanvasElement>();
  private busy = new Set<number>();
  private raf = 0;
  private dead = false;
  private static GAP = 14;

  constructor(private file: File) { this.cv.width = W; this.cv.height = H; }

  static accepts(f: File) { return /^image\//.test(f.type) || f.type === 'application/pdf' || /\.pdf$/i.test(f.name); }
  get width() { return this.cv.width; }
  get height() { return this.cv.height; }

  async init() {
    const g = this.cv.getContext('2d')!; g.fillStyle = '#111'; g.fillRect(0, 0, W, H);
    if (this.file.type === 'application/pdf' || /\.pdf$/i.test(this.file.name)) {
      const lib: any = await import('pdfjs-dist');
      const worker: any = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
      lib.GlobalWorkerOptions.workerSrc = worker.default;
      this.pdf = await lib.getDocument({ data: new Uint8Array(await this.file.arrayBuffer()) }).promise;
      this.pages = this.pdf.numPages;
      const p1 = await this.pdf.getPage(1), v1 = p1.getViewport({ scale: 1 });
      const { cw, ch } = fitSize(v1.width, v1.height);
      this.cv.width = cw; this.cv.height = ch;
      this.hs = new Array(this.pages).fill(Math.round(v1.height * cw / v1.width));
      this.relayout();
      this.paintNow();
      // real page heights (pages of a PDF are not always the same size), filled in without holding anything up
      (async () => { for (let i = 2; i <= this.pages && !this.dead; i++) { try { const v = (await this.pdf.getPage(i)).getViewport({ scale: 1 }); this.hs[i - 1] = Math.round(v.height * cw / v.width); } catch { /* keep the guess */ } if (i % 20 === 0) this.relayout(); } this.relayout(); this.paintNow(); })();
    } else {
      this.bmp = await createImageBitmap(this.file, { imageOrientation: 'from-image' } as any);
      this.draw(this.bmp, this.bmp.width, this.bmp.height);
    }
    const stream = (this.cv as any).captureStream(12) as MediaStream;
    this.track = stream.getVideoTracks()[0];
    try { (this.track as any).contentHint = 'detail'; } catch { /* optional */ }
    // a canvas only sends a frame when it changes, so touch it now and then to keep the picture alive for late joiners
    this.timer = window.setInterval(() => { const g2 = this.cv.getContext('2d')!; g2.fillStyle = 'rgba(17,17,17,0.004)'; g2.fillRect(0, 0, 1, 1); }, 700);
  }

  private relayout() { let t = 0; this.tops = this.hs.map(h => { const v = t; t += h + FileShare.GAP; return v; }); this.total = Math.max(0, t - FileShare.GAP); }

  private draw(src: CanvasImageSource, w: number, h: number) {
    const { cw, ch } = fitSize(w, h);
    if (this.cv.width !== cw || this.cv.height !== ch) { this.cv.width = cw; this.cv.height = ch; }
    const g = this.cv.getContext('2d')!; g.fillStyle = '#111'; g.fillRect(0, 0, cw, ch);
    g.imageSmoothingQuality = 'high'; g.drawImage(src, 0, 0, cw, ch);
  }

  /** How far the strip can scroll. */
  get maxY() { return Math.max(0, this.total - this.cv.height); }
  /** Scroll by some strip pixels (positive = further down the document). */
  scrollBy(dy: number) { if (this.pdf) this.scrollTo(this.y + dy); }
  scrollTo(y: number) { if (!this.pdf) return; this.y = Math.max(0, Math.min(this.maxY, y)); this.schedule(); }
  /** Jump so that page n starts at the top. */
  async show(n: number) { if (!this.pdf) return; n = Math.max(1, Math.min(this.pages, n)); this.scrollTo(this.tops[n - 1] || 0); }
  private pageAtTop() { const mid = this.y + Math.min(this.cv.height * 0.3, 200); let i = 0; while (i + 1 < this.tops.length && this.tops[i + 1] <= mid) i++; return i + 1; }

  private schedule() { if (!this.raf && !this.dead) this.raf = requestAnimationFrame(() => { this.raf = 0; this.paintNow(); }); }

  private paintNow() {
    if (this.dead || !this.pdf) return;
    const g = this.cv.getContext('2d')!, cw = this.cv.width, ch = this.cv.height;
    g.fillStyle = '#2a2f3a'; g.fillRect(0, 0, cw, ch);
    const y0 = this.y, y1 = this.y + ch;
    for (let i = 0; i < this.pages; i++) {
      const top = this.tops[i], bot = top + this.hs[i];
      if (bot < y0 || top > y1) continue;
      const c = this.cache.get(i);
      if (c) { g.drawImage(c, 0, top - y0, cw, this.hs[i]); }
      else { g.fillStyle = '#fff'; g.fillRect(0, top - y0, cw, this.hs[i]); this.render(i); }
    }
    const n = this.pageAtTop(); if (n !== this.page) { this.page = n; this.onPage?.(n); }
    // keep a few pages around the window ready
    for (const j of [this.page - 1, this.page, this.page + 1]) if (j >= 0 && j < this.pages && !this.cache.has(j)) this.render(j);
  }

  private async render(i: number) {
    if (this.busy.has(i) || this.cache.has(i) || this.dead) return;
    this.busy.add(i);
    try {
      const pg = await this.pdf.getPage(i + 1), vp0 = pg.getViewport({ scale: 1 }), k = this.cv.width / vp0.width, vp = pg.getViewport({ scale: k });
      const off = document.createElement('canvas'); off.width = Math.ceil(vp.width); off.height = Math.ceil(vp.height);
      const ctx = off.getContext('2d')!; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, off.width, off.height);
      await pg.render({ canvasContext: ctx, viewport: vp }).promise;
      this.hs[i] = Math.round(off.height); this.relayout();
      this.cache.set(i, off);
      if (this.cache.size > 7) { const far = [...this.cache.keys()].sort((a, b) => Math.abs(b - this.page) - Math.abs(a - this.page))[0]; if (far !== undefined && far !== i) this.cache.delete(far); }
    } catch { /* leave it blank; it is tried again when it scrolls into view */ }
    this.busy.delete(i);
    this.schedule();
  }

  stop() {
    this.dead = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    if (this.timer) clearInterval(this.timer);
    try { this.track?.stop(); } catch { /* already stopped */ }
    try { this.bmp?.close(); } catch { /* none */ }
    try { this.pdf?.destroy(); } catch { /* none */ }
    this.cache.clear();
  }
}

/** Share the meeting whiteboard: whatever is drawn on the board's canvas is sent like a shared screen. */
export class CanvasShare {
  track!: MediaStreamTrack;
  private cv = document.createElement('canvas');
  private timer?: number;
  constructor(private src: () => HTMLCanvasElement | null) { this.cv.width = W; this.cv.height = H; }
  init() {
    this.paint();
    this.track = (this.cv as any).captureStream(8).getVideoTracks()[0];
    try { (this.track as any).contentHint = 'detail'; } catch { /* optional */ }
    this.timer = window.setInterval(() => this.paint(), 150);
  }
  private paint() {
    const s = this.src(); const g = this.cv.getContext('2d')!;
    g.fillStyle = '#fff'; g.fillRect(0, 0, W, H);
    if (!s || !s.width || !s.height) return;
    const k = Math.min(W / s.width, H / s.height), dw = s.width * k, dh = s.height * k;
    g.drawImage(s, (W - dw) / 2, (H - dh) / 2, dw, dh);
  }
  stop() { if (this.timer) clearInterval(this.timer); try { this.track?.stop(); } catch { /* already stopped */ } }
}
