import React,{useEffect,useRef,useState,useCallback} from 'react';
import {Youtube,Link2,Unlink,Check,ExternalLink,X,Loader2,Copy} from 'lucide-react';

const API=import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
export type Req=(p:string,o?:any)=>Promise<any>;
/** A request helper for places that only have the sign-in token (the studio session save box). */
export const makeRequest=(token:string):Req=>async(path,options:any={})=>{
  let r:Response;try{r=await fetch(API+path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),Authorization:`Bearer ${token}`,...(options.headers||{})}})}catch{throw new Error('Cannot reach the iSift server. Check that it is still running, then try again.')}
  let d:any={};try{d=await r.json()}catch{}if(!r.ok)throw new Error(d.detail||`Request failed (${r.status})`);return d};

export type Job={id:string;status:'working'|'done'|'error';percent:number;message:string;url?:string;group_id?:string;duration?:number};
/** Follows a long task (an edit or a YouTube upload) until it ends. */
export async function followJob(request:Req,id:string,on:(j:Job)=>void):Promise<Job>{
  for(;;){const j:Job=await request(`/podcasts/jobs/${id}`);on(j);if(j.status!=='working')return j;await new Promise(r=>setTimeout(r,1200))}
}

/** Opens the Google sign-in window and waits for the answer. Used by the settings page and by the Post box, so a person can connect without leaving what they are doing. */
export async function connectYouTube(request:Req):Promise<{ok:boolean;message:string}>{
  const r=await request('/podcasts/youtube/connect',{method:'POST',body:JSON.stringify({origin:location.origin})});
  const w=window.open(r.url,'isift-youtube','width=520,height=720,menubar=no,toolbar=no');
  if(!w)return {ok:false,message:'The Google window was blocked. Allow pop-ups for this page and try again.'};
  return new Promise(res=>{
    const end=(v:{ok:boolean;message:string})=>{window.removeEventListener('message',on);clearInterval(t);res(v)};
    const on=(e:MessageEvent)=>{if(e.origin!==location.origin||e.data?.type!=='isift-youtube')return;end({ok:!!e.data.ok,message:e.data.message||''})};
    window.addEventListener('message',on);const t=setInterval(()=>{if(w.closed)end({ok:false,message:'The Google window was closed before sign-in finished.'})},700);
  });
}

type Status={connected:boolean;channel:string;email:string;connected_at:string;client_id:string;has_secret:boolean;can_connect:boolean;using_shared_app:boolean;shared_ready?:boolean;redirect_uri:string;default_privacy:'private'|'unlisted'|'public'};

