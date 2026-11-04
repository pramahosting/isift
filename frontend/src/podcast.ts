/** HD podcast capture, done entirely in the browser.
 *
 *  Quality: audio is captured at 48 kHz with the browser's voice processing OFF (unless asked for), and kept as Opus at 256 kbps or as a
 *  lossless 24-bit WAV. Video asks the camera for the highest resolution it has (up to 4K), at 30 frames a second, and is recorded
 *  as VP9 (VP8 where VP9 is missing) at a bit rate that suits the resolution.
 *  Coverage: besides the mixed master, every microphone also gets its own separate track, so each voice can be edited on its own. */

export type Mic={id:string;label:string};
export type StudioOpts={mics:Mic[];cam:string;res:'best'|'1080'|'720';audio:'opus'|'wav';clean:boolean};
export type Track={label:string;blob:Blob;ext:'webm'|'wav'};
export type Take={master:Blob;ext:'webm'|'wav';hasVideo:boolean;width:number;height:number;seconds:number;audioKbps:number;audioLabel:string;tracks:Track[]};
export type Session={stream:MediaStream|null;start():void;pause():void;resume():void;stop():Promise<Take>;cancel():void;seconds():number;info:{width:number;height:number;fps:number;sampleRate:number;videoMime:string}};

export const AUDIO_KBPS=256;
/** Video bit rate for a given picture height: the best a browser can usefully record. */
export const videoMbps=(h:number)=>h>=2160?20:h>=1440?12:h>=1080?8:5;

export function videoConstraints(res:StudioOpts['res'],cam:string):MediaTrackConstraints{
  const size=res==='720'?{w:1280,h:720}:res==='1080'?{w:1920,h:1080}:{w:3840,h:2160};
  return {deviceId:cam&&cam!=='default'?{exact:cam}:undefined,width:{ideal:size.w},height:{ideal:size.h},frameRate:{ideal:30,max:30},aspectRatio:{ideal:16/9}};
}
export const micConstraints=(id:string,clean:boolean):MediaTrackConstraints=>({deviceId:id&&id!=='default'?{exact:id}:undefined,channelCount:{ideal:2},sampleRate:{ideal:48000},sampleSize:{ideal:24},echoCancellation:clean,noiseSuppression:clean,autoGainControl:clean});

/** The browser may not offer every format: pick the best one it has. */
export function pickVideoMime():string{
  const list=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'];
  return list.find(m=>{try{return MediaRecorder.isTypeSupported(m)}catch{return false}})||'video/webm';
}
const audioMime=()=>['audio/webm;codecs=opus','audio/webm'].find(m=>{try{return MediaRecorder.isTypeSupported(m)}catch{return false}})||'audio/webm';

/** Records 24-bit stereo PCM from an audio node and writes a WAV file: lossless. About 1 GB an hour per track. */
class WavRec{
  private chunks:Uint8Array[]=[];private node:ScriptProcessorNode;private mute:GainNode;private paused=false;private frames=0;
  constructor(private ctx:AudioContext,src:AudioNode){
    this.node=ctx.createScriptProcessor(4096,2,2);this.node.channelCount=2;this.node.channelCountMode='explicit';this.node.channelInterpretation='speakers';
    this.mute=ctx.createGain();this.mute.gain.value=0;               // the processor must be connected to run, but nothing is played
    src.connect(this.node);this.node.connect(this.mute);this.mute.connect(ctx.destination);
    this.node.onaudioprocess=e=>{if(this.paused)return;const a=e.inputBuffer.getChannelData(0),b=e.inputBuffer.numberOfChannels>1?e.inputBuffer.getChannelData(1):a;
      const n=a.length;const out=new Uint8Array(n*6);let o=0;
      for(let i=0;i<n;i++){for(const s of [a[i],b[i]]){const v=Math.max(-1,Math.min(1,s));const q=Math.round(v<0?v*8388608:v*8388607);out[o++]=q&255;out[o++]=(q>>8)&255;out[o++]=(q>>16)&255}}
      this.chunks.push(out);this.frames+=n};
  }
  pause(){this.paused=true}resume(){this.paused=false}
  finish():Blob{
    try{this.node.onaudioprocess=null;this.node.disconnect();this.mute.disconnect()}catch{}
    const rate=this.ctx.sampleRate,dataLen=this.frames*6,h=new DataView(new ArrayBuffer(44));
    const w=(o:number,s:string)=>{for(let i=0;i<s.length;i++)h.setUint8(o+i,s.charCodeAt(i))};
    w(0,'RIFF');h.setUint32(4,36+dataLen,true);w(8,'WAVE');w(12,'fmt ');h.setUint32(16,16,true);h.setUint16(20,1,true);h.setUint16(22,2,true);h.setUint32(24,rate,true);h.setUint32(28,rate*6,true);h.setUint16(32,6,true);h.setUint16(34,24,true);w(36,'data');h.setUint32(40,dataLen,true);
    return new Blob([h.buffer,...this.chunks as BlobPart[]],{type:'audio/wav'});
  }
}

