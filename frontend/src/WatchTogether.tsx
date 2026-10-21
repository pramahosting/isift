// Watch a YouTube video together: one person pastes a link; everyone's own player follows play, pause and skip.
// The sound and picture come straight from YouTube on each device, so it works the same on phones and computers.
import {useEffect,useRef,useState} from 'react';
import {X,Play,RefreshCw,Square} from 'lucide-react';

export type WatchState={vid:string;by:string;by_id:string;playing:boolean;t:number;at:number}; // at = when this device received t
export const youtubeId=(s:string):string=>{
  const v=(s||'').trim();if(/^[A-Za-z0-9_-]{11}$/.test(v))return v;
  try{const u=new URL(/^https?:\/\//i.test(v)?v:'https://'+v);const h=u.hostname.replace(/^www\.|^m\./,'');
    let id='';if(h==='youtu.be')id=u.pathname.slice(1).split('/')[0];
    else if(h.endsWith('youtube.com')||h.endsWith('youtube-nocookie.com')){id=u.searchParams.get('v')||'';if(!id){const m=u.pathname.match(/^\/(?:shorts|embed|live|v)\/([^/?]+)/);if(m)id=m[1]}}
    return /^[A-Za-z0-9_-]{11}$/.test(id)?id:'';
  }catch{return ''}
};

let apiP:Promise<any>|null=null;
function loadApi():Promise<any>{
  const w=window as any;if(w.YT&&w.YT.Player)return Promise.resolve(w.YT);
  if(!apiP)apiP=new Promise((res,rej)=>{const prev=w.onYouTubeIframeAPIReady;w.onYouTubeIframeAPIReady=()=>{try{prev&&prev()}catch{}res(w.YT)};const s=document.createElement('script');s.src='https://www.youtube.com/iframe_api';s.onerror=()=>{apiP=null;rej(new Error('blocked'))};document.head.appendChild(s)});
  return apiP;
}

export function WatchTogether({state,canControl,myName,onLoad,onOp,onClose}:{state:WatchState|null;canControl:boolean;myName:string;onLoad:(vid:string)=>void;onOp:(op:'play'|'pause'|'seek'|'stop',t:number)=>void;onClose:()=>void}){
  const [link,setLink]=useState('');const [err,setErr]=useState('');const [blocked,setBlocked]=useState(false);
  const host=useRef<HTMLDivElement>(null);const pl=useRef<any>(null);const ready=useRef(false);const quiet=useRef(0);const last=useRef(0);
  const st=useRef(state);st.current=state;const ctl=useRef(canControl);ctl.current=canControl;const ops=useRef(onOp);ops.current=onOp;
  const want=()=>{const s=st.current;if(!s)return 0;return s.t+(s.playing?(Date.now()-s.at)/1000:0)};
  const apply=()=>{const p=pl.current,s=st.current;if(!p||!ready.current||!s)return;
    quiet.current=Date.now()+1500;
    try{const cur=p.getVideoData?.().video_id;
      if(cur!==s.vid){s.playing?p.loadVideoById({videoId:s.vid,startSeconds:want()}):p.cueVideoById({videoId:s.vid,startSeconds:want()});return}
      const t=want();if(Math.abs((p.getCurrentTime?.()||0)-t)>1.5)p.seekTo(t,true);
      const ps=p.getPlayerState?.();if(s.playing&&ps!==1)p.playVideo();if(!s.playing&&ps===1)p.pauseVideo();
    }catch{}};
  // build the player once, when there is a video to show
  useEffect(()=>{
    if(!state||pl.current)return;let dead=false;
    loadApi().then(YT=>{if(dead||!host.current)return;const d=document.createElement('div');host.current.innerHTML='';host.current.appendChild(d);
      pl.current=new YT.Player(d,{width:'100%',height:'100%',videoId:st.current?.vid,playerVars:{playsinline:1,rel:0,modestbranding:1,controls:ctl.current?1:1,origin:location.origin},events:{
        onReady:()=>{ready.current=true;apply()},
        onAutoplayBlocked:()=>setBlocked(true),
        onStateChange:(e:any)=>{
          if(Date.now()<quiet.current||!ctl.current)return;const t=pl.current?.getCurrentTime?.()||0;
          if(e.data===1){setBlocked(false);ops.current('play',t)}else if(e.data===2)ops.current('pause',t);
        }}});
    }).catch(()=>setErr('YouTube could not be loaded on this device. Open the link in another tab instead.'));
    return()=>{dead=true};
  },[!!state]);
  // everyone follows the shared state
  useEffect(()=>{apply()},[state?.vid,state?.playing,state?.t,state?.at]);
  // the person in control: notice skips (a jump in time) and tell everyone
  useEffect(()=>{if(!state||!canControl)return;const id=setInterval(()=>{const p=pl.current;if(!p||!ready.current||Date.now()<quiet.current)return;
    try{const t=p.getCurrentTime?.()||0,ps=p.getPlayerState?.();const exp=last.current+(ps===1?1:0);if(last.current&&Math.abs(t-exp)>2)ops.current('seek',t);last.current=t}catch{}},1000);return()=>clearInterval(id)},[!!state,canControl]);
  // a tidy stop: the player goes away when the video ends for everyone
  useEffect(()=>{if(!state){try{pl.current?.destroy?.()}catch{}pl.current=null;ready.current=false;setBlocked(false)}},[state]);
  useEffect(()=>()=>{try{pl.current?.destroy?.()}catch{}pl.current=null},[]);

  const start=()=>{const id=youtubeId(link);if(!id){setErr('That does not look like a YouTube link. Paste the address from the YouTube share button.');return}setErr('');onLoad(id);setLink('')};
  return <div className="rm-watch" role="dialog" aria-label="Watch a video together">
    <div className="rm-watch-bar"><b>{state?`${state.by===myName?'You are':state.by+' is'} playing a video`:'Share a video link'}</b>
      <span className="muted small">{state?(canControl?'Play, pause and skip here. Everyone follows.':'You will follow along.'):'Everyone in the meeting watches it together.'}</span>
      <span className="rm-watch-btns">
        {state&&!canControl&&<button type="button" onClick={apply} title="Jump to where everyone is"><RefreshCw size={14}/> Sync</button>}
        {state&&canControl&&<button type="button" className="danger" onClick={()=>onOp('stop',0)}><Square size={13}/> Stop for everyone</button>}
        <button type="button" onClick={onClose} aria-label="Hide the video for me" title="Hide for me (keeps playing for others)"><X size={16}/></button>
      </span></div>
    {state?<div className="rm-watch-stage"><div ref={host} className="rm-watch-player"/>{blocked&&<button type="button" className="rm-watch-tap" onClick={()=>{setBlocked(false);try{pl.current?.playVideo()}catch{};apply()}}><Play size={28}/> Tap to play</button>}{err&&<p className="rm-watch-err">{err}</p>}</div>
    :<div className="rm-watch-form"><input value={link} onChange={e=>setLink(e.target.value)} onKeyDown={e=>e.key==='Enter'&&start()} placeholder="Paste a YouTube link" inputMode="url" autoFocus aria-label="YouTube link"/><button type="button" className="primary" onClick={start}>Share video</button>{err&&<p className="rm-watch-err">{err}</p>}<p className="muted small">The sound comes from YouTube on each person's own device, so it is clear on phones too. Only YouTube links work for now.</p></div>}
  </div>;
}
