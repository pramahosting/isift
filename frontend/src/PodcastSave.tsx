import React,{useState} from 'react';
import {Cloud,HardDrive,Check} from 'lucide-react';
import {Take,prettyBytes,clock,slug} from './podcast';

const API=import.meta.env.VITE_API_BASE||(import.meta.env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
export const saveBlob=(blob:Blob,name:string)=>{const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),60000)};
const wait=(ms:number)=>new Promise(r=>setTimeout(r,ms));
export type SaveCfg={cloud_allowed:boolean;cloud_note:string};

/** After a recording: choose where to keep it (this computer, always on Basic, or the cloud on paid plans) and save. Used by Podcast Studio and by studio sessions in a meeting room. */
export function TakeSaver({take,title,token,cfg,onSaved,onDiscard,onCloud}:{take:Take;title:string;token:string;cfg:SaveCfg;onSaved:(saved:boolean)=>void;onDiscard:(saved:boolean)=>void;onCloud?:()=>void}){
  const [dest,setDest]=useState<'local'|'cloud'>('local'),[keepCopy,setKeepCopy]=useState(true),[prog,setProg]=useState(-1),[msg,setMsg]=useState(''),[err,setErr]=useState(''),[done,setDone]=useState(false);
  const cloudOk=cfg.cloud_allowed;
  const names=()=>{const b=slug(title);const d=new Date().toISOString().slice(0,16).replace(/[T:]/g,'-');return {master:`${b} ${d} master.${take.ext}`,track:(x:{label:string;ext:string})=>`${b} ${d} ${slug(x.label)}.${x.ext}`}};
  const saveLocal=async()=>{const n=names();saveBlob(take.master,n.master);for(const x of take.tracks){await wait(500);saveBlob(x.blob,n.track(x))}};
  const upload=()=>new Promise<void>((ok,no)=>{
    const f=new FormData();f.append('title',title||'Podcast');f.append('duration_s',String(take.seconds));f.append('width',String(take.width));f.append('height',String(take.height));f.append('audio_kbps',String(take.audioKbps));
    f.append('master',take.master,`master.${take.ext}`);take.tracks.forEach(x=>{f.append('tracks',x.blob,`track.${x.ext}`);f.append('track_labels',x.label)});
    const x=new XMLHttpRequest();x.open('POST',API+'/podcasts');x.setRequestHeader('Authorization',`Bearer ${token}`);
    x.upload.onprogress=e=>{if(e.lengthComputable)setProg(Math.round(e.loaded/e.total*100))};
    x.onload=()=>{let j:any={};try{j=JSON.parse(x.responseText)}catch{}x.status<300?ok():no(new Error(j.detail||`The upload failed (${x.status}).`))};x.onerror=()=>no(new Error('Cannot reach the iSift server.'));x.send(f)});
  const save=async()=>{
    setErr('');setMsg('');
    try{
      if(dest==='cloud'){if(keepCopy)await saveLocal();setProg(0);await upload();setProg(-1);setMsg('Saved in the cloud'+(keepCopy?' and on this computer.':'.')+' Find it under My cloud podcasts in Podcast Studio.');onCloud?.()}
      else{await saveLocal();setMsg(`Saved on this computer: ${1+take.tracks.length} file${take.tracks.length?'s':''} in your Downloads folder.`)}
      setDone(true);onSaved(true);
    }catch(e:any){setProg(-1);setErr((e?.message||'Could not save.')+(dest==='cloud'?' Your recording is still here: save it on this computer instead.':''))}
  };
  return <div className="pod-save">
    <p>{clock(take.seconds)} long. {take.hasVideo?`Video ${take.width}×${take.height}, `:'Audio only, '}{take.audioLabel}. Master {prettyBytes(take.master.size)}{take.tracks.length?`, plus ${take.tracks.length} separate track${take.tracks.length>1?'s':''}`:''}.</p>
    <h4>Where do you want to keep it?</h4>
    <label className={`pod-dest${dest==='local'?' on':''}`}><input type="radio" name="dest" checked={dest==='local'} onChange={()=>setDest('local')}/><HardDrive size={18}/><span><b>On this computer</b><small>Saved to your Downloads folder. Nothing is stored on iSift.</small></span></label>
    <label className={`pod-dest${dest==='cloud'?' on':''}${cloudOk?'':' off'}`}><input type="radio" name="dest" disabled={!cloudOk} checked={dest==='cloud'} onChange={()=>setDest('cloud')}/><Cloud size={18}/><span><b>In the cloud</b><small>{cloudOk?'Kept at original quality with your other recordings. Counts towards your storage.':cfg.cloud_note||'Not included in your plan.'}</small></span></label>
    {dest==='cloud'&&<label className="pod-check"><input type="checkbox" checked={keepCopy} onChange={e=>setKeepCopy(e.target.checked)}/> Also save a copy on this computer</label>}
    {prog>=0&&<div className="pod-prog" role="progressbar" aria-valuenow={prog}><u style={{width:prog+'%'}}/><span>Uploading {prog}%</span></div>}
    {err&&<p className="error" role="alert">{err}</p>}
    {msg&&<p className="pod-ok"><Check size={15}/> {msg}</p>}
    <div className="pod-ctl"><button className="primary" onClick={save} disabled={prog>=0||done}>{dest==='cloud'?'Save to the cloud':'Save to this computer'}</button><button className="secondary" onClick={()=>{if(!done&&!window.confirm('Discard this recording? It has not been saved yet.'))return;onDiscard(done)}}>{done?'Done':'Discard'}</button></div>
  </div>;
}
