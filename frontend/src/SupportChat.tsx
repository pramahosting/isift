import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {MessageCircle,Sparkles,X,Send} from 'lucide-react';

type Msg={role:'user'|'assistant';content:string};
const API:string=(import.meta as any).env.VITE_API_BASE||((import.meta as any).env.VITE_DEMO_MODE==='true'?'http://127.0.0.1:8000/api/v1':'/api/v1');
const STARTER:Msg={role:'assistant',content:'Hi, I\'m the iSift assistant. Ask me about meetings, recording, booking pages, AI minutes or our plans. For anything about your own account, email info@isift.au.'};
const SUGGEST=['What does iSift cost?','Can I record a meeting?','How do booking pages work?'];

// The chat icon for iSift customers. It stays out of the way inside a live meeting and inside an embedded booking page.
function hidden(){
  try{if(location.pathname.startsWith('/embed'))return true;const h=location.hash;return /^#\/room\//.test(h)||/^#\/book\/.*embed=1/.test(h)}catch{return false}
}

export default function SupportChat(){
  const [open,setOpen]=useState(false);const [msgs,setMsgs]=useState<Msg[]>([STARTER]);const [text,setText]=useState('');const [busy,setBusy]=useState(false);
  const [gone,setGone]=useState(hidden());const box=useRef<HTMLDivElement>(null);const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{const h=()=>setGone(hidden());window.addEventListener('hashchange',h);return()=>window.removeEventListener('hashchange',h)},[]);
  useEffect(()=>{box.current?.scrollTo({top:box.current.scrollHeight,behavior:'smooth'})},[msgs,open,busy]);
  useEffect(()=>{if(open)setTimeout(()=>input.current?.focus(),50)},[open]);
  useEffect(()=>{if(!open)return;const k=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false)};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[open]);
  if(gone)return null;
  const ask=async(q:string)=>{
    q=q.trim();if(!q||busy)return;const next=[...msgs,{role:'user' as const,content:q}];setMsgs(next);setText('');setBusy(true);
    try{
      const r=await fetch(`${API}/support/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:next.slice(1)})});
      const j=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(typeof j.detail==='string'?j.detail:'');
      setMsgs(m=>[...m,{role:'assistant',content:j.reply}]);
    }catch(e:any){setMsgs(m=>[...m,{role:'assistant',content:e?.message||'I could not reach the assistant just now. Please try again, or email info@isift.au.'}])}
    finally{setBusy(false)}
  };
  return createPortal(<div className="sc-wrap">
    {open&&<section className="sc-panel" role="dialog" aria-label="iSift assistant">
      <header className="sc-head"><span className="sc-title"><span className="sc-spark"><Sparkles size={14}/></span> iSift assistant</span><button type="button" onClick={()=>setOpen(false)} aria-label="Close chat" className="sc-x"><X size={16}/></button></header>
      <div ref={box} className="sc-msgs" aria-live="polite">
        {msgs.map((m,i)=><div key={i} className={`sc-msg ${m.role}`}>{m.content}</div>)}
        {busy&&<div className="sc-msg assistant sc-think">thinking…</div>}
        {msgs.length===1&&<div className="sc-suggest">{SUGGEST.map(s=><button key={s} type="button" onClick={()=>ask(s)}>{s}</button>)}</div>}
      </div>
      <form className="sc-form" onSubmit={e=>{e.preventDefault();ask(text)}}>
        <input ref={input} value={text} onChange={e=>setText(e.target.value)} maxLength={500} placeholder="Ask about iSift…" aria-label="Your question"/>
        <button type="submit" disabled={busy||!text.trim()} aria-label="Send message"><Send size={15}/></button>
      </form>
      <p className="sc-note">AI answers can be wrong. For your account, email <a href="mailto:info@isift.au">info@isift.au</a>.</p>
    </section>}
    <button type="button" className="sc-orb" onClick={()=>setOpen(o=>!o)} aria-expanded={open} aria-label={open?'Close chat':'Chat with iSift'}>
      {open?<X size={30} strokeWidth={1.75}/>:<><span className="sc-icon"><MessageCircle size={34} strokeWidth={1.5}/></span><span className="sc-ask">Ask</span><span className="sc-ring" aria-hidden="true"><i/></span></>}
    </button>
  </div>,document.body);
}
