// Pointer and pen on a shared screen. The sharer (or the person the sharer hands the pen to) can point and draw;
// everyone sees it. Positions are fractions (0 to 1) of the shared picture, so they line up on every screen.
import {useEffect,useRef,useState} from 'react';
import {Pencil,MousePointer2,Eraser,X,Hand} from 'lucide-react';

export type Stroke={key:string;by:string;pts:number[][]};
export type Pointer={by:string;name:string;x:number;y:number;at:number};
const COLORS=['#ef4444','#f59e0b','#22c55e','#38bdf8','#a78bfa','#f472b6'];
export const colorOf=(id:string)=>{let h=0;for(const c of id)h=(h*31+c.charCodeAt(0))>>>0;return COLORS[h%COLORS.length]};

export function SharePen({sharer,isSharer,holder,holderName,myId,candidates,ink,pointers,send,onLocalInk,onClear,onAsked}:{
  sharer:string;isSharer:boolean;holder:string;holderName:string;myId:string;candidates:{id:string;name:string}[];ink:Stroke[];pointers:Pointer[];
  send:(m:any)=>void;onLocalInk:(key:string,pts:number[][])=>void;onClear:()=>void;onAsked:()=>void}){
  const root=useRef<HTMLDivElement>(null);const cv=useRef<HTMLCanvasElement>(null);
  const [box,setBox]=useState<{l:number;t:number;w:number;h:number}|null>(null);
  const [mode,setMode]=useState<'off'|'point'|'draw'>('off');const [open,setOpen]=useState(false);const [asked,setAsked]=useState(false);const [,tick]=useState(0);
  const canDraw=isSharer||(!!holder&&holder===myId);
  const cur=useRef<{sid:string;sent:number;pts:number[][]}|null>(null);const flushT=useRef(0);
  // where the picture really is inside its frame (it keeps its own shape), re-measured as the window or zoom changes
  useEffect(()=>{const m=()=>{const r=root.current,v=r?.parentElement?.querySelector('video') as HTMLVideoElement|null;if(!r||!v||!v.videoWidth)return;
      const pr=r.getBoundingClientRect(),vr=v.getBoundingClientRect(),k=Math.min(vr.width/v.videoWidth,vr.height/v.videoHeight),w=v.videoWidth*k,h=v.videoHeight*k;
      const nb={l:vr.left-pr.left+(vr.width-w)/2,t:vr.top-pr.top+(vr.height-h)/2,w,h};
      setBox(o=>o&&Math.abs(o.l-nb.l)<.5&&Math.abs(o.t-nb.t)<.5&&Math.abs(o.w-nb.w)<.5&&Math.abs(o.h-nb.h)<.5?o:nb)};
    m();const id=setInterval(()=>{m();tick(n=>n+1)},300);window.addEventListener('resize',m);return()=>{clearInterval(id);window.removeEventListener('resize',m)}},[]);
  useEffect(()=>{if(!canDraw)setMode('off')},[canDraw]);
  useEffect(()=>{if(holder!==myId)setAsked(false)},[holder]);
  // draw everyone's strokes
  useEffect(()=>{const c=cv.current;if(!c||!box)return;c.width=Math.max(1,Math.round(box.w));c.height=Math.max(1,Math.round(box.h));const g=c.getContext('2d');if(!g)return;
    g.lineCap='round';g.lineJoin='round';g.lineWidth=Math.max(2,box.w*.004);
    for(const s of ink){if(!s.pts.length)continue;g.strokeStyle=colorOf(s.by);g.beginPath();g.moveTo(s.pts[0][0]*c.width,s.pts[0][1]*c.height);if(s.pts.length===1)g.lineTo(s.pts[0][0]*c.width+.1,s.pts[0][1]*c.height);for(const p of s.pts.slice(1))g.lineTo(p[0]*c.width,p[1]*c.height);g.stroke()}
  },[ink,box?.w,box?.h]);
  const pos=(e:React.PointerEvent)=>{const r=(e.currentTarget as HTMLElement).getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))]};
  const flush=()=>{const c=cur.current;if(!c)return;const from=Math.max(0,c.sent-1),pts=c.pts.slice(from);if(pts.length>(c.sent?1:0)){c.sent=c.pts.length;for(let i=0;i<pts.length;i+=50)send({type:'draw',sharer,sid:c.sid,pts:pts.slice(i,i+50)})}};
  const down=(e:React.PointerEvent)=>{if(mode!=='draw')return;try{e.currentTarget.setPointerCapture(e.pointerId)}catch{}const p=pos(e);const sid=Math.random().toString(36).slice(2,8);cur.current={sid,sent:0,pts:[p]};onLocalInk(myId+':'+sid,[p]);flushT.current=window.setInterval(flush,70)};
  const move=(e:React.PointerEvent)=>{const p=pos(e);
    if(mode==='draw'){const c=cur.current;if(!c)return;const l=c.pts[c.pts.length-1];if(Math.hypot(p[0]-l[0],p[1]-l[1])<.002)return;c.pts.push(p);onLocalInk(myId+':'+c.sid,[p])}
    else if(mode==='point')send({type:'pointer',sharer,x:p[0],y:p[1]})};
  const up=()=>{if(cur.current){flush();clearInterval(flushT.current);cur.current=null}};
  const leave=()=>{if(mode==='point')send({type:'pointer',sharer,x:null,y:null})};
  const now=Date.now();const live=pointers.filter(p=>p.x!==null&&now-p.at<4000);
  const give=(v:string)=>send(v?{type:'pen_give',to:v}:{type:'pen_take'});
  const toggle=(m:'point'|'draw')=>{setMode(o=>o===m?'off':m);if(mode==='point')send({type:'pointer',sharer,x:null,y:null})};
  return <div className="rm-pen" ref={root}>
    {box&&<div className={`rm-pen-area${mode!=='off'&&canDraw?' live':''}${mode==='draw'?' drawing':''}`} style={{left:box.l,top:box.t,width:box.w,height:box.h}} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={leave}>
      <canvas ref={cv}/>
      {live.map(p=><span key={p.by} className="rm-penpt" style={{left:`${p.x*100}%`,top:`${p.y*100}%`,['--c' as any]:colorOf(p.by)}}><i/><b>{p.name}</b></span>)}
    </div>}
    <div className="rm-pentools" onPointerDown={e=>e.stopPropagation()}>
      {!open?<button type="button" className={`rm-penbtn${canDraw?' mine':''}`} onClick={()=>setOpen(true)} title="Pointer and pen on the shared screen"><Pencil size={14}/> Pen{holder&&holder!==myId?` · ${holderName}`:canDraw&&!isSharer?' · you':''}</button>
      :<div className="rm-penpanel">
        {canDraw&&<><button type="button" className={mode==='point'?'on':''} onClick={()=>toggle('point')}><MousePointer2 size={14}/> Pointer</button><button type="button" className={mode==='draw'?'on':''} onClick={()=>toggle('draw')}><Pencil size={14}/> Draw</button><button type="button" onClick={()=>{onClear();send({type:'draw_clear',sharer})}}><Eraser size={14}/> Clear</button></>}
        {isSharer&&<select value={holder} onChange={e=>give(e.target.value)} aria-label="Who has the pen"><option value="">Pen: only me</option>{candidates.map(c=><option key={c.id} value={c.id}>Give pen to {c.name}</option>)}</select>}
        {!isSharer&&holder===myId&&<small>You have the pen. The sharer can take it back.</small>}
        {!canDraw&&<button type="button" disabled={asked} onClick={()=>{send({type:'pen_ask',sharer});setAsked(true);onAsked()}}><Hand size={14}/> {asked?'Asked':'Ask for the pen'}</button>}
        {!canDraw&&holder&&<small>Pen: {holderName}</small>}
        <button type="button" className="x" onClick={()=>{setOpen(false);setMode('off')}} aria-label="Close pen tools"><X size={14}/></button>
      </div>}
    </div>
  </div>;
}