/** One recording: the mixed master plus a separate track for each microphone. Open the devices (levels and preview work at once), then call start(). */
export async function openSession(o:StudioOpts,onLevel:(peaks:number[])=>void):Promise<Session>{
  if(!o.mics.length)throw new Error('Choose at least one microphone.');
  if(typeof MediaRecorder==='undefined')throw new Error('This browser cannot record. Use a current Chrome, Edge, Firefox or Safari.');
  const opened:MediaStream[]=[];const closeAll=()=>opened.forEach(s=>s.getTracks().forEach(t=>t.stop()));
  try{
    const ctx=new AudioContext({sampleRate:48000,latencyHint:'playback'});await ctx.resume().catch(()=>{});
    const micStreams:MediaStream[]=[];
    for(const m of o.mics){const s=await navigator.mediaDevices.getUserMedia({audio:micConstraints(m.id,o.clean)});opened.push(s);micStreams.push(s)}
    let vstream:MediaStream|null=null;
    if(o.cam&&o.cam!=='none'){vstream=await navigator.mediaDevices.getUserMedia({video:videoConstraints(o.res,o.cam)});opened.push(vstream)}
    const dest=ctx.createMediaStreamDestination();dest.channelCount=2;const mix=ctx.createGain();mix.connect(dest);
    const srcs=micStreams.map(s=>ctx.createMediaStreamSource(s));
    const peaks=o.mics.map(()=>0);const analysers=srcs.map((s,i)=>{const a=ctx.createAnalyser();a.fftSize=1024;s.connect(a);s.connect(mix);return a});
    const buf=new Float32Array(1024);
    const meter=setInterval(()=>{analysers.forEach((a,i)=>{a.getFloatTimeDomainData(buf);let p=0;for(let k=0;k<buf.length;k++)p=Math.max(p,Math.abs(buf[k]));peaks[i]=p});onLevel([...peaks])},100);
    const vt=vstream?.getVideoTracks()[0];const st=vt?.getSettings()||{};const width=Math.round(st.width||0),height=Math.round(st.height||0);
    const hasVideo=!!vt&&width>0;const vmime=pickVideoMime();
    const recs:{label:string;mr?:MediaRecorder;wav?:WavRec;chunks:Blob[];ext:'webm'|'wav'}[]=[];
    const makeMr=(stream:MediaStream,mime:string,opts:MediaRecorderOptions,label:string)=>{const r={label,chunks:[] as Blob[],ext:'webm' as const,mr:new MediaRecorder(stream,{mimeType:mime,...opts})};r.mr.ondataavailable=e=>{if(e.data.size)r.chunks.push(e.data)};return r};
    let master:typeof recs[number];
    if(hasVideo){master=makeMr(new MediaStream([vt!,...dest.stream.getAudioTracks()]),vmime,{videoBitsPerSecond:videoMbps(height)*1_000_000,audioBitsPerSecond:AUDIO_KBPS*1000},'Master')}
    else if(o.audio==='wav'){const w=new WavRec(ctx,mix);master={label:'Master',wav:w,chunks:[],ext:'wav'}}
    else master=makeMr(dest.stream,audioMime(),{audioBitsPerSecond:AUDIO_KBPS*1000},'Master');
    const separate:typeof recs=[];
    if(o.mics.length>1||hasVideo)o.mics.forEach((m,i)=>{const label=(m.label||`Microphone ${i+1}`).replace(/\s*\([0-9a-f]{4}:[0-9a-f]{4}\)\s*$/i,'');
      if(o.audio==='wav')separate.push({label,wav:new WavRec(ctx,srcs[i]),chunks:[],ext:'wav'});else separate.push(makeMr(micStreams[i],audioMime(),{audioBitsPerSecond:AUDIO_KBPS*1000},label))});
    recs.push(master,...separate);
    let started=0,paused=0,pausedAt=0,done=false;
    const secs=()=>started?Math.max(0,((pausedAt||performance.now())-started-paused)/1000):0;
    recs.forEach(r=>r.wav?.pause());                        // until Start is pressed the microphones only feed the level meters
    const begin=()=>{recs.forEach(r=>{r.mr?.start(1000);r.wav?.resume()});started=performance.now()};
    const stopMr=(r:typeof recs[number])=>new Promise<void>(res=>{if(!r.mr||r.mr.state==='inactive'){res();return}r.mr.onstop=()=>res();try{r.mr.stop()}catch{res()}});
    const shutdown=()=>{if(done)return;done=true;clearInterval(meter);closeAll();ctx.close().catch(()=>{})};
    return {
      stream:vstream,info:{width,height,fps:Math.round(st.frameRate||0),sampleRate:ctx.sampleRate,videoMime:hasVideo?vmime:''},seconds:secs,
      start(){if(!started)begin()},
      pause(){if(pausedAt)return;recs.forEach(r=>{r.mr?.state==='recording'&&r.mr.pause();r.wav?.pause()});pausedAt=performance.now()},
      resume(){if(!pausedAt)return;paused+=performance.now()-pausedAt;pausedAt=0;recs.forEach(r=>{r.mr?.state==='paused'&&r.mr.resume();r.wav?.resume()})},
      cancel(){recs.forEach(r=>{try{r.mr&&r.mr.state!=='inactive'&&r.mr.stop()}catch{}});shutdown()},
      async stop(){
        const total=secs();await Promise.all(recs.map(stopMr));
        const out=(r:typeof recs[number])=>r.wav?r.wav.finish():new Blob(r.chunks,{type:r.mr?.mimeType||'audio/webm'});
        const take:Take={master:out(master),ext:master.ext,hasVideo,width:hasVideo?width:0,height:hasVideo?height:0,seconds:Math.round(total),audioKbps:o.audio==='wav'&&!hasVideo?Math.round(ctx.sampleRate*48/1000):AUDIO_KBPS,
          audioLabel:o.audio==='wav'&&!hasVideo?'Lossless WAV, 24-bit, 48 kHz':'Opus, 256 kbps, 48 kHz stereo',tracks:separate.map(r=>({label:r.label,blob:out(r),ext:r.ext}))};
        shutdown();return take;
      },
    };
  }catch(e){closeAll();throw e}
}

export const prettyBytes=(n:number)=>n>=1073741824?`${(n/1073741824).toFixed(2)} GB`:n>=1048576?`${(n/1048576).toFixed(1)} MB`:`${Math.max(1,Math.round(n/1024))} KB`;
export const clock=(s:number)=>{s=Math.max(0,Math.round(s));const h=Math.floor(s/3600),m=Math.floor(s%3600/60),r=s%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(r).padStart(2,'0')};
export const slug=(s:string)=>(s||'podcast').replace(/[^\w .-]+/g,'_').trim().slice(0,60)||'podcast';
