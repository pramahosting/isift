/** Studio recording for a meeting room: an HD picture of the whole conversation, a mixed master sound, and one separate sound track for every person.
 *
 *  Picture: 1920x1080 at 30 frames a second, recorded as VP9 (VP8 where VP9 is missing). It shows everyone in a grid, or, when someone shares
 *  a screen, a slide deck or document (as PDF), a photo or a video, that shared picture large with the faces beside it.
 *  Sound: the mix at 48 kHz and Opus 256 kbps; each person also gets their own Opus 256 kbps track so they can be edited on their own.
 *  A person who joins after the start gets a track that starts when they arrive: the label says when. */
import type {Take} from './podcast';
import {pickVideoMime,AUDIO_KBPS,videoMbps} from './podcast';

export type StudioWho={key:string;name:string;stream:MediaStream|null;cam:boolean;mic:boolean;screen?:boolean;self?:boolean};
export type StudioInfo={all:StudioWho[];shared:MediaStream|null;sharer:string;speaking:string;backdrop?:string};
const W=1920,H=1080,FPS=30;

export class StudioRecorder{
  private ctx=new AudioContext({sampleRate:48000,latencyHint:'playback'});
  private master=this.ctx.createMediaStreamDestination();
  private canvas=document.createElement('canvas');
  private g=this.canvas.getContext('2d')!;
  private vids=new Map<string,HTMLVideoElement>();
  private lines=new Map<string,{name:string;src:MediaStreamAudioSourceNode;dest:MediaStreamAudioDestinationNode;sid:string;rec:MediaRecorder;chunks:Blob[];at:number}>();
  private bd:HTMLImageElement|null=null;private bdUrl='';
  private timer:any;private masterRec!:MediaRecorder;private masterChunks:Blob[]=[];private t0=0;private last='';private tEnd=0;
  constructor(private info:()=>StudioInfo,private onChange?:()=>void){this.canvas.width=W;this.canvas.height=H}
  seconds(){return Math.round(((this.tEnd||Date.now())-this.t0)/1000)}
  async start(){
    await this.ctx.resume().catch(()=>{});this.t0=Date.now();
    const vs=this.canvas.captureStream(FPS);this.master.stream.getAudioTracks().forEach(t=>vs.addTrack(t));
    this.masterRec=new MediaRecorder(vs,{mimeType:pickVideoMime(),videoBitsPerSecond:videoMbps(1080)*1e6,audioBitsPerSecond:AUDIO_KBPS*1000});
    this.masterRec.ondataavailable=e=>{if(e.data.size)this.masterChunks.push(e.data)};this.masterRec.start(2000);
    this.sync();this.draw();
    try{const wk=new Worker(URL.createObjectURL(new Blob([`setInterval(()=>postMessage(0),${Math.round(1000/FPS)})`],{type:'text/javascript'})));wk.onmessage=()=>this.tick();this.timer=wk}catch{this.timer=setInterval(()=>this.tick(),Math.round(1000/FPS))}
  }
  private n=0;
  private tick(){this.draw();if(++this.n%15===0)this.sync()}
  /** Give every person who is here a sound track; follow the stream if their audio changes. */
  private sync(){
    for(const w of this.info().all){
      const tr=w.stream?.getAudioTracks().find(t=>t.readyState==='live');if(!tr)continue;
      const have=this.lines.get(w.key);
      if(have&&have.sid===tr.id)continue;
      const src=this.ctx.createMediaStreamSource(new MediaStream([tr]));src.connect(this.master);
      if(have){try{have.src.disconnect()}catch{}src.connect(have.dest);have.src=src;have.sid=tr.id;continue}   // same person, new audio track: keep one file
      const dest=this.ctx.createMediaStreamDestination();src.connect(dest);
      const rec=new MediaRecorder(dest.stream,{mimeType:'audio/webm;codecs=opus',audioBitsPerSecond:AUDIO_KBPS*1000});const chunks:Blob[]=[];rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};rec.start(2000);
      this.lines.set(w.key,{name:w.name,src,dest,sid:tr.id,rec,chunks,at:Math.round((Date.now()-this.t0)/1000)});
      this.onChange?.();
    }
  }
  private vid(k:string,st:MediaStream|null){if(!st)return null;let v=this.vids.get(k);if(!v){v=document.createElement('video');v.muted=true;v.playsInline=true;v.autoplay=true;this.vids.set(k,v)}if(v.srcObject!==st){v.srcObject=st;v.play().catch(()=>{})}return v.videoWidth>0&&v.readyState>=2?v:null}
  private fit(v:HTMLVideoElement,x:number,y:number,w:number,h:number){const k=Math.min(w/v.videoWidth,h/v.videoHeight);const dw=v.videoWidth*k,dh=v.videoHeight*k;this.g.drawImage(v,x+(w-dw)/2,y+(h-dh)/2,dw,dh)}
  private cover(v:HTMLVideoElement,x:number,y:number,w:number,h:number){const k=Math.max(w/v.videoWidth,h/v.videoHeight);const sw=w/k,sh=h/k;this.g.drawImage(v,(v.videoWidth-sw)/2,(v.videoHeight-sh)/2,sw,sh,x,y,w,h)}
  private face(p:StudioWho,x:number,y:number,w:number,h:number,hot:boolean){
    const g=this.g;g.save();g.beginPath();g.roundRect(x,y,w,h,18);g.clip();g.fillStyle='#16303f';g.fillRect(x,y,w,h);
    const v=p.cam?this.vid(p.key,p.stream):null;
    if(v)this.cover(v,x,y,w,h);else{const r=Math.min(w,h)*0.2;g.fillStyle='#2f6f8f';g.beginPath();g.arc(x+w/2,y+h/2,r,0,Math.PI*2);g.fill();g.fillStyle='#fff';g.font=`700 ${Math.round(r)}px system-ui,sans-serif`;g.textAlign='center';g.textBaseline='middle';g.fillText((p.name||'?').trim().charAt(0).toUpperCase(),x+w/2,y+h/2+4)}
    const fs=Math.max(24,Math.min(34,Math.round(h/11)));const t=p.name+(p.mic?'':' (muted)');g.font=`600 ${fs}px system-ui,sans-serif`;g.textAlign='left';g.textBaseline='middle';
    const tw=g.measureText(t).width+32;g.fillStyle='rgba(0,0,0,.6)';g.beginPath();g.roundRect(x+16,y+h-fs-34,tw,fs+20,10);g.fill();g.fillStyle='#fff';g.fillText(t,x+32,y+h-fs/2-24);
    g.restore();if(hot){g.strokeStyle='#4cc38a';g.lineWidth=6;g.beginPath();g.roundRect(x+3,y+3,w-6,h-6,18);g.stroke()}
  }
  private draw(){
    const g=this.g,I=this.info();g.fillStyle='#0b1620';g.fillRect(0,0,W,H);
    // the host's own studio set: a picture behind everyone
    if(I.backdrop!==this.bdUrl){this.bdUrl=I.backdrop||'';this.bd=null;if(this.bdUrl){const i=new Image();i.onload=()=>{if(this.bdUrl===I.backdrop)this.bd=i};i.src=this.bdUrl}}
    if(this.bd){const k=Math.max(W/this.bd.width,H/this.bd.height);g.drawImage(this.bd,(W-this.bd.width*k)/2,(H-this.bd.height*k)/2,this.bd.width*k,this.bd.height*k)}
    const all=I.all;if(I.speaking&&all.some(a=>a.key===I.speaking))this.last=I.speaking;
    const pad=24;
    if(I.shared){
      const v=this.vid('__shared',I.shared);const sw=W-pad*2-(all.length>1?400:0)-(all.length>1?pad:0);
      g.fillStyle='#000';g.beginPath();g.roundRect(pad,pad,sw,H-pad*2,18);g.fill();if(v)this.fit(v,pad,pad,sw,H-pad*2);
      if(all.length>0){const fx=pad*2+sw,fw=W-fx-pad;const n=Math.min(all.length,4);const fh=Math.min(fw*9/16,(H-pad*2-(n-1)*pad)/n);
        for(let i=0;i<n;i++)this.face(all[i],fx,pad+i*(fh+pad),fw,fh,all[i].key===this.last)}
    }else{
      const n=all.length||1;const cols=n<=1?1:n<=2?2:n<=4?2:n<=6?3:n<=9?3:4;const rows=Math.ceil(n/cols);
      const cw=(W-pad*(cols+1))/cols,ch=(H-pad*(rows+1))/rows;
      all.forEach((p,i)=>{const r=Math.floor(i/cols),c=i%cols;const inRow=r===rows-1?n-r*cols:cols;const off=r===rows-1?(cols-inRow)*(cw+pad)/2:0;this.face(p,pad+off+c*(cw+pad),pad+r*(ch+pad),cw,ch,n>1&&p.key===this.last)});
    }
  }
  async stop():Promise<Take>{
    this.tEnd=Date.now();(typeof this.timer?.terminate==='function'?this.timer.terminate():clearInterval(this.timer));
    const one=(mr:MediaRecorder)=>new Promise<void>(res=>{if(mr.state==='inactive'){res();return}mr.onstop=()=>res();try{mr.stop()}catch{res()}});
    await Promise.all([one(this.masterRec),...[...this.lines.values()].map(l=>one(l.rec))]);this.ctx.close().catch(()=>{});
    const secs=this.seconds();const mm=(s:number)=>`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
    const tracks=[...this.lines.values()].filter(l=>l.chunks.length).map(l=>({label:l.at>2?`${l.name} (joined at ${mm(l.at)})`:l.name,blob:new Blob(l.chunks,{type:'audio/webm'}),ext:'webm' as const}));
    return {master:new Blob(this.masterChunks,{type:'video/webm'}),ext:'webm',hasVideo:true,width:W,height:H,seconds:secs,audioKbps:AUDIO_KBPS,audioLabel:`Opus ${AUDIO_KBPS} kbps, 48 kHz`,tracks};
  }
  cancel(){this.tEnd=Date.now();(typeof this.timer?.terminate==='function'?this.timer.terminate():clearInterval(this.timer));try{this.masterRec.stop()}catch{}this.lines.forEach(l=>{try{l.rec.stop()}catch{}});this.ctx.close().catch(()=>{})}
  people(){return this.lines.size}
}