/** Podcast settings > YouTube: the Google app details and sign-in used to post videos. */
export function YouTubeSettings({request,cloudOk}:{request:Req;cloudOk:boolean}){
  const [st,setSt]=useState<Status|null>(null),[cid,setCid]=useState(''),[sec,setSec]=useState(''),[busy,setBusy]=useState(false),[err,setErr]=useState(''),[ok,setOk]=useState(''),[help,setHelp]=useState(false);
  const load=useCallback(()=>request('/podcasts/youtube?origin='+encodeURIComponent(location.origin)).then((s:Status)=>{setSt(s);setCid(s.client_id)}).catch((e:any)=>setErr(e.message)),[request]);
  useEffect(()=>{load()},[load]);
  const save=async(extra:any={})=>{setErr('');setOk('');setBusy(true);try{await request('/podcasts/youtube/credentials',{method:'PUT',body:JSON.stringify({client_id:cid.trim(),client_secret:sec.trim(),...extra})});setSec('');await load();setOk('Saved.')}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
  const connect=async()=>{
    setErr('');setOk('');setBusy(true);
    try{
      if(cid.trim()!==st?.client_id||sec.trim())await request('/podcasts/youtube/credentials',{method:'PUT',body:JSON.stringify({client_id:cid.trim(),client_secret:sec.trim()})});
      const r=await connectYouTube(request);if(r.ok)setOk(r.message||'YouTube connected.');else setErr(r.message||'Google sign-in did not finish.');
      setSec('');await load();
    }catch(e:any){setErr(e.message)}finally{setBusy(false)}
  };
  const disconnect=async()=>{if(!window.confirm('Disconnect YouTube? Videos already posted stay on YouTube.'))return;setBusy(true);try{await request('/podcasts/youtube',{method:'DELETE'});await load();setOk('Disconnected.')}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
  if(!st)return <p className="muted">{err||'Loading…'}</p>;
  const copy=()=>{try{navigator.clipboard.writeText(st.redirect_uri);setOk('Address copied.')}catch{}};
  return <div className="pod-col pod-wide pod-yt">
    <h3><Youtube size={18}/> YouTube</h3>
    <p className="muted small">Post a finished podcast to your YouTube channel with one click. iSift never sees your Google password: you give it the details of your own Google app once, sign in to Google, and iSift keeps only a revocable permission.</p>
    {!cloudOk&&<p className="pod-warn"><b>Posting to YouTube is part of the paid plans.</b> Upgrade to Standard or Business to post your podcasts with one click. You can set up the connection now.</p>}
    {st.connected?<div className="pod-yt-on"><span className="pod-ok"><Check size={16}/> Connected{st.channel?` to ${st.channel}`:''}</span>{st.email&&<small className="muted">Google account: {st.email}</small>}
      <div className="pod-ctl"><button className="secondary" onClick={connect} disabled={busy}><Link2 size={14}/> Sign in again</button><button className="secondary danger" onClick={disconnect} disabled={busy}><Unlink size={14}/> Disconnect</button></div></div>
    :<p className="muted"><b>Not connected yet.</b> {st.can_connect?'Press Connect YouTube and approve access in the Google window.':'Enter your Google app details below, then connect.'}</p>}
    <fieldset disabled={busy}><legend>Google app credentials</legend>
      {st.using_shared_app&&!st.client_id&&<p className="muted small">Your administrator has set up a shared Google app, so you can connect without entering anything. Add your own below only if you want to use your own app.</p>}
      <label>Client ID<input type="text" value={cid} onChange={e=>setCid(e.target.value)} placeholder="1234567890-abc.apps.googleusercontent.com" autoComplete="off" spellCheck={false}/></label>
      <label>Client secret<input type="password" value={sec} onChange={e=>setSec(e.target.value)} placeholder={st.has_secret?'Saved. Type only to replace it.':'GOCSPX-…'} autoComplete="new-password"/></label>
      <div className="pod-ctl"><button className="secondary" onClick={()=>save()} disabled={busy||(!cid.trim()&&!sec.trim())}>Save credentials</button>
        <button className="primary" onClick={connect} disabled={busy||(!st.can_connect&&!(cid.trim()&&(sec.trim()||st.has_secret)))}>{busy?<Loader2 size={15} className="spin"/>:<Youtube size={15}/>} {st.connected?'Reconnect YouTube':'Connect YouTube'}</button>
        {(st.client_id||st.has_secret)&&<button type="button" className="textbtn" onClick={()=>{setCid('');save({clear:true})}}>Remove my credentials</button>}</div>
    </fieldset>
    <label>When I post, make the video<select value={st.default_privacy} onChange={e=>save({default_privacy:e.target.value,client_id:'',client_secret:''})}><option value="private">Private (only me, until I publish it in YouTube Studio)</option><option value="unlisted">Unlisted (anyone with the link)</option><option value="public">Public</option></select></label>
    <p className="muted small"><button type="button" className="textbtn" onClick={()=>setHelp(h=>!h)}>{help?'Hide':'Show'} how to get a Client ID and secret</button></p>
    {help&&<ol className="pod-steps muted small">
      <li>Open <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer">Google Cloud Console <ExternalLink size={11}/></a> and create a project (or pick one).</li>
      <li>APIs &amp; Services &gt; Library: turn on <b>YouTube Data API v3</b>.</li>
      <li>APIs &amp; Services &gt; OAuth consent screen: choose External, fill in the app name and your email, and add yourself under Test users.</li>
      <li>APIs &amp; Services &gt; Credentials &gt; Create credentials &gt; OAuth client ID &gt; <b>Web application</b>.</li>
      <li>Under Authorised redirect URIs add this exact address: <code className="pod-uri">{st.redirect_uri}</code> <button type="button" className="textbtn" onClick={copy}><Copy size={12}/> Copy</button></li>
      <li>Copy the Client ID and Client secret into the boxes above, then press Connect YouTube.</li>
      <li>Google keeps videos from unverified apps private. Posting works straight away; to post as public, ask Google to verify the app (APIs &amp; Services &gt; OAuth consent screen &gt; Publish app).</li></ol>}
    {err&&<p className="error" role="alert">{err}</p>}{ok&&<p className="pod-ok"><Check size={15}/> {ok}</p>}
  </div>;
}

/** The one-click post. Opens a small box with the title, description and privacy already filled in; Post sends it. */
export function PostToYouTube({request,groupId,title,onClose,openSettings}:{request:Req;groupId:string;title:string;onClose:()=>void;openSettings?:()=>void}){
  const [st,setSt]=useState<Status|null>(null),[t,setT]=useState(title||'Podcast'),[desc,setDesc]=useState(''),[priv,setPriv]=useState<'private'|'unlisted'|'public'>('private'),[tags,setTags]=useState('');
  const [job,setJob]=useState<Job|null>(null),[err,setErr]=useState(''),[busy,setBusy]=useState(false);const alive=useRef(true);
  useEffect(()=>{alive.current=true;request('/podcasts/youtube').then((s:Status)=>{if(alive.current){setSt(s);setPriv(s.default_privacy)}}).catch((e:any)=>setErr(e.message));return()=>{alive.current=false}},[request]);
  const post=async()=>{
    setErr('');setBusy(true);
    try{
      const r=await request(`/podcasts/${groupId}/youtube`,{method:'POST',body:JSON.stringify({title:t,description:desc,privacy:priv,tags:tags.split(',').map(x=>x.trim()).filter(Boolean)})});
      setJob({id:r.job_id,status:'working',percent:0,message:'Starting…'});
      const j=await followJob(request,r.job_id,x=>alive.current&&setJob(x));if(alive.current)setJob(j);
    }catch(e:any){setErr(e.message)}finally{setBusy(false)}
  };
  const connectHere=async()=>{setErr('');setBusy(true);try{const r=await connectYouTube(request);if(!r.ok)setErr(r.message||'Google sign-in did not finish.');else{const s:Status=await request('/podcasts/youtube');if(alive.current){setSt(s);setPriv(s.default_privacy)}}}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
  const working=job?.status==='working';
  return <div className="pod-modal" role="dialog" aria-modal="true" aria-label="Post to YouTube"><div className="pod-modal-card">
    <button className="pod-x" onClick={onClose} aria-label="Close" disabled={working}><X size={18}/></button>
    <h3><Youtube size={18}/> Post to YouTube</h3>
    {st&&!st.connected&&<><p className="muted">{st.can_connect?'Connect your YouTube channel once. After that, posting is one click.':'YouTube is not connected yet. Add your Google app details once in Podcast settings, then posting is one click.'}</p>
      <div className="pod-ctl">{st.can_connect&&<button className="primary" disabled={busy} onClick={connectHere}><Youtube size={15}/> {busy?'Waiting for Google…':'Connect YouTube'}</button>}{(!st.can_connect||true)&&openSettings&&<button className="secondary" onClick={()=>{onClose();openSettings()}}>{st.can_connect?'Use my own Google app':'Open YouTube settings'}</button>}<button className="secondary" onClick={onClose}>Cancel</button></div></>}
    {st&&st.connected&&!job&&<>
      <p className="muted small">Posting to {st.channel||st.email||'your channel'}.</p>
      <label>Title<input value={t} maxLength={100} onChange={e=>setT(e.target.value)}/></label>
      <label>Description<textarea rows={4} value={desc} maxLength={5000} onChange={e=>setDesc(e.target.value)} placeholder="What is this episode about?"/></label>
      <label>Tags (separated by commas)<input value={tags} onChange={e=>setTags(e.target.value)} placeholder="podcast, interview"/></label>
      <label>Who can watch<select value={priv} onChange={e=>setPriv(e.target.value as any)}><option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select></label>
      <div className="pod-ctl"><button className="primary" onClick={post} disabled={busy||!t.trim()}><Youtube size={15}/> Post now</button><button className="secondary" onClick={onClose}>Cancel</button></div></>}
    {job&&<div className="pod-job" aria-live="polite">
      {working&&<><div className="pod-prog" role="progressbar" aria-valuenow={job.percent}><u style={{width:job.percent+'%'}}/><span>{job.message||'Working…'} {job.percent}%</span></div><small className="muted">Keep this window open until it finishes. A long video takes a few minutes.</small></>}
      {job.status==='done'&&<><p className="pod-ok"><Check size={16}/> {job.message}</p>{job.url&&<p><a href={job.url} target="_blank" rel="noreferrer">Open on YouTube <ExternalLink size={12}/></a></p>}<div className="pod-ctl"><button className="primary" onClick={onClose}>Done</button></div></>}
      {job.status==='error'&&<><p className="error" role="alert">{job.message}</p><div className="pod-ctl"><button className="primary" onClick={()=>setJob(null)}>Try again</button><button className="secondary" onClick={onClose}>Close</button></div></>}</div>}
    {err&&<p className="error" role="alert">{err}</p>}
  </div></div>;
}

/** Admin Console > API and Settings > YouTube: what to do in Google Cloud once, so everybody can post with one click. */
export function YouTubeAdmin({request}:{request:Req}){
  const [d,setD]=useState<any>(null),[chk,setChk]=useState<{ok:boolean;message:string}|null>(null),[busy,setBusy]=useState(false),[err,setErr]=useState(''),[copied,setCopied]=useState('');
  const load=useCallback(()=>request('/podcasts/admin/youtube-setup?origin='+encodeURIComponent(location.origin)).then(setD).catch((e:any)=>setErr(e.message)),[request]);
  useEffect(()=>{load()},[load]);
  const check=async()=>{setBusy(true);setChk(null);try{setChk(await request('/podcasts/admin/youtube-setup/check?origin='+encodeURIComponent(location.origin),{method:'POST'}))}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
  const copy=(t:string)=>{try{navigator.clipboard.writeText(t);setCopied(t);setTimeout(()=>setCopied(''),1500)}catch{}};
  if(!d)return <section className="panel"><p className="muted">{err||'Loading…'}</p></section>;
  const src=d.source==='youtube'?'the YouTube client saved below':d.source==='google'?'the Google sign-in client from Email and calendar':'no client yet';
  const Row=({t,v}:{t:string;v:string})=><div className="pod-copyrow"><code>{v}</code><button type="button" className="textbtn" onClick={()=>copy(v)}><Copy size={12}/> {copied===v?'Copied':t}</button></div>;
  return <section className="panel pod-yt-admin"><div className="panelhead"><h2><Youtube size={17}/> Post podcasts to YouTube</h2></div>
    <p className="hint">Do this once and everyone on a paid plan can connect their channel and post with one click, without entering anything. People never give iSift a password.</p>
    <p><b>Google app in use:</b> {src}. {d.source==='google'&&<span className="muted">The same Google app that signs people in for mail is reused, so there is nothing new to paste. To keep YouTube in its own Google project, add its Client ID and secret in the fields below.</span>}</p>
    <ol className="pod-steps">
      <li>Open the Google Cloud project of that Web client and <b>turn on YouTube Data API v3</b>: <a href={d.api_link} target="_blank" rel="noreferrer">open the API page <ExternalLink size={11}/></a></li>
      <li>On the client (APIs &amp; Services &gt; Credentials), add this under <b>Authorised redirect URIs</b>. Keep the mail address that is already there:<Row t="Copy" v={d.redirect_uri}/></li>
      <li>OAuth consent screen &gt; Data access: add these two permissions:{d.scopes.map((x:string)=><Row key={x} t="Copy" v={x}/>)}</li>
      <li>OAuth consent screen: make sure the app is <b>Published</b> (not "Testing"), or only listed test users can connect.</li>
      <li>Press <b>Check Google client</b> below.</li>
      <li>Optional, for public videos: ask Google to verify the app and pass the YouTube API compliance audit. Until then, posted videos arrive private and people publish them in YouTube Studio.</li></ol>
    <div className="pod-ctl"><button className="primary" onClick={check} disabled={busy||!d.ready}>{busy?<Loader2 size={15} className="spin"/>:<Check size={15}/>} Check Google client</button></div>
    {!d.ready&&<p className="pod-warn">No Google Client ID and secret are saved yet. Save the Google sign-in client under Email and calendar, or a YouTube client in the fields below.</p>}
    {chk&&<p className={chk.ok?'pod-ok':'error'} role="status">{chk.ok?<Check size={15}/>:null} {chk.message}{chk.ok&&' This checks the Client ID and secret only; the steps above still need doing in Google Cloud.'}</p>}
    {err&&<p className="error">{err}</p>}
  </section>;
}
