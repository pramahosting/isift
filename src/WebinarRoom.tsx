import React,{useEffect,useMemo,useState} from 'react';
import {HelpCircle,BarChart3,Users,ThumbsUp,MicOff,VideoOff,Hand,Check,X as XIcon,Radio,Mic} from 'lucide-react';

/* The webinar side panel inside the meeting room: Q&A, polls and (for the host side) who is watching and who may speak.
   Everything is sent over the room's own connection (messages starting wb_); the server answers with wb-data. */

type Peer={id:string;name:string;host?:boolean;cohost?:boolean;mic?:boolean;cam?:boolean;hand?:boolean;attendee?:boolean;speaker?:boolean};
export type WbProps={info:any;data:any;peers:Peer[];send:(m:any)=>void;onClose:()=>void;tab:'qa'|'polls'|'people';setTab:(t:'qa'|'polls'|'people')=>void;style?:React.CSSProperties};

function Bars({counts,options,total}:{counts:number[];options:string[];total:number}){
  return <div className="wb-bars">{options.map((o,i)=>{const n=counts[i]||0;const pc=total?Math.round(100*n/total):0;return <div key={i} className="wb-bar"><span>{o}</span><div><i style={{width:pc+'%'}}/></div><b>{n} · {pc}%</b></div>})}</div>;
}

function QA({info,data,send,staff}:{info:any;data:any;send:(m:any)=>void;staff:boolean}){
  const [text,setText]=useState('');const [anon,setAnon]=useState(false);const [filter,setFilter]=useState<'open'|'answered'|'all'>('open');const [reply,setReply]=useState<Record<string,string>>({});
  const qs:any[]=data.questions||[];
  const shown=qs.filter(q=>filter==='all'?true:filter==='answered'?q.status==='answered':q.status!=='answered').sort((a,b)=>(b.up-a.up)||(a.at<b.at?-1:1));
  const ask=(e:React.FormEvent)=>{e.preventDefault();if(!text.trim())return;send({type:'wb_ask',text:text.trim(),anonymous:anon});setText('')};
  if(!info.qa)return <p className="muted">Questions are not turned on for this webinar.</p>;
  return <div className="wb-qa">
    {!staff&&<form onSubmit={ask} className="wb-ask"><textarea value={text} onChange={e=>setText(e.target.value)} maxLength={500} rows={3} placeholder="Type your question for the host" aria-label="Your question"/>
      <div className="wb-ask-row">{info.qa_anonymous&&<label className="checklabel"><input type="checkbox" checked={anon} onChange={e=>setAnon(e.target.checked)}/> Ask anonymously</label>}<button className="primary" disabled={!text.trim()}>Send</button></div></form>}
    {staff&&<div className="wb-filter" role="group" aria-label="Show questions">{(['open','answered','all'] as const).map(f=><button key={f} type="button" className={filter===f?'on':''} onClick={()=>setFilter(f)}>{f==='open'?'Open':f==='answered'?'Answered':'All'}</button>)}</div>}
    {!shown.length&&<p className="muted small">{staff?'No questions here yet.':'Questions you and others ask appear here.'}</p>}
    {shown.map(q=><div key={q.id} className={`wb-q ${q.status}${q.mine?' mine':''}`}>
      <div className="wb-q-h"><b>{q.name}</b>{q.mine&&<em> (you)</em>}{q.status==='dismissed'&&<span className="wb-tag">dismissed</span>}{q.status==='open'&&!staff&&q.mine&&info.qa_view==='answered'&&<span className="wb-tag">waiting for the host</span>}
        <button type="button" className={`wb-up${q.upped?' on':''}`} onClick={()=>send({type:'wb_up',id:q.id})} aria-label={`Upvote, ${q.up} so far`}><ThumbsUp size={13}/> {q.up}</button></div>
      <p>{q.text}</p>
      {q.status==='answered'&&<p className="wb-ans"><Check size={13}/> {q.answer?<>{q.answer} <span className="muted small">— {q.by}</span></>:<>Answered live by {q.by}</>}</p>}
      {staff&&q.status!=='answered'&&q.status!=='dismissed'&&<div className="wb-q-act"><input value={reply[q.id]||''} onChange={e=>setReply({...reply,[q.id]:e.target.value})} placeholder="Type an answer" aria-label="Answer"/>
        <button type="button" className="secondary" disabled={!(reply[q.id]||'').trim()} onClick={()=>{send({type:'wb_answer',id:q.id,text:reply[q.id]});setReply({...reply,[q.id]:''})}}>Send answer</button>
        <button type="button" className="secondary" onClick={()=>send({type:'wb_answer',id:q.id,live:true})}>Answered live</button><button type="button" className="secondary" onClick={()=>send({type:'wb_dismiss',id:q.id})} aria-label="Dismiss"><XIcon size={13}/></button></div>}
      {staff&&(q.status==='answered'||q.status==='dismissed')&&<div className="wb-q-act"><button type="button" className="secondary" onClick={()=>send({type:'wb_reopen',id:q.id})}>Reopen</button></div>}
    </div>)}
  </div>;
}

