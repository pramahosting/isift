import React,{useEffect,useState} from 'react';
import {Video,Plus,CalendarPlus,CalendarDays,Phone,FileText,Table2,Presentation,PenLine,FileSignature,Play,Send,RefreshCw,Download,Share2,X,Settings as Gear,Sun,MoreHorizontal,Lock,Headphones,Mic,Accessibility,UserCircle,LifeBuoy,Circle,Users,LogOut,ChevronRight,Pin,Check} from 'lucide-react';
import {getPrefs,setPref} from './prefs';
import {help} from './notify';
import {JoinDialog} from './Connections';

// Like the Zoom home screen: big, clear buttons for the things people do most, and the day beside them.
let deferred:any=null;
if(typeof window!=='undefined')window.addEventListener('beforeinstallprompt',(e:any)=>{e.preventDefault();deferred=e;window.dispatchEvent(new Event('isift:installable'))});
const standalone=()=>{try{return window.matchMedia('(display-mode: standalone)').matches||(navigator as any).standalone===true}catch{return false}};
const isIOS=()=>/iphone|ipad|ipod/i.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);

export function InstallBanner({text}:{text?:string}){
  const [hide,setHide]=useState(()=>{try{return sessionStorage.getItem('isift.nobanner')==='1'}catch{return false}});const [help_,setHelp]=useState(false);const [can,setCan]=useState(!!deferred);
  useEffect(()=>{const f=()=>setCan(true);window.addEventListener('isift:installable',f);return()=>window.removeEventListener('isift:installable',f)},[]);
  const [have,setHave]=useState(false);
  useEffect(()=>{try{(navigator as any).getInstalledRelatedApps?.().then((l:any[])=>{if(l&&l.length)setHave(true)}).catch(()=>{})}catch{}},[]);
  if(standalone()||hide)return null;
  if(have){const m=location.hash.match(/^#\/room\/([A-Za-z0-9]+)/);return <div className="inst-banner" role="note"><span className="inst-ic"><Download size={18}/></span><span className="inst-tx"><b>iSift is installed on this device</b><small>Open this meeting in the app for the best experience.</small></span>{m&&<a className="primary" style={{textDecoration:'none',display:'inline-grid',placeItems:'center'}} href={`web+isift://room/${m[1]}`}>Open in iSift app</a>}<button type="button" className="inst-x" aria-label="Hide this message" onClick={()=>{setHide(true);try{sessionStorage.setItem('isift.nobanner','1')}catch{}}}><X size={14}/></button></div>}
  const go=async()=>{if(deferred){try{deferred.prompt();await deferred.userChoice}catch{}deferred=null;setCan(false)}else setHelp(true)};
  return <div className="inst-banner" role="note"><span className="inst-ic"><Download size={18}/></span><span className="inst-tx"><b>Use iSift as an app</b><small>{text||'Opens faster, remembers you, and meeting links open right in the app.'}</small></span><button type="button" className="primary" onClick={go}>{can?'Install':'How to install'}</button><button type="button" className="inst-x" aria-label="Hide this message" onClick={()=>{setHide(true);try{sessionStorage.setItem('isift.nobanner','1')}catch{}}}><X size={14}/></button>{help_&&<InstallHelp onClose={()=>setHelp(false)}/>}</div>;
}
export function InstallHelp({onClose}:{onClose:()=>void}){
  const ios=isIOS(),mac=/Mac/i.test(navigator.platform)&&!ios,and=/android/i.test(navigator.userAgent);
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="login-dialog ws-help" role="dialog" aria-modal="true" aria-label="Install iSift">
    <button className="iconbtn drawer-close" style={{display:'grid'}} onClick={onClose} aria-label="Close"><X size={18}/></button>
    <h2>Put iSift on your {ios||and?'home screen':'taskbar'}</h2>
    {ios?<ol><li>Open this page in <b>Safari</b> (or tap the share icon in your browser).</li><li>Tap <b>Share</b> <Share2 size={14}/>, then <b>Add to Home Screen</b>.</li><li>Tap <b>Add</b>. The iSift icon appears with your apps.</li></ol>
    :and?<ol><li>Tap the browser menu (three dots).</li><li>Tap <b>Install app</b> or <b>Add to Home screen</b>.</li><li>Tap <b>Install</b>. The iSift icon appears with your apps.</li></ol>
    :mac?<ol><li>In Safari choose <b>File, Add to Dock</b>. In Chrome or Edge click the install icon at the right of the address bar.</li><li>iSift opens in its own window and its icon stays in your Dock.</li></ol>
    :<ol><li>In Chrome or Edge click the install icon at the right of the address bar (or menu, <b>Install iSift</b>).</li><li>iSift opens in its own window.</li><li>Right-click its icon on the taskbar and choose <b>Pin to taskbar</b>.</li></ol>}
  </section></div>;
}

const SECTIONS:[string,string,any][]=[['general','General',Gear],['video','Video',Video],['audio','Audio',Mic],['meetings','Meetings',Users],['recording','Recording',Circle],['access','Accessibility',Accessibility],['account','My account',UserCircle],['help','Help',LifeBuoy]];
function Switch({on,onChange,label,hint}:{on:boolean;onChange:(v:boolean)=>void;label:string;hint?:string}){
  return <label className="st-row"><span><b>{label}</b>{hint&&<small>{hint}</small>}</span><input type="checkbox" role="switch" checked={on} onChange={e=>onChange(e.target.checked)}/><i aria-hidden="true"/></label>;
}
export function SettingsDialog({onClose,plan,onTest,go,onSignOut,userName}:{onClose:()=>void;plan:string;onTest:()=>void;go:(p:string)=>void;onSignOut:()=>void;userName?:string}){
  const [sec,setSec]=useState('general');const [p,setP]=useState(getPrefs());const [saved,setSaved]=useState('');
  const set=(k:any,v:boolean)=>{setP(setPref(k,v));setSaved('Saved on this device');setTimeout(()=>setSaved(''),1800)};
  const myName=(()=>{try{return localStorage.getItem('isift.name')||''}catch{return ''}})();const [nm,setNm]=useState(myName);
  const cloud=plan&&plan!=='basic';
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="st-dialog" role="dialog" aria-modal="true" aria-label="Settings">
    <nav className="st-nav" aria-label="Settings sections"><h2>Settings</h2>{SECTIONS.map(([k,l,I])=><button key={k} type="button" className={sec===k?'on':''} onClick={()=>setSec(k)}><I size={18}/><span>{l}</span></button>)}</nav>
    <div className="st-body"><button type="button" className="st-x" onClick={onClose} aria-label="Close settings"><X size={18}/></button>
      {sec==='general'&&<><h3>General</h3>
        <div className="st-card"><div className="st-row"><span><b>Your name in meetings</b><small>{nm?`iSift fills in “${nm}” when you join a meeting link.`:'iSift remembers the name you type the first time you join.'}</small></span>{nm&&<button type="button" className="secondary" onClick={()=>{try{localStorage.removeItem('isift.name')}catch{};setNm('');setSaved('Name forgotten on this device');setTimeout(()=>setSaved(''),1800)}}>Forget it</button>}</div></div>
        <div className="st-card"><div className="st-row"><span><b>Install iSift</b><small>Pin iSift to your taskbar or home screen so it opens like an app.</small></span><button type="button" className="secondary" onClick={()=>{onClose();window.dispatchEvent(new Event('isift:install'))}}>How to install</button></div></div></>}
      {sec==='video'&&<><h3>Video</h3><div className="st-card"><Switch on={p.camOffOnJoin} onChange={v=>set('camOffOnJoin',v)} label="Turn my camera off when I join" hint="You can switch it on any time inside the meeting."/><div className="st-row"><span><b>Check my camera</b><small>See yourself and test the picture before a meeting.</small></span><button type="button" className="secondary" onClick={()=>{onClose();onTest()}}>Test video</button></div></div></>}
      {sec==='audio'&&<><h3>Audio</h3><div className="st-card"><Switch on={p.muteOnJoin} onChange={v=>set('muteOnJoin',v)} label="Mute my microphone when I join" hint="Recommended for large meetings."/><div className="st-row"><span><b>Check my microphone and speaker</b><small>Speak and listen to make sure others can hear you. Headphones prevent echo.</small></span><button type="button" className="secondary" onClick={()=>{onClose();onTest()}}>Test audio</button></div></div></>}
      {sec==='meetings'&&<><h3>Meetings</h3><div className="st-card"><Switch on={p.confirmLeave} onChange={v=>set('confirmLeave',v)} label="Ask me before I leave a meeting" hint="Stops you leaving by a stray tap."/></div></>}
      {sec==='recording'&&<><h3>Recording</h3><div className="st-card"><div className="st-note"><b>{cloud?'Your plan stores recordings in the cloud.':'Your plan saves recordings on your own computer.'}</b><p>{cloud?'When the meeting ends, the recording is stored in the cloud and a download link is emailed to you. Find it any time under Recordings.':'You can record any meeting you host. When the meeting ends you get a Save button to keep the file on this computer. Paid plans store recordings in the cloud and email you a download link.'}</p></div><div className="st-row"><span><b>See my recordings</b></span><button type="button" className="secondary" onClick={()=>{onClose();go('Recordings')}}>Open Recordings</button></div>{!cloud&&<div className="st-row"><span><b>Want cloud recordings?</b></span><button type="button" className="primary" onClick={()=>{onClose();location.hash='#/pricing'}}>See plans</button></div>}</div></>}
      {sec==='access'&&<><h3>Accessibility</h3><div className="st-card"><Switch on={p.bigText} onChange={v=>set('bigText',v)} label="Larger text" hint="Makes text bigger across iSift."/><Switch on={p.reduceMotion} onChange={v=>set('reduceMotion',v)} label="Reduce motion" hint="Turns off animations and movement."/></div></>}
      {sec==='account'&&<><h3>My account</h3><div className="st-card"><div className="st-row"><span><b>{userName||'Your profile'}</b><small>Name, password, time zone and company details.</small></span><button type="button" className="secondary" onClick={()=>{onClose();go('My account')}}>Open</button></div><div className="st-row"><span><b>Plan and billing</b><small>Your plan, people limit, card and payments.</small></span><button type="button" className="secondary" onClick={()=>{onClose();go('Plan and billing')}}>Open</button></div><div className="st-row"><span><b>Sign out</b></span><button type="button" className="secondary" onClick={()=>{onClose();onSignOut()}}><LogOut size={15}/> Sign out</button></div></div></>}
      {sec==='help'&&<><h3>Help</h3><div className="st-card"><div className="st-note"><b>Quick answers</b><ul><li><b>Start a meeting:</b> press New meeting, then copy the link and send it.</li><li><b>Join:</b> press Join and paste a link or meeting ID. Your name is remembered.</li><li><b>No camera or microphone?</b> Allow access in the browser address bar (the padlock or camera icon), then press Test video.</li><li><b>Can’t hear someone?</b> Tap “Tap to hear” on their video, and use headphones to avoid echo.</li><li><b>Share your screen:</b> only laptops and desktops can share their screen. Phones can share a document or picture.</li><li><b>Something not working?</b> A message appears on screen telling you what to do. If it keeps failing, reload the page.</li></ul></div></div></>}
      <div className="st-saved" aria-live="polite">{saved}</div>
    </div></section></div>;
}

export function HomeWorkspace({name,request,modOn,go,onHost,onSchedule,onShareLink,onSync,today,plan,onTest,onSignOut}:{name?:string;request:any;modOn:(m:string)=>boolean;go:(p:string)=>void;onHost:()=>void;onSchedule:()=>void;onShareLink:()=>void;onSync:()=>void;today:any;plan:string;onTest:()=>void;onSignOut:()=>void}){
  const [joinOpen,setJoinOpen]=useState(false);const [now,setNow]=useState(new Date());const [help_,setHelp]=useState(false);const [more,setMore]=useState(false);const [setOpen,setSetOpen]=useState(false);const [canInstall,setCan]=useState(!!deferred);
  useEffect(()=>{const t=setInterval(()=>setNow(new Date()),20000);const f=()=>setCan(true);const j=()=>setJoinOpen(true);const i=()=>setHelp(true);const so=()=>setSetOpen(true);
    window.addEventListener('isift:installable',f);window.addEventListener('isift:join',j);window.addEventListener('isift:install',i);window.addEventListener('isift:settings',so);
    return()=>{clearInterval(t);window.removeEventListener('isift:installable',f);window.removeEventListener('isift:join',j);window.removeEventListener('isift:install',i);window.removeEventListener('isift:settings',so)}},[]);
  const tz=today?.timezone||undefined;
  const fmt=(o:Intl.DateTimeFormatOptions)=>{try{return now.toLocaleString(undefined,{...o,timeZone:tz})}catch{return now.toLocaleString(undefined,o)}};
  const timeOf=(v:string)=>{try{return new Date(v).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit',timeZone:tz})}catch{return ''}};
  const install=async()=>{if(deferred){try{deferred.prompt();await deferred.userChoice}catch{}deferred=null;setCan(false)}else setHelp(true)};
  type It={k:string;label:string;note:string;icon:any;c:string;run:()=>void;mod?:string};
  const off=(i:It)=>!!i.mod&&!modOn(i.mod);
  const tap=(i:It)=>{if(off(i)){help(`${i.label} is not switched on for your account. Ask your administrator to turn it on, or see the plans to upgrade.`,`${i.label} is not available`);return}i.run()};
  const ALL:{group:string;items:It[]}[]=[
    {group:'Meetings',items:[
      {k:'host',label:'Start a meeting',note:'Open your room now',icon:Video,c:'ember',run:onHost,mod:'meetings'},
      {k:'join',label:'Join a meeting',note:'Paste a link or ID',icon:Plus,c:'cobalt',run:()=>setJoinOpen(true),mod:'meetings'},
      {k:'sched',label:'Schedule',note:'Pick a date and time',icon:CalendarPlus,c:'cobalt',run:onSchedule,mod:'meetings'},
      {k:'book',label:'Booking page',note:'Let people book you',icon:CalendarDays,c:'cobalt',run:()=>go('Booking'),mod:'scheduling'},
      {k:'call',label:'Call',note:'Ring an iSift user',icon:Phone,c:'cobalt',run:()=>window.dispatchEvent(new Event('isift:call'))},
      {k:'rec',label:'Recordings',note:'Your recorded meetings',icon:Play,c:'cobalt',run:()=>go('Recordings'),mod:'meetings'},
      {k:'share',label:'Share booking link',note:'Email it to someone',icon:Send,c:'cobalt',run:onShareLink,mod:'scheduling'},
      {k:'sync',label:'Sync calendar',note:'Pull in today’s events',icon:RefreshCw,c:'cobalt',run:onSync,mod:'calendar'}]},
    {group:'Documents',items:[
      {k:'notes',label:'Notes',note:'Write and share',icon:FileText,c:'teal',run:()=>go('Notes'),mod:'docs'},
      {k:'pdf',label:'PDFs and signing',note:'Edit, sign, send',icon:FileSignature,c:'teal',run:()=>go('Sign & Edit PDF'),mod:'docs'},
      {k:'wp',label:'WordPerfect',note:'Documents',icon:FileText,c:'teal',run:()=>go('WordPerfect'),mod:'docs'},
      {k:'sheet',label:'SpreadTable',note:'Spreadsheets',icon:Table2,c:'teal',run:()=>go('SpreadTable'),mod:'docs'},
      {k:'deck',label:'PowerPresentation',note:'Slides',icon:Presentation,c:'teal',run:()=>go('PowerPresentation'),mod:'docs'},
      {k:'board',label:'Whiteboard',note:'Sketch ideas',icon:PenLine,c:'teal',run:()=>go('Whiteboard'),mod:'whiteboard'}]},
    {group:'This device',items:[
      ...(standalone()?[]:[{k:'inst',label:'Install iSift app',note:'Pin to taskbar or home screen',icon:Download,c:'plain',run:install} as It]),
      {k:'test',label:'Test audio and video',note:'Check camera and microphone',icon:Headphones,c:'plain',run:onTest}]},
  ];
  const flat=ALL.flatMap(g=>g.items);
  const [pins,setPins]=useState<string[]>(()=>{try{const v=JSON.parse(localStorage.getItem('isift.pins')||'null');if(Array.isArray(v))return v}catch{}return ['host','join','sched','book']});
  const savePins=(p:string[])=>{setPins(p);try{localStorage.setItem('isift.pins',JSON.stringify(p))}catch{}};
  const pinned=pins.map(k=>flat.find(i=>i.k===k)).filter(Boolean) as It[];
  const choose=(i:It)=>{if(!pins.includes(i.k))savePins([...pins,i.k]);setMore(false);setAdded(i.label)};
  const [added,setAdded]=useState('');useEffect(()=>{if(!added)return;const t=setTimeout(()=>setAdded(''),3500);return()=>clearTimeout(t)},[added]);
  const meetings=(today?.meetings||[]).slice(0,4);
  const Btn=({i}:{i:It})=><div className="ws-cardwrap"><button type="button" className={`ws-btn${off(i)?' locked':''}`} onClick={()=>tap(i)}><span className={`ws-ic ${i.c}`}><i.icon size={32}/>{off(i)&&<em className="ws-lock"><Lock size={12}/></em>}</span><span className="ws-lb">{i.label}</span><span className="ws-nt">{i.note}</span></button><button type="button" className="ws-unpin" onClick={()=>savePins(pins.filter(k=>k!==i.k))} aria-label={`Remove ${i.label} from the workspace`} title="Remove from workspace"><X size={14}/></button></div>;
  return <section className="ws" aria-label="iSift workspace">
    <div className="ws-main">
      <div className="ws-grid" role="group" aria-label="Your tools">{pinned.map(i=><Btn key={i.k} i={i}/>)}
        <button type="button" className="ws-btn ws-more-btn" onClick={()=>setMore(true)}><span className="ws-ic more"><MoreHorizontal size={32}/></span><span className="ws-lb">More tools</span><span className="ws-nt">{pinned.length?'Add tools to this page':'Choose the tools you want here'}</span></button></div>
      {added&&<p className="ws-added" role="status">{added} added to your workspace. Remove it any time with the × on its card.</p>}
    </div>
    {more&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setMore(false)}}><section className="ws-pop" role="dialog" aria-modal="true" aria-label="More tools"><button type="button" className="st-x" onClick={()=>setMore(false)} aria-label="Close"><X size={18}/></button><h3>Add tools to your workspace</h3><p className="ws-popnote">Choose a tool to put it on your workspace page. Remove it again with the × on its card.</p>{ALL.map(g=>g.items.length>0&&<div key={g.group}><h4>{g.group}</h4><div className="ws-list">{g.items.map(i=>{const on=pins.includes(i.k);return <div key={i.k} className="ws-row"><button type="button" className="ws-rowmain" onClick={()=>on?savePins(pins.filter(k=>k!==i.k)):choose(i)}><span className={`ws-ic sm ${i.c}`}><i.icon size={20}/></span><span><b>{i.label}</b><small>{i.note}</small></span></button>{on?<button type="button" className="ws-pinned" onClick={()=>savePins(pins.filter(k=>k!==i.k))}><Check size={14}/> On workspace · Remove</button>:<button type="button" className="ws-add" onClick={()=>choose(i)}><Pin size={14}/> Add</button>}</div>})}</div></div>)}</section></div>}
    <aside className="ws-side" aria-label="Today">
      <div className="ws-clock"><button type="button" className="ws-gear" onClick={()=>setSetOpen(true)} aria-label="Settings" title="Settings"><Gear size={20}/></button><em className="ws-sunmark"><Sun size={22}/></em><b>{fmt({hour:'numeric',minute:'2-digit'})}</b><span>{fmt({weekday:'long',month:'long',day:'numeric'})}</span></div>
      <div className="ws-day"><h3>Coming up</h3>{meetings.length?meetings.map((m:any)=><button type="button" key={m.id} className="ws-ev" onClick={()=>go('Meetings')}><b>{m.title}</b><small>{timeOf(m.start_at)}</small></button>):<p>Nothing planned today. Choose <b>Start a meeting</b> to begin one, or <b>Plan for later</b>.</p>}</div>
          </aside>
    {joinOpen&&<JoinDialog request={request} name={name} onClose={()=>setJoinOpen(false)}/>}
    {help_&&<InstallHelp onClose={()=>setHelp(false)}/>}
    {setOpen&&<SettingsDialog onClose={()=>setSetOpen(false)} plan={plan} onTest={onTest} go={go} onSignOut={onSignOut} userName={name}/>}
  </section>;
}
