import React,{useCallback,useEffect,useState} from 'react';
import {Check,Copy,Send,Trash2,Link2,Users,Mail,MessageSquare,X} from 'lucide-react';
import {Modal} from './Modal';

const copyText=async(t:string)=>{try{await navigator.clipboard.writeText(t)}catch{window.prompt('Copy this:',t)}};
export const KIND_NAME:Record<string,string>={doc:'note',board:'whiteboard',wp:'document',sheet:'workbook',deck:'presentation'};
const PERMS=[['viewer','Viewer','can open and read it'],['commenter','Commenter','can read it and add comments'],['editor','Editor','can change it']] as const;
const permName=(p:string)=>({viewer:'Viewer',commenter:'Commenter',editor:'Editor',owner:'Owner'} as any)[p]||p;
const when=(s?:string|null)=>s?new Date(s).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'}):'';
const dayEnd=(d:string)=>d?new Date(d+'T23:59:59').toISOString():null;       // the chosen day, until its end in the person's time
/** Draw note text onto A4-shaped pages (JPEG) for notes with letters the server's PDF font cannot show. */
export function notePages(title:string,text:string):string[]{
  const W=1240,H=1754,M=110,fs=26,lh=38,out:string[]=[];let c:HTMLCanvasElement,g:CanvasRenderingContext2D,y=0;
  const fresh=()=>{c=document.createElement('canvas');c.width=W;c.height=H;g=c.getContext('2d')!;g.fillStyle='#fff';g.fillRect(0,0,W,H);g.fillStyle='#172033';y=M+10;out.push('')};
  const done=()=>{out[out.length-1]=c.toDataURL('image/jpeg',0.9)};
  fresh();g.font='bold 40px sans-serif';for(const l of wrapText(g,title||'Untitled',W-2*M)){g.fillText(l,M,y);y+=54}y+=18;g.font=`${fs}px sans-serif`;
  for(const raw of text.replace(/\r\n/g,'\n').split('\n')){for(const l of wrapText(g,raw,W-2*M)){if(y>H-M){done();fresh();g.font=`${fs}px sans-serif`}g.fillText(l,M,y);y+=lh}if(!raw)y+=lh}
  done();return out}
function wrapText(g:CanvasRenderingContext2D,line:string,w:number):string[]{
  if(!line)return[''];const words=line.split(/(\s+)/);const res:string[]=[];let cur='';
  for(const wd of words){let t=cur+wd;if(g.measureText(t).width>w&&cur.trim()){res.push(cur.trimEnd());cur=wd.trimStart()}else cur=t;
    while(g.measureText(cur).width>w&&cur.length>1){let k=cur.length-1;while(k>1&&g.measureText(cur.slice(0,k)).width>w)k--;res.push(cur.slice(0,k));cur=cur.slice(k)}}
  res.push(cur.trimEnd());return res}

