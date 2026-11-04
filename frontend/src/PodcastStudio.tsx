import React,{useEffect,useRef,useState,useCallback} from 'react';
import {Podcast,Mic,Pause,Play,Square,Download,Trash2,Info,Users} from 'lucide-react';
import {TakeSaver,saveBlob} from './PodcastSave';
import {openSession,Session,Take,Mic as MicDev,prettyBytes,clock,slug,videoMbps,AUDIO_KBPS} from './podcast';
import {PRESETS,readImage} from './vbg';
import type {BgMode} from './vbg';

const API=import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
type Cfg={allowed:boolean;cloud_allowed:boolean;cloud_note:string;cloud_storage:string;max_file_mb:number;max_tracks:number};
type Cloud={group_id:string;title:string;created_at:string;tracks:{id:string;label:string;is_master:boolean;has_video:boolean;width:number;height:number;duration_s:number;size_bytes:number;mimetype:string}[]};


/** Podcast Studio: HD podcast recording in the browser. Saved on this computer (always on Basic) or, on paid plans, in the cloud. */
export function PodcastStudio({request,token,notify}:{request:(p:string,o?:any)=>Promise<any>;token:string;notify:(m:string)=>void}){
  const [cfg,setCfg]=useState<Cfg|null>(null),[err,setErr]=useState('');
  const [mics,setMics]=useState<MicDev[]>([]),[cams,setCams]=useState<MicDev[]>([]),[ready,setReady]=useState(false);
  const [pick,setPick]=useState<string[]>([]),[cam,setCam]=useState('none'),[res,setRes]=useState<'best'|'1080'|'720'>('best'),[fmt,setFmt]=useState<'opus'|'wav'>('opus'),[clean,setClean]=useState(false);
  const [title,setTitle]=useState(''),[sess,setSess]=useState<Session|null>(null),[state,setState]=useState<'idle'|'live'|'paused'|'saving'>('idle');
  const [levels,setLevels]=useState<number[]>([]),[secs,setSecs]=useState(0),[take,setTake]=useState<Take|null>(null);
  const [bg,setBg]=useState<BgMode>({kind:'none'}),[bgName,setBgName]=useState('');const bgFile=useRef<HTMLInputElement>(null);
  const [mine,setMine]=useState<Cloud[]>([]),[studioBusy,setStudioBusy]=useState(false);const vid=useRef<HTMLVideoElement>(null);const saved=useRef(true);

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
    try{const s=await openSession({mics:mics.filter(m=>pick.includes(m.id)),cam,res,audio:fmt,clean,bg},p=>setLevels(p));setSess(s);setErr('')}catch(e:any){setErr(e?.message||'Could not open the devices.')}
  };
  useEffect(()=>{if(state==='idle'&&ready&&!take)void setupPreview();/* eslint-disable-next-line */},[ready,pick.join(),cam,res,fmt,clean,!!take,JSON.stringify(bg).length+(bg.kind==='image'?bg.id:'')]);

  const start=()=>{if(!sess)return;sess.start();setSecs(0);setState('live');setTake(null);saved.current=false};
  const pause=()=>{sess?.pause();setState('paused')};const resume=()=>{sess?.resume();setState('live')};
  const stop=async()=>{if(!sess)return;setState('saving');try{const t=await sess.stop();setSess(null);setTake(t);setState('idle')}catch(e:any){setErr(e?.message||'Could not finish the recording.');setState('idle')}};
  const studio=async()=>{setStudioBusy(true);setErr('');try{const r=await request('/rooms',{method:'POST',body:JSON.stringify({base_url:location.origin+location.pathname})});try{sessionStorage.setItem('isift.start',JSON.stringify({video:true,screen:false}));sessionStorage.setItem('isift.studio','1')}catch{}location.hash='#/room/'+r.code}catch(e:any){setErr(e?.message||'Could not open a studio session.');setStudioBusy(false)}};
  const dl=async(id:string,name:string)=>{try{const r=await fetch(`${API}/podcasts/${id}/file`,{headers:{Authorization:`Bearer ${token}`}});if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||'Could not download.');saveBlob(await r.blob(),name)}catch(e:any){notify(e.message)}};
  const del=async(g:string)=>{if(!window.confirm('Delete this podcast from the cloud, with all its tracks?'))return;try{await request(`/podcasts/${g}`,{method:'DELETE'});loadMine()}catch(e:any){notify(e.message)}};

  if(err&&!cfg)return <section className="panel pod"><p className="error">{err}</p></section>;
  if(!cfg)return <section className="panel pod"><p className="muted">Loading Podcast Studio…</p></section>;
  const cloudOk=cfg.cloud_allowed;const live=state==='live'||state==='paused';
  const estMBh=(()=>{const h=sess?.info.height||0;const v=h?videoMbps(h):0;return Math.round(((v+AUDIO_KBPS/1000)/8)*3600)})();
  return <div className="pod">
    <section className="panel pod-top"><div className="pod-head"><span className="pod-ic"><Podcast size={22}/></span><div><h2>HD podcast recording</h2><p className="muted">Studio-quality sound and up to 4K video, recorded in your browser. Every microphone also gets its own separate track.</p></div></div>
      <div className="pod-badges"><span>48 kHz stereo audio</span><span>Opus 256 kbps or lossless WAV</span><span>Up to 4K video, 30 fps</span><span>Separate track per microphone</span></div></section>
    <section className="panel pod-step pod-studio"><div className="pod-head"><span className="pod-ic"><Users size={22}/></span><div><h3>Interview or record with guests</h3><p className="muted">Open a studio session: guests join from a link, each person gets their own sound track, and you can share a screen, slides, a document, photos or a video while you record. The recording shows everyone and whatever is shared, in 1080p HD.</p></div></div><div className="pod-ctl"><button className="primary" onClick={studio} disabled={studioBusy}><Users size={16}/> {studioBusy?'Opening…':'Start a studio session'}</button></div><p className="muted small">Inside the session, choose <b>Studio recording</b> in the menu. Slides and documents: share them as a PDF with <b>Share a file</b>, or share the window or tab where they are open.</p></section>
    {err&&<p className="error pod-err" role="alert">{err}</p>}
    {!ready&&<section className="panel pod-step"><h3>1. Choose your equipment</h3><p className="muted">Allow the microphone (and camera, if you want video). Nothing is recorded until you press Record.</p><button className="primary" onClick={allow}><Mic size={16}/> Allow microphone and camera</button></section>}
    {ready&&!take&&<section className="panel pod-step"><div className="pod-grid">
      <div className="pod-col"><h3>Podcast</h3><label>Title<input value={title} maxLength={120} onChange={e=>setTitle(e.target.value)} placeholder="Episode 1" disabled={live}/></label>
        <fieldset disabled={live}><legend>Microphones (one track each)</legend>{mics.map(m=><label key={m.id} className="pod-check"><input type="checkbox" checked={pick.includes(m.id)} onChange={e=>setPick(p=>e.target.checked?[...p,m.id].slice(0,cfg.max_tracks):p.filter(x=>x!==m.id))}/> {m.label}</label>)}</fieldset>
        <label>Camera<select value={cam} onChange={e=>setCam(e.target.value)} disabled={live}><option value="none">No camera (audio only)</option>{cams.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
        <label>Studio background<select value={bg.kind==='none'?'none':bg.kind==='blur'?'blur':bg.kind==='image'?bg.id:'none'} disabled={live||cam==='none'} onChange={e=>{const v=e.target.value;if(v==='upload'){bgFile.current?.click();return}if(v==='none')setBg({kind:'none'});else if(v==='blur')setBg({kind:'blur',level:12});else{const p=PRESETS.find(x=>x.id===v);if(p)setBg({kind:'image',id:p.id,url:p.url})}}}><option value="none">My real room (no change)</option><option value="blur">Blur my room</option>{PRESETS.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}{bg.kind==='image'&&bg.id==='custom'&&<option value="custom">{bgName||'My picture'}</option>}<option value="upload">Upload my own studio picture…</option></select></label>
        <input ref={bgFile} type="file" accept="image/*" hidden onChange={async e=>{const f=e.target.files?.[0];e.target.value='';if(!f)return;try{const url=await readImage(f);setBgName(f.name.replace(/\.[^.]+$/,'').slice(0,30));setBg({kind:'image',id:'custom',url})}catch{setErr('That picture could not be opened. Try a JPG or PNG.')}}}/>
        {bg.kind!=='none'&&<p className="muted small">The studio background is applied to the video. It is recorded at up to 1080p.</p>}
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
    {take&&<section className="panel pod-step"><h3>Your recording is ready</h3><TakeSaver take={take} title={title} token={token} cfg={cfg} onSaved={s=>{saved.current=s}} onDiscard={()=>{setTake(null);saved.current=true}} onCloud={loadMine}/></section>}
    {(cloudOk||mine.length>0)&&<section className="panel pod-step"><h3>My cloud podcasts</h3>{mine.length===0?<p className="muted">Nothing here yet. Choose "In the cloud" when you save a recording.</p>:mine.map(g=><div key={g.group_id} className="pod-item"><div className="pod-item-h"><b>{g.title||'Podcast'}</b><span className="muted small">{new Date(g.created_at).toLocaleString()}</span><button className="secondary danger" onClick={()=>del(g.group_id)} aria-label="Delete podcast"><Trash2 size={14}/></button></div>
      <div className="pod-tracks">{g.tracks.map(t=><button key={t.id} className="secondary" onClick={()=>dl(t.id,`${slug(g.title)} ${slug(t.label)}.${t.mimetype==='audio/wav'?'wav':'webm'}`)}><Download size={14}/> {t.label}{t.has_video?` ${t.width}×${t.height}`:''} <small>{prettyBytes(t.size_bytes)}</small></button>)}</div></div>)}</section>}
    <p className="muted small pod-note">Basic always saves on your own computer. Standard and Business can also keep podcasts in the cloud. Tell everyone you are recording, and keep this tab open while you record.</p>
  </div>;
}
