// The parts of the meeting screen that sit around the toolbar: the More menu (tools can be pinned to the bar), reactions,
// live captions with a transcript, and the host tools menu. Room.tsx owns the state; these only draw it.
import React,{useEffect,useRef,useState} from 'react';
import {Pin,PinOff,X,Hand,Download,Lock,LockOpen,ShieldCheck,Mic,Subtitles,ChevronRight,Users} from 'lucide-react';

export type Tool={id:string;label:string;hint?:string;icon:React.ReactNode;on?:boolean;group:'Meeting'|'Share and work'|'Host'|'View';run:()=>void};

/** Tools the person pinned to the bar stay there in every meeting on this device. */
const PIN_KEY='isift.pinned';
export const loadPins=():string[]=>{try{const v=JSON.parse(localStorage.getItem(PIN_KEY)||'[]');return Array.isArray(v)?v.filter(x=>typeof x==='string'):[]}catch{return []}};
export const savePins=(p:string[])=>{try{localStorage.setItem(PIN_KEY,JSON.stringify(p))}catch{/* private window */}};

export const REACTIONS=['👍','👏','❤️','😂','😮','🎉','🙏','😢','🔥','💯','👎','✅'];

function useEscape(onClose:()=>void){useEffect(()=>{const f=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',f);return()=>window.removeEventListener('keydown',f)},[onClose])}

/** A tool shown on the bar next to the core buttons. The small pin keeps it there; the cross sends an unpinned tool back to More. */
export function ToolButton({tool,pinned,onPin,onHide}:{tool:Tool;pinned:boolean;onPin:()=>void;onHide:()=>void}){
  return <div className="rm-xwrap">
    <button type="button" className={`rm-btn${tool.on?' on':''}`} onClick={tool.run} aria-label={tool.label} aria-pressed={tool.on?true:undefined} title={tool.hint||tool.label}>{tool.icon}<span>{tool.label}</span></button>
    <span className="rm-xctl">
      <button type="button" aria-label={pinned?`Unpin ${tool.label} (back to More)`:`Pin ${tool.label} to the toolbar`} title={pinned?'Unpin: move back to More':'Pin to the toolbar'} onClick={onPin}>{pinned?<PinOff size={11}/>:<Pin size={11}/>}</button>
      {!pinned&&<button type="button" aria-label={`Move ${tool.label} back to More`} title="Move back to More" onClick={onHide}><X size={11}/></button>}
    </span>
  </div>;
}

/** The More menu: every tool in one place. Pick one to use it (it moves onto the bar); the pin keeps it there for good. */
export function MoreMenu({tools,pins,onPick,onPin,onClose}:{tools:Tool[];pins:string[];onPick:(t:Tool)=>void;onPin:(id:string)=>void;onClose:()=>void}){
  useEscape(onClose);
  const groups=(['Meeting','Share and work','Host','View'] as const).map(g=>({g,items:tools.filter(t=>t.group===g)})).filter(x=>x.items.length);
  return <><div className="rm-pop-shade" onClick={onClose}/>
    <div className="rm-pop rm-more" role="menu" aria-label="More tools">
      <div className="rm-pop-head"><b>More</b><span className="muted small">Pick a tool to use it. Pin it to keep it on the toolbar.</span></div>
      {groups.map(({g,items})=><div key={g} className="rm-more-group"><small>{g}</small>
        {items.map(t=><div key={t.id} className={`rm-more-row${t.on?' on':''}`}>
          <button type="button" role="menuitem" onClick={()=>onPick(t)} title={t.hint||t.label}>{t.icon}<span>{t.label}</span>{t.on&&<em>on</em>}</button>
          <button type="button" className={`rm-pin${pins.includes(t.id)?' on':''}`} aria-pressed={pins.includes(t.id)} aria-label={pins.includes(t.id)?`Unpin ${t.label}`:`Pin ${t.label} to the toolbar`} title={pins.includes(t.id)?'Pinned. Press to unpin':'Pin to the toolbar'} onClick={()=>onPin(t.id)}>{pins.includes(t.id)?<PinOff size={14}/>:<Pin size={14}/>}</button>
        </div>)}
      </div>)}
    </div></>;
}

/** Reactions: tap an emoji and it floats up on everyone's screen; or raise a hand. */
export function ReactMenu({onReact,handUp,onHand,onClose}:{onReact:(e:string)=>void;handUp:boolean;onHand:()=>void;onClose:()=>void}){
  useEscape(onClose);
  return <><div className="rm-pop-shade" onClick={onClose}/>
    <div className="rm-pop rm-react" role="dialog" aria-label="Reactions">
      <div className="rm-emojis">{REACTIONS.map(e=><button key={e} type="button" onClick={()=>onReact(e)} aria-label={`React ${e}`}>{e}</button>)}</div>
      <button type="button" className={`rm-handbtn${handUp?' on':''}`} onClick={()=>{onHand();onClose()}}><Hand size={16}/> {handUp?'Lower hand':'Raise hand'}</button>
    </div></>;
}

export type Floater={k:string;emoji:string;name:string;x:number};
export function FloatingReactions({items}:{items:Floater[]}){
  return <div className="rm-floats" aria-hidden="true">{items.map(f=><span key={f.k} className="rm-float" style={{left:`${f.x}%`}}>{f.emoji}<small>{f.name}</small></span>)}</div>;
}

export type CapLine={k:string;id:string;name:string;text:string;final:boolean;at:number};
/** Live captions: the last few spoken lines, and the full transcript to read back or save. */
export function CaptionsBar({lines,history,supported,onClose}:{lines:CapLine[];history:CapLine[];supported:boolean;onClose:()=>void}){
  const [open,setOpen]=useState(false);const end=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(open)end.current?.scrollIntoView({block:'end'})},[open,history.length]);
  const save=()=>{const t=history.map(l=>`[${new Date(l.at).toLocaleTimeString()}] ${l.name}: ${l.text}`).join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:'text/plain'}));a.download='meeting-transcript.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),2000)};
  return <div className="rm-caps" role="region" aria-label="Live captions">
    {open&&<div className="rm-trans" role="log" aria-label="Transcript">{history.length?history.map(l=><p key={l.k}><b>{l.name}</b> {l.text}</p>):<p className="muted">Nothing said yet.</p>}<div ref={end}/></div>}
    <div className="rm-capline" aria-live="polite">{lines.length?lines.map(l=><p key={l.k} className={l.final?'':'interim'}><b>{l.name}:</b> {l.text}</p>):<p className="muted">{supported?'Captions are on. Words appear here as people speak.':'Captions are on. This browser cannot write your own words (use Chrome, Edge or Safari), but you will see everyone else’s.'}</p>}</div>
    <div className="rm-capctl"><button type="button" onClick={()=>setOpen(o=>!o)} aria-expanded={open}>{open?'Hide transcript':'Transcript'}</button>{history.length>0&&<button type="button" onClick={save} title="Save the transcript as a text file"><Download size={13}/> Save</button>}<button type="button" onClick={onClose} aria-label="Turn captions off" title="Turn captions off"><X size={14}/></button></div>
  </div>;
}

