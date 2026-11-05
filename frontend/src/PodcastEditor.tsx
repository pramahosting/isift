import React,{useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Scissors,Plus,Trash2,ArrowLeft,ArrowRight,Play,Pause,Mic,Square,Film,Upload,Youtube,Save,Loader2,SkipBack,Copy,Wand2,Check} from 'lucide-react';
import {Req,Job,followJob,PostToYouTube} from './PodcastYouTube';
import {BgProcessor,PRESETS,readImage} from './vbg';
import type {BgMode} from './vbg';
import {clock} from './podcast';

type Cloud={group_id:string;title:string;created_at:string;tracks:{id:string;label:string;is_master:boolean;has_video:boolean;width:number;height:number;duration_s:number;size_bytes:number;mimetype:string}[]};
type Src={key:string;kind:'rec'|'asset';id:string;label:string;url:string;duration:number;hasVideo:boolean;hasAudio:boolean;width:number;height:number};
type Seg={uid:number;src:string;start:number;end:number};
type VO={uid:number;src:string;label:string;at:number;gain:number;duration:number};
const r3=(n:number)=>Math.round(n*1000)/1000;
const fmt=(s:number)=>{const m=Math.floor(s/60),x=s-m*60;return `${m}:${x<10?'0':''}${x.toFixed(1)}`};
let uidN=1;

/** Edit a podcast video: cut, trim, join, insert a clip inside a video, smooth the joins, add a voice-over, change the background.
 *  The original is never changed: the finished edit is saved as a new podcast. */
