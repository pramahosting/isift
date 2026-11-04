import React,{useEffect,useRef,useState,useCallback} from 'react';
import {Podcast,Mic,Camera,Pause,Play,Square,Cloud,HardDrive,Download,Trash2,Check,Info} from 'lucide-react';
import {openSession,Session,Take,Mic as MicDev,prettyBytes,clock,slug,videoMbps,AUDIO_KBPS} from './podcast';

const API=import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
type Cfg={allowed:boolean;cloud_allowed:boolean;cloud_note:string;cloud_storage:string;max_file_mb:number;max_tracks:number};
type Cloud={group_id:string;title:string;created_at:string;tracks:{id:string;label:string;is_master:boolean;has_video:boolean;width:number;height:number;duration_s:number;size_bytes:number;mimetype:string}[]};

const saveBlob=(blob:Blob,name:string)=>{const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),60000)};
const wait=(ms:number)=>new Promise(r=>setTimeout(r,ms));

/** Podcast Studio: HD podcast recording in the browser. Saved on this computer (always on Basic) or, on paid plans, in the cloud. */
export function PodcastStudio({request,token,notify}:{request:(p:string,o?:any)=>Promise<any>;token:string;notify:(m:string)=>void}){
  const [cfg,setCfg]=useState<Cfg|null>(null),[err,setErr]=useState('');
  const [mics,setMics]=useState<MicDev[]>([]),[cams,setCams]=useState<MicDev[]>([]),[ready,setReady]=useState(false);
  const [pick,setPick]=useState<string[]>([]),[cam,setCam]=useState('none'),[res,setRes]=useState<'best'|'1080'|'720'>('best'),[fmt,setFmt]=useState<'opus'|'wav'>('opus'),[clean,setClean]=useState(false);
  const [title,setTitle]=useState(''),[sess,setSess]=useState<Session|null>(null),[state,setState]=useState<'idle'|'live'|'paused'|'saving'>('idle');
  const [levels,setLevels]=useState<number[]>([]),[secs,setSecs]=useState(0),[take,setTake]=useState<Take|null>(null);
  const [dest,setDest]=useState<'local'|'cloud'>('local'),[keepCopy,setKeepCopy]=useState(true),[prog,setProg]=useState(-1),[msg,setMsg]=useState('');
  const [done,setDone]=useState(false),[mine,setMine]=useState<Cloud[]>([]);const vid=useRef<HTMLVideoElement>(null);const saved=useRef(true);

  const loadMine=useCallback(()=>request('/podcasts').then((r:Cloud[])=>setMine(r)).catch(()=>{}),[request]);
  useEffect(()=>{request('/podcasts/config').then((c:Cfg)=>setCfg(c)).catch((e:any)=>setErr(e.message||'Podcast Studio is not available.'));loadMine()},[request,loadMine]);
  useEffect(()=>{if(sess&&vid.current){vid.current.srcObject=sess.stream;vid.current.play().catch(()=>{})}},[sess]);
  useEffect(()=>{if(state!=='live')return;const t=setInterval(()=>sess&&setSecs(sess.seconds()),250);return()=>clearInterval(t)},[state,sess]);
  useEffect(()=>{const h=(e:BeforeUnloadEvent)=>{if(state==='live'||state==='paused'||(take&&!saved.current)){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',h);return()=>window.removeEventListener('beforeunload',h)},[state,take]);
  useEffect(()=>()=>{sess?.cancel()},[]);          // eslint-disable-line

  const allow=async()=>{
    setErr('');
    try{
      let s:MediaStream;try{s=await navigator.mediaDevices.getUserMedia({audio:true,video:true})}catch{s=await navigator.mediaDevices.getUserMedia({audio:true})}
      s.getTracks().forEach(t=>t.stop());
      const d=await navigator.mediaDevices.enumerateDevices();
      const m=d.filter(x=>x.kind==='audioinput'&&x.deviceId!=='communications').map((x,i)=>({id:x.deviceId,label:x.label||`Microphone ${i+1}`}));
      setMics(m);setCams(d.filter(x=>x.kind==='videoinput').map((x,i)=>({id:x.deviceId,label:x.label||`Camera ${i+1}`})));setPick(m.length?[m[0].id]:[]);setReady(true);
    }catch(e:any){setErr(e?.name==='NotAllowedError'?'The browser was not allowed to use the microphone. Allow it in the address bar, then try again.':(e?.message||'Could not open the microphone.'))}
  };
  const setupPreview=async()=>{
    sess?.cancel();setSess(null);setLevels([]);if(!ready||!pick.length)return;
    try{const s=await openSession({mics:mics.filter(m=>pick.includes(m.id)),cam,res,audio:fmt,clean},p=>setLevels(p));setSess(s);setErr('')}catch(e:any){setErr(e?.message||'Could not open the devices.')}
  };
  useEffect(()=>{if(state==='idle'&&ready&&!take)void setupPreview();/* eslint-disable-next-line */},[ready,pick.join(),cam,res,fmt,clean,!!take]);

  const start=()=>{if(!sess)return;sess.start();setSecs(0);setState('live');setTake(null);setMsg('');setDone(false);saved.current=false};
  const pause=()=>{sess?.pause();setState('paused')};const resume=()=>{sess?.resume();setState('live')};
  const stop=async()=>{if(!sess)return;setState('saving');try{const t=await sess.stop();setSess(null);setTake(t);setDone(false);setDest('local');setState('idle')}catch(e:any){setErr(e?.message||'Could not finish the recording.');setState('idle')}};
  const discard=()=>{if(!take)return;if(!saved.current&&!window.confirm('Discard this recording? It has not been saved yet.'))return;setTake(null);saved.current=true;setMsg('');setDone(false)};

  const names=(t:Take)=>{const b=slug(title);const d=new Date().toISOString().slice(0,16).replace(/[T:]/g,'-');return {master:`${b} ${d} master.${t.ext}`,track:(x:{label:string;ext:string})=>`${b} ${d} ${slug(x.label)}.${x.ext}`}};
  const saveLocal=async(t:Take)=>{const n=names(t);saveBlob(t.master,n.master);for(const x of t.tracks){await wait(500);saveBlob(x.blob,n.track(x))}};
  const upload=(t:Take)=>new Promise<void>((ok,no)=>{
    const f=new FormData();f.append('title',title||'Podcast');f.append('duration_s',String(t.seconds));f.append('width',String(t.width));f.append('height',String(t.height));f.append('audio_kbps',String(t.audioKbps));
    f.append('master',t.master,`master.${t.ext}`);t.tracks.forEach(x=>{f.append('tracks',x.blob,`track.${x.ext}`);f.append('track_labels',x.label)});
    const x=new XMLHttpRequest();x.open('POST',API+'/podcasts');x.setRequestHeader('Authorization',`Bearer ${token}`);
    x.upload.onprogress=e=>{if(e.lengthComputable)setProg(Math.round(e.loaded/e.total*100))};
    x.onload=()=>{let j:any={};try{j=JSON.parse(x.responseText)}catch{}x.status<300?ok():no(new Error(j.detail||`The upload failed (${x.status}).`))};x.onerror=()=>no(new Error('Cannot reach the iSift server.'));x.send(f)});
  const save=async()=>{
    if(!take)return;setErr('');setMsg('');
    try{
      if(dest==='cloud'){
        if(keepCopy)await saveLocal(take);
        setProg(0);await upload(take);setProg(-1);saved.current=true;setMsg('Saved in the cloud'+(keepCopy?' and on this computer.':'.')+' Find it under My cloud podcasts below.');setDone(true);loadMine();
      }else{await saveLocal(take);saved.current=true;setDone(true);setMsg(`Saved on this computer: ${1+take.tracks.length} file${take.tracks.length?'s':''} in your Downloads folder.`)}
    }catch(e:any){setProg(-1);setErr((e?.message||'Could not save.')+(dest==='cloud'?' Your recording is still here: save it on this computer instead.':''))}
  };
  const dl=async(id:string,name:string)=>{try{const r=await fetch(`${API}/podcasts/${id}/file`,{headers:{Authorization:`Bearer ${token}`}});if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||'Could not download.');saveBlob(await r.blob(),name)}catch(e:any){notify(e.message)}};
  const del=async(g:string)=>{if(!window.confirm('Delete this podcast from the cloud, with all its tracks?'))return;try{await request(`/podcasts/${g}`,{method:'DELETE'});loadMine()}catch(e:any){notify(e.message)}};

  if(err&&!cfg)return <section className="panel pod"><p className="error">{err}</p></section>;
  if(!cfg)return <section className="panel pod"><p className="muted">Loading Podcast Studio…</p></section>;
  const cloudOk=cfg.cloud_allowed;const live=state==='live'||state==='paused';
  const estMBh=(()=>{const h=sess?.info.height||0;const v=h?videoMbps(h):0;return Math.round(((v+AUDIO_KBPS/1000)/8)*3600)})();
  return <div className="pod">
    <section className="panel pod-top"><div className="pod-head"><span className="pod-ic"><Podcast size={22}/></span><div><h2>HD podcast recording</h2><p className="muted">Studio-quality sound and up to 4K video, recorded in your browser. Every microphone also gets its own separate track.</p></div></div>
      <div className="pod-badges"><span>48 kHz stereo audio</span><span>Opus 256 kbps or lossless WAV</span><span>Up to 4K video, 30 fps</span><span>Separate track per microphone</span></div></section>
    {err&&<p className="error pod-err" role="alert">{err}</p>}
    {!ready&&<section className="panel pod-step"><h3>1. Choose your equipment</h3><p className="muted">Allow the microphone (and camera, if you want video). Nothing is recorded until you press Record.</p><button className="primary" onClick={allow}><Mic size={16}/> Allow microphone and camera</button></section>}
    {ready&&!take&&<section className="panel pod-step"><div className="pod-grid">
      <div className="pod-col"><h3>Podcast</h3><label>Title<input value={title} maxLength={120} onChange={e=>setTitle(e.target.value)} placeholder="Episode 1" disabled={live}/></label>
        <fieldset disabled={live}><legend>Microphones (one track each)</legend>{mics.map(m=><label key={m.id} className="pod-check"><input type="checkbox" checked={pick.includes(m.id)} onChange={e=>setPick(p=>e.target.checked?[...p,m.id].slice(0,cfg.max_tracks):p.filter(x=>x!==m.id))}/> {m.label}</label>)}</fieldset>
        <label>Camera<select value={cam} onChange={e=>setCam(e.target.value)} disabled={live}><option value="none">No camera (audio only)</option>{cams.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
        <label>Video quality<select value={res} onChange={e=>setRes(e.target.value as any)} disabled={live||cam==='none'}><option value="best">Best the camera has (up to 4K)</option><option value="1080">Full HD 1080p</option><option value="720">HD 720p</option></select></label>
        <label>Audio format<select value={fmt} onChange={e=>setFmt(e.target.value as any)} disabled={live}><option value="opus">Opus 256 kbps (recommended, small files)</option><option value="wav">Lossless WAV, 24-bit (about 1 GB an hour per track)</option></select></label>
        <label className="pod-check"><input type="checkbox" checked={clean} onChange={e=>setClean(e.target.checked)} disabled={live}/> Clean up voice (echo cancellation, noise reduction). Leave off for the best quality, and wear headphones.</label></div>
      <div className="pod-col"><h3>Preview</h3><div className="pod-preview">{cam!=='none'&&sess?.stream?<video ref={vid} muted playsInline autoPlay aria-label="Camera preview"/>:<div className="pod-novideo"><Mic size={40}/><span>Audio only</span></div>}
          {live&&<span className="pod-rec"><i/> {state==='paused'?'PAUSED':'REC'} {clock(secs)}</span>}</div>
        <div className="pod-meters" aria-label="Microphone levels">{pick.map((id,i)=><div key={id}><small>{(mics.find(m=>m.id===id)?.label||'Mic').slice(0,34)}</small><div className="pod-meter"><u style={{width:Math.min(100,Math.round((levels[i]||0)*100))+'%'}} className={(levels[i]||0)>0.95?'hot':''}/></div></div>)}</div>
        {sess&&<p className="muted small"><Info size={13}/> {sess.info.height?`Camera: ${sess.info.width}×${sess.info.height} at ${sess.info.fps||30} fps. About ${prettyBytes(estMBh*1048576)} an hour.`:'Audio only.'} Audio: {sess.info.sampleRate/1000} kHz.</p>}
        <div className="pod-ctl">{state==='idle'&&<button className="primary pod-recbtn" onClick={start} disabled={!sess}><i/> Record</button>}
          {state==='live'&&<><button className="secondary" onClick={pause}><Pause size={15}/> Pause</button><button className="primary" onClick={stop}><Square size={14}/> Stop</button></>}
          {state==='paused'&&<><button className="secondary" onClick={resume}><Play size={15}/> Resume</button><button className="primary" onClick={stop}><Square size={14}/> Stop</button></>}
          {state==='saving'&&<span className="muted">Finishing the files…</span>}</div></div></div></section>}
    {take&&<section className="panel pod-step"><h3>Your recording is ready</h3>
      <p>{clock(take.seconds)} long. {take.hasVideo?`Video ${take.width}×${take.height}, `:'Audio only, '}{take.audioLabel}. Master {prettyBytes(take.master.size)}{take.tracks.length?`, plus ${take.tracks.length} separate track${take.tracks.length>1?'s':''}`:''}.</p>
      <h4>Where do you want to keep it?</h4>
      <label className={`pod-dest${dest==='local'?' on':''}`}><input type="radio" name="dest" checked={dest==='local'} onChange={()=>setDest('local')}/><HardDrive size={18}/><span><b>On this computer</b><small>Saved to your Downloads folder. Nothing is stored on iSift.</small></span></label>
      <label className={`pod-dest${dest==='cloud'?' on':''}${cloudOk?'':' off'}`}><input type="radio" name="dest" disabled={!cloudOk} checked={dest==='cloud'} onChange={()=>setDest('cloud')}/><Cloud size={18}/><span><b>In the cloud</b><small>{cloudOk?'Kept at original quality with your other recordings. Counts towards your storage.':cfg.cloud_note||'Not included in your plan.'}</small></span></label>
      {dest==='cloud'&&<label className="pod-check"><input type="checkbox" checked={keepCopy} onChange={e=>setKeepCopy(e.target.checked)}/> Also save a copy on this computer</label>}
      {prog>=0&&<div className="pod-prog" role="progressbar" aria-valuenow={prog}><u style={{width:prog+'%'}}/><span>Uploading {prog}%</span></div>}
      {msg&&<p className="pod-ok"><Check size={15}/> {msg}</p>}
      <div className="pod-ctl"><button className="primary" onClick={save} disabled={prog>=0||done}>{dest==='cloud'?'Save to the cloud':'Save to this computer'}</button><button className="secondary" onClick={discard}>{saved.current?'Record another':'Discard'}</button></div></section>}
    {(cloudOk||mine.length>0)&&<section className="panel pod-step"><h3>My cloud podcasts</h3>{mine.length===0?<p className="muted">Nothing here yet. Choose "In the cloud" when you save a recording.</p>:mine.map(g=><div key={g.group_id} className="pod-item"><div className="pod-item-h"><b>{g.title||'Podcast'}</b><span className="muted small">{new Date(g.created_at).toLocaleString()}</span><button className="secondary danger" onClick={()=>del(g.group_id)} aria-label="Delete podcast"><Trash2 size={14}/></button></div>
      <div className="pod-tracks">{g.tracks.map(t=><button key={t.id} className="secondary" onClick={()=>dl(t.id,`${slug(g.title)} ${slug(t.label)}.${t.mimetype==='audio/wav'?'wav':'webm'}`)}><Download size={14}/> {t.label}{t.has_video?` ${t.width}×${t.height}`:''} <small>{prettyBytes(t.size_bytes)}</small></button>)}</div></div>)}</section>}
    <p className="muted small pod-note">Basic always saves on your own computer. Standard and Business can also keep podcasts in the cloud. Tell everyone you are recording, and keep this tab open while you record.</p>
  </div>;
}