function Polls({data,send,staff}:{data:any;send:(m:any)=>void;staff:boolean}){
  const polls:any[]=data.polls||[];const [pick,setPick]=useState<Record<string,number[]>>({});
  if(!polls.length)return <p className="muted small">{staff?'No polls yet. Add them before the webinar under Meetings, Webinars, Polls.':'No poll is open right now.'}</p>;
  return <div className="wb-polls">{polls.map(p=>{const mine:number[]=p.mine||[];const voted=mine.length>0;const sel=pick[p.id]||[];const show=p.counts!==undefined;
    return <div key={p.id} className={`wb-poll ${p.status}`}>
      <div className="wb-q-h"><b>{p.question}</b><span className="wb-tag">{p.status==='draft'?'not launched':p.status==='open'?'open':'closed'}</span></div>
      {!staff&&p.status==='open'&&!voted&&<form onSubmit={e=>{e.preventDefault();if(sel.length)send({type:'wb_vote',id:p.id,choices:sel})}}>
        {p.options.map((o:string,i:number)=><label key={i} className="wb-opt"><input type={p.multi?'checkbox':'radio'} name={'p'+p.id} checked={sel.includes(i)} onChange={e=>setPick({...pick,[p.id]:p.multi?(e.target.checked?[...sel,i]:sel.filter(x=>x!==i)):[i]})}/> {o}</label>)}
        <button className="primary" disabled={!sel.length}>Vote</button>{p.multi&&<small className="muted"> You can choose more than one.</small>}</form>}
      {!staff&&voted&&!show&&<p className="muted small">Thank you, your answer was counted. {p.status==='open'?'Results appear when the host shares them.':''}</p>}
      {show&&<Bars counts={p.counts} options={p.options} total={p.total||0}/>}
      {show&&<p className="muted small">{p.total||0} vote{p.total===1?'':'s'}{voted?' · you voted':''}</p>}
      {staff&&<div className="wb-q-act">
        {p.status!=='open'&&<button type="button" className="primary" onClick={()=>send({type:'wb_poll',action:'open',id:p.id})}>{p.status==='closed'?'Launch again':'Launch poll'}</button>}
        {p.status==='open'&&<><button type="button" className="secondary" onClick={()=>send({type:'wb_poll',action:'close',id:p.id,share:true})}>End and share results</button><button type="button" className="secondary" onClick={()=>send({type:'wb_poll',action:'close',id:p.id,share:false})}>End</button></>}
        {p.status==='closed'&&<button type="button" className="secondary" onClick={()=>send({type:'wb_poll',action:'share',id:p.id,on:!p.share})}>{p.share?'Hide results from attendees':'Share results'}</button>}
      </div>}
    </div>})}</div>;
}