export function PodcastEditor({allowed,request,token,podcasts,start,onSaved,openSettings}:{allowed:boolean;request:Req;token:string;podcasts:Cloud[];start:{gid:string;n:number}|null;onSaved:()=>void;openSettings:()=>void}){
  const [srcs,setSrcs]=useState<Src[]>([]),[segs,setSegs]=useState<Seg[]>([]),[cur,setCur]=useState(0),[pos,setPos]=useState(0),[vos,setVos]=useState<VO[]>([]);
  const [smooth,setSmooth]=useState(true),[xf,setXf]=useState(0.5),[fadeIn,setFadeIn]=useState(0.5),[fadeOut,setFadeOut]=useState(1),[polish,setPolish]=useState(false),[origVol,setOrigVol]=useState(100),[height,setHeight]=useState('source');
  const [bgMode,setBgMode]=useState<'none'|'color'|'image'>('none'),[key,setKey]=useState('#00ff00'),[sim,setSim]=useState(0.25),[bgColor,setBgColor]=useState('#1b2a41'),[bgImg,setBgImg]=useState('');
  const [title,setTitle]=useState(''),[busy,setBusy]=useState(''),[err,setErr]=useState(''),[job,setJob]=useState<Job|null>(null),[playAll,setPlayAll]=useState(false),[recVO,setRecVO]=useState(false),[post,setPost]=useState<{gid:string;title:string}|null>(null);
  const [cutA,setCutA]=useState(''),[cutB,setCutB]=useState(''),[aiBusy,setAiBusy]=useState(-1);
  const vid=useRef<HTMLVideoElement>(null),file=useRef<HTMLInputElement>(null),imgFile=useRef<HTMLInputElement>(null),voFile=useRef<HTMLInputElement>(null),want=useRef<{t:number;play:boolean}|null>(null),shown=useRef('');
  const recorder=useRef<{mr:MediaRecorder;stream:MediaStream;chunks:Blob[];at:number}|null>(null),aiStop=useRef<(()=>void)|null>(null);

  const src=(k:string)=>srcs.find(s=>s.key===k);
  const seg=segs[cur];const sSrc=seg?src(seg.src):undefined;
  const nextKey=useCallback(()=>{let n=srcs.length+1;while(srcs.some(s=>s.key==='s'+n))n++;return 's'+n},[srcs]);

  // ---- timeline arithmetic (matches the server) ----
  const xfEff=useMemo(()=>{if(!smooth||segs.length<2)return 0;const shortest=Math.min(...segs.map(s=>s.end-s.start));return Math.max(0,Math.min(xf,2,shortest/2-0.01))},[smooth,xf,segs]);
  const startOf=(i:number)=>segs.slice(0,i).reduce((a,s)=>a+(s.end-s.start),0)-xfEff*i;
  const total=Math.max(0,segs.reduce((a,s)=>a+(s.end-s.start),0)-xfEff*Math.max(0,segs.length-1));
  const headT=seg?startOf(cur)+Math.max(0,pos-seg.start):0;                   // the playhead on the finished timeline

  // ---- adding clips to the bin ----
  const addSrc=(s:Omit<Src,'key'>):Src=>{const full={...s,key:nextKey()};setSrcs(x=>[...x,full]);return full};
  const openRec=async(id:string,label:string):Promise<Src|null>=>{
    const have=srcs.find(s=>s.kind==='rec'&&s.id===id);if(have)return have;
    setErr('');setBusy('Opening the video…');
    try{const o=await request(`/podcasts/edit/open/${id}`,{method:'POST'});return addSrc({kind:'rec',id,label:label||o.label,url:o.url,duration:o.duration,hasVideo:o.has_video,hasAudio:o.has_audio,width:o.width,height:o.height})}
    catch(e:any){setErr(e.message);return null}finally{setBusy('')}
  };
  const upAsset=async(f:File|Blob,name:string,kind:'clip'|'voice'|'image')=>{
    const fd=new FormData();fd.append('kind',kind);fd.append('file',f,name);
    const a=await request('/podcasts/edit/assets',{method:'POST',body:fd});return a};
  const addLocal=async(f:File)=>{
    setErr('');setBusy('Uploading the clip…');
    try{const a=await upAsset(f,f.name,'clip');addSrc({kind:'asset',id:a.id,label:a.label,url:a.url,duration:a.duration,hasVideo:a.has_video,hasAudio:a.has_audio,width:a.width,height:a.height})}
    catch(e:any){setErr(e.message)}finally{setBusy('')}
  };
  const startWith=async(gid:string)=>{
    const g=podcasts.find(x=>x.group_id===gid);const t=g?.tracks.find(x=>x.is_master)||g?.tracks[0];if(!g||!t)return;
    const s=await openRec(t.id,g.title||'Podcast');if(!s)return;
    setSegs([{uid:uidN++,src:s.key,start:0,end:r3(s.duration)}]);setCur(0);setTitle(g.title?g.title+' (edited)':'');want.current={t:0,play:false};
  };
  const first=useRef(0);
  useEffect(()=>{if(start&&first.current!==start.n){first.current=start.n;void startWith(start.gid)}},[start?.n]);   // eslint-disable-line

  // ---- preview: show the selected piece, play it, or play the whole timeline ----
  const goTo=(i:number,t?:number,play=false)=>{const s=segs[i];if(!s)return;setCur(i);want.current={t:t??s.start,play};const v=vid.current;const sc=src(s.src);if(v&&sc&&shown.current===sc.url){v.currentTime=want.current.t;if(play)v.play().catch(()=>{});want.current=null}};
  useEffect(()=>{
    const v=vid.current;if(!v||!sSrc)return;
    if(shown.current!==sSrc.url){shown.current=sSrc.url;v.src=sSrc.url;v.load()}
    else if(want.current){v.currentTime=want.current.t;if(want.current.play)v.play().catch(()=>{});want.current=null}
  },[cur,sSrc?.url]);   // eslint-disable-line
  const onMeta=()=>{const v=vid.current;if(v&&want.current){v.currentTime=want.current.t;if(want.current.play)v.play().catch(()=>{});want.current=null}};
  const onTime=()=>{
    const v=vid.current;if(!v||!seg)return;setPos(v.currentTime);
    if(!v.paused&&v.currentTime>=seg.end-0.04){
      if(playAll&&cur<segs.length-1){goTo(cur+1,undefined,true)}
      else{v.pause();v.currentTime=seg.end;setPos(seg.end);setPlayAll(false);if(recorder.current)void stopVO()}
    }
  };
  const toggle=()=>{const v=vid.current;if(!v||!seg)return;if(v.paused){if(v.currentTime<seg.start||v.currentTime>=seg.end-0.05)v.currentTime=seg.start;v.play().catch(()=>{})}else{v.pause();setPlayAll(false)}};
  const playTimeline=()=>{if(!segs.length)return;setPlayAll(true);goTo(0,undefined,true)};

  // ---- editing the timeline ----
  const edit=(f:(s:Seg[])=>Seg[],sel?:number)=>{setSegs(s=>f(s.map(x=>({...x}))));if(sel!==undefined)setCur(sel)};
  const setRange=(a:number,b:number)=>{if(!seg||!sSrc)return;const s=Math.max(0,Math.min(a,sSrc.duration)),e=Math.max(0,Math.min(b,sSrc.duration));if(e-s<0.2)return;edit(x=>{x[cur].start=r3(s);x[cur].end=r3(e);return x})};
  const splitHere=()=>{if(!seg)return;const t=r3(pos);if(t<=seg.start+0.2||t>=seg.end-0.2){setErr('Move the playhead inside the piece first.');return}setErr('');edit(x=>{const a=x[cur];x.splice(cur+1,0,{uid:uidN++,src:a.src,start:t,end:a.end});a.end=t;return x},cur+1)};
  const remove=(i:number)=>{if(segs.length<2){setErr('The timeline needs at least one piece.');return}setErr('');edit(x=>{x.splice(i,1);return x},Math.max(0,Math.min(cur,segs.length-2)))};
  const move=(i:number,d:number)=>{const j=i+d;if(j<0||j>=segs.length)return;edit(x=>{[x[i],x[j]]=[x[j],x[i]];return x},j)};
  const dup=(i:number)=>edit(x=>{x.splice(i+1,0,{...x[i],uid:uidN++});return x},i+1);
  /** Cut out a section of the video: everything between a and b (seconds into the picked video) is removed and the rest closes up. */
  const cutOut=()=>{
    if(!seg)return;const a=parseFloat(cutA),b=parseFloat(cutB);
    if(!(a>=seg.start&&b<=seg.end&&b-a>=0.1)){setErr(`Enter a start and end between ${fmt(seg.start)} and ${fmt(seg.end)} (seconds), with the end after the start.`);return}
    setErr('');const L=a-seg.start>=0.2,R=seg.end-b>=0.2;
    if(!L&&!R){remove(cur);return}
    edit(x=>{const o=x[cur],parts:Seg[]=[];if(L)parts.push({uid:uidN++,src:o.src,start:o.start,end:r3(a)});if(R)parts.push({uid:uidN++,src:o.src,start:r3(b),end:o.end});x.splice(cur,1,...parts);return x},cur);
    setCutA('');setCutB('');
  };
  /** Put a whole clip into the video at the playhead. A 10 second video with a 2 second clip put in at 4 seconds becomes 4 + 2 + 6 = 12 seconds. */
  const insertAt=(s:Src,atPlayhead:boolean)=>{
    const piece:Seg={uid:uidN++,src:s.key,start:0,end:r3(s.duration)};
    if(!segs.length){setSegs([piece]);setCur(0);return}
    if(!atPlayhead||!seg){setSegs(x=>[...x,piece]);setCur(segs.length);return}
    const t=r3(pos);
    if(t<=seg.start+0.2){edit(x=>{x.splice(cur,0,piece);return x},cur);return}
    if(t>=seg.end-0.2){edit(x=>{x.splice(cur+1,0,piece);return x},cur+1);return}
    edit(x=>{const a=x[cur];x.splice(cur+1,0,piece,{uid:uidN++,src:a.src,start:t,end:a.end});a.end=t;return x},cur+1);
  };

  // ---- voice-over: record the microphone while the video plays ----
  const startVO=async()=>{
    if(!seg||recorder.current)return;setErr('');
    try{
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}});
      const mr=new MediaRecorder(stream);const chunks:Blob[]=[];mr.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
      recorder.current={mr,stream,chunks,at:r3(headT)};mr.start(250);setRecVO(true);setPlayAll(true);goTo(cur,pos<seg.end-0.3?pos:seg.start,true);
    }catch(e:any){setErr(e?.name==='NotAllowedError'?'Allow the microphone in the address bar, then try again.':(e?.message||'Could not open the microphone.'))}
  };
  const stopVO=async()=>{
    const r=recorder.current;if(!r)return;recorder.current=null;setRecVO(false);vid.current?.pause();setPlayAll(false);
    await new Promise<void>(res=>{r.mr.onstop=()=>res();try{r.mr.stop()}catch{res()}});r.stream.getTracks().forEach(t=>t.stop());
    const blob=new Blob(r.chunks,{type:'audio/webm'});if(blob.size<2000){setErr('Nothing was recorded.');return}
    setBusy('Saving the voice-over…');
    try{const a=await upAsset(blob,'voiceover.webm','voice');const s=addSrcOnly({kind:'asset',id:a.id,label:'Voice-over',url:a.url,duration:a.duration,hasVideo:false,hasAudio:true,width:0,height:0});setVos(v=>[...v,{uid:uidN++,src:s.key,label:'Voice-over '+(v.length+1),at:r.at,gain:1,duration:a.duration}])}
    catch(e:any){setErr(e.message)}finally{setBusy('')}
  };
  const addSrcOnly=(s:Omit<Src,'key'>):Src=>{const key='v'+uidN++;const full={...s,key};setSrcs(x=>[...x,full]);return full};
  const addVOFile=async(f:File)=>{setErr('');setBusy('Uploading the voice-over…');try{const a=await upAsset(f,f.name,'voice');const s=addSrcOnly({kind:'asset',id:a.id,label:a.label,url:a.url,duration:a.duration,hasVideo:false,hasAudio:true,width:0,height:0});setVos(v=>[...v,{uid:uidN++,src:s.key,label:a.label,at:r3(headT),gain:1,duration:a.duration}])}catch(e:any){setErr(e.message)}finally{setBusy('')}};
  useEffect(()=>()=>{recorder.current?.stream.getTracks().forEach(t=>t.stop());aiStop.current?.()},[]);

  // ---- background ----
  const pickBgImage=async(f:File)=>{setErr('');setBusy('Uploading the picture…');try{const url=await readImage(f);const blob=await (await fetch(url)).blob();const a=await upAsset(blob,'background.jpg','image');const s=addSrcOnly({kind:'asset',id:a.id,label:'Background',url:a.url,duration:0,hasVideo:true,hasAudio:false,width:0,height:0});setBgImg(s.key);setBgMode('image')}catch(e:any){setErr(e.message||'That picture could not be opened.')}finally{setBusy('')}};
  /** Replace the background of a person filmed in front of any room (no green screen). The picture is cut out frame by frame in this browser while the video plays through once, so it takes as long as the video. */
  const aiBackground=async(i:number,mode:BgMode)=>{
    const s=srcs[i];if(!s||!s.hasVideo)return;setErr('');setAiBusy(0);
    const v=document.createElement('video');v.src=s.url;v.muted=false;v.playsInline=true;v.crossOrigin='anonymous';
    let proc:BgProcessor|null=null,ctx:AudioContext|null=null,stopped=false;
    const cleanup=()=>{try{proc?.stop()}catch{}try{ctx?.close()}catch{}v.pause();v.removeAttribute('src');v.load();setAiBusy(-1);aiStop.current=null};
    aiStop.current=()=>{stopped=true;cleanup()};
    try{
      await new Promise<void>((ok,no)=>{v.onloadedmetadata=()=>ok();v.onerror=()=>no(new Error('The video could not be opened.'))});
      const cap:MediaStream=(v as any).captureStream?(v as any).captureStream():(v as any).mozCaptureStream();
      const raw=cap.getVideoTracks()[0];if(!raw)throw new Error('This browser cannot process the video. Use a current Chrome or Edge.');
      proc=new BgProcessor(raw);proc.setMode(mode);
      const ready=await new Promise<boolean>(res=>{proc!.onready=()=>res(true);proc!.onfail=()=>res(false);v.play().catch(()=>{});setTimeout(()=>res(false),12000)});
      if(!ready)throw new Error('The background tool could not start. Check your connection and try again.');
      ctx=new AudioContext();const dest=ctx.createMediaStreamDestination();if(s.hasAudio)ctx.createMediaElementSource(v).connect(dest);        // the sound is taken from the video without playing out loud
      const out=new MediaStream([proc.track,...dest.stream.getAudioTracks()]);
      const mime=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'].find(m=>MediaRecorder.isTypeSupported(m))||'video/webm';
      const mr=new MediaRecorder(out,{mimeType:mime,videoBitsPerSecond:8_000_000,audioBitsPerSecond:192_000});const chunks:Blob[]=[];mr.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
      v.currentTime=0;await new Promise(r=>setTimeout(r,200));mr.start(1000);await v.play();
      const tick=setInterval(()=>setAiBusy(Math.min(99,Math.round(v.currentTime*100/(s.duration||1)))),400);
      await new Promise<void>(res=>{v.onended=()=>res();const w=setInterval(()=>{if(stopped){clearInterval(w);res()}},500)});
      clearInterval(tick);await new Promise<void>(res=>{mr.onstop=()=>res();try{mr.stop()}catch{res()}});
      if(stopped)return;
      setBusy('Saving the new video…');
      const a=await upAsset(new Blob(chunks,{type:'video/webm'}),'background-changed.webm','clip');
      const ns=addSrcOnly({kind:'asset',id:a.id,label:s.label+' (new background)',url:a.url,duration:a.duration,hasVideo:true,hasAudio:a.has_audio,width:a.width,height:a.height});
      setSegs(x=>x.map(g=>g.src===s.key?{...g,src:ns.key,end:Math.min(g.end,r3(a.duration))}:g));shown.current='';setCur(c=>c);
    }catch(e:any){if(!stopped)setErr(e.message||'The background could not be changed.')}
    finally{cleanup();setBusy('')}
  };

  // ---- save ----
  const used=useMemo(()=>{const k=new Set<string>();segs.forEach(s=>k.add(s.src));vos.forEach(v=>k.add(v.src));if(bgMode==='image'&&bgImg)k.add(bgImg);return k},[segs,vos,bgMode,bgImg]);
  const render=async()=>{
    setErr('');setJob(null);
    if(!segs.length){setErr('Add a video to the timeline first.');return}
    const sources:any={};srcs.filter(s=>used.has(s.key)).forEach(s=>{sources[s.key]={kind:s.kind,id:s.id}});
    const body:any={title:title.trim(),sources,segments:segs.map(s=>({source:s.src,start:s.start,end:s.end})),crossfade:smooth?xf:0,fade_in:fadeIn,fade_out:fadeOut,polish,height,
      original_volume:origVol/100,voiceovers:vos.map(v=>({source:v.src,at:v.at,gain:v.gain}))};
    if(bgMode==='color')body.background={mode:'color',key_color:key.slice(1),similarity:sim,color:bgColor.slice(1)};
    if(bgMode==='image'&&bgImg)body.background={mode:'image',key_color:key.slice(1),similarity:sim,image:bgImg};
    try{
      const r=await request('/podcasts/edit/render',{method:'POST',body:JSON.stringify(body)});
      setJob({id:r.job_id,status:'working',percent:0,message:'Starting…'});
      const j=await followJob(request,r.job_id,setJob);setJob(j);if(j.status==='done')onSaved();
    }catch(e:any){setErr(e.message)}
  };
  const working=job?.status==='working';
  const bin=podcasts.filter(g=>g.tracks.some(t=>t.is_master));

  if(!allowed)return <section className="panel pod-step" role="tabpanel"><h3><Film size={18}/> Edit videos</h3><p><b>The video editor is part of the paid plans (Standard and Business).</b></p><p className="muted">Cut and trim, cut out a section, join videos, insert a clip inside a video, smooth the joins, add a voice-over and change the background, then post to YouTube with one click. Upgrade your plan to use it. Your recordings are not affected.</p></section>;
  if(!bin.length&&!srcs.length)return <section className="panel pod-step"><h3>Edit videos</h3><p className="muted">Editing works on podcasts kept in the cloud. Record a podcast and choose "In the cloud" when you save it, then come back here.</p><p className="muted small">If your plan keeps recordings on your own computer only, you can still add video clips from this computer here once cloud podcasts are allowed on your plan.</p></section>;
  return <section className="panel pod-step pod-edit" role="tabpanel">
    <h3><Film size={18}/> Edit videos</h3>
    <p className="muted small">Your original is never changed. The finished edit is saved as a new podcast next to it.</p>
    {err&&<p className="error" role="alert">{err}</p>}{busy&&<p className="muted"><Loader2 size={14} className="spin"/> {busy}</p>}
    <div className="pod-ed-grid">
      <div className="pod-ed-main">
        {!segs.length&&<div className="pod-ed-start"><b>Start with a video</b><select defaultValue="" onChange={e=>{if(e.target.value)void startWith(e.target.value)}}><option value="">Choose a podcast…</option>{bin.map(g=><option key={g.group_id} value={g.group_id}>{g.title||'Podcast'} ({new Date(g.created_at).toLocaleDateString()})</option>)}</select><span className="muted small">or add a clip from this computer on the right.</span></div>}
        <div className="pod-ed-player">
          {seg&&sSrc?(sSrc.hasVideo?<video ref={vid} playsInline preload="auto" onLoadedMetadata={onMeta} onTimeUpdate={onTime} onPause={()=>{}} aria-label="Preview"/>:<><audio ref={vid as any} preload="auto" onLoadedMetadata={onMeta} onTimeUpdate={onTime} aria-label="Preview"/><div className="pod-novideo"><Mic size={40}/><span>Sound only</span></div></>):<div className="pod-novideo"><Film size={40}/><span>Nothing to preview yet</span></div>}
        </div>
        {seg&&<div className="pod-ed-bar">
          <button className="secondary" onClick={()=>goTo(cur,seg.start)} aria-label="Back to the start of this piece"><SkipBack size={14}/></button>
          <button className="primary" onClick={toggle}>{vid.current&&!vid.current.paused?<Pause size={14}/>:<Play size={14}/>} Play piece</button>
          <button className="secondary" onClick={playTimeline}><Play size={14}/> Play all</button>
          <input type="range" min={seg.start} max={seg.end} step={0.05} value={Math.min(Math.max(pos,seg.start),seg.end)} onChange={e=>{const t=+e.target.value;setPos(t);if(vid.current)vid.current.currentTime=t}} aria-label="Position"/>
          <span className="pod-ed-time">{fmt(pos)} · timeline {fmt(headT)} / {fmt(total)}</span></div>}
        <div className="pod-tl" aria-label="Timeline">{segs.map((s,i)=>{const d=s.end-s.start;return <button key={s.uid} className={'pod-seg'+(i===cur?' on':'')+(src(s.src)?.kind==='asset'?' clip':'')} style={{flexGrow:Math.max(d,0.5)}} onClick={()=>goTo(i)} title={`${src(s.src)?.label||''} ${fmt(s.start)}–${fmt(s.end)}`}><b>{i+1}</b><span>{src(s.src)?.label}</span><small>{fmt(d)}</small></button>})}
          {vos.map(v=><span key={v.uid} className="pod-vo-mark" style={{left:(total?Math.min(98,v.at*100/total):0)+'%'}} title={v.label}><Mic size={11}/></span>)}</div>
        {seg&&sSrc&&<div className="pod-ed-tools">
          <div className="pod-ed-row"><b>Piece {cur+1}</b><span className="muted small">{sSrc.label}</span>
            <label>From (s)<input type="number" min={0} max={sSrc.duration} step={0.1} value={seg.start} onChange={e=>setRange(+e.target.value,seg.end)}/></label>
            <label>To (s)<input type="number" min={0} max={sSrc.duration} step={0.1} value={seg.end} onChange={e=>setRange(seg.start,+e.target.value)}/></label>
            <button className="secondary" onClick={()=>setRange(r3(pos),seg.end)}>Start here</button><button className="secondary" onClick={()=>setRange(seg.start,r3(pos))}>End here</button></div>
          <div className="pod-ed-row"><button className="secondary" onClick={splitHere}><Scissors size={14}/> Split at playhead</button>
            <button className="secondary" onClick={()=>move(cur,-1)} disabled={cur===0}><ArrowLeft size={14}/></button><button className="secondary" onClick={()=>move(cur,1)} disabled={cur>=segs.length-1}><ArrowRight size={14}/></button>
            <button className="secondary" onClick={()=>dup(cur)}><Copy size={14}/> Duplicate</button><button className="secondary danger" onClick={()=>remove(cur)}><Trash2 size={14}/> Delete piece</button></div>
          <div className="pod-ed-row"><b>Cut out a section</b><label>from (s)<input type="number" step={0.1} value={cutA} placeholder={String(r3(pos))} onChange={e=>setCutA(e.target.value)}/></label><label>to (s)<input type="number" step={0.1} value={cutB} onChange={e=>setCutB(e.target.value)}/></label>
            <button className="secondary" onClick={()=>setCutA(String(r3(pos)))}>Use playhead</button><button className="secondary danger" onClick={cutOut}><Scissors size={14}/> Remove it</button></div>
        </div>}
      </div>
      <aside className="pod-ed-side">
        <h4>Clips</h4>
        {srcs.filter(s=>!s.key.startsWith('v')).map(s=><div key={s.key} className="pod-bin"><div><b>{s.label}</b><small className="muted">{clock(Math.round(s.duration))}{s.width?` · ${s.width}×${s.height}`:''}</small></div>
          <div className="pod-bin-b"><button className="secondary" onClick={()=>insertAt(s,false)} title="Join to the end"><Plus size={13}/> Add to end</button><button className="secondary" onClick={()=>insertAt(s,true)} disabled={!seg} title="Put this clip into the video at the playhead"><Plus size={13}/> Insert at playhead</button></div></div>)}
        <select value="" onChange={async e=>{const g=bin.find(x=>x.group_id===e.target.value);const t=g?.tracks.find(x=>x.is_master);if(g&&t){const s=await openRec(t.id,g.title||'Podcast');if(s&&!segs.length){setSegs([{uid:uidN++,src:s.key,start:0,end:r3(s.duration)}]);setCur(0)}}}}><option value="">Add one of my podcasts…</option>{bin.map(g=><option key={g.group_id} value={g.group_id}>{g.title||'Podcast'}</option>)}</select>
        <input ref={file} type="file" accept="video/*,audio/*,.mp4,.webm,.mov,.mkv" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void addLocal(f)}}/>
        <button className="secondary" onClick={()=>file.current?.click()}><Upload size={14}/> Add a clip from this computer</button>

        <h4>Smooth</h4>
        <label className="pod-check"><input type="checkbox" checked={smooth} onChange={e=>setSmooth(e.target.checked)}/> Blend the joins (picture and sound fade across each cut)</label>
        {smooth&&<label>Blend length: {xf.toFixed(1)} s<input type="range" min={0.1} max={2} step={0.1} value={xf} onChange={e=>setXf(+e.target.value)}/></label>}
        <label>Fade in: {fadeIn.toFixed(1)} s<input type="range" min={0} max={3} step={0.1} value={fadeIn} onChange={e=>setFadeIn(+e.target.value)}/></label>
        <label>Fade out: {fadeOut.toFixed(1)} s<input type="range" min={0} max={3} step={0.1} value={fadeOut} onChange={e=>setFadeOut(+e.target.value)}/></label>
        <label className="pod-check"><input type="checkbox" checked={polish} onChange={e=>setPolish(e.target.checked)}/> Polish: reduce hiss and noise, even out the loudness</label>

        <h4>Voice-over</h4>
        <div className="pod-ctl">{!recVO?<button className="secondary" onClick={startVO} disabled={!seg||!!busy}><Mic size={14}/> Record from the playhead</button>:<button className="primary pod-recbtn" onClick={stopVO}><Square size={13}/> Stop</button>}
          <input ref={voFile} type="file" accept="audio/*,.wav,.mp3,.ogg,.webm" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void addVOFile(f)}}/><button className="secondary" onClick={()=>voFile.current?.click()}><Upload size={14}/> Add a sound file</button></div>
        <small className="muted">Wear headphones. The video plays while you speak, and your voice is placed at that moment of the finished video.</small>
        {vos.map(v=><div key={v.uid} className="pod-vo"><b>{v.label}</b><label>at (s)<input type="number" step={0.1} min={0} value={v.at} onChange={e=>setVos(x=>x.map(y=>y.uid===v.uid?{...y,at:Math.max(0,+e.target.value)}:y))}/></label>
          <label>volume<input type="range" min={0} max={2} step={0.1} value={v.gain} onChange={e=>setVos(x=>x.map(y=>y.uid===v.uid?{...y,gain:+e.target.value}:y))}/></label><button className="secondary danger" onClick={()=>setVos(x=>x.filter(y=>y.uid!==v.uid))} aria-label="Remove voice-over"><Trash2 size={13}/></button></div>)}
        <label>Original sound: {origVol}%<input type="range" min={0} max={150} step={5} value={origVol} onChange={e=>setOrigVol(+e.target.value)}/></label>

        <h4>Background</h4>
        <label>Change the background<select value={bgMode} onChange={e=>setBgMode(e.target.value as any)}><option value="none">Keep as it is</option><option value="color">Plain colour behind the person</option><option value="image">Picture behind the person</option></select></label>
        {bgMode!=='none'&&<><p className="muted small">This replaces a plain backdrop (a green screen works best). Choose the colour to remove, then what goes there.</p>
          <label>Backdrop colour to remove<input type="color" value={key} onChange={e=>setKey(e.target.value)}/></label><label>How strictly: {sim.toFixed(2)}<input type="range" min={0.05} max={0.6} step={0.01} value={sim} onChange={e=>setSim(+e.target.value)}/></label></>}
        {bgMode==='color'&&<label>New background colour<input type="color" value={bgColor} onChange={e=>setBgColor(e.target.value)}/></label>}
        {bgMode==='image'&&<><input ref={imgFile} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)void pickBgImage(f)}}/><button className="secondary" onClick={()=>imgFile.current?.click()}><Upload size={14}/> {bgImg?'Change the picture':'Choose a picture'}</button></>}
        <details className="pod-ai"><summary><Wand2 size={13}/> Any room, no green screen</summary>
          <p className="muted small">The person is cut out of the picked clip in this browser and placed on a studio picture. The clip plays through once while this works, so it takes as long as the clip, and this page must stay open. The sound is kept.</p>
          {sSrc&&sSrc.hasVideo?(aiBusy>=0?<div className="pod-ctl"><span className="muted small"><Loader2 size={13} className="spin"/> Working… {aiBusy}%</span><button className="secondary" onClick={()=>aiStop.current?.()}>Cancel</button></div>
            :<div className="pod-ctl">{PRESETS.slice(0,4).map(p=><button key={p.id} className="secondary" onClick={()=>void aiBackground(srcs.indexOf(sSrc),{kind:'image',id:p.id,url:p.url})}>{p.name}</button>)}<button className="secondary" onClick={()=>void aiBackground(srcs.indexOf(sSrc),{kind:'blur',level:12})}>Blur room</button></div>):<small className="muted">Pick a piece with a picture first.</small>}</details>

        <h4>Save</h4>
        <label>Title of the new video<input value={title} maxLength={120} onChange={e=>setTitle(e.target.value)} placeholder="Episode 1 (edited)"/></label>
        <label>Picture size<select value={height} onChange={e=>setHeight(e.target.value)}><option value="source">Same as the original</option><option value="1080">Full HD 1080p (at most)</option><option value="720">HD 720p (at most)</option><option value="480">480p (small file)</option></select></label>
        <p className="muted small">Finished length: <b>{fmt(total)}</b> ({segs.length} piece{segs.length===1?'':'s'}{vos.length?`, ${vos.length} voice-over${vos.length>1?'s':''}`:''}).</p>
        <button className="primary" onClick={render} disabled={working||!segs.length||recVO||aiBusy>=0}><Save size={15}/> Save as a new video</button>
        {job&&<div className="pod-job" aria-live="polite">
          {working&&<div className="pod-prog" role="progressbar" aria-valuenow={job.percent}><u style={{width:job.percent+'%'}}/><span>{job.message||'Working…'} {job.percent}%</span></div>}
          {job.status==='error'&&<p className="error" role="alert">{job.message}</p>}
          {job.status==='done'&&<><p className="pod-ok"><Check size={15}/> {job.message}</p><div className="pod-ctl"><button className="primary" onClick={()=>setPost({gid:job.group_id||'',title:title.trim()})}><Youtube size={15}/> Post to YouTube</button></div></>}</div>}
      </aside>
    </div>
    {post&&post.gid&&<PostToYouTube request={request} groupId={post.gid} title={post.title} onClose={()=>setPost(null)} openSettings={openSettings}/>}
  </section>;
}
