// Big meetings: video and sound travel through the Cloudflare video server (an SFU), so each person uploads once
// instead of once per other person. The browser talks to our own server over the meeting's WebSocket; our server
// talks to Cloudflare, so the application secret never reaches a browser.
type Send = (m: any) => void;

const RTC: RTCConfiguration = { iceServers: [{ urls: 'stun:stun.cloudflare.com:3478' }], bundlePolicy: 'max-bundle' };

export class SfuClient {
  private reqs = new Map<string, { ok: (m: any) => void; bad: (e: Error) => void }>();
  private pub?: RTCPeerConnection;
  private subs?: RTCPeerConnection;
  private gen = 0;
  private cur = new Set<string>();
  private tx: { audio?: RTCRtpTransceiver; video?: RTCRtpTransceiver } = {};

  constructor(private send: Send, private onPeer: (id: string, s: MediaStream | null) => void) {}

  /** A reply from our server to one of our requests. */
  handle(m: any) {
    const r = this.reqs.get(m.req);
    if (!r) return;
    this.reqs.delete(m.req);
    if (m.ok) r.ok(m); else r.bad(new Error(m.message || 'The video server refused the request.'));
  }

  private ask(m: any, ms = 20000): Promise<any> {
    const req = Math.random().toString(36).slice(2);
    return new Promise((ok, bad) => {
      const t = setTimeout(() => { this.reqs.delete(req); bad(new Error('The video server did not answer in time.')); }, ms);
      this.reqs.set(req, { ok: v => { clearTimeout(t); ok(v); }, bad: e => { clearTimeout(t); bad(e); } });
      this.send({ ...m, req });
    });
  }

  /** Send our microphone and camera once. */
  async publish(audio?: MediaStreamTrack | null, video?: MediaStreamTrack | null) {
    if (!audio && !video) return;
    this.pub?.close();
    const pc = new RTCPeerConnection(RTC);
    this.pub = pc;
    this.tx = {};
    if (audio) this.tx.audio = pc.addTransceiver(audio, { direction: 'sendonly' });
    if (video) this.tx.video = pc.addTransceiver(video, { direction: 'sendonly', sendEncodings: [{ maxBitrate: 700000, scaleResolutionDownBy: 1.33, maxFramerate: 24 }] });
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const tracks: { mid: string; kind: string }[] = [];
    if (this.tx.audio?.mid != null) tracks.push({ mid: this.tx.audio.mid, kind: 'audio' });
    if (this.tx.video?.mid != null) tracks.push({ mid: this.tx.video.mid, kind: 'video' });
    const r = await this.ask({ type: 'sfu-push', sdp: offer.sdp, tracks });
    await pc.setRemoteDescription({ type: 'answer', sdp: r.sdp });
  }

  /** The camera changed (background effect on or off) or a screen share started or stopped. A shared screen gets more bits. */
  async replaceVideo(t: MediaStreamTrack | null, screen: boolean) {
    const tx = this.tx.video;
    if (!tx) return;
    await tx.sender.replaceTrack(t);
    try {
      const p = tx.sender.getParameters();
      if (!p.encodings || !p.encodings.length) p.encodings = [{}];
      p.encodings[0].maxBitrate = (screen ? 2500 : 700) * 1000;
      p.encodings[0].scaleResolutionDownBy = screen ? 1 : 1.33;
      p.encodings[0].maxFramerate = screen ? 15 : 24;
      await tx.sender.setParameters(p);
    } catch { /* the browser keeps its own settings */ }
  }

  /** Receive these people (the ones on stage). The new set is connected first and swapped in once it is carrying video, so the picture does not blink. */
  async subscribe(ids: string[]) {
    const my = ++this.gen;
    if (!ids.length) { this.dropSubs(); return; }
    const r = await this.ask({ type: 'sfu-pull', ids });
    if (my !== this.gen) return;
    if (!r.session || !r.sdp) { this.dropSubs(); return; }
    const pc = new RTCPeerConnection(RTC);
    const streams = new Map<string, MediaStream>();
    const byMid = new Map<string, string>((r.tracks || []).map((t: any) => [String(t.mid), t.id] as [string, string]));
    pc.ontrack = e => {
      const id = byMid.get(String(e.transceiver.mid));
      if (!id) return;
      let s = streams.get(id);
      if (!s) { s = new MediaStream(); streams.set(id, s); }
      s.addTrack(e.track);
    };
    try {
      await pc.setRemoteDescription({ type: 'offer', sdp: r.sdp });
      const ans = await pc.createAnswer();
      await pc.setLocalDescription(ans);
      await this.ask({ type: 'sfu-answer', session: r.session, sdp: ans.sdp });
      await new Promise<void>(done => {
        const t = setTimeout(done, 8000);
        const ok = () => { if (pc.connectionState === 'connected') { clearTimeout(t); done(); } };
        pc.onconnectionstatechange = ok; ok();
      });
    } catch (e) { pc.close(); throw e; }
    if (my !== this.gen) { pc.close(); return; }
    const old = this.subs;
    this.subs = pc;
    for (const id of this.cur) if (!ids.includes(id)) this.onPeer(id, null);
    this.cur = new Set(ids);
    for (const id of ids) this.onPeer(id, streams.get(id) || null);
    setTimeout(() => { try { old?.close(); } catch { /* already closed */ } }, 1500);
  }

  private dropSubs() {
    try { this.subs?.close(); } catch { /* already closed */ }
    this.subs = undefined;
    for (const id of this.cur) this.onPeer(id, null);
    this.cur = new Set();
  }

  close() {
    this.gen++;
    try { this.pub?.close(); } catch { /* already closed */ }
    try { this.subs?.close(); } catch { /* already closed */ }
    this.reqs.forEach(r => r.bad(new Error('closed')));
    this.reqs.clear();
  }
}
