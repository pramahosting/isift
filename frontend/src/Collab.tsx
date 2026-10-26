/* A file everyone in the meeting sees live. The owner shares a note, document, spreadsheet, presentation or whiteboard; the owner (or a host) lets one person at a time edit it, and every change appears for everyone as it happens. */
import React,{useEffect,useRef,useState} from 'react';
import {Board} from './Whiteboard';
import {WordEditor,SheetEditor,DeckEditor} from './DocsEditors';

export type CollabState={kind:string;title:string;owner:string;owner_name:string;holder:string;holder_name:string;rev:number;note:string;content:string};
export const COLLAB_KINDS:[string,string][]=[['doc','Notes'],['wp','Documents'],['sheet','Spreadsheets'],['deck','Presentations'],['board','Whiteboards']];
const NAME:Record<string,string>={doc:'note',wp:'document',sheet:'spreadsheet',deck:'presentation',board:'whiteboard'};

export function CollabPanel({c,ended,myId,isHost,people,asks,token,api,onClose,send,onEdit,onDismissAsk,onDismissEnded}:{c:CollabState|null;ended:{title:string;kind:string;content:string;reason:string}|null;myId:string;isHost:boolean;people:{id:string;name:string}[];asks:{id:string;name:string}[];token:string;api:string;onClose:()=>void;send:(m:any)=>void;onEdit:(content:string)=>void;onDismissAsk:(id:string)=>void;onDismissEnded:()=>void}){
  const [kind,setKind]=useState('doc');const [files,setFiles]=useState<any[]>([]);const [busy,setBusy]=useState('');const [msg,setMsg]=useState('');const [give,setGive]=useState('');
  const req=async(path:string,init?:any)=>{const r=await fetch(api+path,{...init,headers:{'content-type':'application/json',Authorization:`Bearer ${token}`}});if(!r.ok)throw new Error(String(r.status));return r.json()};
  useEffect(()=>{if(c||!token)return;let on=true;setFiles([]);req(`/notes?kind=${kind}`).then(l=>{if(on)setFiles(Array.isArray(l)?l:[])}).catch(()=>{});return()=>{on=false}},[kind,!!c,token]);
  const share=async(id:string)=>{setBusy(id);try{const n=await req(`/notes/${id}`);send({type:'collab_open',kind,title:n.title,content:n.content||'',note:id})}catch{setMsg('That file could not be opened.')}setBusy('')};
  const blank=()=>send({type:'collab_open',kind,title:`New ${NAME[kind]}`,content:''});
  const saveCopy=async(k:string,title:string,content:string)=>{try{await req('/notes',{method:'POST',body:JSON.stringify({kind:k,title:`${title} (copy)`.slice(0,120),content})});setMsg('Saved to your files.')}catch{setMsg('Could not save a copy.')}};
  const iOwn=!!c&&c.owner===myId,iHold=!!c&&c.holder===myId,canGive=!!c&&(iOwn||isHost);
  // the owner keeps the saved file up to date, whoever is typing
  const saved=useRef('');useEffect(()=>{if(!c||!iOwn||!c.note||!token||c.content===saved.current)return;const t=setTimeout(()=>{saved.current=c.content;req(`/notes/${c.note}`,{method:'PUT',body:JSON.stringify({content:c.content})}).catch(()=>{saved.current=''})},1500);return()=>clearTimeout(t)},[c?.content,c?.note,iOwn]);
  const editor=()=>{if(!c)return null;const ro=!iHold;const key=`${c.kind}:${c.holder}:${ro?c.rev:'edit'}`;const p={content:c.content,onChange:onEdit,readOnly:ro,title:c.title};
    return c.kind==='doc'?<textarea key={key} className="ws-doc rm-cb-text" value={c.content} readOnly={ro} aria-label="Shared note" placeholder={ro?'':'Start typing…'} onChange={e=>onEdit(e.target.value)}/>
      :c.kind==='board'?<Board key={key} name={c.title} readOnly={ro} libOpen={false} content={c.content} onChange={onEdit}/>
      :c.kind==='wp'?<WordEditor key={key} {...p}/>:c.kind==='sheet'?<SheetEditor key={key} {...p}/>:<DeckEditor key={key} {...p}/>};
  const others=people.filter(p=>p.id!==c?.holder);
  return <div className="rm-wb open rm-cb" role="dialog" aria-label="Shared file">
    <div className="rm-wbbar">{c?<><b className="rm-cb-t">{c.title}</b><span className="muted small">Shared by {iOwn?'you':c.owner_name} · {iHold?'You can edit':`${iOwn&&c.holder===c.owner?'You':c.holder_name||c.owner_name} ${iOwn&&c.holder===c.owner?'are':'is'} editing`}</span></>:<b className="rm-cb-t">Work on a file together</b>}<span className="sp"/>
      {c&&canGive&&c.holder!==c.owner&&<button type="button" className="secondary" onClick={()=>send({type:'collab_take'})}>Take editing back</button>}
      {c&&canGive&&others.length>0&&<><select className="rm-cb-sel" aria-label="Let someone edit" value={give} onChange={e=>setGive(e.target.value)}><option value="">Let someone edit…</option>{others.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select><button type="button" className="secondary" disabled={!give} onClick={()=>{send({type:'collab_give',to:give});setGive('')}}>Allow</button></>}
      {c&&!iHold&&!canGive&&<button type="button" className="secondary" onClick={()=>{send({type:'collab_ask'});setMsg('Asked the owner to let you edit.')}}>Ask to edit</button>}
      {c&&token&&!iOwn&&<button type="button" className="secondary" onClick={()=>saveCopy(c.kind,c.title,c.content)}>Save a copy</button>}
      {c&&canGive&&<button type="button" className="secondary" onClick={()=>{if(window.confirm('Stop sharing this file with everyone?'))send({type:'collab_close'})}}>Stop sharing</button>}
      <button type="button" className="primary" onClick={onClose}>Back to meeting</button></div>
    {(msg||asks.length>0||ended)&&<div className="rm-cb-notes" role="status">
      {asks.map(a=><span key={a.id} className="rm-cb-note">{a.name} asks to edit. <button type="button" className="textbtn" onClick={()=>{send({type:'collab_give',to:a.id});onDismissAsk(a.id)}}>Allow</button> <button type="button" className="textbtn" onClick={()=>onDismissAsk(a.id)}>Not now</button></span>)}
      {ended&&!c&&<span className="rm-cb-note">{ended.reason==='owner_left'?'The owner left, so sharing ended.':'Sharing ended.'} {token&&ended.content&&<button type="button" className="textbtn" onClick={()=>saveCopy(ended.kind,ended.title,ended.content)}>Save a copy of "{ended.title}"</button>} <button type="button" className="textbtn" onClick={onDismissEnded}>Dismiss</button></span>}
      {msg&&<span className="rm-cb-note">{msg} <button type="button" className="textbtn" onClick={()=>setMsg('')}>OK</button></span>}</div>}
    <div className="rm-wbbody rm-cb-body">{c?<section className="ws-editor rm-cb-ed">{editor()}</section>:
      <div className="rm-cb-pick"><p className="muted">Pick a file to show everyone. They see it live, and you decide who can edit it.</p>
        <div className="notes-scope" role="tablist" aria-label="Kind of file">{COLLAB_KINDS.map(([k,l])=><button key={k} type="button" role="tab" aria-selected={kind===k} className={`wb-cat${kind===k?' on':''}`} onClick={()=>setKind(k)}>{l}</button>)}</div>
        <div className="rm-cb-list">{token?(files.length?files.map(f=><button key={f.id} type="button" className="ws-ch shared-row" disabled={!!busy} onClick={()=>share(f.id)}><div className="ws-main"><b>{f.title}</b><small className="muted">{busy===f.id?'Opening…':'Edited '+new Date(f.updated_at).toLocaleString(undefined,{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})}</small></div></button>):<p className="muted">You have no {NAME[kind]}s yet.</p>):<p className="muted">Sign in to share your own files. You can still start a blank one.</p>}</div>
        <button type="button" className="primary" onClick={blank}>Start a blank {NAME[kind]}</button></div>}</div>
  </div>;
}