function People({info,data,peers,send}:{info:any;data:any;peers:Peer[];send:(m:any)=>void}){
  const [q,setQ]=useState('');const [sel,setSel]=useState<string[]>([]);
  const att=useMemo(()=>peers.filter(p=>p.attendee).filter(p=>!q.trim()||p.name.toLowerCase().includes(q.trim().toLowerCase())).sort((a,b)=>(+!!b.hand)-(+!!a.hand)||a.name.localeCompare(b.name)),[peers,q]);
  const spk=peers.filter(p=>p.speaker);const c=data.counts||{};
  const toggle=(id:string)=>setSel(s=>s.includes(id)?s.filter(x=>x!==id):[...s,id]);
  useEffect(()=>{setSel(s=>s.filter(id=>peers.some(p=>p.id===id&&p.attendee)))},[peers]);
  return <div className="wb-people">
    <p className="muted small"><b>{c.watching??att.length+spk.length}</b> watching{c.holding?<> · <b>{c.holding}</b> waiting for you to go live</>:null}</p>
    {spk.length>0&&<><h5>Speaking ({spk.length})</h5>{spk.map(p=><div key={p.id} className="wb-person"><span>{p.name}</span>
      <button type="button" className="secondary" title="Mute microphone" onClick={()=>send({type:'force',id:p.id,mic:false})}><MicOff size={13}/></button>
      <button type="button" className="secondary" title="Turn video off" onClick={()=>send({type:'force',id:p.id,cam:false})}><VideoOff size={13}/></button>
      <button type="button" className="secondary" onClick={()=>send({type:'wb_demote',ids:[p.id]})}>Back to watching</button></div>)}
      <div className="actions"><button type="button" className="secondary" onClick={()=>send({type:'wb_mute_all',cam:false})}><MicOff size={13}/> Mute all speakers</button><button type="button" className="secondary" onClick={()=>send({type:'wb_mute_all',cam:true})}><VideoOff size={13}/> Mute and video off</button></div></>}
    <h5>Attendees ({att.length})</h5>
    <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search attendees" aria-label="Search attendees"/>
    {sel.length>0&&<div className="actions"><button type="button" className="primary" onClick={()=>{send({type:'wb_promote',ids:sel});setSel([])}}><Mic size={13}/> Let {sel.length} speak</button><button type="button" className="secondary" onClick={()=>setSel([])}>Clear</button></div>}
    {!att.length&&<p className="muted small">{q?'Nobody matches.':'Nobody is watching yet.'}</p>}
    <div className="wb-list">{att.map(p=><div key={p.id} className={`wb-person${p.hand?' hand':''}`}><label><input type="checkbox" checked={sel.includes(p.id)} onChange={()=>toggle(p.id)} aria-label={`Select ${p.name}`}/> {p.hand&&<Hand size={13} aria-label="Hand raised"/>} {p.name}</label>
      {p.hand&&<button type="button" className="secondary" onClick={()=>send({type:'wb_hand_clear',id:p.id})}>Lower hand</button>}
      <button type="button" className="secondary" onClick={()=>send({type:'wb_promote',ids:[p.id]})}>Let speak</button></div>)}</div>
  </div>;
}

export function WebinarPanel({info,data,peers,send,onClose,tab,setTab,style}:WbProps){
  const staff=info.role==='host'||info.role==='panelist';const open=(data.polls||[]).filter((p:any)=>p.status==='open'&&!(p.mine||[]).length).length;
  return <aside className="rm-chat wb-panel" aria-label="Webinar Q&A and polls" style={style}>
    <div className="rm-chat-h"><b>{info.title||'Webinar'}</b><button type="button" className="secondary" onClick={onClose} aria-label="Close"><XIcon size={14}/></button></div>
    <div className="wb-tabs" role="tablist"><button role="tab" aria-selected={tab==='qa'} className={tab==='qa'?'on':''} onClick={()=>setTab('qa')}><HelpCircle size={14}/> Q&amp;A</button>
      <button role="tab" aria-selected={tab==='polls'} className={tab==='polls'?'on':''} onClick={()=>setTab('polls')}><BarChart3 size={14}/> Polls{open>0&&<i className="dot"/>}</button>
      {staff&&<button role="tab" aria-selected={tab==='people'} className={tab==='people'?'on':''} onClick={()=>setTab('people')}><Users size={14}/> People</button>}</div>
    <div className="wb-body">{tab==='qa'&&<QA info={info} data={data} send={send} staff={staff}/>}{tab==='polls'&&<Polls data={data} send={send} staff={staff}/>}{tab==='people'&&staff&&<People info={info} data={data} peers={peers} send={send}/>}</div>
  </aside>;
}

export function LiveBanner({info,data,send}:{info:any;data:any;send:(m:any)=>void}){
  if(!info)return null;const host=info.role==='host';const c=data.counts||{};
  if(info.live)return <div className="wb-banner live" role="status"><Radio size={14}/> LIVE{host||info.role==='panelist'?<> · {c.watching??0} watching</>:null}</div>;
  if(host)return <div className="wb-banner" role="status"><span>Practice session: only you and your panelists can see this. {c.holding?<b>{c.holding} waiting.</b>:'Attendees can open their link and wait.'}</span><button type="button" className="primary" onClick={()=>send({type:'wb_live',on:true})}>Go live</button></div>;
  return <div className="wb-banner" role="status">Practice session: attendees are not let in yet.</div>;
}
