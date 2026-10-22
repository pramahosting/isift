import React,{useCallback,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {rememberRoom} from './Connections';
import {Scene,ScenePicker} from './Scenes';
import {BgProcessor,PRESETS,loadSaved,save as saveBg,readImage} from './vbg';
import type {BgMode} from './vbg';
import {SfuClient} from './sfu';
import {FileShare,CanvasShare} from './shareFile';
import {Board} from './Whiteboard';
import {SharePen,type Stroke,type Pointer} from './SharePen';
import {WatchTogether,type WatchState} from './WatchTogether';
import {PenLine,ZoomIn,ZoomOut,Pencil,Image as ImageIcon,Maximize,Minimize,ChevronDown,ChevronUp,SlidersHorizontal,Armchair,Mic,MicOff,Video,VideoOff,MonitorUp,MessageSquare,Circle,Square,PhoneOff,Link2,Users,Send,X,UserX,ShieldCheck,Check,Plus,LockKeyhole,Table2,LayoutGrid,RectangleHorizontal,Group,Megaphone,HandHelping,Timer,Smile,Hand,Captions,Ellipsis,NotebookPen,EyeOff} from 'lucide-react';
import {Tool,ToolButton,MoreMenu,ReactMenu,FloatingReactions,CaptionsBar,HostMenu,loadPins,savePins,Floater,CapLine} from './MeetingTools';
let HIDE_PICS=false;   // set while the meeting screen draws: tiles without video then show no letter or picture

type Peer={id:string;name:string;host?:boolean;cohost?:boolean;stream:MediaStream;shot?:MediaStream;mic:boolean;cam:boolean;screen:boolean;hand?:boolean};
const wsUrl=(api:string,code:string)=>{const base=api.startsWith('http')?api:location.origin+api;return base.replace(/^http/,'ws')+`/ws/rooms/${code}`};

// Seat positions (percent of the room) for n people around the table. Index 0 is "you", at the bottom, so everyone sees themselves nearest.
/* The wall clock shows the real time on this computer. */
function WallClock(){
  const [t,setT]=useState(()=>new Date());
  useEffect(()=>{const id=setInterval(()=>setT(new Date()),1000);return()=>clearInterval(id)},[]);
  const sec=t.getSeconds(),min=t.getMinutes()+sec/60,hr=(t.getHours()%12)+min/60;
  return <g transform="translate(76,13.2) scale(1,1.7778) scale(.68)" style={{filter:'drop-shadow(0 .4px .5px rgba(0,0,0,.45))'}}>
    <circle r="5.6" fill="#5b3d27"/><circle r="5.1" fill="#fffdf8" stroke="#d9cfbd" strokeWidth=".15"/>
    {Array.from({length:60},(_,i)=>{const a=i*6*Math.PI/180,l=i%5===0?.75:.3;return <line key={i} x1={Math.sin(a)*(4.6-l)} y1={-Math.cos(a)*(4.6-l)} x2={Math.sin(a)*4.6} y2={-Math.cos(a)*4.6} stroke="#3b2f25" strokeWidth={i%5===0?.22:.08}/>})}
    {[[12,0,-3.5],[3,3.5,0],[6,0,3.5],[9,-3.5,0]].map(([n,x,y])=><text key={n} x={x} y={y+.55} fontSize="1.35" fontWeight="700" textAnchor="middle" fill="#3b2f25" fontFamily="Georgia,serif">{n}</text>)}
    <line x1="0" y1=".7" x2="0" y2="-2.6" stroke="#26180f" strokeWidth=".42" strokeLinecap="round" transform={`rotate(${hr*30})`}/>
    <line x1="0" y1=".9" x2="0" y2="-3.9" stroke="#26180f" strokeWidth=".28" strokeLinecap="round" transform={`rotate(${min*6})`}/>
    <line x1="0" y1="1" x2="0" y2="-4.2" stroke="#c0392b" strokeWidth=".1" transform={`rotate(${sec*6})`}/>
    <circle r=".38" fill="#c0392b"/>
  </g>;
}
/* Window with curtains on a side wall (drawn for the left wall, mirrored for the right). */
function SideWindow({scene}:{scene:string}){
  return <g>
    <linearGradient id="vw-glare" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#fff" stopOpacity=".34"/><stop offset=".28" stopColor="#fff" stopOpacity=".05"/><stop offset=".5" stopColor="#fff" stopOpacity=".16"/><stop offset=".62" stopColor="#fff" stopOpacity="0"/><stop offset="1" stopColor="#fff" stopOpacity=".12"/></linearGradient>
    <clipPath id="vw-glass"><polygon points="3.2,10.7 12.8,11.7 12.8,31.6 3.2,36.0"/></clipPath>
    <linearGradient id="vw-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4f9fe0"/><stop offset=".55" stopColor="#a9d6f5"/><stop offset="1" stopColor="#e9f6ff"/></linearGradient>
    <linearGradient id="vw-cur" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#dcdad4"/><stop offset=".3" stopColor="#ffffff"/><stop offset=".6" stopColor="#e6e4de"/><stop offset=".85" stopColor="#ffffff"/><stop offset="1" stopColor="#d8d6d0"/></linearGradient>
    <polygon points="2.8,9.9 13.2,11.0 13.2,32.4 2.8,36.9" fill="#f6f3ec" stroke="#cdc6b6" strokeWidth=".15"/>
    <g clipPath="url(#vw-glass)"><svg x="3.2" y="10.7" width="9.6" height="25.3" viewBox="0 0 100 148" preserveAspectRatio="xMidYMid slice"><Scene id={scene} w={100} h={148}/></svg>
      <polygon points="3.2,10.7 12.8,11.7 12.8,31.6 3.2,36.0" fill="url(#vw-glare)"/></g>
    <polygon points="3.2,10.7 12.8,11.7 12.8,31.6 3.2,36.0" fill="none" stroke="#ffffff" strokeOpacity=".55" strokeWidth=".14"/>
        <line x1="2" y1="8.7" x2="14" y2="10.2" stroke="#4a3426" strokeWidth=".35" strokeLinecap="round"/><circle cx="2" cy="8.7" r=".45" fill="#8c6a3f"/><circle cx="14" cy="10.2" r=".45" fill="#8c6a3f"/>
    <polygon points="2.4,9.0 5.6,9.4 5.6,44.6 2.4,47.0" fill="url(#vw-cur)"/><polygon points="10.6,9.9 13.8,10.3 13.8,38.2 10.6,40.6" fill="url(#vw-cur)"/>
    {[3.2,4.0,4.8].map(x=><line key={x} x1={x} y1={9.1+ (x-2.4)*.12} x2={x} y2={46.6-(x-2.4)*.9} stroke="#00000022" strokeWidth=".15"/>)}
    {[11.4,12.2,13.0].map(x=><line key={x} x1={x} y1={10+(x-10.6)*.12} x2={x} y2={40.2-(x-10.6)*.8} stroke="#00000022" strokeWidth=".15"/>)}
  </g>;
}
function RoomDecor({win,pic,pick}:{win:string;pic:string;pick:(k:'win'|'pic')=>void}){
  return <svg className="rm-decor" viewBox="0 0 100 100" preserveAspectRatio="none">
    <g className="rm-pick" pointerEvents="all" onClick={()=>pick('win')}><title>Click to change the view outside</title><SideWindow scene={win}/></g><g className="rm-pick" pointerEvents="all" onClick={()=>pick('win')} transform="translate(100,0) scale(-1,1)"><title>Click to change the view outside</title><SideWindow scene={win}/></g>
    <g className="rm-pick" pointerEvents="all" onClick={()=>pick('pic')} transform="translate(20,9.6) scale(.7917,.8082) translate(-19,-10.2)" style={{filter:'drop-shadow(0 .5px .7px rgba(0,0,0,.4))'}}>
      <polyline points="21.5,10.2 25,6.2 28.5,10.2" fill="none" stroke="#7a6a58" strokeWidth=".18"/><circle cx="25" cy="6.1" r=".35" fill="#7a6a58"/>
      <rect x="19" y="10.2" width="12" height="14.6" rx=".3" fill="#a9792f"/><rect x="19.5" y="10.8" width="11" height="13.4" fill="#d8b26a"/><rect x="20.1" y="11.5" width="9.8" height="12" fill="#fbf8f0"/>
      <title>Click to change the picture</title><svg x="20.9" y="12.2" width="8.2" height="10.6" viewBox="0 0 135 100" preserveAspectRatio="xMidYMid slice"><Scene id={pic} w={135} h={100}/></svg>
    </g>
    <WallClock/>
  </svg>;
}

export const EDGE_Y=42;
export const seatWidth=(n:number)=>n<=2?22:n<=4?19:n<=5?17:14;      // width of one person on the table view, in % of the room
export function seatPoints(n:number,_shape?:'rect'|'round'):{x:number;y:number;py:number}[]{
  // Everyone sits just behind the far edge of the table, looking at the viewer: the table hides the bottom of each picture and a name plate stands on the table in front of them.
  if(n<=0)return [];
  const sw=seatWidth(n),h=sw*4/3,EDGE=42;                                  // h: picture height in % of the room height; EDGE: far edge of the table
  const back=n<=5?0:Math.floor(n/2),front=n-back;
  const fy=EDGE+2-h/2,by=fy-0.8*h;
  const row=(k:number,y:number,py:number)=>{const step=k<2?0:Math.min(sw+2,76/(k-1));return Array.from({length:k},(_,i)=>({x:50+(i-(k-1)/2)*step,y,py}))};
  const byCentre=(r:{x:number;y:number;py:number}[])=>[...r].sort((a,b)=>Math.abs(a.x-50)-Math.abs(b.x-50)||b.x-a.x);   // the middle seat first, then right, left, right...
  return [...byCentre(row(front,fy,EDGE+(back?13:4))),...byCentre(row(back,by,EDGE+4))];
}
// The boardroom table is for rooms of 10 or fewer people (the main meeting or a discussion group); bigger rooms use the gallery.
export const TABLE_MAX=10;

/* The big picture (a shared screen or a highlighted person) can be zoomed and moved: mouse wheel, + and - buttons, pinch, drag, double-click or double-tap. */
function ZoomPane({children,resetKey}:{children:React.ReactNode;resetKey:string}){
  const [z,setZ]=useState({s:1,x:0,y:0});const box=useRef<HTMLDivElement>(null);const ptrs=useRef(new Map<number,{x:number;y:number}>());const last=useRef<{d:number;cx:number;cy:number}|null>(null);const [drag,setDrag]=useState(false);
  useEffect(()=>{setZ({s:1,x:0,y:0})},[resetKey]);
  const clamp=(s:number,x:number,y:number)=>{const r=box.current?.getBoundingClientRect();const mx=(s-1)*(r?.width||0)/2,my=(s-1)*(r?.height||0)/2;return {s,x:Math.max(-mx,Math.min(mx,x)),y:Math.max(-my,Math.min(my,y))}};
  const zoomAt=(f:number,cx?:number,cy?:number)=>setZ(o=>{const s=Math.max(1,Math.min(6,o.s*f));if(s<=1.001)return {s:1,x:0,y:0};const r=box.current?.getBoundingClientRect();const px=r&&cx!==undefined?cx-r.left-r.width/2:0,py=r&&cy!==undefined?cy-r.top-r.height/2:0;const k=s/o.s;return clamp(s,px-(px-o.x)*k,py-(py-o.y)*k)});
  useEffect(()=>{const el=box.current;if(!el)return;const w=(e:WheelEvent)=>{e.preventDefault();zoomAt(Math.exp(-e.deltaY*(e.ctrlKey?0.01:0.0025)),e.clientX,e.clientY)};el.addEventListener('wheel',w,{passive:false});return()=>el.removeEventListener('wheel',w)},[]);
  const down=(e:React.PointerEvent<HTMLDivElement>)=>{ptrs.current.set(e.pointerId,{x:e.clientX,y:e.clientY});try{e.currentTarget.setPointerCapture(e.pointerId)}catch{}if(ptrs.current.size===2){const [a,b]=[...ptrs.current.values()];last.current={d:Math.hypot(a.x-b.x,a.y-b.y),cx:(a.x+b.x)/2,cy:(a.y+b.y)/2}}setDrag(true)};
  const move=(e:React.PointerEvent<HTMLDivElement>)=>{const p=ptrs.current.get(e.pointerId);if(!p)return;const nx={x:e.clientX,y:e.clientY};ptrs.current.set(e.pointerId,nx);
    if(ptrs.current.size===2){const [a,b]=[...ptrs.current.values()];const d=Math.hypot(a.x-b.x,a.y-b.y),cx=(a.x+b.x)/2,cy=(a.y+b.y)/2,l=last.current;if(l&&l.d>0){zoomAt(d/l.d,cx,cy);setZ(o=>clamp(o.s,o.x+(cx-l.cx),o.y+(cy-l.cy)))}last.current={d,cx,cy}}
    else setZ(o=>o.s>1?clamp(o.s,o.x+nx.x-p.x,o.y+nx.y-p.y):o)};
  const up=(e:React.PointerEvent<HTMLDivElement>)=>{ptrs.current.delete(e.pointerId);last.current=null;if(!ptrs.current.size)setDrag(false)};
  return <div className="rm-zoomwrap" ref={box} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onDoubleClickCapture={e=>{e.stopPropagation();setZ(o=>o.s>1?{s:1,x:0,y:0}:o);if(z.s<=1)zoomAt(2.5,e.clientX,e.clientY)}} style={{touchAction:z.s>1?'none':'pan-x',cursor:z.s>1?(drag?'grabbing':'grab'):'zoom-in'}}>
    <div className="rm-zoomin" style={{transform:`translate(${z.x}px,${z.y}px) scale(${z.s})`,transition:drag?'none':'transform .12s'}}>{children}</div>
    <div className="rm-zoomctl" onPointerDown={e=>e.stopPropagation()} onDoubleClick={e=>e.stopPropagation()}><button type="button" aria-label="Zoom out" title="Zoom out" onClick={()=>zoomAt(1/1.4)} disabled={z.s<=1}><ZoomOut size={16}/></button><span aria-live="polite">{Math.round(z.s*100)}%</span><button type="button" aria-label="Zoom in" title="Zoom in" onClick={()=>zoomAt(1.4)} disabled={z.s>=6}><ZoomIn size={16}/></button>{z.s>1&&<button type="button" className="fit" onClick={()=>setZ({s:1,x:0,y:0})}>Fit</button>}</div>
  </div>;
}
// Phones and tablets: ask for the front camera in its own natural shape (upright when held upright) instead of a fixed 16:9 landscape picture, which phones crop or turn sideways.
const isTouchDevice=()=>{try{return window.matchMedia('(pointer: coarse)').matches&&!window.matchMedia('(hover: hover)').matches}catch{return false}};
const weakPc=():boolean=>{const n=navigator as any;return (n.deviceMemory&&n.deviceMemory<=4)||(n.hardwareConcurrency&&n.hardwareConcurrency<=4)};     // an older computer: a smaller picture keeps it from choking while it also decodes everyone else
const phoneCam=():MediaTrackConstraints=>isTouchDevice()?{facingMode:'user',height:{ideal:720},frameRate:{ideal:24,max:30}}:weakPc()?{width:{ideal:640,max:640},height:{ideal:360,max:360},frameRate:{ideal:20,max:24}}:{width:{ideal:1280,max:1280},height:{ideal:720,max:720},frameRate:{ideal:24,max:30}};
/** The person sharing a PDF scrolls it by dragging up and down or with the mouse wheel on the picture: everyone sees the page move. */
function DocScroll({fs}:{fs:{scrollBy?:(dy:number)=>void;width?:number;height?:number}}){
  const me=useRef<HTMLSpanElement>(null);
  useEffect(()=>{const host=me.current?.parentElement;if(!host)return;const old=host.style.touchAction;host.style.touchAction='pan-x';
    const k=()=>{const v=host.querySelector('video') as HTMLVideoElement|null;const r=v?.getBoundingClientRect();if(!r||!fs.width||!fs.height)return 1;return 1/Math.max(0.05,Math.min(r.width/fs.width,r.height/fs.height))};
    const skip=(t:EventTarget|null)=>!!(t as HTMLElement)?.closest?.('button,select,input,.rm-pentools,.rm-pen-area.live,.rm-zoomctl,.rm-sharebar');
    const wheel=(e:WheelEvent)=>{if(skip(e.target))return;e.preventDefault();e.stopPropagation();fs.scrollBy?.(e.deltaY*k())};
    let last=-1;let id=-1;
    const down=(e:PointerEvent)=>{if(skip(e.target)||e.pointerType==='mouse'&&e.button!==0)return;last=e.clientY;id=e.pointerId};
    const move=(e:PointerEvent)=>{if(e.pointerId!==id||last<0)return;const dy=last-e.clientY;last=e.clientY;if(Math.abs(dy)>0)fs.scrollBy?.(dy*k())};
    const up=(e:PointerEvent)=>{if(e.pointerId===id){last=-1;id=-1}};
    host.addEventListener('wheel',wheel,{passive:false,capture:true});host.addEventListener('pointerdown',down);host.addEventListener('pointermove',move);host.addEventListener('pointerup',up);host.addEventListener('pointercancel',up);
    return()=>{host.style.touchAction=old;host.removeEventListener('wheel',wheel,{capture:true} as any);host.removeEventListener('pointerdown',down);host.removeEventListener('pointermove',move);host.removeEventListener('pointerup',up);host.removeEventListener('pointercancel',up)}},[fs]);
  return <span ref={me} style={{display:'none'}} aria-hidden="true"/>;
}
// A person's sound must play once. The same person can be drawn in two places at once (the big view and a page of tiles), and two
// tiles playing the same stream make a doubled, delayed sound that feels like an echo. Only the first tile of a stream is allowed to make sound.
const AUDIO_TILES=new Map<string,{id:object;set:(b:boolean)=>void}[]>();
function useSingleVoice(stream:MediaStream|null,muted?:boolean):boolean{
  const [loud,setLoud]=useState(false);
  useEffect(()=>{if(!stream||muted){setLoud(false);return}const key=stream.id,me={id:{},set:setLoud};const list=AUDIO_TILES.get(key)||[];list.push(me);AUDIO_TILES.set(key,list);list.forEach((t,i)=>t.set(i===0));
    return()=>{const l=(AUDIO_TILES.get(key)||[]).filter(t=>t!==me);if(l.length)AUDIO_TILES.set(key,l);else AUDIO_TILES.delete(key);l.forEach((t,i)=>t.set(i===0))}},[stream,muted]);
  return loud;
}
function VideoTile({stream,name,muted,off,host,cohost,screen,self,speaking,plate,onDouble,hand}:{hand?:boolean;onDouble?:()=>void;stream:MediaStream|null;name:string;muted?:boolean;off?:boolean;host?:boolean;cohost?:boolean;screen?:boolean;self?:boolean;speaking?:boolean;plate?:boolean}){
  const ref=useRef<HTMLVideoElement>(null);const [portrait,setPortrait]=useState(false);const [blocked,setBlocked]=useState(false);const loud=useSingleVoice(stream,muted);
  useEffect(()=>{const v=ref.current;if(!v)return;v.muted=!loud;if(loud)v.play().then(()=>setBlocked(false)).catch(()=>setBlocked(true))},[loud]);
  useEffect(()=>{const v=ref.current;if(v&&v.srcObject!==stream){v.srcObject=stream;v.play().catch(()=>{})}},[stream]);
  useEffect(()=>{const v=ref.current;if(!v)return;const f=()=>setPortrait(v.videoHeight>v.videoWidth&&v.videoWidth>0);f();v.addEventListener('loadedmetadata',f);v.addEventListener('resize',f);return()=>{v.removeEventListener('loadedmetadata',f);v.removeEventListener('resize',f)}},[stream]);   // an upright phone picture is shown whole and centred, never cropped
  return <div className={`rm-tile${self?' self':''}${portrait&&!screen?' portrait':''}${screen?' scr':''}${speaking?' speaking':''}`} data-name={name} onDoubleClick={onDouble} title={onDouble?'Double-click to highlight':undefined}>
    <video ref={ref} autoPlay playsInline muted className={off?'hidden':''}/>
    {speaking&&<span className="rm-talk" title="Speaking" aria-label="Speaking"><Mic size={14}/></span>}
    {off&&!HIDE_PICS&&<div className="rm-avatar">{(name||'?').trim().charAt(0).toUpperCase()}</div>}
    {blocked&&<button type="button" className="rm-tapsound" onClick={()=>{ref.current?.play().then(()=>setBlocked(false)).catch(()=>{})}}>Tap to hear</button>}
    {hand&&<span className="rm-handtag" title="Hand raised" aria-label="Hand raised">✋</span>}
    {!plate&&<span className="rm-name">{name}{self?' (you)':''}{host?(cohost?' · co-host':' · host'):''}{screen?' · sharing':''}</span>}
  </div>;
}

export function RoomPage({code,api,token,defaultName,onLeave,onSignIn,onActive}:{onActive?:(hash:string)=>void;code:string;api:string;token:string;defaultName:string;onLeave:()=>void;onSignIn?:()=>void}){
  const [info,setInfo]=useState<any>(null);const [err,setErr]=useState('');
  const [phase,setPhase]=useState<'lobby'|'waiting'|'room'|'ended'>('lobby');
  // while you are in the meeting, the browser's back swipe, pull-down refresh and accidental reload must not take you out; only the Leave button does
  useEffect(()=>{if(phase!=='room')return;onActive?.(location.hash);document.documentElement.classList.add('in-room');const bu=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',bu);return()=>{onActive?.('');document.documentElement.classList.remove('in-room');window.removeEventListener('beforeunload',bu)}},[phase]);
  const [passcode,setPasscode]=useState('');const [waitList,setWaitList]=useState<{id:string;name:string}[]>([]);const [hostInfo,setHostInfo]=useState<any>(null);const [secOpen,setSecOpen]=useState(false);
  const [name,setName]=useState(defaultName||'');
  useEffect(()=>{if(defaultName)setName(n=>n||defaultName)},[defaultName]);   // a person who has just signed in gets their own name filled in
  const [mic,setMic]=useState(true);const [cam,setCam]=useState(true);const [screen,setScreen]=useState(false);const fileShare=useRef<{stop:()=>void;page?:number;pages?:number;show?:(n:number)=>Promise<void>;scrollBy?:(dy:number)=>void;width?:number;height?:number;onPage?:(n:number)=>void}|null>(null);const [wbOpen,setWbOpen]=useState(false);const [wbTab,setWbTab]=useState<'board'|'apps'>('board');const [appsLoaded,setAppsLoaded]=useState(false);const [wbOn,setWbOn]=useState(false);const wbContent=useRef('');const wbBox=useRef<HTMLDivElement>(null);const [wbSaved,setWbSaved]=useState('');
  useEffect(()=>{if(!token)return;const h=(e:MessageEvent)=>{if(e.origin===location.origin&&e.data?.type==='isift-ready'&&e.source)(e.source as Window).postMessage({type:'isift-token',token},location.origin)};window.addEventListener('message',h);return()=>window.removeEventListener('message',h)},[token]);
  const filePick=useRef<HTMLInputElement>(null);const [filePg,setFilePg]=useState<{n:number;of:number}|null>(null);const [screenStream,setScreenStream]=useState<MediaStream|null>(null);const [stripHide,setStripHide]=useState(false);
  const [peers,setPeers]=useState<Record<string,Peer>>({});
  const [vrOn,setVrOn]=useState(true);const [vrAllowed,setVrAllowed]=useState(true);const [pin,setPin]=useState('');const [isHost,setIsHost]=useState(false);const [cohost,setCohost]=useState(false);const [policy,setPolicy]=useState({audio:true,video:true});const [peopleOpen,setPeopleOpen]=useState(false);const [menuFor,setMenuFor]=useState('');const [ask,setAsk]=useState<null|{by:string;what:string}>(null);const [inviteOpen,setInviteOpen]=useState(false);const [invTo,setInvTo]=useState('');const [invMsg,setInvMsg]=useState('');const [invBusy,setInvBusy]=useState(false);const [invRes,setInvRes]=useState<any>(null);const [suggest,setSuggest]=useState<{name:string;email:string}[]>([]);const [recording,setRecording]=useState(false);const [recBusy,setRecBusy]=useState(false);
  type ChatMsg={name:string;text:string;at:string;me?:boolean;key:string;names:Record<string,string>;g:string};const [chat,setChat]=useState<ChatMsg[]>([]);const [chatOpen,setChatOpen]=useState(false);const [chatText,setChatText]=useState('');const [chatKey,setChatKey]=useState('all');const [unread,setUnread]=useState<Record<string,number>>({});const [picking,setPicking]=useState(false);const [pickSel,setPickSel]=useState<string[]>([]);const [extraKeys,setExtraKeys]=useState<string[]>([]);const chatKeyRef=React.useRef('all'),chatOpenRef=React.useRef(false);chatKeyRef.current=chatKey;chatOpenRef.current=chatOpen;
  const [notice,setNotice]=useState('');const [canRec,setCanRec]=useState(true);const [endWarn,setEndWarn]=useState<{at:number;msg:string}|null>(null);const [endNow,setEndNow]=useState(0);const [endWhy,setEndWhy]=useState('');useEffect(()=>{if(!endWarn)return;const id=setInterval(()=>setEndNow(Date.now()),1000);return()=>clearInterval(id)},[endWarn]);const [localStream,setLocalStream]=useState<MediaStream|null>(null);const [mediaNote,setMediaNote]=useState('');
  const ws=useRef<WebSocket|null>(null);const pcs=useRef<Record<string,RTCPeerConnection>>({});const pendIce=useRef<Record<string,any[]>>({});const sigQ=useRef<Record<string,Promise<any>>>({});const myId=useRef('');
  const local=useRef<{audio?:MediaStreamTrack;mixed?:MediaStreamTrack;video?:MediaStreamTrack;cam?:MediaStreamTrack;raw?:MediaStreamTrack;proc?:BgProcessor}>({});
  const iceRef=useRef<any[]>([]);const peerStreams=useRef<Record<string,MediaStream>>({});const peerShots=useRef<Record<string,MediaStream>>({});
  const sfuRef=useRef<SfuClient|null>(null);const sfuOnRef=useRef(false);const [sfuOn,setSfuOn]=useState(false);const [stage,setStage]=useState<string[]>([]);const stageRef=useRef<string[]>([]);const sfuInfo=useRef<Record<string,any>>({});const resubT=useRef<any>(null);
  const [cloud,setCloud]=useState(false);const [recPlan,setRecPlan]=useState('');
  const rec=useRef<any>(null);const wasRecording=useRef(false);
  // discussion groups, boardroom table and active speaker
  const [group,setGroup]=useState<{id:string;name:string}|null>(null);const [groupEnds,setGroupEnds]=useState<string|null>(null);const [roster,setRoster]=useState<any>(null);const [groupsOpen,setGroupsOpen]=useState(false);const [banner,setBanner]=useState<{name:string;text:string}|null>(null);
  const groupRef=useRef<{id:string;name:string}|null>(null);groupRef.current=group;
  const [view,setViewState]=useState<'table'|'gallery'>(()=>{try{return localStorage.getItem('isift.view')==='gallery'?'gallery':'table'}catch{return 'table'}});
  const TUNE0={tw:1,td:1,ps:1,pd:0,pf:1};const [tb,setTb]=useState<{x0:number;y0:number;x1:number;y1:number;rw:number;rh:number}|null>(null);const gripDrag=useRef<any>(null);const [tune,setTuneState]=useState<typeof TUNE0>(()=>{try{return {...TUNE0,...JSON.parse(localStorage.getItem('isift.roomtune')||'{}')}}catch{return TUNE0}});const [tuneOpen,setTuneOpen]=useState(false);
  const setTune=(t:Partial<typeof TUNE0>)=>setTuneState(o=>{const n={...o,...t};try{localStorage.setItem('isift.roomtune',JSON.stringify(n))}catch{}return n});
  type PL={x:number;y:number;s:number;f:number;font:string};
  const [pl,setPl]=useState<Record<string,PL>>(()=>{try{return JSON.parse(localStorage.getItem('isift.plates')||'{}')}catch{return {}}});
  const P=(n:string):PL=>({x:0,y:0,s:1,f:1,font:'',...(pl[n]||{})});
  const setP=(n:string,t:Partial<PL>)=>setPl(o=>{const w={...o,[n]:{...P(n),...t}};try{localStorage.setItem('isift.plates',JSON.stringify(w))}catch{}return w});
  const [scenes,setScenesS]=useState<{win:string;pic:string}>(()=>{try{return {win:'meadow',pic:'mountains',...JSON.parse(localStorage.getItem('isift.scenes')||'{}')}}catch{return {win:'meadow',pic:'mountains'}}});
  /* drag the corner handle to resize a tile (free width and height, along its own turned axes) and the round handle to turn it to any angle */
  const seatHandle=(name:string,kind:'size'|'turn')=>(e:React.PointerEvent)=>{e.preventDefault();e.stopPropagation();const seat=(e.currentTarget as HTMLElement).closest('.rm-seat') as HTMLElement,r=seat.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2,q=SSg(name),a=q.rot*Math.PI/180,ux=Math.cos(a),uy=Math.sin(a),vx=-uy,vy=ux;
    const proj=(px:number,py:number)=>[Math.abs((px-cx)*ux+(py-cy)*uy),Math.abs((px-cx)*vx+(py-cy)*vy)];const p0=proj(e.clientX,e.clientY);const el=e.currentTarget as HTMLElement;try{el.setPointerCapture(e.pointerId)}catch{}
    const mv=(ev:PointerEvent)=>{if(kind==='size'){const p=proj(ev.clientX,ev.clientY);setSS(name,{w:Math.max(.3,Math.min(3,+(q.w*p[0]/Math.max(8,p0[0])).toFixed(3))),h:Math.max(.3,Math.min(3,+(q.h*p[1]/Math.max(8,p0[1])).toFixed(3)))})}
      else{let d=Math.atan2(ev.clientY-cy,ev.clientX-cx)*180/Math.PI+90;d=((d+540)%360)-180;for(const k of [-180,-90,0,90,180])if(Math.abs(d-k)<4)d=k;setSS(name,{rot:Math.round(d)})}};
    const up=()=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up)};window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)};
  const clampX=(x:number)=>{const w=gridRef.current?.getBoundingClientRect().width||1000,m=(250/w)*100;return Math.max(m,Math.min(100-m,x))};
  const [editMe,setEditMe]=useState(false);const [meDraft,setMeDraft]=useState('');
  const [renaming,setRenaming]=useState(false);const [nameDraft,setNameDraft]=useState('');
  const renameTo=async(t:string)=>{const v=t.trim();if(!v)return;try{const r=await fetch(`${api}/rooms/${code}/rename`,{method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:v})});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||'Could not rename.');setInfo((i:any)=>i?{...i,title:j.title}:i);setRenaming(false)}catch(e:any){setNotice(e.message)}};
  const [scenePick,setScenePick]=useState<''|'win'|'pic'>('');
  const setScenes=(t:Partial<{win:string;pic:string}>)=>setScenesS(o=>{const n={...o,...t};try{localStorage.setItem('isift.scenes',JSON.stringify(n))}catch{}return n});
  type SS={w:number;h:number;rot:number};
  const [ss,setSs]=useState<Record<string,SS>>(()=>{try{return JSON.parse(localStorage.getItem('isift.seatset')||'{}')}catch{return {}}});
  const SSg=(n:string):SS=>({w:1,h:1,rot:0,...(ss[n]||{})});
  const setSS=(n:string,t:Partial<SS>)=>setSs(o=>{const w={...o,[n]:{...SSg(n),...t}};try{localStorage.setItem('isift.seatset',JSON.stringify(w))}catch{}return w});
  const [selSeat,setSelSeat]=useState('');
  const [sideW,setSideW]=useState<Record<string,{w:number;h:number}>>(()=>{try{return JSON.parse(localStorage.getItem('isift.sidesize')||'{}')}catch{return {}}});
  const sideDrag=(k:string,axis:'w'|'h')=>(e:React.PointerEvent)=>{e.preventDefault();e.stopPropagation();const el=(e.currentTarget as HTMLElement).parentElement!,r=el.getBoundingClientRect(),sx=e.clientX,sy=e.clientY,w0=r.width,h0=r.height;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const mv=(ev:PointerEvent)=>setSideW(o=>{const cur=o[k]||{w:0,h:0};const n={...o,[k]:{w:axis==='w'?Math.max(160,Math.min(window.innerWidth*.8,w0+(sx-ev.clientX))):cur.w,h:axis==='h'?Math.max(160,Math.min(window.innerHeight-90,h0+(ev.clientY-sy))):cur.h}};return n});
    const up=()=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);setSideW(o=>{try{localStorage.setItem('isift.sidesize',JSON.stringify(o))}catch{}return o})};window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)};
  const sideStyle=(k:string):React.CSSProperties=>{const z=sideW[k];return z?{...(z.w?{width:z.w}:{}),...(z.h?{height:z.h,alignSelf:'flex-start'}:{})}:{}};
  const [selPl,setSelPl]=useState('');const platDrag=useRef<{n:string;sx:number;sy:number;ox:number;oy:number;on:boolean}|null>(null);
  const [moved,setMoved]=useState<Record<string,{x:number;y:number}>>({});const dragSeat=useRef<{id:string;sx:number;sy:number;ox:number;oy:number;on:boolean}|null>(null);
  const [shape,setShapeState]=useState<'rect'|'round'>(()=>{try{return localStorage.getItem('isift.shape')==='round'?'round':'rect'}catch{return 'rect'}});
  const setView=(v:'table'|'gallery')=>{setViewState(v);try{localStorage.setItem('isift.view',v)}catch{}};
  const setShape=(v:'rect'|'round')=>{setShapeState(v);try{localStorage.setItem('isift.shape',v)}catch{}};
  const [wide,setWide]=useState(()=>typeof window==='undefined'||window.innerWidth>=720);
  useEffect(()=>{const f=()=>setWide(window.innerWidth>=720);window.addEventListener('resize',f);return()=>window.removeEventListener('resize',f)},[]);
  const isSmall=()=>{try{return window.innerHeight<600||(window.matchMedia('(pointer: coarse)').matches&&Math.min(window.innerWidth,window.innerHeight)<700)}catch{return window.innerHeight<600}};const [small,setSmall]=useState(isSmall);useEffect(()=>{const f=()=>setSmall(isSmall());window.addEventListener('resize',f);window.addEventListener('orientationchange',f);return()=>{window.removeEventListener('resize',f);window.removeEventListener('orientationchange',f)}},[]);       // phones, also when turned sideways, always get the straight gallery: the angled table is too small there
  const [portrait,setPortrait]=useState(()=>{try{return window.innerHeight>=window.innerWidth}catch{return true}});useEffect(()=>{const f=()=>setPortrait(window.innerHeight>=window.innerWidth);window.addEventListener('resize',f);window.addEventListener('orientationchange',f);return()=>{window.removeEventListener('resize',f);window.removeEventListener('orientationchange',f)}},[]);
  const [pins,setPins]=useState<string[]>(loadPins);const [shown,setShown]=useState<string[]>([]);const [moreOpen,setMoreOpen]=useState(false);const [reactOpen,setReactOpen]=useState(false);const [hostOpen,setHostOpen]=useState(false);const [leaveOpen,setLeaveOpen]=useState(false);
  const [shareBarHidden,setShareBarHidden]=useState(false);const lastTalk=useRef('');const [stripSz,setStripSz]=useState<number>(()=>{try{const v=parseInt(localStorage.getItem('isift.stripsz')||'1',10);return v>=0&&v<=2?v:1}catch{return 1}});const bumpStrip=()=>setStripSz(s=>{const n=(s+1)%3;try{localStorage.setItem('isift.stripsz',String(n))}catch{}return n});const [multiShare,setMultiShare]=useState(true);const [pens,setPens]=useState<Record<string,string>>({});const [pointers,setPointers]=useState<Record<string,Record<string,Pointer>>>({});const [inks,setInks]=useState<Record<string,Stroke[]>>({});const [penAsks,setPenAsks]=useState<{id:string;name:string}[]>([]);const [watch,setWatch]=useState<WatchState|null>(null);const [watchOpen,setWatchOpen]=useState(false);const [myHand,setMyHand]=useState(false);const [floats,setFloats]=useState<Floater[]>([]);
  const [capsView,setCapsView]=useState(false);const [capsActive,setCapsActive]=useState(false);const [capLines,setCapLines]=useState<CapLine[]>([]);const [capHist,setCapHist]=useState<CapLine[]>([]);
  const [locked,setLocked]=useState(false);const [hidePics,setHidePics]=useState(false);const [hideSelf,setHideSelf]=useState(false);const [hideNoVideo,setHideNoVideo]=useState(false);
  HIDE_PICS=hidePics;
  const [page,setPage]=useState(0);const pagerRef=useRef<HTMLDivElement>(null);const sharingNow=screen||Object.values(peers).some(p=>p.screen);useEffect(()=>{try{pagerRef.current?.scrollTo({left:0,behavior:'smooth'})}catch{}},[sharingNow]);const barAuto=useRef(false);useEffect(()=>{if(small&&sharingNow){setStripHide(true);if(barOn){barAuto.current=true;setBarOn(false)}}else if(barAuto.current){barAuto.current=false;setBarOn(true)}},[small,sharingNow]);   // phones: the shared page gets the whole screen; "Show people" brings the strip back
  const [speaking,setSpeaking]=useState('');const peersRef=useRef<Record<string,Peer>>({});const localRef=useRef<MediaStream|null>(null);const seatIds=useRef<string[]>([]);
  const [gCount,setGCount]=useState(2);const [gMinutes,setGMinutes]=useState('');const [gHosts,setGHosts]=useState(false);const [announce,setAnnounce]=useState('');const [, tickClock]=useState(0);

  useEffect(()=>{fetch(`${api}/rooms/${code}`,{headers:token?{Authorization:`Bearer ${token}`}:{}}).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||'This meeting link is not valid.');setInfo(j);iceRef.current=j.ice||[];if(j.ended)setPhase('ended')}).catch(e=>setErr(e.message))},[api,code]);

  // ---- local media ----
  const getMedia=useCallback(async()=>{
    let stream:MediaStream|null=null;
    try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1},video:phoneCam()})}
    catch(e1:any){
      // strict settings can be refused by some cameras: retry with plain settings before giving up on video
      try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:true})}
      catch(e2:any){
        const why=({NotAllowedError:'the browser has blocked the camera for this site',NotReadableError:'another app or tab is using the camera',OverconstrainedError:'the camera does not support the requested settings',NotFoundError:'no camera was found'} as any)[e2?.name||e1?.name]||(e2?.name||e1?.name||'unknown reason');
        try{stream=await navigator.mediaDevices.getUserMedia({audio:true});setMediaNote(`Camera not available (${why}) - joining with microphone only.`)}catch{setMediaNote('No camera or microphone available - you can still watch, listen and chat.')}
      }
    }
    if(stream){local.current.audio=stream.getAudioTracks()[0];local.current.video=stream.getVideoTracks()[0];local.current.cam=local.current.video;local.current.raw=local.current.video;setCam(!!local.current.video);setMic(!!local.current.audio);try{const jo=JSON.parse(sessionStorage.getItem('isift.join')||'{}');if(jo.audio===false&&local.current.audio){local.current.audio.enabled=false;setMic(false)}if(jo.video===false&&local.current.cam){local.current.cam.enabled=false;setCam(false)}if(jo.name)setName(n=>n||jo.name)}catch{}}else{setCam(false);setMic(false)}
    setLocalStream(stream);return stream;
  },[]);
  useEffect(()=>{if(phase==='lobby'&&info&&!localStream&&!err)getMedia()},[phase,info]);// preview in the lobby
  useEffect(()=>()=>{local.current.audio?.stop();local.current.cam?.stop();local.current.video?.stop();local.current.raw?.stop();local.current.proc?.stop()},[]);

  // ---- peer connections ----
  const send=(m:any)=>{if(ws.current?.readyState===1)ws.current.send(JSON.stringify(m))};
  const upsert=(id:string,patch:Partial<Peer>)=>setPeers(p=>({...p,[id]:{id,name:'Guest',stream:peerStreams.current[id],mic:true,cam:true,screen:false,...p[id],...patch}}));
  const makePc=(id:string)=>{
    if(pcs.current[id])return pcs.current[id];
    const pc=new RTCPeerConnection({iceServers:iceRef.current});pcs.current[id]=pc;
    peerStreams.current[id]=peerStreams.current[id]||new MediaStream();
    pc.onicecandidate=e=>{if(e.candidate)send({type:'signal',to:id,data:{candidate:e.candidate}})};
    pc.ontrack=e=>{const vt=pc.getTransceivers().filter(x=>x.receiver.track.kind==='video');const isShot=e.track.kind==='video'&&vt.length>1&&vt.indexOf(e.transceiver)===1;     // the second video line carries a shared screen; the first carries the camera
      const s=isShot?(peerShots.current[id]=peerShots.current[id]||new MediaStream()):peerStreams.current[id];if(!s.getTracks().includes(e.track))s.addTrack(e.track);upsert(id,isShot?{shot:s}:{stream:s});e.track.onunmute=()=>upsert(id,{});recorderRefresh()};
    let retried=0,t:any=null;
    const restart=async()=>{if(retried++>=3||pc.signalingState!=='stable')return;try{const o=await pc.createOffer({iceRestart:true});await pc.setLocalDescription(o);send({type:'signal',to:id,data:{sdp:pc.localDescription}})}catch{}};
    pc.oniceconnectionstatechange=()=>{clearTimeout(t);if(pc.iceConnectionState==='disconnected')t=setTimeout(restart,4000);else if(pc.iceConnectionState==='failed')restart();else if(pc.iceConnectionState==='connected'||pc.iceConnectionState==='completed'){retried=0;tuneSenders()}};
    pc.onconnectionstatechange=()=>{if(pc.connectionState==='failed')setNotice('Could not connect video and sound to another person on this network. Ask the administrator to set up a TURN relay (Admin Console, Video meetings).')};
    (pc as any).kick=restart;
    return pc;
  };
  const tuneSenders=()=>{      // fewer bits per person as the room grows, so everyone's video and sound stay smooth
    const list=Object.values(pcs.current),n=list.length;
    const kbps=n<=1?2500:n<=2?1500:n<=3?1000:n<=6?500:250,scale=n<=2?1:n<=3?1.33:n<=6?2:3;
    for(const pc of list)for(const tx of pc.getSenders()){if(tx.track?.kind!=='video')continue;try{const vt=pc.getTransceivers().filter(x=>x.receiver.track.kind==='video'),isShot=vt.length>1&&vt[1].sender===tx;const p=tx.getParameters();if(!p.encodings||!p.encodings.length)p.encodings=[{}];p.encodings[0].maxBitrate=(isShot?Math.max(kbps,1200):Math.min(kbps,vt.length>1?900:kbps))*1000;p.encodings[0].scaleResolutionDownBy=isShot?1:scale;p.encodings[0].maxFramerate=n>6?15:24;(p as any).degradationPreference='balanced';tx.setParameters(p).catch(()=>{})}catch{}}
  };
  const attachLocal=async(pc:RTCPeerConnection)=>{
    const L=local.current,two=pc.getTransceivers().filter(x=>x.receiver.track.kind==='video').length>1,share=L.video&&L.video!==L.cam?L.video:null;let vi=0;
    for(const tx of pc.getTransceivers()){
      const kind=tx.receiver.track.kind;tx.direction='sendrecv';
      let t:MediaStreamTrack|null|undefined;
      if(kind==='audio')t=L.mixed||L.audio;else{const i=vi++;t=!two?L.video:i===0?L.cam:share}     // two video lines: the camera keeps going while a screen is shared on the other
      await tx.sender.replaceTrack(t||null);
    }
    tuneSenders();
  };
  const callPeer=async(id:string)=>{ // we are the newcomer: we send the offer
    const pc=makePc(id);pc.addTransceiver('audio',{direction:'sendrecv'});pc.addTransceiver('video',{direction:'sendrecv'});pc.addTransceiver('video',{direction:'sendrecv'});
    await attachLocal(pc);const offer=await pc.createOffer();await pc.setLocalDescription(offer);send({type:'signal',to:id,data:{sdp:pc.localDescription}});
  };
  const onSignalNow=async(from:string,data:any)=>{
    const pc=makePc(from);
    if(data.sdp){
      await pc.setRemoteDescription(data.sdp);
      const q=pendIce.current[from]||[];pendIce.current[from]=[];for(const c of q){try{await pc.addIceCandidate(c)}catch{}}     // candidates that arrived before the offer was applied
      if(data.sdp.type==='offer'){await attachLocal(pc);const ans=await pc.createAnswer();await pc.setLocalDescription(ans);send({type:'signal',to:from,data:{sdp:pc.localDescription}})}
    }else if(data.candidate){
      if(pc.remoteDescription){try{await pc.addIceCandidate(data.candidate)}catch{}}else(pendIce.current[from]=pendIce.current[from]||[]).push(data.candidate);
    }
  };
  // Frozen-picture watchdog: a person whose camera is on but whose video has stopped arriving gets their connection refreshed (the person with the lower id re-offers, so both sides never do it at once)
  const stall=useRef<Record<string,{b:number;n:number}>>({});
  useEffect(()=>{const iv=setInterval(async()=>{for(const [id,pc] of Object.entries(pcs.current)){
    const pr=peersRef.current[id];if(!pr||!pr.cam||pr.screen||pc.connectionState!=='connected')continue;
    try{let bytes=-1;(await pc.getStats()).forEach((r:any)=>{if(r.type==='inbound-rtp'&&r.kind==='video'&&r.bytesReceived>bytes&&!r.trackIdentifier?.includes('screen'))bytes=Math.max(bytes,r.bytesReceived)});
      const st=stall.current[id]||(stall.current[id]={b:-1,n:0});if(bytes<0)continue;if(bytes>st.b+2000){st.b=bytes;st.n=0}else st.n++;
      if(st.n>=4){st.n=0;if((myId.current||'')<id)(pc as any).kick?.()}}catch{}}},3000);return()=>clearInterval(iv)},[]);
  // When the last share ends, every picture is re-attached so all cameras are running again exactly as before the share
  const anyShare=screen||Object.values(peers).some(p=>p.screen);const wasShare=useRef(false);
  useEffect(()=>{if(wasShare.current&&!anyShare){
    for(const id of Object.keys(peerStreams.current)){const o=peerStreams.current[id];peerStreams.current[id]=new MediaStream(o.getTracks());upsert(id,{stream:peerStreams.current[id]})}
    setLocalStream(l=>l?new MediaStream(l.getTracks()):l);
    tuneSenders();
  }wasShare.current=anyShare},[anyShare]);
  const onSignal=(from:string,data:any)=>{sigQ.current[from]=(sigQ.current[from]||Promise.resolve()).then(()=>onSignalNow(from,data)).catch(()=>{})};     // one message at a time per person, in order
  const dropPeer=(id:string)=>{delete sfuInfo.current[id];pcs.current[id]?.close();delete pcs.current[id];delete pendIce.current[id];delete sigQ.current[id];setTimeout(()=>tuneSenders(),0);delete peerStreams.current[id];delete peerShots.current[id];setPeers(p=>{const n={...p};delete n[id];return n});recorderRefresh()};
  // ---- big meetings: everyone sends once to the Cloudflare video server; we receive the people on stage ----
  const resub=()=>{clearTimeout(resubT.current);resubT.current=setTimeout(()=>{const c=sfuRef.current;if(!c)return;c.subscribe(stageRef.current.filter(id=>id!==myId.current&&sfuInfo.current[id])).catch(e=>{if(e?.message!=='closed')setNotice(e?.message||'Could not receive video from the meeting.')})},400)};
  const enterSfu=async()=>{
    if(sfuOnRef.current)return;sfuOnRef.current=true;setSfuOn(true);
    Object.keys(pcs.current).forEach(id=>{try{pcs.current[id].close()}catch{}delete pcs.current[id];delete pendIce.current[id];delete sigQ.current[id]});     // direct connections give way to the video server
    for(const id of Object.keys(peerStreams.current)){peerStreams.current[id]=new MediaStream();delete peerShots.current[id]}
    setPeers(p=>{const n:Record<string,Peer>={};for(const id in p)n[id]={...p[id],stream:peerStreams.current[id],shot:undefined};return n});
    const c=new SfuClient(send,(id,st)=>{peerStreams.current[id]=st||new MediaStream();upsert(id,{stream:peerStreams.current[id]});recorderRefresh()});sfuRef.current=c;
    setNotice('This is a big meeting, so video now goes through our video server. Speakers, people sharing and the host are shown; everyone is in the Participants list.');
    try{await c.publish(local.current.mixed||local.current.audio,local.current.video)}catch(e:any){if(e?.message!=='closed')setNotice(e?.message||'Could not connect to the video server for this big meeting.')}
    resub();
  };

  const authH:any={'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})};
  const loadHostInfo=()=>!token?Promise.resolve():fetch(`${api}/rooms/${code}/host`,{headers:authH}).then(r=>r.ok?r.json():null).then(j=>j&&setHostInfo(j)).catch(()=>{});
  const changeSecurity=async(patch:any)=>{const r=await fetch(`${api}/rooms/${code}`,{method:'PATCH',headers:authH,body:JSON.stringify(patch)});if(r.ok)setHostInfo({...hostInfo,...(await r.json())});else setNotice('Could not change the meeting settings.')};
  useEffect(()=>{if(info?.you_are_host)loadHostInfo()},[info]);
  const [copied,setCopied]=useState('');
  const copyText=async(id:string,t:string)=>{try{await navigator.clipboard.writeText(t);setCopied(id);setTimeout(()=>setCopied(''),2000)}catch{window.prompt('Copy this:',t)}};
  const endMeeting=async()=>{if(!window.confirm('End this meeting? The link stops working and the meeting is cancelled.'))return;const r=await fetch(`${api}/rooms/${code}/end`,{method:'POST',headers:authH,body:JSON.stringify({cancel:true})});if(r.ok){local.current.audio?.stop();local.current.cam?.stop();onLeave()}else setErr('Could not end the meeting. Try again.')};
  const [joining,setJoining]=useState(false);const [barOn,setBarOn]=useState(true);const [fs,setFs]=useState(false);
  const goFs=()=>{try{if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen()}catch{}};
  useEffect(()=>{const f=()=>setFs(!!document.fullscreenElement);document.addEventListener('fullscreenchange',f);return()=>document.removeEventListener('fullscreenchange',f)},[]);
  useEffect(()=>{if(phase!=='lobby'||err)setJoining(false)},[phase,err]);
  const join=async()=>{
    if(joining)return;setErr('');setJoining(true);try{document.documentElement.requestFullscreen?.().catch(()=>{})}catch{}
    const slow=setTimeout(()=>{setErr('Could not reach the meeting. Check your connection and press Join again.');setJoining(false);try{ws.current?.close()}catch{}},20000);
    const sock=new WebSocket(wsUrl(api,code));ws.current=sock;
    sock.onopen=()=>send({type:'join',client:(()=>{try{let c=sessionStorage.getItem('isift.cid');if(!c){c=Math.random().toString(36).slice(2)+Date.now().toString(36);sessionStorage.setItem('isift.cid',c)}return c}catch{return ''}})(),name:name.trim()||'Guest',token:token||undefined,passcode:passcode.trim()||undefined});
    sock.onmessage=async ev=>{
      clearTimeout(slow);const m=JSON.parse(ev.data);
      if(m.type==='waiting'){setPhase('waiting')}
      else if(m.type==='denied'){setErr('The host did not let you in.');setPhase('ended')}
      else if(m.type==='waiting-list'){setWaitList(m.list||[]);if((m.list||[]).length)setNotice(`${m.list[m.list.length-1].name} is waiting to join`)}
      else if(m.type==='welcome'){setWaitList(m.waiting||[]);if(m.roster)setRoster(m.roster);if(m.host)loadHostInfo();myId.current=m.id;setIsHost(!!m.host);setCohost(!!m.cohost);setPolicy(m.policy||{audio:true,video:true});setRecording(!!m.recording);setLocked(!!m.locked);setHidePics(!!m.hide_pics);setMultiShare(!!m.multi_share);setPens(m.pens||{});if(m.video){setWatch({...m.video,at:Date.now()});setWatchOpen(true)};setCapsActive(!!m.captions);setCanRec(m.can_record!==false);if(typeof m.ends_in==='number'&&m.ends_in<=600)setEndWarn({at:Date.now()+m.ends_in*1000,msg:'This meeting will end soon because the host\u2019s plan limits its length.'});setPhase('room');{let jo:any={};try{jo=JSON.parse(sessionStorage.getItem('isift.join')||'{}');sessionStorage.removeItem('isift.join')}catch{}rememberRoom(code,info?.title||'Meeting');if(jo.audio===false&&local.current.audio){local.current.audio.enabled=false;setMic(false)}if(jo.video===false&&local.current.cam){local.current.cam.enabled=false;setCam(false)}const o=m.options||{};setVrOn(o.virtual_room!==false);setVrAllowed(m.vroom_allowed!==false);if(m.shape)setShapeState(m.shape==="round"?"round":"rect");if(!m.host){if((o.mute_on_entry||m.policy?.audio===false)&&local.current.audio){local.current.audio.enabled=false;setMic(false)}if((o.video_off_on_entry||m.policy?.video===false)&&local.current.cam){local.current.cam.enabled=false;setCam(false)}}else{let so:any={};try{so=JSON.parse(sessionStorage.getItem('isift.start')||'{}');sessionStorage.removeItem('isift.start')}catch{}if((so.video===false||o.host_video_off)&&local.current.cam){local.current.cam.enabled=false;setCam(false)}if(so.screen)setTimeout(()=>screenRef.current?.(),500);if(o.auto_record&&!m.recording)setTimeout(()=>autoRec.current?.(),800)}}for(const p of m.peers){upsert(p.id,{name:p.name,host:p.host,cohost:p.cohost,hand:!!p.hand,...(p.sfu?{screen:!!p.screen}:{})});if(p.sfu)sfuInfo.current[p.id]=p.sfu;if(!m.sfu)await callPeer(p.id)}if(m.sfu){stageRef.current=m.stage||[];setStage(m.stage||[]);await enterSfu()}send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false})}
      else if(m.type==='peer-joined'){upsert(m.id,{name:m.name,host:m.host,cohost:m.cohost});if(!sfuOnRef.current)setNotice(`${m.name} joined`);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false})}
      else if(m.type==='renamed'){if(m.id===myId.current)setName(m.name);else upsert(m.id,{name:m.name})}
      else if(m.type==='peer-left'){if(!sfuOnRef.current)setPeers(p=>{if(p[m.id])setNotice(`${p[m.id].name} left`);return p});dropPeer(m.id)}
      else if(m.type==='sfu'){enterSfu()}
      else if(m.type==='sfu-active'){stageRef.current=m.ids||[];setStage(m.ids||[]);resub()}
      else if(m.type==='sfu-pub'){sfuInfo.current[m.id]=m.sfu;if(m.screen)upsert(m.id,{screen:true});if(stageRef.current.includes(m.id))resub()}
      else if(m.type==='sfu-res'){sfuRef.current?.handle(m)}
      else if(m.type==='signal')onSignal(m.from,m.data);
      else if(m.type==='share-denied'){stopShareNow();setNotice(`${m.by||'Someone'} is sharing. You can share after they stop.`)}
      else if(m.type==='react')addFloat(m.emoji,m.name)
      else if(m.type==='hand'){upsert(m.id,{hand:!!m.up});if(m.up)setNotice(`${m.name||'Someone'} raised a hand`)}
      else if(m.type==='captions')setCapsActive(!!m.on)
      else if(m.type==='caption')addCaption(m.id,m.name,m.text,!!m.final)
      else if(m.type==='locked'){setLocked(!!m.on);setNotice(`${m.by||'The host'} ${m.on?'locked':'unlocked'} the meeting.`)}
      else if(m.type==='hidepics')setHidePics(!!m.on)
      else if(m.type==='multishare'){setMultiShare(!!m.on);setNotice(m.on?'The host allows several people to share at once.':'The host switched back to one share at a time.')}
      else if(m.type==='pen'){setPens(o=>{const n={...o};if(m.holder)n[m.sharer]=m.holder;else delete n[m.sharer];return n});if(m.holder&&m.holder===myId.current)setNotice('You have the pen on the shared screen. Open Pen to point or draw.')}
      else if(m.type==='pointer'){setPointers(o=>({...o,[m.sharer]:{...(o[m.sharer]||{}),[m.by]:{by:m.by,name:m.name,x:m.x,y:m.y,at:Date.now()}}}))}
      else if(m.type==='draw'){addInk(m.sharer,m.by+':'+m.sid,m.by,m.pts||[])}
      else if(m.type==='draw_clear'){setInks(o=>({...o,[m.sharer]:[]}))}
      else if(m.type==='pen_ask'){setPenAsks(a=>[...a.filter(x=>x.id!==m.id),{id:m.id,name:m.name}])}
      else if(m.type==='plan-limit'){setNotice(m.message||'That is not included in the host’s plan.')}
      else if(m.type==='video-error'){setNotice(m.message||'That link cannot be shown.')}
      else if(m.type==='video'){if(m.stopped){setWatch(null);setWatchOpen(false);setNotice((m.by||'Someone')+' stopped the video.')}else{setWatch({kind:m.kind==='web'?'web':'yt',vid:m.vid||'',url:m.url,label:m.label,by:m.by,by_id:m.by_id,playing:!!m.playing,t:Number(m.t)||0,at:Date.now()});setWatchOpen(true)}}
      else if(m.type==='state')upsert(m.id,{mic:m.mic,cam:m.cam,screen:m.screen});
      else if(m.type==='chat'){const ids:string[]=m.to?Array.from(new Set<string>([m.from,...m.to])).sort():[];const key=m.to?ids.join(','):'all';const names:Record<string,string>={[m.from]:m.name};(m.to||[]).forEach((x:string,k:number)=>{names[x]=m.to_names?.[k]||'Someone'});const me=m.from===myId.current;setChat(c=>[...c,{name:m.name,text:m.text,at:m.at,me,key,names,g:groupRef.current?.id||'main'}]);if(!me&&(!chatOpenRef.current||chatKeyRef.current!==key)){setUnread(u=>({...u,[key]:(u[key]||0)+1}));if(!chatOpenRef.current)setNotice(`${m.to?'(private) ':''}${m.name}: ${m.text.slice(0,60)}`)}}else if(m.type==='chat-error'){setNotice(m.message)}
      else if(m.type==='recording'){setRecording(m.on);setNotice(m.on?'This meeting is now being recorded.':'Recording stopped.')}
      else if(m.type==='role'){if(m.id===myId.current){setIsHost(!!m.host);setCohost(!!m.cohost);if(m.self){setNotice(m.transferred?(m.host?'You are now the host.':'You are no longer the host.'):m.host?'You are now a co-host.':'You are no longer a co-host.');if(m.host&&!m.cohost)loadHostInfo()}}else setPeers(p=>p[m.id]?{...p,[m.id]:{...p[m.id],host:!!m.host,cohost:!!m.cohost}}:p)}
      else if(m.type==='role-error'){setNotice(m.message)}
      else if(m.type==='roster'){setRoster(m)}
      else if(m.type==='groups-error'){setNotice(m.message)}
      else if(m.type==='announce'){setBanner({name:m.name,text:m.text});setNotice(`${m.name}: ${m.text.slice(0,80)}`)}
      else if(m.type==='help'){setNotice(`${m.name} in ${m.group||'a group'} asks for the host`)}
      else if(m.type==='group'){
        const keep=new Set<string>((m.peers||[]).map((x:any)=>x.id));
        Object.keys(pcs.current).filter(id=>!keep.has(id)).forEach(dropPeer);
        setPeers(p=>{const n:Record<string,Peer>={};for(const id in p)if(keep.has(id))n[id]=p[id];return n});
        seatIds.current=[];
        if((groupRef.current?.id||'')!==(m.group?.id||'')){setExtraKeys([]);setChatKey('all');setPicking(false)}
        setGroup(m.group||null);setGroupEnds(m.ends_at||null);
        for(const x of m.peers||[])upsert(x.id,{name:x.name,host:x.host,cohost:x.cohost});
        for(const id of m.offer_to||[])await callPeer(id);
        send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false});
        if(m.moved)setNotice(m.group?(m.reason==='assigned'?`You are in ${m.group.name}`:`You were moved to ${m.group.name}`):m.reason==='time'?'Discussion time is over. Back in the main room.':'Back in the main room.');
        if(!m.group)setBanner(null)}
      else if(m.type==='tshape'){setShapeState(m.shape==='round'?'round':'rect')}
      else if(m.type==='vroom'){setVrOn(!!m.on);if(m.on)setView('table');setNotice(`${m.by||'The host'} switched the virtual room ${m.on?'on':'off'}.`)}
      else if(m.type==='policy'){setPolicy({audio:!!m.audio,video:!!m.video});setNotice(`${m.by||'The host'} changed what participants may switch on.`)}
      else if(m.type==='force'){
        if(m.mic===false){if(local.current.audio)local.current.audio.enabled=false;setMic(false)}
        if(m.cam===false){if(local.current.cam)local.current.cam.enabled=false;setCam(false)}
        send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false});
        setNotice(m.reason==='policy'?'The host has not allowed participants to turn that on.':m.all?`${m.by||'The host'} muted everyone.`:`${m.by||'The host'} turned off your ${m.mic===false&&m.cam===false?'microphone and camera':m.mic===false?'microphone':'camera'}.`)}
      else if(m.type==='ask'){setAsk({by:m.by,what:m.what})}
      else if(m.type==='kicked'){leaveLocal();setErr('You were removed from the meeting by the host.');setPhase('ended')}
      else if(m.type==='title'){setInfo((i:any)=>i?{...i,title:m.title}:i)}
      else if(m.type==='notice'){if(m.kind==='ending')setEndWarn({at:Date.now()+(m.ends_in||0)*1000,msg:m.message});else if(m.message)setNotice(m.message)}
      else if(m.type==='ended'){if(m.reason==='limit')setEndWhy('The time limit of the host\u2019s plan was reached, so this meeting has ended.');leaveLocal();setPhase('ended')}
      else if(m.type==='error'){setErr(m.message);sock.close()}
    };
    sock.onclose=()=>{clearTimeout(slow);setPhase(p=>{if(p==='lobby'){setErr(e=>e||'Could not connect to the meeting. Press Join again.');setJoining(false)}return p==='room'||p==='waiting'?'ended':p})};
    sock.onerror=()=>{setJoining(false)};
  };
  const leaveLocal=()=>{if(tabAud.current){try{tabAud.current.track.stop();tabAud.current.ctx.close().catch(()=>{})}catch{}tabAud.current=null;local.current.mixed=undefined}sfuRef.current?.close();sfuRef.current=null;Object.keys(pcs.current).forEach(id=>{pcs.current[id].close();delete pcs.current[id]});local.current.audio?.stop();local.current.cam?.stop();local.current.video?.stop();local.current.raw?.stop();local.current.proc?.stop();ws.current?.close()};
  const leave=async()=>{if(rec.current)await stopRecording(false);leaveLocal();onLeave()};
  const endAll=async()=>{if(rec.current)await stopRecording(true);send({type:'end'});leaveLocal();onLeave()};

  // ---- controls ----
  const toggleMic=()=>{const t=local.current.audio;if(!t)return;if(!t.enabled&&phase==='room'&&!isHost&&!policy.audio){setNotice('The host has not allowed participants to unmute. Ask the host.');return}t.enabled=!t.enabled;setMic(t.enabled);send({type:'state',mic:t.enabled,cam:!!local.current.video?.enabled,screen})};
  const toggleCam=()=>{const t=local.current.cam;if(!t)return;if(!t.enabled&&phase==='room'&&!isHost&&!policy.video){setNotice('The host has not allowed participants to start their video. Ask the host.');return}t.enabled=!t.enabled;setCam(t.enabled);send({type:'state',mic:!!local.current.audio?.enabled,cam:t.enabled,screen})};
  const replaceVideo=async(track?:MediaStreamTrack)=>{
    const cam=local.current.cam,isCam=!track||track===cam;
    for(const pc of Object.values(pcs.current)){
      const vt=pc.getTransceivers().filter(x=>x.receiver.track.kind==='video');
      try{
        if(vt.length>1){await vt[0].sender.replaceTrack(cam||null);await vt[1].sender.replaceTrack(isCam?null:track!)}     // camera stays on the first line, the screen goes on the second
        else if(vt[0])await vt[0].sender.replaceTrack(track||null);
      }catch{}
    }
    await sfuRef.current?.replaceVideo(track||null,!!track&&track!==local.current.cam).catch(()=>{});
    tuneSenders();
  };
  const [bg,setBg]=useState<BgMode>(loadSaved);const [bgOpen,setBgOpen]=useState(false);const [bgBusy,setBgBusy]=useState(false);const [bgSel,setBgSel]=useState<BgMode>(()=>loadSaved());const openBg=()=>{setBgSel(bg);setBgOpen(true)};const bgInit=useRef(false);
  // Sound of a shared browser tab (a video, a recording): mixed with the microphone and sent on the same audio line, so there is nothing extra to connect. Muting the microphone still leaves the tab's sound on.
  const tabAud=useRef<{ctx:AudioContext;track:MediaStreamTrack}|null>(null);
  const replaceAudio=async(track:MediaStreamTrack|null)=>{for(const pc of Object.values(pcs.current)){const tx=pc.getTransceivers().find(x=>x.receiver.track.kind==='audio');if(tx)try{await tx.sender.replaceTrack(track)}catch{}}await sfuRef.current?.replaceAudio(track).catch(()=>{})};
  const stopTabAudio=async(restore=true)=>{const t=tabAud.current;if(!t)return;tabAud.current=null;local.current.mixed=undefined;try{t.track.stop()}catch{}if(restore)await replaceAudio(local.current.audio||null);try{await t.ctx.close()}catch{}};
  const startTabAudio=async(track:MediaStreamTrack):Promise<boolean>=>{try{await stopTabAudio(false);const Ctx=(window as any).AudioContext||(window as any).webkitAudioContext;const ctx:AudioContext=new Ctx();await ctx.resume().catch(()=>{});const dest=ctx.createMediaStreamDestination();if(local.current.audio)ctx.createMediaStreamSource(new MediaStream([local.current.audio])).connect(dest);ctx.createMediaStreamSource(new MediaStream([track])).connect(dest);const mix=dest.stream.getAudioTracks()[0];tabAud.current={ctx,track};local.current.mixed=mix;await replaceAudio(mix);recorderRefresh();return true}catch{local.current.mixed=undefined;tabAud.current=null;return false}};
  // ---- reactions, raised hand, live captions ----
  const addFloat=(emoji:string,name:string)=>{const k=Math.random().toString(36).slice(2);const x=8+Math.random()*84;setFloats(f=>[...f.slice(-24),{k,emoji,name,x}]);setTimeout(()=>setFloats(f=>f.filter(i=>i.k!==k)),3400)};
  const sendReact=(emoji:string)=>send({type:'react',emoji});
  const toggleHand=()=>{const v=!myHand;setMyHand(v);send({type:'hand',up:v});setNotice(v?'Hand raised. Everyone can see it.':'Hand lowered.')};
  const addCaption=(id:string,name:string,text:string,final:boolean)=>{const now=Date.now();
    setCapLines(L=>{let out=L.filter(l=>now-l.at<9000);const i=out.findIndex(l=>l.id===id&&!l.final);const line:CapLine={k:i>=0?out[i].k:id+now,id,name,text,final,at:now};out=i>=0?out.map((l,j)=>j===i?line:l):[...out,line];return out.slice(-3)});
    if(final)setCapHist(H=>[...H.slice(-500),{k:id+now+Math.random(),id,name,text,final:true,at:now}])};
  const toggleCaps=()=>{const v=!capsView;setCapsView(v);send({type:'captions_want',on:v});if(!v)setCapLines([])};
  const SR:any=typeof window!=='undefined'?((window as any).SpeechRecognition||(window as any).webkitSpeechRecognition):null;
  // while anyone wants captions, this browser writes down what its own microphone hears and sends the words on
  useEffect(()=>{if(!capsActive||!SR||!mic||phase!=='room')return;let run=true,last=0;const rc=new SR();rc.continuous=true;rc.interimResults=true;rc.lang=navigator.language||'en-US';
    rc.onresult=(e:any)=>{for(let i=e.resultIndex;i<e.results.length;i++){const res=e.results[i];const text=String(res[0]?.transcript||'').trim();if(!text)continue;const final=!!res.isFinal;const now=Date.now();if(!final&&now-last<450)continue;last=now;send({type:'caption',text,final});addCaption(myId.current,'You',text,final)}};
    rc.onend=()=>{if(run)try{rc.start()}catch{}};rc.onerror=(e:any)=>{if(e?.error==='not-allowed'||e?.error==='service-not-allowed'){run=false}};
    try{rc.start()}catch{}
    return()=>{run=false;try{rc.onend=null;rc.stop()}catch{}}},[capsActive,mic,phase]);
  useEffect(()=>{if(!capsView)return;const iv=setInterval(()=>setCapLines(L=>{const f=L.filter(l=>Date.now()-l.at<9000);return f.length===L.length?L:f}),1500);return()=>clearInterval(iv)},[capsView]);
  const swapCam=async(nt:MediaStreamTrack)=>{const L=local.current,old=L.cam,en=old?old.enabled!==false:true,sharing=!!L.video&&L.video!==old;nt.enabled=en;L.cam=nt;if(!sharing){L.video=nt;await replaceVideo(nt)}else for(const pc of Object.values(pcs.current)){const vt=pc.getTransceivers().filter(x=>x.receiver.track.kind==='video');if(vt.length>1)try{await vt[0].sender.replaceTrack(nt)}catch{}}setLocalStream(new MediaStream([...(L.audio?[L.audio]:[]),nt]))};
  const applyBg=async(m:BgMode)=>{
    setBg(m);saveBg(m);const L=local.current,raw=L.raw;if(!raw)return;
    if(m.kind==='none'){const p=L.proc;if(p){L.proc=undefined;await swapCam(raw);p.stop()}setBgBusy(false);return}
    if(L.proc){L.proc.setMode(m);return}
    setBgBusy(true);const p=new BgProcessor(raw);L.proc=p;p.setMode(m);
    p.onfail=()=>{setNotice('Background effects are not supported on this device or browser.');if(L.proc===p){L.proc=undefined;p.stop()}setBgBusy(false);setBg({kind:'none'});saveBg({kind:'none'})};
    p.onready=async()=>{if(L.proc===p){await swapCam(p.track);setBgBusy(false)}};
  };
  useEffect(()=>{if(localStream&&!bgInit.current&&local.current.raw){bgInit.current=true;if(bg.kind!=='none')applyBg(bg)}},[localStream]);
  const bgPanel=<div className="rm-bgwrap" onClick={()=>setBgOpen(false)}><div className="rm-bgpanel" role="dialog" aria-label="Background and effects" onClick={e=>e.stopPropagation()}>
    <div className="rm-bghead"><b>Background &amp; effects</b><button type="button" onClick={()=>setBgOpen(false)} aria-label="Close"><X size={16}/></button></div>
    {!local.current.raw&&<p className="muted small">No camera is available, so there is nothing to change.</p>}
    <div className="rm-bggrid">
      <button type="button" className={`rm-bgopt${bgSel.kind==='none'?' on':''}`} onClick={()=>setBgSel({kind:'none'})}><i className="none"><X size={18}/></i><span>None</span></button>
      <button type="button" className={`rm-bgopt${bgSel.kind==='blur'&&bgSel.level<14?' on':''}`} onClick={()=>setBgSel({kind:'blur',level:8})}><i className="blur"/><span>Slight blur</span></button>
      <button type="button" className={`rm-bgopt${bgSel.kind==='blur'&&bgSel.level>=14?' on':''}`} onClick={()=>setBgSel({kind:'blur',level:20})}><i className="blur strong"/><span>Strong blur</span></button>
      {PRESETS.map(p=><button type="button" key={p.id} className={`rm-bgopt${bgSel.kind==='image'&&bgSel.id===p.id?' on':''}`} onClick={()=>setBgSel({kind:'image',id:p.id,url:p.url})}><i style={{backgroundImage:`url("${p.url}")`}}/><span>{p.name}</span></button>)}
      <label className={`rm-bgopt${bgSel.kind==='image'&&bgSel.id==='custom'?' on':''}`}><i className="up"><Plus size={20}/></i><span>Upload image</span><input type="file" accept="image/*" hidden onChange={async e=>{const f=e.target.files?.[0];e.target.value='';if(!f)return;try{setBgSel({kind:'image',id:'custom',url:await readImage(f)})}catch{setNotice('That image could not be read.')}}}/></label>
    </div>
    <p className="muted small">{bgBusy?'Starting background effect…':'Pick a background, then press Apply. Everyone in the meeting sees your choice.'}</p>
    <div className="rm-bgact"><button type="button" className="secondary" onClick={()=>setBgOpen(false)}>Cancel</button><button type="button" className="primary" onClick={()=>{applyBg(bgSel);setBgOpen(false)}}>Apply</button></div>
  </div></div>;
  const startFileShare=async(f:File)=>{
    if(!FileShare.accepts(f)){setNotice('Choose a photo or a PDF.');return}
    if(blockedShare())return;
    setNotice('Opening '+f.name+'…');
    try{
      const fs=new FileShare(f);await fs.init();fileShare.current=fs;fs.onPage=n=>setFilePg({n,of:fs.pages});const t=fs.track;
      local.current.video=t;setScreenStream(new MediaStream([t]));
      await replaceVideo(t);setScreen(true);setFilePg(fs.pages>1?{n:fs.page,of:fs.pages}:null);
      setNotice(fs.pages>1?'Sharing your PDF. Use the arrows to change page. Everyone can zoom in.':'Sharing your photo. Everyone can zoom in.');
      send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:true});
    }catch(e){fileShare.current?.stop();fileShare.current=null;setNotice('That file could not be opened. Try a photo (JPG or PNG) or a PDF.')}
  };
  const stopShareNow=async()=>{stopTabAudio();fileShare.current?.stop();fileShare.current=null;setFilePg(null);const st=local.current.video;await replaceVideo(local.current.cam);local.current.video=local.current.cam;if(st&&st!==local.current.cam)try{st.stop()}catch{};setScreenStream(null);setScreen(false);setWbOn(false)};
  const sharingKey=[...(screen?[myId.current]:[]),...Object.entries(peers).filter(([,p]:any)=>p.screen).map(([id])=>id)].join(',');
  useEffect(()=>{const on=new Set(sharingKey.split(',').filter(Boolean));const prune=(o:any)=>{const k=Object.keys(o).filter(x=>!on.has(x));if(!k.length)return o;const n={...o};k.forEach(x=>delete n[x]);return n};setInks(prune);setPointers(prune);if(!screen)setPenAsks([])},[sharingKey]);
  const addInk=(sharer:string,key:string,by:string,pts:number[][])=>setInks(o=>{const a=(o[sharer]||[]).slice();const i=a.findIndex(s=>s.key===key);if(i>=0)a[i]={...a[i],pts:[...a[i].pts,...pts]};else a.push({key,by,pts});return {...o,[sharer]:a.slice(-400)}});
  const otherSharer=()=>Object.values(peers).find((p:any)=>p.screen) as any;const blockedShare=()=>{if(multiShare)return false;const o=otherSharer();if(o){setNotice(`${o.name||'Someone'} is sharing. You can share after they stop.`);return true}return false};
  const shareBoard=async()=>{
    if(wbOn){await stopShareNow();send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:false});return}
    if(blockedShare())return;
    try{
      if(screen){stopTabAudio();const st=local.current.video;try{await replaceVideo(local.current.cam)}catch{};if(st&&st!==local.current.cam)try{st.stop()}catch{};fileShare.current?.stop()}
      const cs=new CanvasShare(()=>wbBox.current?.querySelector('canvas')||null);cs.init();fileShare.current=cs;const t=cs.track;
      local.current.video=t;setScreenStream(new MediaStream([t]));await replaceVideo(t);setScreen(true);setWbOn(true);setFilePg(null);
      setNotice('You are sharing the whiteboard. Draw on it and everyone sees it. Everyone can zoom in.');
      send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:true});
    }catch{setNotice('The whiteboard could not be shared.')}
  };
  const saveBoard=async()=>{if(!token)return;try{const r=await fetch(`${api}/notes`,{method:'POST',headers:{'content-type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({kind:'board',title:`Meeting whiteboard · ${info?.title||''}`.slice(0,120),content:wbContent.current||''})});setWbSaved(r.ok?'Saved to your Whiteboards.':'Could not save.')}catch{setWbSaved('Could not save.')}setTimeout(()=>setWbSaved(''),4000)};
  const filePage=async(d:number)=>{const fs=fileShare.current;if(!fs||!fs.show)return;await fs.show((fs.page||1)+d);setFilePg({n:fs.page||1,of:fs.pages||1})};
  const docScroll=fileShare.current&&(fileShare.current as any).scrollBy&&screen&&!wbOn&&filePg?<DocScroll key="docscroll" fs={fileShare.current as any}/>:null;
  const toggleScreen=async()=>{
    if(screen){stopTabAudio();setWbOn(false);fileShare.current?.stop();fileShare.current=null;setFilePg(null);const st=local.current.video;await replaceVideo(local.current.cam);local.current.video=local.current.cam;if(st&&st!==local.current.cam)try{st.stop()}catch{};setScreenStream(null);setScreen(false);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:false});return}
    if(blockedShare())return;
    if(!(navigator.mediaDevices as any)?.getDisplayMedia&&/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)){filePick.current?.click();return}
    if(!(navigator.mediaDevices as any)?.getDisplayMedia){setNotice(/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)?'Phones and tablets do not allow web pages to share the screen: this is a limit of Safari and Chrome on mobile, not of iSift. To present, join this meeting from a laptop or desktop computer. You can still show a document by sharing it from a computer, or by turning your camera on and pointing it at the paper.':'This browser cannot share the screen. Use a current Chrome, Edge, Firefox or Safari on a computer.');return}
    try{const d=await (navigator.mediaDevices as any).getDisplayMedia({video:{frameRate:{ideal:15,max:30}},audio:true,selfBrowserSurface:'exclude',surfaceSwitching:'include'});const t=d.getVideoTracks()[0];const sound=d.getAudioTracks()[0];try{(t as any).contentHint='detail'}catch{}local.current.video=t;setScreenStream(new MediaStream([t]));t.onended=()=>{stopTabAudio();replaceVideo(local.current.cam);local.current.video=local.current.cam;setScreenStream(null);setScreen(false);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:false})};await replaceVideo(t);const withSound=sound?await startTabAudio(sound):false;setScreen(true);setNotice((withSound?'You are sharing your screen and its sound. ':'You are sharing your screen. To also share the sound of a video, stop and share again, choose a Chrome tab and tick Also share tab audio. ')+'Wear headphones to avoid echo, and share a window or tab (not the whole screen) to avoid a mirror-in-mirror picture.');send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:true})}catch(e:any){setNotice(e?.name==='NotAllowedError'?'Screen sharing was cancelled or not allowed. Allow screen recording for your browser in the computer’s privacy settings and try again.':'Screen sharing is not available in this browser.')}
  };
  const others=(key:string)=>key==='all'?[]:key.split(',').filter(x=>x!==myId.current);
  const sendChat=(e:React.FormEvent)=>{e.preventDefault();if(!chatText.trim())return;const to=others(chatKey);send({type:'chat',text:chatText,...(to.length?{to}:{})});setChatText('')};
  const nameOf=(id:string)=>peers[id]?.name||chat.map(c=>c.names[id]).filter(Boolean).pop()||'Someone';
  const threadLabel=(key:string)=>key==='all'?'Everyone':others(key).map(nameOf).join(', ');
  const curChat=chat.filter(c=>c.g===(group?.id||'main'));const threadKeys=['all',...Array.from(new Set([...extraKeys,...curChat.map(c=>c.key).filter(k=>k!=='all')]))];
  const openThread=(k:string)=>{setChatKey(k);setUnread(u=>({...u,[k]:0}))};
  const startPrivate=()=>{if(!pickSel.length)return;const k=Array.from(new Set([myId.current,...pickSel])).sort().join(',');setExtraKeys(x=>x.includes(k)?x:[...x,k]);openThread(k);setPicking(false);setPickSel([])};
  const copyLink=async()=>{const link=`${location.origin}${location.pathname}#/room/${code}`;const txt=link+(hostInfo?.passcode?`\nPasscode: ${hostInfo.passcode}`:'')+`\nMeeting ID: ${code}`;try{await navigator.clipboard.writeText(txt);setNotice(hostInfo?.passcode?'Link and passcode copied.':'Invitation link copied.')}catch{setNotice(txt)}};

  const openInvite=async()=>{setInviteOpen(true);setInvRes(null);if(token&&!suggest.length){try{const h={Authorization:`Bearer ${token}`};const [cs,acct]=await Promise.all([fetch(`${api}/contacts`,{headers:h}).then(r=>r.ok?r.json():[]),fetch(`${api}/account`,{headers:h}).then(r=>r.ok?r.json():null)]);const list:{name:string;email:string}[]=[];(acct?.company?.members||[]).forEach((m:any)=>list.push({name:m.name||m.email,email:m.email}));(Array.isArray(cs)?cs:cs?.contacts||[]).forEach((c:any)=>{if(c.email)list.push({name:c.name||c.email,email:c.email})});const seen=new Set<string>();setSuggest(list.filter(x=>x.email&&!seen.has(x.email.toLowerCase())&&seen.add(x.email.toLowerCase())&&x.email.toLowerCase()!==(acct?.user?.email||'').toLowerCase()))}catch{}}};
  const sendInvites=async(e:React.FormEvent)=>{e.preventDefault();setInvBusy(true);setInvRes(null);try{const r=await fetch(`${api}/rooms/${code}/invite`,{method:'POST',headers:authH,body:JSON.stringify({emails:invTo,message:invMsg,base_url:location.origin+location.pathname})});const j=await r.json().catch(()=>({}));if(!r.ok)setInvRes({error:typeof j.detail==='string'?j.detail:'The invitation could not be sent.'});else{setInvRes(j);setInvTo('');}}catch{setInvRes({error:'Could not reach the server.'})}finally{setInvBusy(false)}};
  const addInvite=(email:string)=>setInvTo(t=>t.toLowerCase().includes(email.toLowerCase())?t:(t.trim()?t.replace(/[,\s]+$/,'')+', ':'')+email);

  // ---- recording (host only): audio mix for the transcript + composite video for the archive ----
  const gridRef=useRef<HTMLDivElement>(null);
  /* where the table top really is on screen (it is drawn in perspective), so the legs, the shadow and the resize grips can be placed against it */
  useLayoutEffect(()=>{const room=gridRef.current,t=room?.querySelector('.rm-table') as HTMLElement|null;if(!room||!t||!room.classList.contains('rm-room')){setTb(null);return}
    const m=()=>{const a=room.getBoundingClientRect(),b=t.getBoundingClientRect();const n={x0:b.left-a.left,y0:b.top-a.top,x1:b.right-a.left,y1:b.bottom-a.top,rw:a.width,rh:a.height};setTb(o=>o&&Math.abs(o.x0-n.x0)<.5&&Math.abs(o.y0-n.y0)<.5&&Math.abs(o.x1-n.x1)<.5&&Math.abs(o.y1-n.y1)<.5&&Math.abs(o.rw-n.rw)<.5&&Math.abs(o.rh-n.rh)<.5?o:n)};
    m();const ro=new ResizeObserver(m);ro.observe(room);return()=>ro.disconnect()});
  const infoRef=useRef<any>({peers:[],local:null,name:'',cam:false,mic:false,screen:false,speaking:''});
  infoRef.current={peers:Object.values(peers),local:localStream,name,cam,mic,screen,speaking,vtrack:local.current.video};
  const recorderRefresh=()=>{const r=rec.current;if(!r)return;const have=new Set<string>(r.sources.keys());
    const streams:Record<string,MediaStream>={...peerStreams.current,__me:localStream||new MediaStream()};if(tabAud.current)streams.__tab=new MediaStream([tabAud.current.track]);
    for(const [k,s] of Object.entries(streams)){const t=s.getAudioTracks()[0];if(t&&!have.has(k+t.id)){try{const src=r.ctx.createMediaStreamSource(new MediaStream([t]));src.connect(r.dest);r.sources.set(k+t.id,src)}catch{}}}};
  useEffect(()=>{if(!recording)return;const h=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',h);return()=>window.removeEventListener('beforeunload',h)},[recording]);
  const autoRec=useRef<null|(()=>void)>(null);const screenRef=useRef<null|(()=>void)>(null);
  const startRecording=async(auto?:boolean)=>{
    if(!isHost||rec.current)return;
    if(!canRec){if(auto!==true)setNotice('Recording is not included in the Basic plan. Upgrade your plan, or ask an administrator to allow recording for you.');return}
    if(auto!==true&&!window.confirm('Start recording? Everyone in the meeting is told it is being recorded. Keep this tab open while recording (it may stay in the background).'))return;
    const ctx=new AudioContext();const dest=ctx.createMediaStreamDestination();const r:any={ctx,dest,sources:new Map(),audioChunks:[],videoChunks:[]};rec.current=r;
    await ctx.resume().catch(()=>{});
    const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;const g=canvas.getContext('2d')!;
    // The archive shows only: the person speaking (or the shared screen), attendee names, an initial/photo when a camera is off. Never the on-screen table or room.
    r.vids=new Map<string,HTMLVideoElement>();r.last='';
    const vidFor=(k:string,st:MediaStream|null)=>{if(!st)return null;let v=r.vids.get(k);if(!v){v=document.createElement('video');v.muted=true;v.playsInline=true;v.autoplay=true;r.vids.set(k,v)}if(v.srcObject!==st){v.srcObject=st;v.play().catch(()=>{})}return v.videoWidth>0&&v.readyState>=2?v:null};
    const fit=(v:HTMLVideoElement,x:number,y:number,w:number,h:number)=>{const k=Math.min(w/v.videoWidth,h/v.videoHeight);const dw=v.videoWidth*k,dh=v.videoHeight*k;g.drawImage(v,x+(w-dw)/2,y+(h-dh)/2,dw,dh)};
    const face=(who:any,x:number,y:number,w:number,h:number,label:boolean)=>{
      const v=who.cam?vidFor(who.key,who.stream):null;g.fillStyle='#16303f';g.fillRect(x,y,w,h);
      if(v)fit(v,x,y,w,h);else{const rr=Math.min(w,h)*0.22;g.fillStyle='#2f6f8f';g.beginPath();g.arc(x+w/2,y+h/2,rr,0,Math.PI*2);g.fill();g.fillStyle='#fff';g.font=`600 ${Math.round(rr*1.1)}px system-ui,sans-serif`;g.textAlign='center';g.textBaseline='middle';g.fillText((who.name||'?').trim().charAt(0).toUpperCase(),x+w/2,y+h/2+2)}
      if(label){const t=who.name+(who.mic?'':' (muted)');g.font='600 22px system-ui,sans-serif';g.textAlign='left';g.textBaseline='middle';const tw=g.measureText(t).width+24;g.fillStyle='rgba(0,0,0,.6)';g.fillRect(x+12,y+h-48,tw,36);g.fillStyle='#fff';g.fillText(t,x+24,y+h-30)}};
    const draw=()=>{const I=infoRef.current;g.fillStyle='#0b1620';g.fillRect(0,0,1280,720);
      const all=[{key:'__me',name:I.name||'Host',stream:I.local,cam:I.cam,mic:I.mic,screen:I.screen,self:true},...I.peers.map((p:any)=>({key:p.id,name:p.name,stream:p.stream,cam:p.cam,mic:p.mic,screen:p.screen}))];
      const sharer=all.find(x=>x.screen);if(I.speaking&&all.some(x=>x.key===I.speaking))r.last=I.speaking;
      const spk=all.find(x=>x.key===r.last)||all.find(x=>!x.self)||all[0];
      const top=60,bot=720-64;
      if(sharer){const sst=sharer.self&&I.vtrack?(r.ss&&r.ssId===I.vtrack.id?r.ss:(r.ssId=I.vtrack.id,r.ss=new MediaStream([I.vtrack]))):sharer.stream;const v=vidFor(sharer.key+(sharer.self?r.ssId:''),sst);g.fillStyle='#000';g.fillRect(0,top,1280,bot-top);if(v)fit(v,0,top,1280,bot-top);
        const sp=spk&&spk.key!==sharer.key?spk:null;if(sp)face(sp,1280-324,bot-186,312,174,true);
        g.fillStyle='#fff';g.font='600 22px system-ui,sans-serif';g.textAlign='left';g.textBaseline='middle';g.fillText(sharer.name+' is sharing their screen',20,30)}
      else{face(spk,240,top,800,bot-top,true);g.fillStyle='#fff';g.font='600 22px system-ui,sans-serif';g.textAlign='left';g.textBaseline='middle';g.fillText(spk.name+' is speaking',20,30)}
      g.fillStyle='#0f2431';g.fillRect(0,bot,1280,64);g.font='500 20px system-ui,sans-serif';g.textBaseline='middle';let x=20;g.textAlign='left';
      for(const a of all){const t=a.name+(a.key===spk?.key?' ●':'');const w=g.measureText(t).width+24;if(x+w>1260){g.fillStyle='#8fb2c4';g.fillText('…',x,bot+32);break}g.fillStyle=a.key===spk?.key?'#2f6f8f':'#1b3b4d';g.fillRect(x,bot+14,w,36);g.fillStyle='#fff';g.fillText(t,x+12,bot+32);x+=w+8}};
    try{const wk=new Worker(URL.createObjectURL(new Blob(['setInterval(()=>postMessage(0),66)'],{type:'text/javascript'})));wk.onmessage=draw;r.timer=wk}catch{r.timer=setInterval(draw,66)}
    recorderRefresh();
    const mk=(stream:MediaStream,mime:string,opts:any,sink:Blob[])=>{const mr=new MediaRecorder(stream,{mimeType:mime,...opts});mr.ondataavailable=e=>{if(e.data.size)sink.push(e.data)};mr.start(2000);return mr};
    r.audioRec=mk(dest.stream,'audio/webm;codecs=opus',{audioBitsPerSecond:32000},r.audioChunks);
    const vs=canvas.captureStream(15);dest.stream.getAudioTracks().forEach(t=>vs.addTrack(t));
    r.videoRec=mk(vs,MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus')?'video/webm;codecs=vp8,opus':'video/webm',{videoBitsPerSecond:1500000},r.videoChunks);
    send({type:'record',on:true});setRecording(true);wasRecording.current=true;
  };
  autoRec.current=()=>{startRecording(true)};screenRef.current=()=>{toggleScreen()};
  const stopRecording=async(_ending?:boolean)=>{
    const r=rec.current;if(!r)return;rec.current=null;setRecBusy(true);
    const stopOne=(mr:MediaRecorder)=>new Promise<void>(res=>{mr.onstop=()=>res();try{mr.stop()}catch{res()}});
    await Promise.all([stopOne(r.audioRec),stopOne(r.videoRec)]);(typeof r.timer?.terminate==='function'?r.timer.terminate():clearInterval(r.timer));r.ctx.close().catch(()=>{});
    send({type:'record',on:false});setRecording(false);
    try{
      // The recording is always saved to the host's own computer first.
      try{const whole=r.videoChunks.length?new Blob(r.videoChunks,{type:'video/webm'}):new Blob(r.audioChunks,{type:'audio/webm'});const a=document.createElement('a');a.href=URL.createObjectURL(whole);a.download=`${(info?.title||'meeting').replace(/[^\w .-]+/g,'_').slice(0,50)} ${new Date().toISOString().slice(0,16).replace(/[T:]/g,'-')}.webm`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),60000)}catch{}
      const form=new FormData();form.append('consent_acknowledged','true');form.append('cloud',cloud?'true':'false');
      form.append('audio',new Blob(r.audioChunks,{type:'audio/webm'}),'speech.webm');
      if(cloud&&r.videoChunks.length)form.append('video',new Blob(r.videoChunks,{type:'video/webm'}),'meeting.webm');
      const res=await fetch(`${api}/rooms/${code}/recording`,{method:'POST',headers:{Authorization:`Bearer ${token}`},body:form});const j=await res.json().catch(()=>({}));
      setNotice(res.ok?j.message:(j.detail||'The recording could not be saved.'));
    }catch{setNotice('The recording could not be uploaded. Check the connection.')}finally{setRecBusy(false)}
  };
  useEffect(()=>{if(!isHost||!token)return;fetch(`${api}/billing/me`,{headers:{Authorization:`Bearer ${token}`}}).then(r=>r.ok?r.json():null).then(j=>j&&setRecPlan(j.plan||'')).catch(()=>{})},[isHost,token]);
  useEffect(()=>{if(notice){const t=setTimeout(()=>setNotice(''),6000);return()=>clearTimeout(t)}},[notice]);

  peersRef.current=peers;localRef.current=localStream;
  // Active speaker: listen to the real audio of each person in this room and mark whoever is loudest.
  useEffect(()=>{
    if(phase!=='room')return;const AC:any=(window as any).AudioContext||(window as any).webkitAudioContext;if(!AC)return;
    let ctx:AudioContext;try{ctx=new AC()}catch{return}
    const nodes=new Map<string,{track:string;an:AnalyserNode;src:MediaStreamAudioSourceNode}>();const buf=new Uint8Array(512);let last='',lastTalk=0;
    const level=(id:string,stream:MediaStream|null|undefined)=>{
      const t=stream?.getAudioTracks()[0];const cur=nodes.get(id);
      if(!t||t.readyState!=='live'){if(cur){try{cur.src.disconnect()}catch{}nodes.delete(id)}return 0}
      if(!cur||cur.track!==t.id){if(cur){try{cur.src.disconnect()}catch{}}try{const src=ctx.createMediaStreamSource(new MediaStream([t]));const an=ctx.createAnalyser();an.fftSize=512;src.connect(an);nodes.set(id,{track:t.id,an,src})}catch{return 0}}
      const n=nodes.get(id);if(!n)return 0;n.an.getByteTimeDomainData(buf);let sum=0;for(let i=0;i<buf.length;i++){const v=(buf[i]-128)/128;sum+=v*v}return Math.sqrt(sum/buf.length)};
    const tick=()=>{
      if(ctx.state==='suspended')ctx.resume().catch(()=>{});
      const live=new Set<string>(['__me',...Object.keys(peersRef.current)]);for(const id of Array.from(nodes.keys()))if(!live.has(id)){try{nodes.get(id)!.src.disconnect()}catch{}nodes.delete(id)}
      let best='',top=0.02;
      const me=localRef.current;if(me&&local.current.audio?.enabled){const l=level('__me',me);if(l>top){top=l;best='__me'}if(sfuOnRef.current&&l>0.03&&Date.now()-lastTalk>3000){lastTalk=Date.now();send({type:'talk'})}}
      for(const id of Object.keys(peersRef.current)){const l=level(id,peersRef.current[id].stream);if(l>top){top=l;best=id}}
      if(best!==last){last=best;setSpeaking(best)}};
    const iv=setInterval(tick,250);
    return()=>{clearInterval(iv);nodes.forEach(n=>{try{n.src.disconnect()}catch{}});try{ctx.close()}catch{}};
  },[phase]);
  useEffect(()=>{if(!groupEnds)return;const iv=setInterval(()=>tickClock(x=>x+1),1000);return()=>clearInterval(iv)},[groupEnds]);
  useEffect(()=>{if(banner){const t=setTimeout(()=>setBanner(null),25000);return()=>clearTimeout(t)}},[banner]);

  // ---------- views ----------
  if(err&&phase!=='ended'&&!info)return <div className="rm-center"><div className="rm-card"><h1>Meeting not available</h1><p>{err}</p><button className="primary" onClick={onLeave}>Back to the app</button></div></div>;
  if(phase==='ended')return <div className="rm-center"><div className="rm-card"><h1>{err?'You left the meeting':'This meeting has ended'}</h1><p>{err||endWhy||'Thanks for joining.'}</p><button className="primary" onClick={onLeave}>{token?'Back to the app':'Close'}</button></div></div>;
  if(!info)return <div className="rm-center"><div className="rm-card">Loading…</div></div>;
  if(phase==='lobby')return <div className="rm-center"><div className="rm-card lobby"><button type="button" className="rm-x" aria-label="Close and leave this meeting" title="Close" onClick={()=>{leaveLocal();onLeave()}}><X size={20}/></button>
    <h1>{info.title}{info.you_are_host&&!!token&&<button type="button" className="rm-editname dark" title="Rename this meeting" aria-label="Rename this meeting" onClick={()=>{const t=window.prompt('Meeting name',info.title);if(t&&t.trim())renameTo(t)}}><Pencil size={17}/></button>}</h1><p className="muted">Hosted by {info.host||'the organizer'} · {info.people_now} {info.people_now===1?'person':'people'} in the meeting</p>
    <div className="rm-preview"><VideoTile stream={localStream} name={name||'You'} muted off={!cam||!localStream?.getVideoTracks().length} self/></div>
    {mediaNote&&<p className="muted">{mediaNote}</p>}
    <p className="muted small">Tip: wear headphones. Speakers next to a microphone, or two devices in the same room, cause echo that no software can fully remove.</p>
    <label>Your name<input value={name} onChange={e=>setName(e.target.value)} maxLength={60} placeholder="Your name" autoFocus/></label>
    {!info.signed_in&&!info.you_are_host&&info.access!=='signed_in'&&<p className="rm-guest" role="note"><b>Joining as a guest.</b> No account is needed: enter your name and join.{onSignIn&&<> Have an account? <button type="button" className="linkbtn" onClick={()=>{leaveLocal();onSignIn()}}>Sign in</button></>}</p>}
    {info.you_are_host&&<div className="rm-hostbox"><b>Share this meeting</b>
      {[['Link',`${location.origin}${location.pathname}#/room/${code}`,'l'],['Meeting ID',code,'i'],...(hostInfo?.passcode?[['Passcode',hostInfo.passcode,'p']]:[])].map(([lab,val,id])=><div key={id} className="mc-row"><span>{lab}</span><input readOnly value={val} aria-label={lab} onFocus={e=>e.currentTarget.select()}/><button type="button" className="secondary" onClick={()=>copyText(id,val)}>{copied===id?'Copied':'Copy'}</button></div>)}
      <div className="rm-hostactions"><button type="button" className="secondary" onClick={()=>copyText('all',`${info.title}\nJoin: ${location.origin}${location.pathname}#/room/${code}\nMeeting ID: ${code}${hostInfo?.passcode?`\nPasscode: ${hostInfo.passcode}`:''}`)}>{copied==='all'?'Invitation copied':'Copy invitation'}</button><button type="button" className="end-btn" onClick={endMeeting}>End meeting</button></div></div>}
    {info.access==='passcode'&&!info.you_are_host&&<label>Meeting passcode<input value={passcode} onChange={e=>setPasscode(e.target.value)} maxLength={12} placeholder="Passcode from your invitation" autoComplete="off"/></label>}
    {info.access==='signed_in'&&!info.signed_in&&<p className="syncerr" role="alert">This meeting is only open to people with an account. Sign in to join.{onSignIn&&<> <button type="button" className="primary" onClick={()=>{leaveLocal();onSignIn()}}>Sign in</button></>}</p>}
    {info.waiting_room&&!info.you_are_host&&<p className="muted small">The host will let you in when they are ready.</p>}
    {bgOpen&&bgPanel}<div className="rm-lobbyctl"><button type="button" className={`secondary${!mic?' off':''}`} onClick={toggleMic} disabled={!local.current.audio}>{mic?<Mic size={16}/>:<MicOff size={16}/>} {mic?'Mic on':'Mic off'}</button><button type="button" className={`secondary${!cam?' off':''}`} onClick={toggleCam} disabled={!local.current.cam}>{cam?<Video size={16}/>:<VideoOff size={16}/>} {cam?'Camera on':'Camera off'}</button><button type="button" className={`secondary${bg.kind!=='none'?' on':''}`} onClick={openBg} disabled={!local.current.raw}><ImageIcon size={16}/> Background</button></div>
    <p className="muted small">The host may record this meeting. You will see a clear “Recording” banner if they do, and you can leave at any time.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    {info.access==='passcode'&&!info.you_are_host&&passcode.trim().length<4&&<p className="rm-need" role="status">This meeting needs a passcode. Type the passcode from your invitation (at least 4 characters) to enable the join button.</p>}
    {!name.trim()&&<p className="rm-need" role="status">Type your name to enable the join button.</p>}
    <button className={`primary join${joining?' busy':''}`} aria-busy={joining} onClick={join} disabled={joining||!name.trim()||(info.access==="passcode"&&!info.you_are_host&&passcode.trim().length<4)||(info.access==="signed_in"&&!info.signed_in)}>{joining?"Joining…":!info.signed_in&&!info.you_are_host&&info.access!=='signed_in'?(info.waiting_room?"Ask to join as guest":"Join as guest"):(info.waiting_room&&!info.you_are_host?"Ask to join":"Join meeting")}</button>
  </div></div>;
  if(phase==='waiting')return <div className="rm-center"><div className="rm-card"><h1>Waiting for the host</h1><p>The host will let you in shortly. You can leave this page at any time.</p><button className="secondary" onClick={()=>{ws.current?.close();onLeave()}}>Cancel</button></div></div>;
  const everyone=Object.values(peers);const list=sfuOn?everyone.filter(p=>stage.includes(p.id)):everyone;const tiles=list.length+1;const total=everyone.length+1;
  const rankOf=(h?:boolean,c?:boolean)=>!h?0:c?1:2;const myRank=rankOf(isHost,cohost);const primary=myRank===2;
  type Row={id:string;self?:boolean;name:string;host?:boolean;cohost?:boolean;mic:boolean;cam:boolean;screen:boolean;stream:MediaStream|null;shot?:MediaStream|null;hand?:boolean};
  const ordered:Row[]=[{id:'__me',self:true,name:name||'You',host:isHost,cohost,mic,cam,screen,stream:localStream,hand:myHand},...list.map(p=>({id:p.id,name:p.name,host:p.host,cohost:p.cohost,mic:p.mic,cam:p.cam,screen:p.screen,stream:p.stream||null,shot:p.shot||null,hand:p.hand}))]
    .map((r,i)=>({r,i})).sort((a,b)=>rankOf(b.r.host,b.r.cohost)-rankOf(a.r.host,a.r.cohost)||a.i-b.i).map(x=>x.r);     // the host first, then co-hosts, then everyone else
  const orderedAll:Row[]=sfuOn?[...ordered,...everyone.filter(p=>!stage.includes(p.id)).map(p=>({id:p.id,name:p.name,host:p.host,cohost:p.cohost,mic:p.mic,cam:p.cam,screen:p.screen,stream:null}))]:ordered;
  const viewRows=(()=>{const v=ordered.filter(r=>!(hideSelf&&r.self)&&!(hideNoVideo&&!r.self&&!r.cam&&!r.screen));return v.length?v:ordered})();
  const curG=group?.id||'main';const sharing=ordered.some(r=>r.screen);
  const sharerRow=ordered.find(r=>r.screen);const autoShare=!pin&&!!sharerRow;const pinnedRow=pin?ordered.find(r=>r.id===pin):sharerRow;       // someone is sharing: their screen takes the big space and everyone else shrinks to the strip
  const selfStream=screen&&screenStream?screenStream:localStream;const togglePin=(id:string)=>setPin(p=>p===id?'':id);
  const spotTile=(r:Row,big?:boolean)=>r.self?<VideoTile stream={big?selfStream:(localStream||selfStream)} name={r.name} muted off={big?(!cam&&!screen):!cam} self host={isHost} cohost={cohost} screen={big&&screen} speaking={speaking==='__me'} hand={myHand} onDouble={()=>togglePin('__me')}/>:<VideoTile stream={big&&r.screen&&r.shot?r.shot:r.stream} name={r.name} off={big?(!r.cam&&!r.screen):(!r.cam&&!(r.screen&&!r.shot))} host={r.host} cohost={r.cohost} screen={big&&r.screen} speaking={speaking===r.id} hand={r.hand} onDouble={()=>togglePin(r.id)}/>;
  const whoName=(id:string)=>id===myId.current?(name||'You'):((peers as any)[id]?.name||'Someone');
  const penFor=(r:Row)=>{if(!r.screen)return null;const sid=r.self?(myId.current||''):r.id;if(!sid)return null;return <SharePen key={'pen'+sid} sharer={sid} isSharer={!!r.self} holder={pens[sid]||''} holderName={pens[sid]?whoName(pens[sid]):''} myId={myId.current||''} candidates={ordered.filter(x=>!x.self&&x.id!==sid).map(x=>({id:x.id,name:x.name}))} ink={inks[sid]||[]} pointers={Object.values(pointers[sid]||{}).filter(p=>p.by!==myId.current)} send={send} onLocalInk={(k,pts)=>addInk(sid,k,myId.current||'',pts)} onClear={()=>setInks(o=>({...o,[sid]:[]}))} onAsked={()=>setNotice('Asked '+r.name+' for the pen.')}/>};
  const sharerRows=ordered.filter(r=>r.screen);const multiMode=!pin&&sharerRows.length>1;
  const autoT=tiles<=1?.5:tiles===2?.58:tiles===3?.68:tiles===4?.76:tiles===5?.84:tiles<=7?.92:1;                  // the table grows with the number of people
  const tableOk=vrOn&&!sfuOn&&!small&&tiles<=TABLE_MAX&&!sharing&&wide;const mode:'table'|'gallery'=tableOk?'table':'gallery';
  {const here=new Set(list.map(p=>p.id));seatIds.current=seatIds.current.filter(id=>here.has(id));list.forEach(p=>{if(!seatIds.current.includes(p.id))seatIds.current.push(p.id)})}
  const seatRows:Row[]=[ordered.find(r=>r.self)!,...seatIds.current.map(id=>ordered.find(r=>r.id===id)).filter(Boolean) as Row[]];
  const seats=seatPoints(seatRows.length,shape);const seatW=seatWidth(tiles);
  const secsLeft=groupEnds?Math.max(0,Math.round((new Date(groupEnds).getTime()-Date.now())/1000)):null;
  const clock=secsLeft===null?'':`${Math.floor(secsLeft/60)}:${String(secsLeft%60).padStart(2,'0')}`;
  const hostRow=ordered.find(r=>rankOf(r.host,r.cohost)===2);const hostName=hostRow?(hostRow.self?'you':hostRow.name):(info.host||'');
  const canAct=(r:Row)=>!r.self&&myRank>rankOf(r.host,r.cohost);
  const togglePeople=()=>{setPeopleOpen(o=>!o);setChatOpen(false);setMenuFor('')};
  // Phone, held upright (like Zoom on mobile): swipe sideways between screens. Without a share: you large with a few people small, then more people. While someone shares: the shared screen fills the first screen and people follow.
  const mobilePager=small&&portrait;
  const mobileView=!mobilePager?null:(()=>{
    const cell=(r:Row)=>r.self&&screen?<div key={r.id} className="rm-wrap"><div className="rm-tile rm-mysharetile"><MonitorUp size={26}/><b>You are sharing</b><small>Everyone can see it on the first screen</small><button type="button" className="primary" onClick={toggleScreen}>Stop sharing</button></div></div>:<div key={r.id} className="rm-wrap">{spotTile(r)}{!r.mic&&<span className="rm-muted" title="Muted"><MicOff size={13}/></span>}</div>;
    const chunk=(a:Row[],n:number)=>{const o:Row[][]=[];for(let i=0;i<a.length;i+=n)o.push(a.slice(i,i+n));return o};
    const me=viewRows.find(r=>r.self)||viewRows[0];const rest=viewRows.filter(r=>r!==me);const pages:JSX.Element[]=[];
    if(pinnedRow&&(pinnedRow.screen||multiMode)){
      (multiMode?sharerRows:[pinnedRow]).forEach(sr=>{      pages.push(<div key={"share"+sr.id} className="rm-page rm-pg-share"><div className="rm-spot-main"><ZoomPane resetKey={sr.id}>{spotTile(sr,true)}</ZoomPane>{sr.self&&screen&&(shareBarHidden?<button type="button" className="rm-sharepill" onClick={()=>setShareBarHidden(false)} aria-label="Show sharing bar"><MonitorUp size={14}/> Sharing <ChevronUp size={14}/></button>:<div className="rm-sharebar" role="status"><MonitorUp size={16}/><span>You are sharing{filePg&&filePg.of>1?` · page ${filePg.n}/${filePg.of}`:''}</span>{filePg&&filePg.of>1&&<><button type="button" className="iconbtn" onClick={()=>filePage(-1)} aria-label="Previous page" disabled={filePg.n<=1}><ChevronUp size={16}/></button><button type="button" className="iconbtn" onClick={()=>filePage(1)} aria-label="Next page" disabled={filePg.n>=filePg.of}><ChevronDown size={16}/></button></>}<button type="button" className="primary" onClick={toggleScreen}>Stop sharing</button><button type="button" className="iconbtn" onClick={()=>setShareBarHidden(true)} aria-label="Hide sharing bar" title="Hide"><ChevronDown size={16}/></button></div>)}{!(sr.self&&screen)&&<div className="rm-spot-tag"><b>{autoShare?`${sr.self?'You are':sr.name+' is'} sharing ${sr.self?'your':'their'} screen`:`Highlighted: ${sr.name}${sr.self?' (you)':''}`}</b>{!autoShare&&<button type="button" onClick={()=>setPin('')}>Back to everyone</button>}</div>}{sr.self&&docScroll}{penFor(sr)}</div></div>);});
      chunk(viewRows,6).forEach((c,i)=>pages.push(<div key={'p'+i} className="rm-page"><div className="rm-pgrid">{c.map(cell)}</div></div>));
    }else{
      // the first screen shows someone else large (a highlighted person, whoever spoke last, or the newest person), and you as a small picture
      if(speaking&&speaking!=='__me')lastTalk.current=speaking;
      const others=viewRows.filter(r=>!r.self);
      const focus=(pinnedRow&&others.concat(me).includes(pinnedRow)?pinnedRow:null)||others.find(r=>r.id===speaking)||others.find(r=>r.id===lastTalk.current)||others[others.length-1]||me;
      const small=viewRows.filter(r=>r!==focus);
      pages.push(<div key="first" className="rm-page"><div className="rm-bigself"><div className="rm-bigbox">{cell(focus)}{pin&&pinnedRow===focus&&<div className="rm-spot-tag"><b>Highlighted: {focus.name}{focus.self?' (you)':''}</b><button type="button" onClick={()=>setPin('')}>Back to everyone</button></div>}</div></div>{small.length>0&&<div className="rm-thumbs">{small.slice(0,3).map(cell)}</div>}</div>);
      chunk(small.slice(3),6).forEach((c,i)=>pages.push(<div key={'p'+i} className="rm-page"><div className="rm-pgrid">{c.map(cell)}</div></div>));
    }
    const at=Math.min(page,pages.length-1);
    return <><div className="rm-pager" ref={pagerRef} onScroll={e=>{const el=e.currentTarget;const n=Math.round(el.scrollLeft/Math.max(1,el.clientWidth));if(n!==page)setPage(n)}}>{pages}</div>{pages.length>1&&<div className="rm-dots" role="tablist" aria-label="Screens">{pages.map((_,i)=><i key={i} className={i===at?'on':''}/>)}</div>}</>;
  })();
  // ---- the toolbar: a few core buttons, and everything else under More (pick a tool and it joins the bar; pin it to keep it) ----
  const tools:Tool[]=[
    {id:'captions',group:'Meeting',label:'Captions',hint:'Show live captions and the transcript',icon:<Captions size={18}/>,on:capsView,run:toggleCaps},
    {id:'bg',group:'Meeting',label:'Background',hint:'Background and effects',icon:<ImageIcon size={18}/>,on:bg.kind!=='none',run:openBg},
    {id:'invite',group:'Meeting',label:'Invite',hint:'Invite people by email or copy the link',icon:<Link2 size={18}/>,on:inviteOpen,run:()=>inviteOpen?setInviteOpen(false):openInvite()},
    ...(canRec&&(primary||(isHost&&!!info?.options?.open_room))?[{id:'record',group:'Meeting' as const,label:recording?(recBusy?'Saving…':'Stop rec'):'Record',hint:recording?'Stop recording':'Start recording',icon:recording?<Square size={18}/>:<Circle size={18}/>,on:recording,run:()=>{if(recBusy)return;if(recording)stopRecording();else startRecording()}}]:[]),
    {id:'video',group:'Share and work',label:'Share a link',hint:'Watch a YouTube video in sync, or show a Google Doc, Sheet, Slides or Microsoft 365 document to everyone',icon:<Video size={18}/>,on:!!watch,run:()=>setWatchOpen(o=>!o)},
    {id:'whiteboard',group:'Share and work',label:'Whiteboard',hint:'Draw on a whiteboard without leaving the meeting',icon:<PenLine size={18}/>,on:wbOpen&&wbTab==='board',run:()=>{if(wbOpen&&wbTab==='board')setWbOpen(false);else{setWbTab('board');setWbOpen(true)}}},
    ...(token?[{id:'notes',group:'Share and work' as const,label:'Notes and docs',hint:'Open your notes, documents and other files',icon:<NotebookPen size={18}/>,on:wbOpen&&wbTab==='apps',run:()=>{if(wbOpen&&wbTab==='apps')setWbOpen(false);else{setWbTab('apps');setAppsLoaded(true);setWbOpen(true)}}}]:[]),
    ...(isHost?[{id:'groups',group:'Host' as const,label:'Breakout rooms',hint:'Split the meeting into smaller groups',icon:<Group size={18}/>,on:groupsOpen||!!roster?.groups,run:()=>setGroupsOpen(o=>!o)}]:[]),
    ...(isHost&&vrAllowed?[{id:'vroom',group:'Host' as const,label:`Virtual room: ${vrOn?'On':'Off'}`,hint:vrOn?'Everyone sees the boardroom table. Press to switch it off for everyone.':'Everyone sees the gallery. Press to switch the boardroom table on for everyone.',icon:<Armchair size={18}/>,on:vrOn,run:()=>{const v=!vrOn;setVrOn(v);if(v)setView('table');send({type:'vroom',on:v})}}]:[]),
    ...(mode==='table'&&isHost?[{id:'shape',group:'Host' as const,label:shape==='rect'?'Round table':'Rect table',hint:'Change the table shape for everyone',icon:shape==='rect'?<Circle size={18}/>:<RectangleHorizontal size={18}/>,run:()=>{const v=shape==='rect'?'round':'rect';setShapeState(v);send({type:'tshape',shape:v})}}]:[]),
    ...(primary?[{id:'security',group:'Host' as const,label:'Passcode and sign-in',hint:'Who can join: link, passcode or signed-in people',icon:<ShieldCheck size={18}/>,on:secOpen,run:()=>{loadHostInfo();setSecOpen(o=>!o)}}]:[]),
    {id:'hideself',group:'View',label:hideSelf?'Show my video':'Hide my video',hint:'Hide your own picture on this screen only',icon:<EyeOff size={18}/>,on:hideSelf,run:()=>setHideSelf(v=>!v)},
    {id:'hidenovid',group:'View',label:'Only people with video',hint:'Hide people whose camera is off, on this screen only',icon:<Users size={18}/>,on:hideNoVideo,run:()=>setHideNoVideo(v=>!v)},
  ];
  const onBar=tools.filter(t=>pins.includes(t.id)||shown.includes(t.id));
  const pickTool=(t:Tool)=>{t.run();setShown(s=>s.includes(t.id)?s:[...s,t.id]);setMoreOpen(false)};
  const pinTool=(id:string)=>{const has=pins.includes(id);const next=has?pins.filter(x=>x!==id):[...pins,id];setPins(next);savePins(next);setShown(s=>has?s.filter(x=>x!==id):(s.includes(id)?s:[...s,id]))};
  const hideTool=(id:string)=>setShown(s=>s.filter(x=>x!==id));
  return <div className={`rm-shell${barOn?'':' nobar'}${peopleOpen||chatOpen?' sideopen':''}`} style={{['--sidew' as any]:`${(peopleOpen?sideW.people?.w:chatOpen?sideW.chat?.w:0)||213}px`}}>
    <header className="rm-top">{renaming?<form className="rm-rename" onSubmit={e=>{e.preventDefault();renameTo(nameDraft)}}><input autoFocus value={nameDraft} maxLength={200} aria-label="Meeting name" onChange={e=>setNameDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setRenaming(false)}}/><button type="submit" className="primary">Save</button><button type="button" className="secondary" onClick={()=>setRenaming(false)}>Cancel</button></form>:<b className="rm-title">{info.title}{isHost&&!!token&&<button type="button" className="rm-editname" title="Rename this meeting" aria-label="Rename this meeting" onClick={()=>{setNameDraft(info.title);setRenaming(true)}}><Pencil size={15}/></button>}</b>}{hostName&&<span className="muted rm-hostname">Host: {hostName}</span>}{recording&&<span className="rm-rec"><Circle size={10} fill="currentColor"/> Recording</span>}{group&&<span className="rm-group"><Group size={13}/> {group.name}</span>}{clock&&<span className="rm-clock" title="Time left in the discussion groups"><Timer size={13}/> {clock}</span>}<span className="muted"><Users size={14}/> {total}</span>{endWarn&&<div className="rm-endwarn" role="alert"><b>Meeting ending soon.</b> {endWarn.msg} <span className="rm-endleft">{(()=>{const s=Math.max(0,Math.round((endWarn.at-(endNow||Date.now()))/1000));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')} left`})()}</span><button aria-label="Dismiss" onClick={()=>setEndWarn(null)}>×</button></div>}
{notice&&<span className="rm-notice" role="status">{notice}</span>}</header>
    {ask&&<div className="rm-ask" role="alert"><span>{ask.by} asks you to turn on your {ask.what==='cam'?'camera':'microphone'}.</span><button className="primary" onClick={()=>{if(ask.what==='cam')toggleCam();else toggleMic();const t=ask.what==='cam'?local.current.cam:local.current.audio;if(t&&!t.enabled){}setAsk(null)}}>Turn on</button><button className="secondary" onClick={()=>setAsk(null)}>Not now</button></div>}
    {banner&&<div className="rm-banner" role="status"><Megaphone size={16}/><span><b>{banner.name}:</b> {banner.text}</span><button type="button" className="iconbtn" aria-label="Dismiss" onClick={()=>setBanner(null)}><X size={14}/></button></div>}
    {group&&<div className="rm-groupbar" role="status"><span>You are in <b>{group.name}</b> · {tiles} {tiles===1?'person':'people'}{vrOn&&tiles<=TABLE_MAX?' · boardroom table':' · gallery'}</span>{!isHost&&<button type="button" className="secondary" onClick={()=>{send({type:'help'});setNotice('The host has been told you asked for help.')}}><HandHelping size={14}/> Ask the host</button>}</div>}
    {inviteOpen&&<div className="rm-invite" role="dialog" aria-label="Invite people"><div className="rm-invhead"><b>Invite people</b><button type="button" className="iconbtn" aria-label="Close" onClick={()=>setInviteOpen(false)}><X size={16}/></button></div>
      {token?<form onSubmit={sendInvites}>
        <label>Email addresses<textarea value={invTo} onChange={e=>setInvTo(e.target.value)} rows={2} placeholder="name@company.com, other@company.com" required autoFocus/></label>
        {suggest.length>0&&<div className="rm-sugg"><small>Pick from your people:</small><div>{suggest.slice(0,12).map(c=><button key={c.email} type="button" className={invTo.toLowerCase().includes(c.email.toLowerCase())?'on':''} onClick={()=>addInvite(c.email)} title={c.email}>{c.name}</button>)}</div></div>}
        <label>Message (optional)<input value={invMsg} onChange={e=>setInvMsg(e.target.value)} maxLength={500} placeholder="Join us now"/></label>
        <button className="primary" disabled={invBusy||!invTo.trim()}><Send size={15}/> {invBusy?'Sending…':'Send invitation'}</button>
        {invRes?.error&&<p className="syncerr" role="alert">{invRes.error}</p>}
        {invRes&&!invRes.error&&<p className="okmsg" role="status">{invRes.message}{invRes.failed?.length>0&&<> Not emailed: {invRes.failed.map((f:any)=>f.to).join(', ')} ({invRes.failed[0].reason}).</>}</p>}
        <small className="muted">People with an iSift account see an alert as soon as they open the app. Everyone gets the link by email when an email account is set up.</small>
      </form>:<p className="muted small">Sign in to send invitations by email. You can still copy the link below.</p>}
      <div className="rm-invcopy"><button type="button" className="secondary" onClick={copyLink}><Link2 size={14}/> Copy invitation link</button></div></div>}
    {isHost&&waitList.length>0&&<div className="rm-wait" role="region" aria-label="People waiting"><b>Waiting to join</b>{waitList.map(w=><div key={w.id} className="rm-waitrow"><span>{w.name}</span><button className="primary" onClick={()=>send({type:'admit',id:w.id})}>Admit</button><button className="secondary" onClick={()=>send({type:'deny',id:w.id})}>Deny</button></div>)}{waitList.length>1&&<button className="secondary" onClick={()=>send({type:'admit_all'})}>Admit all</button>}</div>}
    {isHost&&groupsOpen&&(()=>{
      const open=!!roster?.groups;const people:any[]=roster?.people||[];
      const eligible=open?0:list.filter(p=>gHosts||!p.host).length+(gHosts?1:0);
      const suggested=Math.max(2,Math.ceil(eligible/TABLE_MAX));const per=eligible?Math.ceil(eligible/Math.max(2,gCount)):0;
      const nameOfPerson=(id:string)=>id===myId.current?'You':(people.find(x=>x.id===id)?.name||'Someone');
      return <div className="rm-groups" role="dialog" aria-label="Discussion groups"><div className="rm-invhead"><b>Discussion groups</b><button type="button" className="iconbtn" aria-label="Close" onClick={()=>setGroupsOpen(false)}><X size={16}/></button></div>
      {!open?<>
        <p className="muted small">Split this meeting into smaller groups. Each group sees, hears and chats only with its own members. Groups of {TABLE_MAX} or fewer get the boardroom table.</p>
        <label>Number of groups<input type="number" min={2} max={30} value={gCount} onChange={e=>setGCount(Math.max(2,Math.min(30,Number(e.target.value)||2)))}/></label>
        <div className="rm-ghint">{eligible<2?<span>At least two participants are needed.</span>:<span>{eligible} {eligible===1?'person':'people'} into {gCount} groups: about {per} each. {per>TABLE_MAX?<b className="warn">That is more than {TABLE_MAX} per group, so those groups use the gallery.</b>:'Every group gets the boardroom table.'}</span>}{eligible>=2&&gCount<suggested&&<button type="button" className="linkbtn" onClick={()=>setGCount(suggested)}>Use {suggested} groups (at most {TABLE_MAX} each)</button>}</div>
        <label>Time limit in minutes (optional)<input type="number" min={1} max={240} value={gMinutes} placeholder="No limit" onChange={e=>setGMinutes(e.target.value)}/></label>
        <label className="check"><input type="checkbox" checked={gHosts} onChange={e=>setGHosts(e.target.checked)}/> Put hosts into groups too</label>
        <button type="button" className="primary" disabled={eligible<2} onClick={()=>send({type:'groups_start',count:gCount,minutes:Number(gMinutes)||0,include_hosts:gHosts})}>Start {gCount} groups</button>
      </>:<>
        {clock&&<p className="muted small"><Timer size={13}/> {clock} left. Everyone returns automatically.</p>}
        {[{id:null as string|null,name:'Main room'},...(roster.groups||[])].map((g:any)=>{const mem=people.filter(x=>(x.group||null)===g.id);return <div key={g.id||'main'} className="rm-gbox"><div className="rm-gtitle"><b>{g.name}</b><span className={mem.length<=TABLE_MAX?'rm-gtag':'rm-gtag big'}>{mem.length} · {mem.length<=TABLE_MAX?'table':'gallery'}</span></div>
          {mem.length?mem.map((x:any)=><div key={x.id} className="rm-gperson"><span>{x.id===myId.current?'You':x.name}{x.host?(x.cohost?' (co-host)':' (host)'):''}</span><select aria-label={`Move ${nameOfPerson(x.id)}`} value={x.group||''} onChange={e=>send({type:'groups_move',id:x.id,group:e.target.value||null})}><option value="">Main room</option>{(roster.groups||[]).map((gg:any)=><option key={gg.id} value={gg.id}>{gg.name}</option>)}</select></div>):<small className="muted">Nobody here.</small>}</div>})}
        <form className="rm-gannounce" onSubmit={e=>{e.preventDefault();if(announce.trim()){send({type:'announce',text:announce});setAnnounce('')}}}><input value={announce} onChange={e=>setAnnounce(e.target.value)} maxLength={300} placeholder="Message to everyone, e.g. 5 minutes left" aria-label="Announcement"/><button className="secondary" disabled={!announce.trim()}><Megaphone size={14}/> Send</button></form>
        <button type="button" className="end-btn" onClick={()=>{if(window.confirm('Bring everyone back to the main room?'))send({type:'groups_end'})}}>Bring everyone back</button>
      </>}</div>})()}
    {primary&&secOpen&&hostInfo&&<div className="rm-sec" role="dialog" aria-label="Meeting security"><b>Who can join</b>
      <label><input type="radio" name="acc" checked={hostInfo.access==='open'} onChange={()=>changeSecurity({access:'open'})}/> Anyone with the link</label>
      <label><input type="radio" name="acc" checked={hostInfo.access==='passcode'} onChange={()=>changeSecurity({access:'passcode'})}/> Link and passcode{hostInfo.passcode&&hostInfo.access==='passcode'?<> · <b>{hostInfo.passcode}</b></>:null}</label>
      <label><input type="radio" name="acc" checked={hostInfo.access==='signed_in'} onChange={()=>changeSecurity({access:'signed_in'})}/> Signed-in people only</label>
      <label><input type="checkbox" checked={!!hostInfo.waiting_room} onChange={e=>changeSecurity({waiting_room:e.target.checked})}/> Waiting room</label>
      <small className="muted">Changes apply to people who join from now on.</small><button className="secondary" onClick={()=>setSecOpen(false)}>Close</button></div>}
    <div className="rm-main">{mobileView?mobileView:multiMode?<div className={`rm-spot sz${stripSz}`}><div className="rm-multi" style={{['--c' as any]:sharerRows.length<=4?2:3}}>{sharerRows.map(r=><div key={r.id} className="rm-multicell rm-spot-main">{r.self?<div className="rm-selfshare"><MonitorUp size={26}/><h2>You are sharing</h2><div className="rm-selfprev"><VideoTile stream={selfStream} name={r.name} muted off={false} self screen/></div><button type="button" className="primary" onClick={toggleScreen}>Stop sharing</button></div>:<ZoomPane resetKey={r.id}>{spotTile(r,true)}</ZoomPane>}{r.self&&docScroll}{penFor(r)}<div className="rm-spot-tag"><b>{r.self?'You':r.name}</b><button type="button" onClick={()=>setPin(r.id)}>Enlarge</button></div></div>)}</div>{!stripHide&&<div className="rm-spot-strip">{ordered.filter(r=>!r.screen||r.self||!!r.shot).map(r=><div key={r.id} className="rm-wrap">{spotTile(r)}{!r.mic&&<span className="rm-muted" title="Muted"><MicOff size={13}/></span>}</div>)}</div>}</div>:pinnedRow?<div className={`rm-spot sz${stripSz}`}><div className="rm-spot-main">{pinnedRow.self&&screen?<div className="rm-selfshare"><MonitorUp size={34}/><h2>You are sharing your screen</h2><p>Everyone can see it. To avoid a picture-in-picture loop, your own screen is shown here as a small preview.</p><div className="rm-selfprev"><VideoTile stream={selfStream} name={pinnedRow.name} muted off={false} self screen/></div><button type="button" className="primary" onClick={toggleScreen}>Stop sharing</button></div>:<ZoomPane resetKey={pinnedRow.id}>{spotTile(pinnedRow,true)}</ZoomPane>}{pinnedRow.self&&docScroll}{penFor(pinnedRow)}<div className="rm-spot-tag"><b>{autoShare?`${pinnedRow.self?'You are':pinnedRow.name+' is'} sharing ${pinnedRow.self?'your':'their'} screen`:`Highlighted: ${pinnedRow.name}${pinnedRow.self?' (you)':''}`}</b>{!autoShare&&<button type="button" onClick={()=>setPin('')}>Back to everyone</button>}<button type="button" onClick={()=>setStripHide(h=>!h)}>{stripHide?'Show people':'Hide people'}</button>{!stripHide&&<button type="button" onClick={bumpStrip} title="Make the people pictures smaller or larger">People: {['small','medium','large'][stripSz]}</button>}</div></div>{!stripHide&&<div className="rm-spot-strip">{ordered.filter(r=>r.id!==pinnedRow.id||(autoShare&&(r.self||!!r.shot))).map(r=><div key={r.id} className="rm-wrap">{spotTile(r)}{!r.mic&&<span className="rm-muted" title="Muted"><MicOff size={13}/></span>}</div>)}</div>}</div>:mode==='table'?<div className="rm-table-stage"><div ref={gridRef} className={`rm-room ${shape}`} style={{['--tw' as any]:+(autoT*tune.tw).toFixed(3),['--td' as any]:+((0.7+0.3*autoT)*tune.td).toFixed(3),['--ps' as any]:tune.ps,['--pf' as any]:tune.pf}} aria-label={`Boardroom table with ${tiles} ${tiles===1?'person':'people'}`}>
      <div className="rm-walls" aria-hidden="true"><i className="w-ceil"/><i className="w-back"/><i className="w-left"/><i className="w-right"/><i className="w-floor"/><i className="w-skirt"/></div>{tb&&(()=>{const w=tb.x1-tb.x0,legH=Math.max(10,Math.min(tb.rh*.15,tb.rh-tb.y1-4)),lw=Math.max(8,tb.rw*.02);return <><div className="rm-floorshadow" style={{left:tb.x0+w*.04,width:w*.92,top:tb.y1+legH*.55,height:Math.max(10,tb.rh*.06)}}/>{shape==="round"?<><div className="rm-leg ped" style={{left:(tb.x0+tb.x1)/2-lw*1.6,width:lw*3.2,top:tb.y1-6,height:legH+6}}/><div className="rm-foot" style={{left:(tb.x0+tb.x1)/2-w*.16,width:w*.32,top:tb.y1+legH-6}}/></>:<><div className="rm-leg" style={{left:tb.x0+w*.09,width:lw,top:tb.y1-6,height:legH+6}}/><div className="rm-leg" style={{left:tb.x1-w*.09-lw,width:lw,top:tb.y1-6,height:legH+6}}/></>}</>})()}<RoomDecor win={scenes.win} pic={scenes.pic} pick={k=>setScenePick(k)}/><div className="rm-table" aria-hidden="true"/>
      {seatRows.map((r,i)=>{const b=seats[i],mv=moved[r.id]||{x:0,y:0},pt={x:b.x+mv.x,y:b.y+mv.y,py:b.py+mv.y};const qs=SSg(r.name);return <div key={r.id} onPointerDown={e=>{if((e.target as HTMLElement).closest('button'))return;dragSeat.current={id:r.id,sx:e.clientX,sy:e.clientY,ox:mv.x,oy:mv.y,on:false};try{(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)}catch{}}} onPointerMove={e=>{const d=dragSeat.current,box=gridRef.current?.getBoundingClientRect();if(!d||d.id!==r.id||!box)return;const dx=e.clientX-d.sx,dy=e.clientY-d.sy;if(!d.on&&Math.hypot(dx,dy)<5)return;d.on=true;const nx=Math.max(4-b.x,Math.min(96-b.x,d.ox+dx/box.width*100)),ny=Math.max(8-b.y,Math.min(92-b.y,d.oy+dy/box.height*100));setMoved(m=>({...m,[r.id]:{x:nx,y:ny}}))}} onPointerUp={e=>{const d=dragSeat.current;dragSeat.current=null;if(d&&!d.on&&!(e.target as HTMLElement).closest('button'))setSelSeat(v=>v===r.name?'':r.name)}} onPointerCancel={()=>{dragSeat.current=null}} className={`rm-seat top${selSeat===r.name?' sel':''}${dragSeat.current?.id===r.id&&dragSeat.current.on?' dragging':''}${speaking===r.id||(r.self&&speaking==='__me')?' speaking':''}`} style={{left:`${pt.x}%`,top:`${pt.y}%`,width:`${seatW*qs.w}%`,['--ta' as any]:(4/3*qs.w/qs.h).toFixed(4),['--rz' as any]:`${qs.rot}deg`,zIndex:pt.y>EDGE_Y?55:Math.max(1,Math.min(40,Math.round(pt.y))),['--ry' as any]:qs.rot?'0deg':`${(Math.max(-1,Math.min(1,(50-pt.x)/38))*40).toFixed(1)}deg`,['--rx' as any]:qs.rot?'0deg':`${(Math.max(-1,Math.min(1,(pt.y-50)/30))*12).toFixed(1)}deg`,['--sc' as any]:'0.96'}}>
        <VideoTile stream={r.self?selfStream:r.stream} name={r.name} muted={r.self} off={r.self?(!cam&&!screen):(!r.cam&&!r.screen)} self={r.self} host={r.host} cohost={r.cohost} screen={r.screen} speaking={speaking===(r.self?'__me':r.id)} plate hand={r.hand} onDouble={()=>togglePin(r.id)}/>
{selSeat===r.name&&<><span className="rm-hrot" title="Drag to turn this tile to any angle" onPointerDown={seatHandle(r.name,'turn')}/><span className="rm-hres" title="Drag to make this tile bigger or smaller" onPointerDown={seatHandle(r.name,'size')}/></>}
</div>})}
      {seatRows.map((r,i)=>{const b=seats[i],mv=moved[r.id]||{x:0,y:0},q=P(r.name),pt={x:b.x+mv.x,y:b.y+mv.y,py:b.py+mv.y};return <div key={'pl'+r.id} className={`rm-plate onTable${selPl===r.name?' sel':''}`} style={{left:`${pt.x+q.x}%`,top:`${pt.py+tune.pd+q.y}%`,maxWidth:`${seatW*q.s+8}%`,fontFamily:q.font||undefined,['--pf' as any]:tune.pf*q.f,['--ps' as any]:tune.ps*q.s}} title="Drag to move. Click for font and size." onPointerDown={e=>{e.stopPropagation();platDrag.current={n:r.name,sx:e.clientX,sy:e.clientY,ox:q.x,oy:q.y,on:false};try{e.currentTarget.setPointerCapture(e.pointerId)}catch{}}} onPointerMove={e=>{const d=platDrag.current,box=gridRef.current?.getBoundingClientRect();if(!d||d.n!==r.name||!box)return;const dx=e.clientX-d.sx,dy=e.clientY-d.sy;if(!d.on&&Math.hypot(dx,dy)<4)return;d.on=true;setP(r.name,{x:d.ox+dx/box.width*100,y:d.oy+dy/box.height*100})}} onPointerUp={()=>{const d=platDrag.current;platDrag.current=null;if(d&&!d.on)setSelPl(v=>v===r.name?'':r.name)}} onPointerCancel={()=>{platDrag.current=null}}><span className="rm-plname">{r.name}{r.self?' (you)':''}</span>{r.host&&<em>{r.cohost?'co-host':'host'}</em>}{r.screen&&<em>sharing</em>}<span className="rm-plstate">{(r.self?mic:r.mic)?null:<MicOff size={12} className="off" aria-label="Muted"/>}{(r.self?cam:r.cam)?null:<VideoOff size={12} className="off" aria-label="Camera off"/>}</span></div>})}
      {(()=>{const r=seatRows.find(x=>x.name===selSeat);if(!r)return null;const i=seatRows.indexOf(r),b=seats[i],mv=moved[r.id]||{x:0,y:0},q=SSg(r.name),a=q.rot*Math.PI/180,wV=seatW*q.w*9/16,hV=seatW*q.w*q.h*4/3,half=(Math.abs(Math.sin(a))*wV+Math.abs(Math.cos(a))*hV)/2;
        return <div className="rm-plbar rm-seatbar" style={{left:`${clampX(b.x+mv.x)}%`,top:`${Math.max(2,b.y+mv.y-half-1)}%`}} onPointerDown={e=>e.stopPropagation()}>
          <button type="button" title="Narrower" aria-label="Narrower" onClick={()=>setSS(r.name,{w:Math.max(.4,+(q.w-.1).toFixed(2))})}>W−</button><button type="button" title="Wider" aria-label="Wider" onClick={()=>setSS(r.name,{w:Math.min(2.4,+(q.w+.1).toFixed(2))})}>W+</button>
          <button type="button" title="Shorter" aria-label="Shorter" onClick={()=>setSS(r.name,{h:Math.max(.4,+(q.h-.1).toFixed(2))})}>H−</button><button type="button" title="Taller" aria-label="Taller" onClick={()=>setSS(r.name,{h:Math.min(2.4,+(q.h+.1).toFixed(2))})}>H+</button>
          <input type="range" min="-180" max="180" step="1" value={q.rot} aria-label="Angle" title={`Angle ${q.rot}°`} onChange={e=>setSS(r.name,{rot:+e.target.value})}/>
          <button type="button" title="Turn 90° left" aria-label="Turn 90 degrees left" onClick={()=>setSS(r.name,{rot:((q.rot-90+540)%360)-180})}>⟲90</button><button type="button" title="Turn 90° right" aria-label="Turn 90 degrees right" onClick={()=>setSS(r.name,{rot:((q.rot+90+540)%360)-180})}>90⟳</button><button type="button" title="Turn upside down" aria-label="Turn 180 degrees" onClick={()=>setSS(r.name,{rot:q.rot>=0?q.rot-180:q.rot+180})}>180°</button>
          <button type="button" onClick={()=>setSS(r.name,{w:1,h:1,rot:0})}>Reset</button><button type="button" aria-label="Close" onClick={()=>setSelSeat('')}>✕</button></div>})()}
      {(()=>{const r=seatRows.find(x=>x.name===selPl);if(!r)return null;const i=seatRows.indexOf(r),b=seats[i],mv=moved[r.id]||{x:0,y:0},q=P(r.name);return <div className="rm-plbar" style={{left:`${clampX(b.x+mv.x+q.x)}%`,top:`${b.py+mv.y+tune.pd+q.y}%`}} onPointerDown={e=>e.stopPropagation()}>
        <select aria-label="Name font" value={q.font} onChange={e=>setP(r.name,{font:e.target.value})}><option value="">Default font</option><option value="Georgia,serif">Serif</option><option value="'Brush Script MT','Segoe Script',cursive">Handwriting</option><option value="'Courier New',monospace">Typewriter</option><option value="'Trebuchet MS',sans-serif">Rounded</option></select>
        <button type="button" aria-label="Smaller letters" title="Smaller letters" onClick={()=>setP(r.name,{f:Math.max(.5,+(q.f-.1).toFixed(2))})}>A−</button>
        <button type="button" aria-label="Larger letters" title="Larger letters" onClick={()=>setP(r.name,{f:Math.min(2.2,+(q.f+.1).toFixed(2))})}>A+</button>
        <button type="button" aria-label="Smaller plate" title="Smaller plate" onClick={()=>setP(r.name,{s:Math.max(.5,+(q.s-.1).toFixed(2))})}>−</button>
        <button type="button" aria-label="Larger plate" title="Larger plate" onClick={()=>setP(r.name,{s:Math.min(2.2,+(q.s+.1).toFixed(2))})}>+</button>
        <button type="button" onClick={()=>setP(r.name,{x:0,y:0,s:1,f:1,font:''})}>Reset</button><button type="button" aria-label="Close" onClick={()=>setSelPl('')}>✕</button></div>})()}
      {tb&&<>
        <span className="rm-grip h" title="Drag to make the table wider or narrower" style={{left:tb.x1-9,top:(tb.y0+tb.y1)/2-9}} onPointerDown={e=>{e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);gripDrag.current={k:'h',s:e.clientX,v:tune.tw,w:tb.x1-tb.x0}}} onPointerMove={e=>{const g=gripDrag.current;if(!g||g.k!=='h')return;setTune({tw:Math.max(.4,Math.min(1.6,g.v*(g.w+2*(e.clientX-g.s))/g.w))})}} onPointerUp={()=>{gripDrag.current=null}}/>
        <span className="rm-grip v" title="Drag to make the table deeper or shallower" style={{left:(tb.x0+tb.x1)/2-9,top:tb.y1+4}} onPointerDown={e=>{e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);gripDrag.current={k:'v',s:e.clientY,v:tune.td,h:tb.y1-tb.y0}}} onPointerMove={e=>{const g=gripDrag.current;if(!g||g.k!=='v')return;setTune({td:Math.max(.4,Math.min(1.6,g.v*(g.h+(e.clientY-g.s))/g.h))})}} onPointerUp={()=>{gripDrag.current=null}}/></>}
      <button type="button" className="rm-tunebtn" onClick={()=>setTuneOpen(o=>!o)} aria-expanded={tuneOpen} title="Adjust table size and name plates"><SlidersHorizontal size={14}/> Adjust</button>
      {tuneOpen&&<div className="rm-tune" role="group" aria-label="Adjust the room">
        <label>Table width<input type="range" min="0.4" max="1.6" step="0.01" value={tune.tw} onChange={e=>setTune({tw:+e.target.value})}/></label>
        <label>Table depth<input type="range" min="0.4" max="1.6" step="0.01" value={tune.td} onChange={e=>setTune({td:+e.target.value})}/></label>
        <label>Name plate size<input type="range" min="0.5" max="1.8" step="0.01" value={tune.ps} onChange={e=>setTune({ps:+e.target.value})}/></label>
        <label>Name letters: smaller / larger<input type="range" min="0.5" max="1.8" step="0.01" value={tune.pf} onChange={e=>setTune({pf:+e.target.value})}/></label>
        <label>Name plate: closer / further<input type="range" min="-6" max="14" step="0.5" value={tune.pd} onChange={e=>setTune({pd:+e.target.value})}/></label>
        <button type="button" className="secondary" onClick={()=>setTune(TUNE0)}>Reset</button></div>}
      {Object.keys(moved).length>0&&<button type="button" className="rm-resetseats" onClick={()=>setMoved({})}>Reset seats</button>}
    </div></div>:<div ref={gridRef} className={`rm-grid n${Math.min(tiles,9)}${tiles>TABLE_MAX?' big':''}`}>
      {viewRows.map(r=>r.self?<VideoTile key="__me" stream={selfStream} name={r.name} muted off={!cam&&!screen} self host={isHost} cohost={cohost} screen={screen} speaking={speaking==='__me'} hand={myHand} onDouble={()=>togglePin('__me')}/>:<div key={r.id} className="rm-wrap">
        <VideoTile stream={r.stream} name={r.name} off={!r.cam&&!r.screen} host={r.host} cohost={r.cohost} screen={r.screen} speaking={speaking===r.id} hand={r.hand} onDouble={()=>togglePin(r.id)}/>
        {!r.mic&&<span className="rm-muted" title="Muted"><MicOff size={13}/></span>}
        {isHost&&canAct(r)&&<button className="rm-kick" title={`Remove ${r.name}`} onClick={()=>window.confirm(`Remove ${r.name} from the meeting?`)&&send({type:'kick',id:r.id})}><UserX size={14}/></button>}
      </div>)}
    </div>}
    {peopleOpen&&<aside className="rm-chat rm-people" aria-label="Participants" style={sideStyle('people')}><span className="rm-rsz-l" title="Drag to make this window wider or narrower" onPointerDown={sideDrag('people','w')}/><span className="rm-rsz-b" title="Drag to make this window taller or shorter" onPointerDown={sideDrag('people','h')}/><div className="rm-chathead"><b>Participants ({total})</b><button className="iconbtn" onClick={()=>setPeopleOpen(false)} aria-label="Hide participants" title="Hide participants"><X size={16}/></button></div>
      <ul className="rm-plist">{orderedAll.map(r=><li key={r.id}>
        <div className="rm-prow"><span className="rm-pname">{r.self&&editMe?<form className="rm-myname" onSubmit={e=>{e.preventDefault();const v=meDraft.trim();if(v)send({type:'rename',name:v});setEditMe(false)}}><input autoFocus value={meDraft} maxLength={60} aria-label="Your name" onChange={e=>setMeDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setEditMe(false)}}/><button type="submit" className="primary">Save</button></form>:<><b>{r.name}</b>{r.self?' (me)':''}</>}{r.hand&&<span title="Hand raised" aria-label="Hand raised"> ✋</span>}{r.host?<em className="rm-badge">{r.cohost?'Co-host':'Host'}</em>:null}</span>
          <span className="rm-pstate">
            {r.self&&!editMe&&<button type="button" className="rm-pbtn" aria-label="Change your name" title="Change your name" onClick={()=>{setMeDraft(name);setEditMe(true)}}><Pencil size={15}/></button>}
            <button type="button" className="rm-pbtn" disabled={r.self?!local.current.audio:!(isHost&&canAct(r))} onClick={()=>r.self?toggleMic():send(r.mic?{type:'force',id:r.id,mic:false}:{type:'ask',id:r.id,what:'mic'})} aria-label={r.self?(r.mic?'Mute your microphone':'Unmute your microphone'):(r.mic?`Mute ${r.name}`:`Ask ${r.name} to unmute`)} title={r.self?(r.mic?'Mute yourself':'Unmute yourself'):(isHost&&canAct(r)?(r.mic?'Mute':'Ask to unmute'):(r.mic?'Mic on':'Muted'))}>{r.mic?<Mic size={15}/>:<MicOff size={15} className="off"/>}</button>
            <button type="button" className="rm-pbtn" disabled={r.self?!local.current.cam:!(isHost&&canAct(r))} onClick={()=>r.self?toggleCam():send(r.cam?{type:'force',id:r.id,cam:false}:{type:'ask',id:r.id,what:'cam'})} aria-label={r.self?(r.cam?'Turn your camera off':'Turn your camera on'):(r.cam?`Stop ${r.name}'s video`:`Ask ${r.name} to start video`)} title={r.self?(r.cam?'Stop your video':'Start your video'):(isHost&&canAct(r)?(r.cam?'Stop video':'Ask to start video'):(r.cam?'Camera on':'Camera off'))}>{r.cam?<Video size={15}/>:<VideoOff size={15} className="off"/>}</button></span></div>
        {!r.self&&<div className="rm-pact"><button type="button" className="secondary" onClick={()=>{const k=[myId.current,r.id].sort().join(',');setExtraKeys(x=>x.includes(k)?x:[...x,k]);openThread(k);setPeopleOpen(false);setChatOpen(true)}}>Chat</button>{isHost&&canAct(r)&&<><button type="button" className="secondary" onClick={()=>send(r.mic?{type:'force',id:r.id,mic:false}:{type:'ask',id:r.id,what:'mic'})}>{r.mic?'Mute':'Ask to unmute'}</button><button type="button" className="secondary" onClick={()=>send(r.cam?{type:'force',id:r.id,cam:false}:{type:'ask',id:r.id,what:'cam'})}>{r.cam?'Stop video':'Ask to start video'}</button><button type="button" className="secondary" aria-expanded={menuFor===r.id} onClick={()=>setMenuFor(menuFor===r.id?'':r.id)}>More</button></>}</div>}
        {menuFor===r.id&&canAct(r)&&<div className="rm-pmenu" role="menu">
          {primary&&!r.cohost&&<button role="menuitem" onClick={()=>{send({type:'role',id:r.id,role:'cohost'});setMenuFor('')}}>Make co-host</button>}
          {primary&&r.cohost&&<button role="menuitem" onClick={()=>{send({type:'role',id:r.id,role:'participant'});setMenuFor('')}}>Remove co-host</button>}
          {primary&&<button role="menuitem" onClick={()=>{if(window.confirm(`Make ${r.name} the host? You will no longer be the host.`)){send({type:'role',id:r.id,role:'host'});setMenuFor('')}}}>Make host</button>}
          <button role="menuitem" className="danger" onClick={()=>{if(window.confirm(`Remove ${r.name} from the meeting?`)){send({type:'kick',id:r.id});setMenuFor('')}}}>Remove from meeting</button></div>}
      </li>)}</ul>
      {isHost&&<div className="rm-pfoot"><button type="button" className="secondary" onClick={()=>send({type:'mute_all'})}><MicOff size={14}/> Mute all</button>
        <label className="check"><input type="checkbox" checked={policy.audio} onChange={e=>{setPolicy(p=>({...p,audio:e.target.checked}));send(e.target.checked?{type:'policy',audio:true}:{type:'policy',audio:false,mute_now:true})}}/> Participants can unmute themselves</label>
        <label className="check"><input type="checkbox" checked={policy.video} onChange={e=>{setPolicy(p=>({...p,video:e.target.checked}));send({type:'policy',video:e.target.checked})}}/> Participants can start their video</label></div>}
    </aside>}
    <div className={`rm-wb${wbOpen?' open':''}`} role="dialog" aria-label="Whiteboard" aria-hidden={!wbOpen}>
      <div className="rm-wbbar"><span className="rm-wbtabs" role="tablist"><button type="button" role="tab" aria-selected={wbTab==='board'} className={wbTab==='board'?'on':''} onClick={()=>setWbTab('board')}>Whiteboard</button>{token&&<button type="button" role="tab" aria-selected={wbTab==='apps'} className={wbTab==='apps'?'on':''} onClick={()=>{setWbTab('apps');setAppsLoaded(true)}}>Notes, Docs, Phone…</button>}</span><span className="muted small rm-wbhint">The meeting keeps running behind this window.</span><span className="sp"/>{wbSaved&&<span className="small">{wbSaved}</span>}
        {wbTab==='board'&&<button type="button" className={`secondary${wbOn?' on':''}`} onClick={shareBoard}>{wbOn?'Stop sharing board':'Share board with everyone'}</button>}
        {wbTab==='board'&&token&&<button type="button" className="secondary" onClick={saveBoard}>Save</button>}
        {wbTab==='apps'&&<button type="button" className="secondary rm-newtab" title="Opens iSift in its own tab. To show it to everyone, press Share and pick that tab." onClick={()=>{window.open(`${location.origin}${location.pathname}#/workspace`,'_blank')}}>Open in a new tab</button>}
        <button type="button" className="primary" onClick={()=>setWbOpen(false)}>Back to meeting</button></div>
      <div className="rm-wbbody" ref={wbBox} style={{display:wbTab==='board'?undefined:'none'}}><Board content={wbContent.current} onChange={c=>{wbContent.current=c}} libOpen={false}/></div>
      {appsLoaded&&<iframe className="rm-wbapps" title="iSift workspace" src={`${location.origin}${location.pathname}#/workspace`} style={{display:wbTab==='apps'?'block':'none'}} allow="microphone; camera; clipboard-read; clipboard-write"/>}
    </div>
    {chatOpen&&<aside className="rm-chat" aria-label="Meeting chat" style={sideStyle('chat')}><span className="rm-rsz-l" title="Drag to make this window wider or narrower" onPointerDown={sideDrag('chat','w')}/><span className="rm-rsz-b" title="Drag to make this window taller or shorter" onPointerDown={sideDrag('chat','h')}/><div className="rm-chathead"><b>Chat</b><button className="iconbtn" onClick={()=>setChatOpen(false)} aria-label="Hide chat" title="Hide chat"><X size={16}/></button></div>
      <div className="rm-threads" role="tablist" aria-label="Conversations">{threadKeys.map(k=><button key={k} role="tab" aria-selected={chatKey===k} className={chatKey===k?'on':''} onClick={()=>openThread(k)} title={threadLabel(k)}>{k==='all'?'Everyone':threadLabel(k)}{!!unread[k]&&<i className="rm-dot">{unread[k]}</i>}</button>)}<button className="rm-newpriv" onClick={()=>{setPicking(p=>!p);setPickSel([])}} aria-label="Chat privately with someone" title="Chat privately with one person or a group"><Plus size={14}/></button></div>
      {picking&&<div className="rm-pick"><small>Choose one person, or several for a group:</small>{list.length?list.map(pe=><label key={pe.id}><input type="checkbox" checked={pickSel.includes(pe.id)} onChange={e=>setPickSel(x=>e.target.checked?[...x,pe.id]:x.filter(y=>y!==pe.id))}/> {pe.name}{pe.host?' (host)':''}</label>):<small className="muted">No one else has joined yet.</small>}<div><button className="primary" disabled={!pickSel.length} onClick={startPrivate}>Start chat</button> <button className="secondary" onClick={()=>setPicking(false)}>Cancel</button></div></div>}
      {chatKey!=='all'&&<p className="rm-private"><LockKeyhole size={12}/> Private: only {threadLabel(chatKey)} and you can see this.</p>}
      <div className="rm-msgs">{curChat.filter(c=>c.key===chatKey).map((c,i)=><div key={i} className={`rm-msg${c.me?' me':''}`}><b>{c.me?'You':c.name}</b><p>{c.text}</p></div>)}{!curChat.some(c=>c.key===chatKey)&&<p className="muted">No messages yet.</p>}</div>
      <form onSubmit={sendChat}><label className="rm-to"><span>To:</span><select value={chatKey} onChange={e=>{const v=e.target.value;if(v==='all'||v.includes(','))openThread(v);else{const k=[myId.current,v].sort().join(',');setExtraKeys(x=>x.includes(k)?x:[...x,k]);openThread(k)}}} aria-label="Send to"><option value="all">Everyone</option>{chatKey!=='all'&&!list.some(pe=>[myId.current,pe.id].sort().join(',')===chatKey)&&<option value={chatKey}>{threadLabel(chatKey)}</option>}{list.map(pe=><option key={pe.id} value={[myId.current,pe.id].sort().join(',')}>{pe.name}{pe.host?(pe.cohost?' (co-host)':' (host)'):''}</option>)}</select></label><input value={chatText} onChange={e=>setChatText(e.target.value)} placeholder={chatKey==='all'?'Message everyone':`Message ${threadLabel(chatKey)}`} maxLength={2000}/><button className="primary" aria-label="Send"><Send size={15}/></button></form></aside>}
    </div>
    {barOn&&<footer className="rm-bar">
      <button className={`rm-btn${!mic?' off':''}`} onClick={toggleMic} disabled={!local.current.audio} aria-label={mic?'Mute microphone':'Unmute microphone'}>{mic?<Mic size={18}/>:<MicOff size={18}/>}<span>{mic?'Mute':'Unmute'}</span></button>
      <button className={`rm-btn${!cam?' off':''}`} onClick={toggleCam} disabled={!local.current.cam} aria-label={cam?'Turn camera off':'Turn camera on'}>{cam?<Video size={18}/>:<VideoOff size={18}/>}<span>{cam?'Camera':'Camera off'}</span></button>
      <button className={`rm-btn${screen?' on':''}`} onClick={toggleScreen} aria-label="Share screen" title={(navigator.mediaDevices as any)?.getDisplayMedia?'Share your screen':'Share a photo or PDF from this phone'}><MonitorUp size={18}/><span>{screen?'Stop sharing':'Share'}</span></button><input ref={filePick} type="file" accept="image/*,application/pdf" hidden onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)startFileShare(f)}}/>{filePg&&<span className="rm-pgbar"><button type="button" aria-label="Previous page" disabled={filePg.n<=1} onClick={()=>filePage(-1)}>‹</button><b>{filePg.n} / {filePg.of}</b><button type="button" aria-label="Next page" disabled={filePg.n>=filePg.of} onClick={()=>filePage(1)}>›</button></span>}
      <button className={`rm-btn${peopleOpen?' on':''}`} onClick={togglePeople} aria-label="Participants"><Users size={18}/><span>People ({total})</span></button>
      <button className={`rm-btn${chatOpen?' on':''}`} onClick={()=>{setChatOpen(o=>!o);setPeopleOpen(false);if(!chatOpen)setUnread(u=>({...u,[chatKey]:0}))}} aria-label="Chat"><MessageSquare size={18}/><span>Chat</span>{Object.values(unread).reduce((a,b)=>a+b,0)>0&&<i className="rm-dot">{Object.values(unread).reduce((a,b)=>a+b,0)}</i>}</button>
      <button className={`rm-btn${reactOpen?' on':''}${myHand?' hand':''}`} onClick={()=>{setReactOpen(o=>!o);setMoreOpen(false);setHostOpen(false)}} aria-label="Reactions" aria-expanded={reactOpen}>{myHand?<Hand size={18}/>:<Smile size={18}/>}<span>{myHand?'Hand up':'React'}</span></button>
      {onBar.map(t=><ToolButton key={t.id} tool={t} pinned={pins.includes(t.id)} onPin={()=>pinTool(t.id)} onHide={()=>hideTool(t.id)}/>)}
      {isHost&&<button className={`rm-btn${hostOpen||locked?' on':''}`} onClick={()=>{loadHostInfo();setHostOpen(o=>!o);setMoreOpen(false);setReactOpen(false)}} aria-label="Host tools" aria-expanded={hostOpen}><ShieldCheck size={18}/><span>{locked?'Locked':'Host tools'}</span></button>}
      <button className={`rm-btn${moreOpen?' on':''}`} onClick={()=>{setMoreOpen(o=>!o);setReactOpen(false);setHostOpen(false)}} aria-label="More tools" aria-expanded={moreOpen}><Ellipsis size={18}/><span>More</span></button>
      <button className="rm-btn leave" onClick={()=>primary?setLeaveOpen(o=>!o):leave()} aria-label="Leave meeting" aria-expanded={primary?leaveOpen:undefined}><PhoneOff size={18}/><span>Leave</span></button>
    </footer>}
    {screen&&penAsks.length>0&&<div className="rm-penask" role="status">{penAsks.map(a=><div key={a.id}><span><b>{a.name}</b> asks for the pen</span><button type="button" className="primary" onClick={()=>{send({type:'pen_give',to:a.id});setPenAsks(x=>x.filter(y=>y.id!==a.id))}}>Give pen</button><button type="button" onClick={()=>setPenAsks(x=>x.filter(y=>y.id!==a.id))}>Not now</button></div>)}</div>}
    {watchOpen&&<WatchTogether state={watch} canControl={!watch||watch.by_id===myId.current||isHost||cohost} myName={name} onLoad={vid=>send({type:'video',op:'load',vid})} onWeb={url=>send({type:'video',op:'web',url})} onOp={(op,t)=>{send({type:'video',op,t});if(op==='stop'){setWatch(null);setWatchOpen(false)}else setWatch(w=>w?{...w,playing:op==='play'?true:op==='pause'?false:w.playing,t,at:Date.now()}:w)}} onClose={()=>setWatchOpen(false)}/>}
    {capsView&&<CaptionsBar lines={capLines} history={capHist} supported={!!SR} onClose={toggleCaps}/>}
    <FloatingReactions items={floats}/>
    {moreOpen&&<MoreMenu tools={tools} pins={pins} onPick={pickTool} onPin={pinTool} onClose={()=>setMoreOpen(false)}/>}
    {reactOpen&&<ReactMenu onReact={e=>{sendReact(e);setReactOpen(false)}} handUp={myHand} onHand={toggleHand} onClose={()=>setReactOpen(false)}/>}
    {hostOpen&&<HostMenu multi={multiShare} onMulti={v=>send({type:'multishare',on:v})} locked={locked} onLock={v=>send({type:'lock',on:v})} waiting={primary&&hostInfo?!!hostInfo.waiting_room:null} onWaiting={primary?(v=>changeSecurity({waiting_room:v})):undefined} hidePics={hidePics} onHidePics={v=>send({type:'hidepics',on:v})} policy={policy} onPolicy={(k,v)=>send({type:'policy',[k]:v})} onMuteAll={()=>send({type:'mute_all'})} onAdvanced={()=>setMoreOpen(true)} onSecurity={primary?()=>{loadHostInfo();setSecOpen(true)}:undefined} onClose={()=>setHostOpen(false)}/>}
    {leaveOpen&&<><div className="rm-pop-shade" onClick={()=>setLeaveOpen(false)}/><div className="rm-pop rm-leavemenu" role="dialog" aria-label="Leave or end"><button type="button" className="secondary" onClick={()=>{setLeaveOpen(false);leave()}}><PhoneOff size={15}/> Leave meeting</button><button type="button" className="end-btn" onClick={()=>{setLeaveOpen(false);endAll()}}><X size={15}/> End meeting for everyone</button></div></>}
    {bgOpen&&bgPanel}
    {scenePick&&<ScenePicker title={scenePick==='win'?'View outside the window':'Picture on the wall'} value={scenes[scenePick]} w={scenePick==='win'?100:135} h={scenePick==='win'?148:100} onClose={()=>setScenePick('')} onApply={id=>{setScenes({[scenePick]:id});setScenePick('')}}/>}
    <div className="rm-viewctl"><button onClick={goFs} aria-label={fs?"Exit full screen":"Full screen"} title={fs?"Exit full screen":"Full screen"}>{fs?<Minimize size={16}/>:<Maximize size={16}/>}</button><button onClick={()=>setBarOn(v=>!v)} aria-label={barOn?"Hide buttons":"Show buttons"} title={barOn?"Hide buttons":"Show buttons"}>{barOn?<ChevronDown size={16}/>:<ChevronUp size={16}/>}</button></div>
  </div>;
}