type Pick={groups:string[];contacts:string[]};
export function ShareDialog({request,note,kind,title,content,picture,onClose}:{request:any;note:string;kind:string;title:string;content:string;picture:()=>string|null;onClose:()=>void}){
  const [tab,setTab]=useState<'people'|'link'|'pdf'>('people');const what=KIND_NAME[kind]||'file';
  const [data,setData]=useState<any>({contacts:[],groups:[]});const [acc,setAcc]=useState<any>({people:[],links:[]});
  const loadAcc=useCallback(()=>request(`/notes/${note}/shares`).then(setAcc).catch(()=>{}),[request,note]);
  useEffect(()=>{request('/contacts').then(setData).catch(()=>{});loadAcc()},[]);
  /* people and groups */
  const [q,setQ]=useState('');const [pick,setPick]=useState<Pick>({groups:[],contacts:[]});const [typed,setTyped]=useState('');const [perm,setPerm]=useState('viewer');const [exp,setExp]=useState('');const [msg,setMsg]=useState('');const [mail,setMail]=useState(true);
  const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [res,setRes]=useState<any>(null);
  const tog=(k:keyof Pick,id:string)=>setPick(p=>({...p,[k]:p[k].includes(id)?p[k].filter(x=>x!==id):[...p[k],id]}));
  const match=(s:string)=>s.toLowerCase().includes(q.trim().toLowerCase());
  const groups=data.groups.filter((g:any)=>match(g.name));const contacts=data.contacts.filter((c:any)=>c.email&&(match(c.name)||match(c.email)));
  const shareNow=async()=>{setErr('');setRes(null);const emails=typed.split(/[\s,;]+/).map(x=>x.trim()).filter(Boolean);
    if(!emails.length&&!pick.groups.length&&!pick.contacts.length){setErr('Choose a group, a contact, or type an email address.');return}
    setBusy(true);try{const r=await request(`/notes/${note}/shares`,{method:'POST',body:JSON.stringify({emails,contact_ids:pick.contacts,group_ids:pick.groups,permission:perm,message:msg,send_email:mail,expires_at:dayEnd(exp),base_url:location.origin+location.pathname})});setRes(r);setPick({groups:[],contacts:[]});setTyped('');loadAcc()}catch(e:any){setErr(e.message||'Could not share.')}setBusy(false)};
  const setShare=async(id:string,body:any)=>{try{await request(`/notes/${note}/shares/${id}`,{method:'PATCH',body:JSON.stringify(body)});loadAcc()}catch(e:any){setErr(e.message)}};
  const revoke=async(id:string,name:string)=>{if(!window.confirm(`Remove access for ${name}?`))return;try{await request(`/notes/${note}/shares/${id}`,{method:'DELETE'});loadAcc()}catch(e:any){setErr(e.message)}};
  const stopAll=async()=>{if(!window.confirm('Stop sharing with everyone and revoke all links?'))return;try{await request(`/notes/${note}/stop-sharing`,{method:'POST'});setRes(null);loadAcc()}catch(e:any){setErr(e.message)}};
  /* link */
  const [lp,setLp]=useState('viewer');const [lexp,setLexp]=useState('');const [lonly,setLonly]=useState('');const [made,setMade]=useState<any>(null);const [chatTo,setChatTo]=useState('');const [note_,setNote_]=useState('');
  const makeLink=async()=>{setErr('');setNote_('');try{const only=lonly.split(/[\s,;]+/).map(x=>x.trim()).filter(Boolean);const r=await request(`/notes/${note}/links`,{method:'POST',body:JSON.stringify({permission:lp,expires_at:dayEnd(lexp),emails:only,base_url:location.origin+location.pathname})});setMade(r);loadAcc()}catch(e:any){setErr(e.message)}};
  const sendChat=async()=>{if(!made||!chatTo)return;setErr('');try{const body=chatTo.startsWith('g:')?{group_id:chatTo.slice(2)}:{contact_ids:[chatTo]};const ch=await request('/chat/channels',{method:'POST',body:JSON.stringify(body)});
      await request(`/chat/channels/${ch.id}/messages`,{method:'POST',body:JSON.stringify({text:`I shared the ${what} “${title||'Untitled'}” with you (${permName(made.permission)} access): ${made.url}`})});setNote_('Sent in iSift Chat.')}catch(e:any){setErr(e.message)}};
  /* pdf */
  const [typedPdf,setTypedPdf]=useState('');const [pdfMsg,setPdfMsg]=useState('');const [pdfDone,setPdfDone]=useState<any>(null);const [pc,setPc]=useState<Pick>({groups:[],contacts:[]});
  const sendPdf=async()=>{setErr('');const emails=typedPdf.split(/[\s,;]+/).map(x=>x.trim()).filter(Boolean);
    if(!emails.length&&!pc.contacts.length&&!pc.groups.length){setErr('Choose a group, a contact, or type an email address.');return}
    setBusy(true);try{await request(`/notes/${note}`,{method:'PUT',body:JSON.stringify({title,content})});
      const body:any={emails,contact_ids:pc.contacts,group_ids:pc.groups,message:pdfMsg};
      if(kind==='board'){const pic=picture();if(!pic){setErr('The whiteboard is empty. Draw something first.');setBusy(false);return}body.pages=[pic]}
      let r=await request(`/notes/${note}/share`,{method:'POST',body:JSON.stringify(body)});
      if(r.needs_pictures){body.pages=notePages(title,content);r=await request(`/notes/${note}/share`,{method:'POST',body:JSON.stringify(body)})}
      setPdfDone(r)}catch(e:any){setErr(e.message||'Could not send.')}setBusy(false)};
  const chk=(on:boolean,fn:()=>void,label:React.ReactNode,key:string)=><label key={key} className="check"><input type="checkbox" checked={on} onChange={fn}/> {label}</label>;
  const people=acc.people||[];
  return <Modal title={`Share ${what}: ${title||'Untitled'}`} onClose={onClose} wide>
    <div className="st-tabs" role="tablist" aria-label="How to share">
      <button type="button" role="tab" aria-selected={tab==='people'} className={`wb-cat${tab==='people'?' on':''}`} onClick={()=>{setTab('people');setErr('')}}><Users size={13}/> People and groups</button>
      <button type="button" role="tab" aria-selected={tab==='link'} className={`wb-cat${tab==='link'?' on':''}`} onClick={()=>{setTab('link');setErr('')}}><Link2 size={13}/> iSift link</button>
      <button type="button" role="tab" aria-selected={tab==='pdf'} className={`wb-cat${tab==='pdf'?' on':''}`} onClick={()=>{setTab('pdf');setErr('')}}><Mail size={13}/> Email a PDF copy</button></div>
    {err&&<p className="error" role="alert">{err}</p>}
    {tab==='people'&&<div className="share-body">
      <input type="search" placeholder="Search your contacts and groups by name or email" value={q} onChange={e=>setQ(e.target.value)} aria-label="Search recipients"/>
      {groups.length>0&&<><b className="small">Groups</b><div className="share-pick">{groups.map((g:any)=>chk(pick.groups.includes(g.id),()=>tog('groups',g.id),<>{g.name} <small className="muted">({g.contact_ids.length} {g.contact_ids.length===1?'member':'members'}; access follows the group)</small></>,g.id))}</div></>}
      {contacts.length>0&&<><b className="small">People</b><div className="share-pick">{contacts.map((c:any)=>chk(pick.contacts.includes(c.id),()=>tog('contacts',c.id),<>{c.name} <small className="muted">{c.email}{c.user_id?'':' · no iSift account yet'}</small></>,c.id))}</div></>}
      {!groups.length&&!contacts.length&&<small className="muted">{q?'No contacts match.':'You have no contacts yet. Type email addresses below, or add contacts in Commbox.'}</small>}
      <label>Other email addresses<input value={typed} onChange={e=>setTyped(e.target.value)} placeholder="name@example.com, another@example.com" aria-label="Other email addresses"/></label>
      <div className="share-row"><label>Access<select value={perm} onChange={e=>setPerm(e.target.value)} aria-label="Access level">{PERMS.map(([v,l,d])=><option key={v} value={v}>{l} — {d}</option>)}</select></label>
        <label>Access ends (optional)<input type="date" value={exp} min={new Date().toISOString().slice(0,10)} onChange={e=>setExp(e.target.value)} aria-label="Access ends on"/></label></div>
      <label>Message (optional)<textarea rows={2} value={msg} onChange={e=>setMsg(e.target.value)} aria-label="Message"/></label>
      <label className="check"><input type="checkbox" checked={mail} onChange={e=>setMail(e.target.checked)}/> Email each person a secure link (people with an iSift account also get an alert)</label>
      <div className="modal-actions"><button className="primary" disabled={busy} onClick={shareNow}><Send size={15}/> {busy?'Sharing…':'Share'}</button></div>
      {res&&<div role="status" className="share-res">{!res.email_configured&&mail&&<p className="error">No email account is set up, so no emails could be sent. Access was still given.</p>}
        {res.results.map((x:any,i:number)=><p key={i}>{x.status==='skipped'?<X size={13}/>:<Check size={13}/>} <b>{x.to}</b>{x.group?` (group, ${x.members} members)`:''}: {x.status==='shared'?'shared':x.status==='updated'?'access updated':x.status==='unchanged'?'already had this access (no new email)':'not shared'}{x.status==='shared'&&mail&&(x.emailed===true?' · emailed':x.emailed===false?` · ${x.error||'not emailed'}`:x.emailed_count!==undefined?` · ${x.emailed_count} emailed${x.failed_count?`, ${x.failed_count} failed`:''}`:'')}{x.status==='skipped'?` · ${x.error}`:''}</p>)}</div>}
      <h3 className="share-h">Who has access</h3>
      {people.length?<table className="modtable share-tbl"><thead><tr><th>Who</th><th>Access</th><th>Ends</th><th>Since</th><th/></tr></thead><tbody>{people.map((p:any)=><tr key={p.id}>
        <td><b>{p.name}</b>{p.kind==='group'?<small className="muted"> group: {p.members.map((m:any)=>m.name).join(', ')||'no members'}</small>:p.email&&p.email!==p.name?<small className="muted"> {p.email}{p.has_account?'':' · no account yet'}</small>:null}</td>
        <td><select value={p.permission} aria-label={`Access for ${p.name}`} onChange={e=>setShare(p.id,{permission:e.target.value})}>{PERMS.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>{p.status!=='active'&&<small className="error"> {p.status}</small>}</td>
        <td><input type="date" value={p.expires_at?p.expires_at.slice(0,10):''} aria-label={`Access ends for ${p.name}`} onChange={e=>setShare(p.id,{expires_at:dayEnd(e.target.value)})}/></td><td>{when(p.created_at)}</td>
        <td><button className="iconbtn" aria-label={`Remove ${p.name}`} title="Remove access" onClick={()=>revoke(p.id,p.name)}><Trash2 size={15}/></button></td></tr>)}</tbody></table>:<small className="muted">Only you can open this {what}.</small>}
      {(people.length>0||acc.links?.length>0)&&<button type="button" className="textbtn danger" onClick={stopAll}>Stop sharing with everyone</button>}
      <small className="muted">Everyone with access works on the same {what}. It is not live co-editing: if two people with Editor access save at once, the later save is refused and that person reloads to see the other's changes.</small>
    </div>}
    {tab==='link'&&<div className="share-body">
      <p className="muted small">A link opens the {what} only for people signed in to iSift, never for the public. It stops working when it expires or when you revoke it.</p>
      <div className="share-row"><label>Access<select value={lp} onChange={e=>setLp(e.target.value)} aria-label="Link access level">{PERMS.map(([v,l,d])=><option key={v} value={v}>{l} — {d}</option>)}</select></label>
        <label>Link ends (optional)<input type="date" value={lexp} min={new Date().toISOString().slice(0,10)} onChange={e=>setLexp(e.target.value)} aria-label="Link ends on"/></label></div>
      <label>Only these people (optional, emails)<input value={lonly} onChange={e=>setLonly(e.target.value)} placeholder="Leave empty to allow anyone signed in who has the link" aria-label="Restrict link to these emails"/></label>
      <div className="modal-actions"><button className="primary" onClick={makeLink}><Link2 size={15}/> Create link</button></div>
      {made&&<div className="share-res" role="status"><p><b>Copy it now: it is shown only once.</b></p><div className="share-row"><input readOnly value={made.url} aria-label="Share link" onFocus={e=>e.target.select()}/><button className="secondary" onClick={()=>{copyText(made.url);setNote_('Copied.')}}><Copy size={14}/> Copy link</button></div>
        <div className="share-row"><label>Send it in iSift Chat<select value={chatTo} onChange={e=>setChatTo(e.target.value)} aria-label="Send the link in chat to"><option value="">Choose a person or group…</option>
          {data.groups.length>0&&<optgroup label="Groups">{data.groups.map((g:any)=><option key={g.id} value={'g:'+g.id}>{g.name}</option>)}</optgroup>}<optgroup label="People with an iSift account">{data.contacts.filter((c:any)=>c.user_id).map((c:any)=><option key={c.id} value={c.id}>{c.name}</option>)}</optgroup></select></label>
          <button className="secondary" disabled={!chatTo} onClick={sendChat}><MessageSquare size={14}/> Send</button></div>{note_&&<small role="status">{note_}</small>}</div>}
      <h3 className="share-h">Links you made</h3>
      {acc.links?.length?<table className="modtable share-tbl"><thead><tr><th>Link</th><th>Access</th><th>Ends</th><th>Opened by</th><th/></tr></thead><tbody>{acc.links.map((l:any)=><tr key={l.id}><td>{l.restricted?`Only ${l.emails.join(', ')}`:'Anyone signed in'}<small className="muted"> made {when(l.created_at)}</small></td>
        <td><select value={l.permission} aria-label="Link access" onChange={e=>setShare(l.id,{permission:e.target.value})}>{PERMS.map(([v,x])=><option key={v} value={v}>{x}</option>)}</select></td><td>{l.status==='active'?(l.expires_at?when(l.expires_at):'No end'):<span className="error">{l.status}</span>}</td><td>{l.opened_by}</td>
        <td><button className="textbtn danger" onClick={()=>revoke(l.id,'this link')}>Revoke</button></td></tr>)}</tbody></table>:<small className="muted">No links yet.</small>}
    </div>}
    {tab==='pdf'&&(pdfDone?<><p role="status"><Check size={15}/> Sent to {pdfDone.sent.length} {pdfDone.sent.length===1?'person':'people'} as <b>{pdfDone.file}</b>.</p>{pdfDone.failed?.length>0&&<p className="error">Could not reach: {pdfDone.failed.join(', ')}</p>}<div className="modal-actions"><button className="primary" onClick={onClose}>Done</button></div></>
      :<div className="share-body"><p className="muted small">A PDF copy is attached to the email. People who receive it cannot edit your {what}; use People and groups to give them access.</p>
        {data.groups.length>0&&<><b className="small">Groups</b><div className="share-pick">{data.groups.map((g:any)=>chk(pc.groups.includes(g.id),()=>setPc(p=>({...p,groups:p.groups.includes(g.id)?p.groups.filter(x=>x!==g.id):[...p.groups,g.id]})),<>{g.name} <small className="muted">({g.contact_ids.length})</small></>,g.id))}</div></>}
        {data.contacts.length>0&&<><b className="small">Contacts and participants</b><div className="share-pick">{data.contacts.filter((c:any)=>c.email).map((c:any)=>chk(pc.contacts.includes(c.id),()=>setPc(p=>({...p,contacts:p.contacts.includes(c.id)?p.contacts.filter(x=>x!==c.id):[...p.contacts,c.id]})),<>{c.name} <small className="muted">{c.email}</small></>,c.id))}</div></>}
        <label>Other email addresses<input value={typedPdf} onChange={e=>setTypedPdf(e.target.value)} placeholder="name@example.com, another@example.com" aria-label="PDF recipients"/></label>
        <label>Message (optional)<textarea rows={2} value={pdfMsg} onChange={e=>setPdfMsg(e.target.value)} aria-label="PDF message"/></label>
        <div className="modal-actions"><button className="primary" disabled={busy} onClick={sendPdf}><Send size={15}/> {busy?'Sending…':'Send PDF'}</button></div></div>)}
  </Modal>}

/** Shown above a file someone shared with you: who owns it and what you may do. */
export function SharedBanner({access,owner,kind}:{access:string;owner?:{name:string;email:string};kind:string}){
  if(access==='owner'||!access)return null;const what=KIND_NAME[kind]||'file';
  const may=access==='viewer'?`You can read this ${what} but not change it.`:access==='commenter'?`You can read this ${what} and add comments, but not change it.`:`You can change this ${what}. It saves for everyone with access; if someone saves first, yours is refused and you can reload.`;
  return <div className="shared-banner" role="note"><b>{permName(access)}</b> access · shared by {owner?.name||owner?.email||'the owner'}{owner?.email&&owner.name?` (${owner.email})`:''} · {may}</div>}

export function CommentsPanel({request,note,canWrite}:{request:any;note:string;canWrite:boolean}){
  const [items,setItems]=useState<any[]>([]);const [text,setText]=useState('');const [err,setErr]=useState('');const [open,setOpen]=useState(false);
  const load=useCallback(()=>request(`/notes/${note}/comments`).then((r:any)=>setItems(r.items)).catch(()=>{}),[request,note]);
  useEffect(()=>{load()},[note]);
  const add=async()=>{setErr('');if(!text.trim())return;try{await request(`/notes/${note}/comments`,{method:'POST',body:JSON.stringify({text})});setText('');load()}catch(e:any){setErr(e.message)}};
  const del=async(id:string)=>{try{await request(`/notes/${note}/comments/${id}`,{method:'DELETE'});load()}catch(e:any){setErr(e.message)}};
  return <div className="comments"><button type="button" className="textbtn" aria-expanded={open} onClick={()=>setOpen(!open)}>Comments ({items.length})</button>
    {open&&<div className="comments-body">{items.length?items.map(c=><div key={c.id} className="comment"><b>{c.author}</b> <small className="muted">{new Date(c.at).toLocaleString(undefined,{day:'numeric',month:'short',hour:'numeric',minute:'2-digit'})}</small>{c.can_delete&&<button className="iconbtn" aria-label="Delete comment" onClick={()=>del(c.id)}><Trash2 size={13}/></button>}<p>{c.text}</p></div>):<small className="muted">No comments yet.</small>}
      {canWrite?<div className="share-row"><input value={text} onChange={e=>setText(e.target.value)} placeholder="Write a comment…" aria-label="New comment" onKeyDown={e=>{if(e.key==='Enter')add()}}/><button className="secondary" onClick={add}>Comment</button></div>:<small className="muted">Your access does not allow comments.</small>}
      {err&&<p className="error" role="alert">{err}</p>}</div>}</div>}
