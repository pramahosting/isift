import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Upload,Trash2,Download,Eye,RefreshCw,Pencil,Film,FileText,File as FileIcon,Link2,Check,X,Play,LoaderCircle} from 'lucide-react';

const API:string=import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
const size=(n:number)=>n>=1048576?`${(n/1048576).toFixed(1)} MB`:n>=1024?`${Math.round(n/1024)} KB`:`${n} bytes`;
const day=(v:string)=>{try{return new Date(v).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'})}catch{return ''}};

/** Admin Console > Sales & Marketing: the videos, the playbook and any other files kept for selling iSift. */
export function MarketingAdmin({request,download,view}:any){
  const [items,setItems]=useState<any[]|null>(null),[r2,setR2]=useState(false),[err,setErr]=useState(''),[msg,setMsg]=useState(''),[busy,setBusy]=useState('');
  const [edit,setEdit]=useState<any>(null),[del,setDel]=useState<any>(null);
  const add=useRef<HTMLInputElement>(null),rep=useRef<HTMLInputElement>(null),repId=useRef('');
  const load=useCallback(async()=>{try{const d=await request('/admin/marketing');setItems(d.items);setR2(!!d.r2);setErr('')}catch(e:any){setErr(e.message)}},[request]);
  useEffect(()=>{load()},[load]);
  const send=async(f:File,path:string,method:string)=>request(path,{method,body:f,headers:{'Content-Type':f.type||'application/octet-stream'}});
  const upload=async(files:FileList|null)=>{if(!files?.length)return;setErr('');setMsg('');
    for(const f of Array.from(files)){setBusy(`Uploading ${f.name} (${size(f.size)})…`);
      try{await send(f,`/admin/marketing?filename=${encodeURIComponent(f.name)}`,'POST');setMsg(`${f.name} added.`)}catch(e:any){setErr(`${f.name}: ${e.message}`);break}}
    setBusy('');load()};
  const replace=async(files:FileList|null)=>{const f=files?.[0];if(!f||!repId.current)return;setErr('');setMsg('');setBusy(`Replacing with ${f.name} (${size(f.size)})…`);
    try{await send(f,`/admin/marketing/${repId.current}/file?filename=${encodeURIComponent(f.name)}`,'PUT');setMsg(`Replaced with ${f.name}.`)}catch(e:any){setErr(e.message)}setBusy('');load()};
  const patch=async(id:string,body:any,ok='')=>{setErr('');try{await request(`/admin/marketing/${id}`,{method:'PATCH',body:JSON.stringify(body)});if(ok)setMsg(ok);await load()}catch(e:any){setErr(e.message)}};
  const remove=async()=>{if(!del)return;try{await request(`/admin/marketing/${del.id}`,{method:'DELETE'});setMsg(`${del.title} deleted.`);setDel(null);load()}catch(e:any){setErr(e.message);setDel(null)}};
  const copy=async(a:any)=>{const u=`${location.origin}${API.startsWith('http')?API:API}/marketing/${a.id}/file`;try{await navigator.clipboard.writeText(u);setMsg('Public link copied.')}catch{setMsg(u)}};
  const Ic=(k:string)=>k==='video'?<Film size={16}/>:k==='document'?<FileText size={16}/>:<FileIcon size={16}/>;
  return <section className="panel mkt">
    <div className="panelhead"><h2>Videos and documents</h2>
      <button type="button" className="primary" disabled={!!busy} onClick={()=>add.current?.click()}><Upload size={15}/> Add files</button></div>
    <input ref={add} type="file" multiple hidden onChange={e=>{upload(e.target.files);e.target.value=''}}/>
    <input ref={rep} type="file" hidden onChange={e=>{replace(e.target.files);e.target.value=''}}/>
    <p className="hint">Keep the marketing video, the playbook and any other sales files here. Add, replace, rename or delete them at any time. Tick <b>Public</b> to let anyone with the link open a file, and <b>Landing page</b> to put a video behind the Watch button, or a document as the playbook download link, on the home page. The video on the landing page is always named <b>isift-video</b> and the playbook <b>isift-playbook</b>, whatever the uploaded file was called. The first video and first document you upload take those places automatically.
      {r2?' Files are stored in your Cloudflare R2 bucket.':' Files are stored in the database (up to 150 MB each). Set up Cloudflare R2 under API and Settings for larger files.'}</p>
    {busy&&<p className="muted" role="status"><LoaderCircle size={15} className="spin"/> {busy} Please keep this page open.</p>}
    {msg&&<p className="notice-ok" role="status">{msg}</p>}{err&&<p className="syncerr" role="alert">{err}</p>}
    {items===null?<p className="muted">Loading…</p>:!items.length?<p className="muted">Nothing here yet. Use <b>Add files</b> to upload the marketing video and the playbook.</p>
    :<div className="utable mkt-table"><div className="urow uhead"><span>File</span><span>Type</span><span>Size</span><span>Added</span><span>Public</span><span>Landing page</span><span>Actions</span></div>
      {items.map(a=><div className="urow" key={a.id}>
        <span className="ucell" data-label="File">{edit?.id===a.id?<span className="mkt-edit"><input value={edit.title} onChange={e=>setEdit({...edit,title:e.target.value})} aria-label="Title"/><input value={edit.description} onChange={e=>setEdit({...edit,description:e.target.value})} placeholder="Note (optional)" aria-label="Note"/>
            <button type="button" className="iconbtn" title="Save" onClick={async()=>{await patch(a.id,{title:edit.title,description:edit.description},'Saved.');setEdit(null)}}><Check size={15}/></button><button type="button" className="iconbtn" title="Cancel" onClick={()=>setEdit(null)}><X size={15}/></button></span>
          :<><b>{a.title}</b><small className="muted block">{a.filename}{a.description?` · ${a.description}`:''}</small></>}</span>
        <span className="ucell" data-label="Type">{Ic(a.kind)} {a.kind==='video'?'Video':a.kind==='document'?'Document':'Other'}</span>
        <span className="ucell" data-label="Size">{size(a.size_bytes)}</span>
        <span className="ucell" data-label="Added">{day(a.created_at)}</span>
        <span className="ucell" data-label="Public"><label className="checklabel"><input type="checkbox" checked={a.public} onChange={e=>patch(a.id,{public:e.target.checked})}/> {a.public?'Yes':'No'}</label>{a.public&&<button type="button" className="textbtn" onClick={()=>copy(a)}><Link2 size={13}/> Copy link</button>}</span>
        <span className="ucell" data-label="Landing page">{a.kind==='video'||a.kind==='document'?<label className="checklabel"><input type="checkbox" checked={a.landing} onChange={e=>patch(a.id,{landing:e.target.checked},e.target.checked?(a.kind==='video'?'This video now plays from the Watch button on the landing page and is named isift-video.':'This document is now the playbook download on the landing page and is named isift-playbook.'):(a.kind==='video'?'The Watch button is hidden until a video is chosen.':'The playbook link is hidden until a document is chosen.'))}/> {a.landing?'Showing':'Show'}</label>:<span className="muted">—</span>}</span>
        <span className="ucell mkt-actions" data-label="Actions">
          <button type="button" className="iconbtn" title="View" onClick={()=>view(`/admin/marketing/${a.id}/file`)}><Eye size={15}/></button>
          <button type="button" className="iconbtn" title="Download" onClick={()=>download(`/admin/marketing/${a.id}/file?download=true`,a.filename)}><Download size={15}/></button>
          <button type="button" className="iconbtn" title="Rename or add a note" onClick={()=>setEdit({id:a.id,title:a.title,description:a.description})}><Pencil size={15}/></button>
          <button type="button" className="iconbtn" title="Replace with another file" disabled={!!busy} onClick={()=>{repId.current=a.id;rep.current?.click()}}><RefreshCw size={15}/></button>
          <button type="button" className="iconbtn danger" title="Delete" onClick={()=>setDel(a)}><Trash2 size={15}/></button></span></div>)}</div>}
    {del&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setDel(null)}}><section className="login-dialog" role="alertdialog" aria-modal="true" aria-label="Delete file"><div className="dialog-body"><h2>Delete “{del.title}”?</h2><p className="muted">The file is removed for good{del.public?', and its public link stops working':''}.</p>
      <div className="actions"><button type="button" className="secondary" onClick={()=>setDel(null)}>Keep it</button><button type="button" className="primary danger" onClick={remove}><Trash2 size={15}/> Delete</button></div></div></section></div>}
  </section>;
}

