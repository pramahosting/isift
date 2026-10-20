// Present a photo or a PDF from a phone: the picture is drawn on a canvas and the canvas is sent like a shared screen,
// so everyone gets it full-size with the same zoom and pan as a screen share. Phones cannot capture their own screen.
const W = 1920, H = 1080;

export class FileShare {
  pages = 1;
  page = 1;
  track!: MediaStreamTrack;
  private cv = document.createElement('canvas');
  private bmp?: ImageBitmap;
  private pdf?: any;
  private timer?: number;
  private gen = 0;

  constructor(private file: File) { this.cv.width = W; this.cv.height = H; }

  static accepts(f: File) { return /^image\//.test(f.type) || f.type === 'application/pdf' || /\.pdf$/i.test(f.name); }

  async init() {
    const g = this.cv.getContext('2d')!; g.fillStyle = '#111'; g.fillRect(0, 0, W, H);
    if (this.file.type === 'application/pdf' || /\.pdf$/i.test(this.file.name)) {
      const lib: any = await import('pdfjs-dist');
      const worker: any = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
      lib.GlobalWorkerOptions.workerSrc = worker.default;
      this.pdf = await lib.getDocument({ data: new Uint8Array(await this.file.arrayBuffer()) }).promise;
      this.pages = this.pdf.numPages;
      await this.show(1);
    } else {
      this.bmp = await createImageBitmap(this.file, { imageOrientation: 'from-image' } as any);
      this.draw(this.bmp, this.bmp.width, this.bmp.height);
    }
    const stream = (this.cv as any).captureStream(5) as MediaStream;
    this.track = stream.getVideoTracks()[0];
    try { (this.track as any).contentHint = 'detail'; } catch { /* optional */ }
    // a canvas only sends a frame when it changes, so touch it now and then to keep the picture alive for late joiners
    this.timer = window.setInterval(() => { const g2 = this.cv.getContext('2d')!; g2.fillStyle = 'rgba(17,17,17,0.004)'; g2.fillRect(0, 0, 1, 1); }, 700);
  }

  private draw(src: CanvasImageSource, w: number, h: number) {
    const g = this.cv.getContext('2d')!; g.fillStyle = '#111'; g.fillRect(0, 0, W, H);
    const k = Math.min(W / w, H / h), dw = w * k, dh = h * k;
    g.imageSmoothingQuality = 'high'; g.drawImage(src, (W - dw) / 2, (H - dh) / 2, dw, dh);
  }

  async show(n: number) {
    if (!this.pdf) return;
    const my = ++this.gen;
    n = Math.max(1, Math.min(this.pages, n));
    const pg = await this.pdf.getPage(n);
    const vp0 = pg.getViewport({ scale: 1 }), k = Math.min(W / vp0.width, H / vp0.height);
    const vp = pg.getViewport({ scale: k });
    const off = document.createElement('canvas'); off.width = Math.ceil(vp.width); off.height = Math.ceil(vp.height);
    const ctx = off.getContext('2d')!; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, off.width, off.height);
    await pg.render({ canvasContext: ctx, viewport: vp }).promise;
    if (my !== this.gen) return;
    this.page = n; this.draw(off, off.width, off.height);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    try { this.track?.stop(); } catch { /* already stopped */ }
    try { this.bmp?.close(); } catch { /* none */ }
    try { this.pdf?.destroy(); } catch { /* none */ }
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