function Switch({on,onChange,label,hint,disabled}:{on:boolean;onChange:(v:boolean)=>void;label:string;hint?:string;disabled?:boolean}){
  return <label className={`rm-switch${disabled?' dis':''}`} title={hint}><span>{label}{hint&&<small>{hint}</small>}</span><input type="checkbox" role="switch" checked={on} disabled={disabled} onChange={e=>onChange(e.target.checked)}/><i aria-hidden="true"/></label>;
}

/** Host tools, in one place: lock the meeting, the waiting room, hide pictures, what people may switch on. */
export function HostMenu(p:{locked:boolean;onLock:(v:boolean)=>void;waiting:boolean|null;onWaiting?:(v:boolean)=>void;hidePics:boolean;onHidePics:(v:boolean)=>void;policy:{audio:boolean;video:boolean};onPolicy:(k:'audio'|'video',v:boolean)=>void;onMuteAll:()=>void;onAdvanced:()=>void;onSecurity?:()=>void;onClose:()=>void}){
  useEscape(p.onClose);
  return <><div className="rm-pop-shade" onClick={p.onClose}/>
    <div className="rm-pop rm-host" role="dialog" aria-label="Host tools">
      <div className="rm-pop-head"><b><ShieldCheck size={15}/> Host tools</b></div>
      <Switch on={p.locked} onChange={p.onLock} label={p.locked?'Meeting is locked':'Lock meeting'} hint="Nobody new can join while it is locked"/>
      {p.waiting!==null&&<Switch on={!!p.waiting} onChange={v=>p.onWaiting?.(v)} disabled={!p.onWaiting} label="Waiting room" hint="New people wait until you let them in"/>}
      <Switch on={p.hidePics} onChange={p.onHidePics} label="Hide profile pictures" hint="No letters or pictures on tiles without video"/>
      <div className="rm-host-sub"><small>Let participants</small>
        <Switch on={p.policy.audio} onChange={v=>p.onPolicy('audio',v)} label="Unmute themselves"/>
        <Switch on={p.policy.video} onChange={v=>p.onPolicy('video',v)} label="Start their video"/>
      </div>
      <div className="rm-host-btns"><button type="button" className="secondary" onClick={()=>{p.onMuteAll();p.onClose()}}><Mic size={14}/> Mute everyone</button>{p.onSecurity&&<button type="button" className="secondary" onClick={()=>{p.onSecurity?.();p.onClose()}}><Lock size={14}/> Passcode and sign-in</button>}</div>
      <button type="button" className="rm-advanced" onClick={()=>{p.onClose();p.onAdvanced()}}>Advanced: all tools <ChevronRight size={15}/></button>
    </div></>;
}

export {Subtitles,Users,LockOpen};