let landingP:Promise<any>|null=null;
const landing=()=>landingP||(landingP=fetch(`${API}/marketing/landing`).then(r=>r.json()).catch(()=>({video:null,playbook:null})));

/** The Watch button on the landing page. It only appears once a video is on the landing page (Admin Console, Sales & Marketing). */
export function WatchButton(){
  const [v,setV]=useState<any>(null),[open,setOpen]=useState(false);
  useEffect(()=>{landing().then(d=>setV(d.video||null))},[]);
  useEffect(()=>{if(!open)return;const k=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false)};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[open]);
  if(!v)return null;
  return <>
    <button type="button" className="hero-watch" onClick={()=>setOpen(true)}><span className="hw-ic"><Play size={14} fill="currentColor"/></span> Watch video</button>
    {open&&<div className="modal-backdrop video-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setOpen(false)}}><section className="video-dialog" role="dialog" aria-modal="true" aria-label="iSift video">
      <button type="button" className="modal-close" onClick={()=>setOpen(false)} aria-label="Close video">×</button>
      <video src={`${API}/marketing/${v.id}/file?v=${v.v}`} controls autoPlay playsInline preload="auto"/></section></div>}</>;
}

/** A download link for the playbook, shown on the landing page once a document is chosen there. */
export function PlaybookLink(){
  const [d,setD]=useState<any>(null);
  useEffect(()=>{landing().then(x=>setD(x.playbook||null))},[]);
  if(!d)return null;
  return <a className="hero-playbook" href={`${API}/marketing/${d.id}/file?download=true&v=${d.v}`} download={d.filename}><Download size={15}/> Download the iSift playbook <small>{d.filename.split('.').pop()?.toUpperCase()} · {size(d.size_bytes)}</small></a>;
}
