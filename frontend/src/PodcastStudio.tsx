import React,{useEffect,useRef,useState,useCallback} from 'react';
import {Settings,Library,Podcast,Mic,Pause,Play,Square,Download,Trash2,Info,Users,Scissors,Youtube,Sliders,Check} from 'lucide-react';
import {TakeSaver,saveBlob} from './PodcastSave';
import {openSession,Session,Take,Mic as MicDev,prettyBytes,clock,slug,videoMbps,AUDIO_KBPS} from './podcast';
import {PRESETS,readImage} from './vbg';
import type {BgMode} from './vbg';
import {YouTubeSettings,PostToYouTube} from './PodcastYouTube';
import {PodcastEditor} from './PodcastEditor';

const API=import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
type Cfg={allowed:boolean;cloud_allowed:boolean;edit_allowed?:boolean;youtube_allowed?:boolean;youtube_direct?:boolean;cloud_note:string;cloud_storage:string;max_file_mb:number;max_tracks:number};
type Cloud={group_id:string;title:string;created_at:string;tracks:{id:string;label:string;is_master:boolean;has_video:boolean;width:number;height:number;duration_s:number;size_bytes:number;mimetype:string}[]};


const KEY='isift.podcast.setup';
type Saved={mics:{id:string;label:string}[];cam:string;camLabel:string;res:'best'|'1080'|'720';fmt:'opus'|'wav';clean:boolean;bg:BgMode;bgName:string};
const loadSetup=():Partial<Saved>=>{try{return JSON.parse(localStorage.getItem(KEY)||'{}')||{}}catch{return {}}};
/** Podcast Studio: HD podcast recording in the browser. Saved on this computer (always on Basic) or, on paid plans, in the cloud. */
export function PodcastStudio({request,token,notify}:{request:(p:string,o?:any)=>Promise<any>;token:string;notify:(m:string)=>void}){
  const [cfg,setCfg]=useState<Cfg|null>(null),[err,setErr]=useState('');
  const [mics,setMics]=useState<MicDev[]>([]),[cams,setCams]=useState<MicDev[]>([]),[ready,setReady]=useState(false);
  type Mode='solo'|'guests'|'edit'|'settings'|'mine';type SetTab='equipment'|'youtube';
  const [mode,setMode]=useState<Mode>(()=>{try{const v=localStorage.getItem('isift.podcast.mode');return v==='guests'||v==='edit'||v==='settings'||v==='mine'?v:'solo'}catch{return 'solo'}});
  const chooseMode=(m:Mode)=>{if(m==='edit')setEditSeen(true);setMode(m);try{localStorage.setItem('isift.podcast.mode',m)}catch{}};
  const [setTab,setSetTab]=useState<SetTab>(()=>{try{return localStorage.getItem('isift.podcast.settab')==='youtube'?'youtube':'equipment'}catch{return 'equipment'}});
  const chooseSetTab=(t:SetTab)=>{setSetTab(t);try{localStorage.setItem('isift.podcast.settab',t)}catch{}};
  const [editStart,setEditStart]=useState<{gid:string;n:number}|null>(null),[editSeen,setEditSeen]=useState(mode==='edit'),[postFor,setPostFor]=useState<{gid:string;title:string}|null>(null);
  const openYouTubeSettings=()=>{chooseSetTab('youtube');chooseMode('settings')};
  const editThis=(gid:string)=>{setEditStart({gid,n:Date.now()});setEditSeen(true);chooseMode('edit')};
  const saved0=useRef<Partial<Saved>>(loadSetup());const [pick,setPick]=useState<string[]>([]),[cam,setCam]=useState('none'),[res,setRes]=useState<'best'|'1080'|'720'>(saved0.current.res||'best'),[fmt,setFmt]=useState<'opus'|'wav'>(saved0.current.fmt||'opus'),[clean,setClean]=useState(!!saved0.current.clean);
  const [title,setTitle]=useState(''),[sess,setSess]=useState<Session|null>(null),[state,setState]=useState<'idle'|'live'|'paused'|'saving'>('idle');
  const [levels,setLevels]=useState<number[]>([]),[secs,setSecs]=useState(0),[take,setTake]=useState<Take|null>(null);
  const [bg,setBg]=useState<BgMode>(saved0.current.bg||{kind:'none'}),[bgName,setBgName]=useState(saved0.current.bgName||'');const bgFile=useRef<HTMLInputElement>(null);
  const [mine,setMine]=useState<Cloud[]>([]),[studioBusy,setStudioBusy]=useState(false);const vid=useRef<HTMLVideoElement>(null);const saved=useRef(true);

  const loadMine=useCallback(()=>request('/podcasts').then((r:Cloud[])=>setMine(r)).catch(()=>{}),[request]);
  useEffect(()=>{request('/podcasts/config').then((c:Cfg)=>setCfg(c)).catch((e:any)=>setErr(e.message||'Podcast Studio is not available.'));loadMine()},[request,loadMine]);
  useEffect(()=>{if(sess&&vid.current){vid.current.srcObject=sess.stream;vid.current.play().catch(()=>{})}},[sess,mode,take,ready]);
  useEffect(()=>{if(state!=='live')return;const t=setInterval(()=>sess&&setSecs(sess.seconds()),250);return()=>clearInterval(t)},[state,sess]);
  useEffect(()=>{const h=(e:BeforeUnloadEvent)=>{if(state==='live'||state==='paused'||(take&&!saved.current)){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',h);return()=>window.removeEventListener('beforeunload',h)},[state,take]);
  useEffect(()=>()=>{sess?.cancel()},[]);          // eslint-disable-line

  // remember the setup on this computer and reuse it next time; skip the Allow step when the browser already lets this site use the microphone
  // the setup is kept on this computer only when the person presses Save; the line under each box shows what is saved
  const [savedS,setSavedS]=useState<Partial<Saved>>(loadSetup),[savedAt,setSavedAt]=useState('');
  const nowSetup=():Saved=>({mics:mics.filter(m=>pick.includes(m.id)).map(m=>({id:m.id,label:m.label})),cam,camLabel:cams.find(c=>c.id===cam)?.label||'',res,fmt,clean,bg,bgName});
  const sig=(o:Partial<Saved>)=>JSON.stringify({m:(o.mics||[]).map(x=>x.id),c:o.cam||'none',r:o.res||'best',f:o.fmt||'opus',cl:!!o.clean,b:o.bg?.kind==='image'?o.bg.id:o.bg?.kind||'none'});
  const dirty=ready&&sig(nowSetup())!==sig(savedS);
  const saveSetup=()=>{const o=nowSetup();try{localStorage.setItem(KEY,JSON.stringify(o))}catch{try{localStorage.setItem(KEY,JSON.stringify({...o,bg:{kind:'none'},bgName:''}))}catch{notify('This browser would not let iSift keep the settings.');return}}
    setSavedS(o);setSavedAt(new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}));notify('Podcast equipment saved on this computer.')};
  const bgText=(o:Partial<Saved>)=>!o.bg||o.bg.kind==='none'?'My real room (no change)':o.bg.kind==='blur'?'Blur my room':o.bg.id==='custom'?(o.bgName||'My own picture'):(PRESETS.find(x=>x.id===(o.bg as any).id)?.name||'Studio picture');
  const Kept=({children}:{children:React.ReactNode})=><small className="pod-kept"><Check size={11}/> Saved: {children}</small>;
  const none=!(savedS.mics||savedS.cam||savedS.res||savedS.fmt);
  useEffect(()=>{if((mode!=='solo'&&mode!=='settings')||ready)return;let live=true;const go=()=>{if(live)void allow()};try{(navigator as any).permissions?.query({name:'microphone'}).then((s:any)=>{if(s.state==='granted')go()}).catch(()=>{if(saved0.current.mics?.length)go()})}catch{if(saved0.current.mics?.length)go()}return()=>{live=false}},[mode]);   // eslint-disable-line
  const resetSetup=()=>{try{localStorage.removeItem(KEY)}catch{}saved0.current={};setSavedS({});setSavedAt('');setPick(mics.length?[mics[0].id]:[]);setCam('none');setRes('best');setFmt('opus');setClean(false);setBg({kind:'none'});setBgName('')};
  const allow=async()=>{
    setErr('');
    try{
      let s:MediaStream;try{s=await navigator.mediaDevices.getUserMedia({audio:true,video:true})}catch{s=await navigator.mediaDevices.getUserMedia({audio:true})}
      s.getTracks().forEach(t=>t.stop());
      const d=await navigator.mediaDevices.enumerateDevices();
      const m=d.filter(x=>x.kind==='audioinput'&&x.deviceId!=='communications').map((x,i)=>({id:x.deviceId,label:x.label||`Microphone ${i+1}`}));
      const cs=d.filter(x=>x.kind==='videoinput').map((x,i)=>({id:x.deviceId,label:x.label||`Camera ${i+1}`}));
      setMics(m);setCams(cs);
      // reuse the equipment chosen last time (matched by id, or by name if the browser changed the ids)
      const sv=saved0.current;const want=(sv.mics||[]).map(x=>m.find(y=>y.id===x.id)||m.find(y=>y.label===x.label)).filter(Boolean) as {id:string}[];
      setPick(want.length?[...new Set(want.map(x=>x.id))].slice(0,8):m.length?[m[0].id]:[]);
      const c=sv.cam&&sv.cam!=='none'?(cs.find(y=>y.id===sv.cam)||cs.find(y=>y.label===sv.camLabel)):null;setCam(c?c.id:'none');
      setReady(true);
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
    <nav className="subtabs pod-tabs" role="tablist" aria-label="Podcast Studio">
      {([['solo','Record on this computer',Mic],['guests','Interview guests online',Users],['edit','Edit videos',Scissors],['settings','Podcast settings',Settings],['mine','My cloud podcasts',Library]] as const).map(([k,l,I])=><button key={k} type="button" role="tab" aria-selected={mode===k} className={mode===k?'active':''} onClick={()=>chooseMode(k)}><I size={15}/> {l}{k==='solo'&&live&&<i className="pod-livedot" title="Recording"/>}</button>)}
    </nav>
    {mode==='guests'&&<section className="panel pod-top" role="tabpanel"><span className="pod-ic"><Users size={20}/></span><h3>Interview guests online</h3><p className="muted">Guests join from a link, on any device. Everyone is recorded in 1080p HD with a separate sound track for each person. Share a screen, slides, documents, photos or a video while you record.</p><button className="primary" onClick={studio} disabled={studioBusy}>{studioBusy?'Opening…':'Start a studio session'}</button><small className="muted">In the session, choose Studio recording in the menu. For slides or a document, use Share a file with a PDF, or share the window.</small></section>}
    {err&&<p className="error pod-err" role="alert">{err}</p>}
    {mode==='settings'&&<section className="panel pod-step" role="tabpanel">
      <nav className="subtabs sub2" role="tablist" aria-label="Podcast settings">{([['equipment','Podcast equipment',Sliders],['youtube','YouTube',Youtube]] as const).map(([k,l,I])=><button key={k} type="button" role="tab" aria-selected={setTab===k} className={setTab===k?'active':''} onClick={()=>chooseSetTab(k)}><I size={14}/> {l}</button>)}</nav>
      {setTab==='youtube'?<YouTubeSettings request={request} cloudOk={!!cfg.youtube_direct}/>:!ready?<div className="pod-col pod-wide"><h3>Choose your equipment</h3><p className="muted">Allow the microphone (and camera, if you want video). The browser asks once. Nothing is recorded until you press Record, and your choices are remembered next time.</p><button className="primary" onClick={allow}><Mic size={16}/> Allow microphone and camera</button></div>:<div className="pod-col pod-wide"><h3>Podcast equipment</h3><p className="muted small pod-remember">Choose your equipment, then press <b>Save</b> to keep it on this computer for next time. <button type="button" className="textbtn" onClick={resetSetup} disabled={live}>Reset</button></p>
        <fieldset disabled={live}><legend>Microphones (one track each)</legend>{mics.map(m=><label key={m.id} className="pod-check"><input type="checkbox" checked={pick.includes(m.id)} onChange={e=>setPick(p=>e.target.checked?[...p,m.id].slice(0,cfg.max_tracks):p.filter(x=>x!==m.id))}/> {m.label}</label>)}</fieldset>{none?null:<Kept>{(savedS.mics||[]).length?(savedS.mics||[]).map(m=>m.label).join(', '):'no microphone'}</Kept>}
        <label>Camera<select value={cam} onChange={e=>setCam(e.target.value)} disabled={live}><option value="none">No camera (audio only)</option>{cams.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select>{none?null:<Kept>{savedS.cam&&savedS.cam!=='none'?(savedS.camLabel||'Camera'):'No camera (audio only)'}</Kept>}</label>
        <label>Studio background<select value={bg.kind==='none'?'none':bg.kind==='blur'?'blur':bg.kind==='image'?bg.id:'none'} disabled={live||cam==='none'} onChange={e=>{const v=e.target.value;if(v==='upload'){bgFile.current?.click();return}if(v==='none')setBg({kind:'none'});else if(v==='blur')setBg({kind:'blur',level:12});else{const p=PRESETS.find(x=>x.id===v);if(p)setBg({kind:'image',id:p.id,url:p.url})}}}><option value="none">My real room (no change)</option><option value="blur">Blur my room</option>{PRESETS.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}{bg.kind==='image'&&bg.id==='custom'&&<option value="custom">{bgName||'My picture'}</option>}<option value="upload">Upload my own studio picture…</option></select>{none?null:<Kept>{bgText(savedS)}</Kept>}</label>
        <input ref={bgFile} type="file" accept="image/*" hidden onChange={async e=>{const f=e.target.files?.[0];e.target.value='';if(!f)return;try{const url=await readImage(f);setBgName(f.name.replace(/\.[^.]+$/,'').slice(0,30));setBg({kind:'image',id:'custom',url})}catch{setErr('That picture could not be opened. Try a JPG or PNG.')}}}/>
        {bg.kind!=='none'&&<p className="muted small">The studio background is applied to the video. It is recorded at up to 1080p.</p>}
        <label>Video quality<select value={res} onChange={e=>setRes(e.target.value as any)} disabled={live||cam==='none'}><option value="best">Best the camera has (up to 4K)</option><option value="1080">Full HD 1080p</option><option value="720">HD 720p</option></select>{none?null:<Kept>{({best:'Best the camera has',1080:'Full HD 1080p',720:'HD 720p'} as any)[savedS.res||'best']}</Kept>}</label>
        <label>Audio format<select value={fmt} onChange={e=>setFmt(e.target.value as any)} disabled={live}><option value="opus">Opus 256 kbps (recommended, small files)</option><option value="wav">Lossless WAV, 24-bit (about 1 GB an hour per track)</option></select>{none?null:<Kept>{savedS.fmt==='wav'?'Lossless WAV, 24-bit':'Opus 256 kbps'}</Kept>}</label>
        <label className="pod-check"><input type="checkbox" checked={clean} onChange={e=>setClean(e.target.checked)} disabled={live}/> Clean up voice (echo cancellation, noise reduction). Leave off for the best quality, and wear headphones.{none?null:<Kept>{savedS.clean?'On':'Off'}</Kept>}</label>
        <div className="pod-ctl pod-savebar"><button className="primary" onClick={saveSetup} disabled={live||(!dirty&&!none)}><Check size={15}/> Save equipment settings</button><span className={dirty||none?'pod-unsaved':'muted small'} role="status">{dirty?'You have changes that are not saved yet.':none?'Nothing is saved yet.':`Saved on this computer${savedAt?' at '+savedAt:''}.`}</span></div></div>}
    </section>}
    {mode==='solo'&&!ready&&<section className="panel pod-step" role="tabpanel"><h3>Set up your equipment first</h3><p className="muted">Choose your microphones, camera and quality once. They are remembered for next time.</p><button className="primary" onClick={()=>chooseMode('settings')}><Settings size={16}/> Open Podcast settings</button></section>}
    {mode==='solo'&&ready&&!take&&<section className="panel pod-step" role="tabpanel"><div className="pod-grid"><div className="pod-col"><label>Title<input value={title} maxLength={120} onChange={e=>setTitle(e.target.value)} placeholder="Episode 1" disabled={live}/></label><p className="muted small">Microphones, camera, background and quality are in <button type="button" className="textbtn" onClick={()=>chooseMode('settings')}>Podcast settings</button>.</p></div><div className="pod-col"><h3>Preview</h3><div className="pod-preview">{cam!=='none'&&sess?.stream?<video ref={vid} muted playsInline autoPlay aria-label="Camera preview"/>:<div className="pod-novideo"><Mic size={40}/><span>Audio only</span></div>}
          {live&&<span className="pod-rec"><i/> {state==='paused'?'PAUSED':'REC'} {clock(secs)}</span>}</div>
        <div className="pod-meters" aria-label="Microphone levels">{pick.map((id,i)=><div key={id}><small>{(mics.find(m=>m.id===id)?.label||'Mic').slice(0,34)}</small><div className="pod-meter"><u style={{width:Math.min(100,Math.round((levels[i]||0)*100))+'%'}} className={(levels[i]||0)>0.95?'hot':''}/></div></div>)}</div>
        {sess&&<p className="muted small"><Info size={13}/> {sess.info.height?`Camera: ${sess.info.width}×${sess.info.height} at ${sess.info.fps||30} fps. About ${prettyBytes(estMBh*1048576)} an hour.`:'Audio only.'} Audio: {sess.info.sampleRate/1000} kHz.</p>}
        <div className="pod-ctl">{state==='idle'&&<button className="primary pod-recbtn" onClick={start} disabled={!sess}><i/> Record</button>}
          {state==='live'&&<><button className="secondary" onClick={pause}><Pause size={15}/> Pause</button><button className="primary" onClick={stop}><Square size={14}/> Stop</button></>}
          {state==='paused'&&<><button className="secondary" onClick={resume}><Play size={15}/> Resume</button><button className="primary" onClick={stop}><Square size={14}/> Stop</button></>}
          {state==='saving'&&<span className="muted">Finishing the files…</span>}</div></div></div></section>}
    {mode==='solo'&&take&&<section className="panel pod-step"><h3>Your recording is ready</h3><TakeSaver take={take} title={title} token={token} cfg={cfg} onSaved={s=>{saved.current=s}} onDiscard={()=>{setTake(null);saved.current=true}} onCloud={loadMine} onEdit={cfg.edit_allowed?(gid=>editThis(gid)):undefined} openSettings={openYouTubeSettings}/></section>}
    {(editSeen||mode==='edit')&&<div hidden={mode!=='edit'}><PodcastEditor allowed={!!cfg.edit_allowed} request={request} token={token} podcasts={mine} start={editStart} onSaved={loadMine} openSettings={openYouTubeSettings}/></div>}
    {mode==='mine'&&<section className="panel pod-step" role="tabpanel"><h3>My cloud podcasts</h3>{mine.length===0?<p className="muted">{cloudOk?'Nothing here yet. Choose "In the cloud" when you save a recording.':'Podcasts saved in the cloud will appear here. Your plan saves recordings on your own computer; paid plans can also keep them in the cloud.'}</p>:mine.map(g=><div key={g.group_id} className="pod-item"><div className="pod-item-h"><b>{g.title||'Podcast'}</b><span className="muted small">{new Date(g.created_at).toLocaleString()}</span>{cfg.edit_allowed&&<button className="secondary" onClick={()=>editThis(g.group_id)} title="Cut, join, add a voice-over and more"><Scissors size={14}/> Edit</button>}{cfg.youtube_allowed&&<button className="secondary" onClick={()=>setPostFor({gid:g.group_id,title:g.title})} title="Post to your YouTube channel"><Youtube size={14}/> Post to YouTube</button>}<button className="secondary danger" onClick={()=>del(g.group_id)} aria-label="Delete podcast"><Trash2 size={14}/></button></div>
      <div className="pod-tracks">{g.tracks.map(t=><button key={t.id} className="secondary" onClick={()=>dl(t.id,`${slug(g.title)} ${slug(t.label)}.${t.mimetype==='audio/wav'?'wav':'webm'}`)}><Download size={14}/> {t.label}{t.has_video?` ${t.width}×${t.height}`:''} <small>{prettyBytes(t.size_bytes)}</small></button>)}</div></div>)}</section>}
    {postFor&&<PostToYouTube request={request} groupId={postFor.gid} title={postFor.title} onClose={()=>setPostFor(null)} openSettings={openYouTubeSettings}/>}
    <p className="muted small pod-note">Basic always saves on your own computer. Standard and Business can also keep podcasts in the cloud. Tell everyone you are recording, and keep this tab open while you record.</p>
  </div>;
}
