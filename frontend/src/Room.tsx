import React,{useCallback,useEffect,useRef,useState} from 'react';
import {rememberRoom} from './Connections';
import {Armchair,Mic,MicOff,Video,VideoOff,MonitorUp,MessageSquare,Circle,Square,PhoneOff,Link2,Users,Send,X,UserX,ShieldCheck,Check,Plus,LockKeyhole,Table2,LayoutGrid,RectangleHorizontal,Group,Megaphone,HandHelping,Timer} from 'lucide-react';

type Peer={id:string;name:string;host?:boolean;cohost?:boolean;stream:MediaStream;mic:boolean;cam:boolean;screen:boolean};
const wsUrl=(api:string,code:string)=>{const base=api.startsWith('http')?api:location.origin+api;return base.replace(/^http/,'ws')+`/ws/rooms/${code}`};

// Seat positions (percent of the room) for n people around the table. Index 0 is "you", at the bottom, so everyone sees themselves nearest.
export function seatPoints(n:number,shape:'rect'|'round'):{x:number;y:number}[]{
  if(n<=0)return [];
  if(shape==='round')return Array.from({length:n},(_,i)=>{const a=Math.PI/2+i*2*Math.PI/n;return{x:50+37*Math.cos(a),y:50+31*Math.sin(a)}});
  const ends=n>=7?2:0,rem=n-ends,bottom=Math.ceil(rem/2),top=rem-bottom;
  const row=(k:number,y:number)=>Array.from({length:k},(_,i)=>({x:k===1?50:16+(68*i)/(k-1),y}));
  const B=row(bottom,80),T=row(top,20).reverse();
  const P=[...B,...(ends?[{x:90,y:50}]:[]),...T,...(ends?[{x:10,y:50}]:[])];
  const me=Math.floor((bottom-1)/2);
  return [P[me],...P.slice(me+1),...P.slice(0,me)];
}
// The boardroom table is for rooms of 10 or fewer people (the main meeting or a discussion group); bigger rooms use the gallery.
export const TABLE_MAX=10;

function VideoTile({stream,name,muted,off,host,cohost,screen,self,speaking,plate,onDouble}:{onDouble?:()=>void;stream:MediaStream|null;name:string;muted?:boolean;off?:boolean;host?:boolean;cohost?:boolean;screen?:boolean;self?:boolean;speaking?:boolean;plate?:boolean}){
  const ref=useRef<HTMLVideoElement>(null);
  useEffect(()=>{const v=ref.current;if(v&&v.srcObject!==stream){v.srcObject=stream;v.play().catch(()=>{})}},[stream]);
  return <div className={`rm-tile${self?' self':''}${speaking?' speaking':''}`} data-name={name} onDoubleClick={onDouble} title={onDouble?'Double-click to highlight':undefined}>
    <video ref={ref} autoPlay playsInline muted={muted} className={off?'hidden':''}/>
    {speaking&&<span className="rm-talk" title="Speaking" aria-label="Speaking"><Mic size={14}/></span>}
    {off&&<div className="rm-avatar">{(name||'?').trim().charAt(0).toUpperCase()}</div>}
    {!plate&&<span className="rm-name">{name}{self?' (you)':''}{host?(cohost?' · co-host':' · host'):''}{screen?' · sharing':''}</span>}
  </div>;
}

export function RoomPage({code,api,token,defaultName,onLeave,onSignIn}:{code:string;api:string;token:string;defaultName:string;onLeave:()=>void;onSignIn?:()=>void}){
  const [info,setInfo]=useState<any>(null);const [err,setErr]=useState('');
  const [phase,setPhase]=useState<'lobby'|'waiting'|'room'|'ended'>('lobby');
  const [passcode,setPasscode]=useState('');const [waitList,setWaitList]=useState<{id:string;name:string}[]>([]);const [hostInfo,setHostInfo]=useState<any>(null);const [secOpen,setSecOpen]=useState(false);
  const [name,setName]=useState(defaultName||'');
  useEffect(()=>{if(defaultName)setName(n=>n||defaultName)},[defaultName]);   // a person who has just signed in gets their own name filled in
  const [mic,setMic]=useState(true);const [cam,setCam]=useState(true);const [screen,setScreen]=useState(false);
  const [peers,setPeers]=useState<Record<string,Peer>>({});
  const [vrOn,setVrOn]=useState(true);const [vrAllowed,setVrAllowed]=useState(true);const [pin,setPin]=useState('');const [isHost,setIsHost]=useState(false);const [cohost,setCohost]=useState(false);const [policy,setPolicy]=useState({audio:true,video:true});const [peopleOpen,setPeopleOpen]=useState(false);const [menuFor,setMenuFor]=useState('');const [ask,setAsk]=useState<null|{by:string;what:string}>(null);const [inviteOpen,setInviteOpen]=useState(false);const [invTo,setInvTo]=useState('');const [invMsg,setInvMsg]=useState('');const [invBusy,setInvBusy]=useState(false);const [invRes,setInvRes]=useState<any>(null);const [suggest,setSuggest]=useState<{name:string;email:string}[]>([]);const [recording,setRecording]=useState(false);const [recBusy,setRecBusy]=useState(false);
  type ChatMsg={name:string;text:string;at:string;me?:boolean;key:string;names:Record<string,string>;g:string};const [chat,setChat]=useState<ChatMsg[]>([]);const [chatOpen,setChatOpen]=useState(false);const [chatText,setChatText]=useState('');const [chatKey,setChatKey]=useState('all');const [unread,setUnread]=useState<Record<string,number>>({});const [picking,setPicking]=useState(false);const [pickSel,setPickSel]=useState<string[]>([]);const [extraKeys,setExtraKeys]=useState<string[]>([]);const chatKeyRef=React.useRef('all'),chatOpenRef=React.useRef(false);chatKeyRef.current=chatKey;chatOpenRef.current=chatOpen;
  const [notice,setNotice]=useState('');const [localStream,setLocalStream]=useState<MediaStream|null>(null);const [mediaNote,setMediaNote]=useState('');
  const ws=useRef<WebSocket|null>(null);const pcs=useRef<Record<string,RTCPeerConnection>>({});const myId=useRef('');
  const local=useRef<{audio?:MediaStreamTrack;video?:MediaStreamTrack;cam?:MediaStreamTrack}>({});
  const iceRef=useRef<any[]>([]);const peerStreams=useRef<Record<string,MediaStream>>({});
  const [cloud,setCloud]=useState(false);const [recPlan,setRecPlan]=useState('');
  const rec=useRef<any>(null);const wasRecording=useRef(false);
  // discussion groups, boardroom table and active speaker
  const [group,setGroup]=useState<{id:string;name:string}|null>(null);const [groupEnds,setGroupEnds]=useState<string|null>(null);const [roster,setRoster]=useState<any>(null);const [groupsOpen,setGroupsOpen]=useState(false);const [banner,setBanner]=useState<{name:string;text:string}|null>(null);
  const groupRef=useRef<{id:string;name:string}|null>(null);groupRef.current=group;
  const [view,setViewState]=useState<'table'|'gallery'>(()=>{try{return localStorage.getItem('isift.view')==='gallery'?'gallery':'table'}catch{return 'table'}});
  const [shape,setShapeState]=useState<'rect'|'round'>(()=>{try{return localStorage.getItem('isift.shape')==='round'?'round':'rect'}catch{return 'rect'}});
  const setView=(v:'table'|'gallery')=>{setViewState(v);try{localStorage.setItem('isift.view',v)}catch{}};
  const setShape=(v:'rect'|'round')=>{setShapeState(v);try{localStorage.setItem('isift.shape',v)}catch{}};
  const [wide,setWide]=useState(()=>typeof window==='undefined'||window.innerWidth>=720);
  useEffect(()=>{const f=()=>setWide(window.innerWidth>=720);window.addEventListener('resize',f);return()=>window.removeEventListener('resize',f)},[]);
  const [speaking,setSpeaking]=useState('');const peersRef=useRef<Record<string,Peer>>({});const localRef=useRef<MediaStream|null>(null);const seatIds=useRef<string[]>([]);
  const [gCount,setGCount]=useState(2);const [gMinutes,setGMinutes]=useState('');const [gHosts,setGHosts]=useState(false);const [announce,setAnnounce]=useState('');const [, tickClock]=useState(0);

  useEffect(()=>{fetch(`${api}/rooms/${code}`,{headers:token?{Authorization:`Bearer ${token}`}:{}}).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||'This meeting link is not valid.');setInfo(j);iceRef.current=j.ice||[];if(j.ended)setPhase('ended')}).catch(e=>setErr(e.message))},[api,code]);

  // ---- local media ----
  const getMedia=useCallback(async()=>{
    let stream:MediaStream|null=null;
    try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:{width:{ideal:1280},height:{ideal:720}}})}
    catch{try{stream=await navigator.mediaDevices.getUserMedia({audio:true});setMediaNote('Camera not available - joining with microphone only.')}catch{setMediaNote('No camera or microphone available - you can still watch, listen and chat.')}}
    if(stream){local.current.audio=stream.getAudioTracks()[0];local.current.video=stream.getVideoTracks()[0];local.current.cam=local.current.video;setCam(!!local.current.video);setMic(!!local.current.audio);try{const jo=JSON.parse(sessionStorage.getItem('isift.join')||'{}');if(jo.audio===false&&local.current.audio){local.current.audio.enabled=false;setMic(false)}if(jo.video===false&&local.current.cam){local.current.cam.enabled=false;setCam(false)}if(jo.name)setName(n=>n||jo.name)}catch{}}else{setCam(false);setMic(false)}
    setLocalStream(stream);return stream;
  },[]);
  useEffect(()=>{if(phase==='lobby'&&info&&!localStream&&!err)getMedia()},[phase,info]);// preview in the lobby
  useEffect(()=>()=>{local.current.audio?.stop();local.current.cam?.stop();local.current.video?.stop()},[]);

  // ---- peer connections ----
  const send=(m:any)=>{if(ws.current?.readyState===1)ws.current.send(JSON.stringify(m))};
  const upsert=(id:string,patch:Partial<Peer>)=>setPeers(p=>({...p,[id]:{id,name:'Guest',stream:peerStreams.current[id],mic:true,cam:true,screen:false,...p[id],...patch}}));
  const makePc=(id:string)=>{
    if(pcs.current[id])return pcs.current[id];
    const pc=new RTCPeerConnection({iceServers:iceRef.current});pcs.current[id]=pc;
    peerStreams.current[id]=peerStreams.current[id]||new MediaStream();
    pc.onicecandidate=e=>{if(e.candidate)send({type:'signal',to:id,data:{candidate:e.candidate}})};
    pc.ontrack=e=>{const s=peerStreams.current[id];if(!s.getTracks().includes(e.track))s.addTrack(e.track);upsert(id,{stream:s});e.track.onunmute=()=>upsert(id,{});recorderRefresh()};
    pc.onconnectionstatechange=()=>{if(pc.connectionState==='failed')setNotice('A connection to another person failed. A TURN server may be needed on this network.')};
    return pc;
  };
  const attachLocal=async(pc:RTCPeerConnection)=>{
    for(const tx of pc.getTransceivers()){
      const kind=tx.receiver.track.kind;tx.direction='sendrecv';
      const t=kind==='audio'?local.current.audio:local.current.video;if(t)await tx.sender.replaceTrack(t);
    }
  };
  const callPeer=async(id:string)=>{ // we are the newcomer: we send the offer
    const pc=makePc(id);pc.addTransceiver('audio',{direction:'sendrecv'});pc.addTransceiver('video',{direction:'sendrecv'});
    await attachLocal(pc);const offer=await pc.createOffer();await pc.setLocalDescription(offer);send({type:'signal',to:id,data:{sdp:pc.localDescription}});
  };
  const onSignal=async(from:string,data:any)=>{
    const pc=makePc(from);
    if(data.sdp){
      await pc.setRemoteDescription(data.sdp);
      if(data.sdp.type==='offer'){await attachLocal(pc);const ans=await pc.createAnswer();await pc.setLocalDescription(ans);send({type:'signal',to:from,data:{sdp:pc.localDescription}})}
    }else if(data.candidate){try{await pc.addIceCandidate(data.candidate)}catch{}}
  };
  const dropPeer=(id:string)=>{pcs.current[id]?.close();delete pcs.current[id];delete peerStreams.current[id];setPeers(p=>{const n={...p};delete n[id];return n});recorderRefresh()};

  const authH:any={'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})};
  const loadHostInfo=()=>fetch(`${api}/rooms/${code}/host`,{headers:authH}).then(r=>r.ok?r.json():null).then(j=>j&&setHostInfo(j)).catch(()=>{});
  const changeSecurity=async(patch:any)=>{const r=await fetch(`${api}/rooms/${code}`,{method:'PATCH',headers:authH,body:JSON.stringify(patch)});if(r.ok)setHostInfo({...hostInfo,...(await r.json())});else setNotice('Could not change the meeting settings.')};
  useEffect(()=>{if(info?.you_are_host)loadHostInfo()},[info]);
  const [copied,setCopied]=useState('');
  const copyText=async(id:string,t:string)=>{try{await navigator.clipboard.writeText(t);setCopied(id);setTimeout(()=>setCopied(''),2000)}catch{window.prompt('Copy this:',t)}};
  const endMeeting=async()=>{if(!window.confirm('End this meeting? The link stops working and the meeting is cancelled.'))return;const r=await fetch(`${api}/rooms/${code}/end`,{method:'POST',headers:authH,body:JSON.stringify({cancel:true})});if(r.ok){local.current.audio?.stop();local.current.cam?.stop();onLeave()}else setErr('Could not end the meeting. Try again.')};
  const join=async()=>{
    setErr('');
    const sock=new WebSocket(wsUrl(api,code));ws.current=sock;
    sock.onopen=()=>send({type:'join',client:(()=>{try{let c=sessionStorage.getItem('isift.cid');if(!c){c=Math.random().toString(36).slice(2)+Date.now().toString(36);sessionStorage.setItem('isift.cid',c)}return c}catch{return ''}})(),name:name.trim()||'Guest',token:token||undefined,passcode:passcode.trim()||undefined});
    sock.onmessage=async ev=>{
      const m=JSON.parse(ev.data);
      if(m.type==='waiting'){setPhase('waiting')}
      else if(m.type==='denied'){setErr('The host did not let you in.');setPhase('ended')}
      else if(m.type==='waiting-list'){setWaitList(m.list||[]);if((m.list||[]).length)setNotice(`${m.list[m.list.length-1].name} is waiting to join`)}
      else if(m.type==='welcome'){setWaitList(m.waiting||[]);if(m.roster)setRoster(m.roster);if(m.host)loadHostInfo();myId.current=m.id;setIsHost(!!m.host);setCohost(!!m.cohost);setPolicy(m.policy||{audio:true,video:true});setRecording(!!m.recording);setPhase('room');{let jo:any={};try{jo=JSON.parse(sessionStorage.getItem('isift.join')||'{}');sessionStorage.removeItem('isift.join')}catch{}rememberRoom(code,info?.title||'Meeting');if(jo.audio===false&&local.current.audio){local.current.audio.enabled=false;setMic(false)}if(jo.video===false&&local.current.cam){local.current.cam.enabled=false;setCam(false)}const o=m.options||{};setVrOn(o.virtual_room!==false);setVrAllowed(m.vroom_allowed!==false);if(!m.host){if((o.mute_on_entry||m.policy?.audio===false)&&local.current.audio){local.current.audio.enabled=false;setMic(false)}if((o.video_off_on_entry||m.policy?.video===false)&&local.current.cam){local.current.cam.enabled=false;setCam(false)}}else{let so:any={};try{so=JSON.parse(sessionStorage.getItem('isift.start')||'{}');sessionStorage.removeItem('isift.start')}catch{}if((so.video===false||o.host_video_off)&&local.current.cam){local.current.cam.enabled=false;setCam(false)}if(so.screen)setTimeout(()=>screenRef.current?.(),500);if(o.auto_record&&!m.recording)setTimeout(()=>autoRec.current?.(),800)}}for(const p of m.peers){upsert(p.id,{name:p.name,host:p.host,cohost:p.cohost});await callPeer(p.id)}send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false})}
      else if(m.type==='peer-joined'){upsert(m.id,{name:m.name,host:m.host,cohost:m.cohost});setNotice(`${m.name} joined`);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false})}
      else if(m.type==='peer-left'){setPeers(p=>{if(p[m.id])setNotice(`${p[m.id].name} left`);return p});dropPeer(m.id)}
      else if(m.type==='signal')onSignal(m.from,m.data);
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
      else if(m.type==='vroom'){setVrOn(!!m.on);if(m.on)setView('table');setNotice(`${m.by||'The host'} switched the virtual room ${m.on?'on':'off'}.`)}
      else if(m.type==='policy'){setPolicy({audio:!!m.audio,video:!!m.video});setNotice(`${m.by||'The host'} changed what participants may switch on.`)}
      else if(m.type==='force'){
        if(m.mic===false){if(local.current.audio)local.current.audio.enabled=false;setMic(false)}
        if(m.cam===false){if(local.current.cam)local.current.cam.enabled=false;setCam(false)}
        send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false});
        setNotice(m.reason==='policy'?'The host has not allowed participants to turn that on.':m.all?`${m.by||'The host'} muted everyone.`:`${m.by||'The host'} turned off your ${m.mic===false&&m.cam===false?'microphone and camera':m.mic===false?'microphone':'camera'}.`)}
      else if(m.type==='ask'){setAsk({by:m.by,what:m.what})}
      else if(m.type==='kicked'){leaveLocal();setErr('You were removed from the meeting by the host.');setPhase('ended')}
      else if(m.type==='ended'){leaveLocal();setPhase('ended')}
      else if(m.type==='error'){setErr(m.message);sock.close()}
    };
    sock.onclose=()=>{setPhase(p=>p==='room'||p==='waiting'?'ended':p)};
  };
  const leaveLocal=()=>{Object.keys(pcs.current).forEach(id=>{pcs.current[id].close();delete pcs.current[id]});local.current.audio?.stop();local.current.cam?.stop();local.current.video?.stop();ws.current?.close()};
  const leave=async()=>{if(rec.current)await stopRecording(false);leaveLocal();onLeave()};
  const endAll=async()=>{if(!window.confirm('End the meeting for everyone?'))return;if(rec.current)await stopRecording(true);send({type:'end'});leaveLocal();onLeave()};

  // ---- controls ----
  const toggleMic=()=>{const t=local.current.audio;if(!t)return;if(!t.enabled&&phase==='room'&&!isHost&&!policy.audio){setNotice('The host has not allowed participants to unmute. Ask the host.');return}t.enabled=!t.enabled;setMic(t.enabled);send({type:'state',mic:t.enabled,cam:!!local.current.video?.enabled,screen})};
  const toggleCam=()=>{const t=local.current.cam;if(!t)return;if(!t.enabled&&phase==='room'&&!isHost&&!policy.video){setNotice('The host has not allowed participants to start their video. Ask the host.');return}t.enabled=!t.enabled;setCam(t.enabled);send({type:'state',mic:!!local.current.audio?.enabled,cam:t.enabled,screen})};
  const replaceVideo=async(track?:MediaStreamTrack)=>{for(const pc of Object.values(pcs.current)){const tx=pc.getTransceivers().find(x=>x.receiver.track.kind==='video');if(tx)await tx.sender.replaceTrack(track||null)}};
  const toggleScreen=async()=>{
    if(screen){await replaceVideo(local.current.cam);local.current.video=local.current.cam;setLocalStream(s=>s);setScreen(false);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:false});return}
    try{const d=await (navigator.mediaDevices as any).getDisplayMedia({video:true});const t=d.getVideoTracks()[0];local.current.video=t;t.onended=()=>{replaceVideo(local.current.cam);local.current.video=local.current.cam;setScreen(false);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:false})};await replaceVideo(t);setScreen(true);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:true})}catch{setNotice('Screen sharing was cancelled or is not available in this browser.')}
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
  const infoRef=useRef<any>({peers:[],local:null,name:'',cam:false,mic:false,screen:false,speaking:''});
  infoRef.current={peers:Object.values(peers),local:localStream,name,cam,mic,screen,speaking,vtrack:local.current.video};
  const recorderRefresh=()=>{const r=rec.current;if(!r)return;const have=new Set<string>(r.sources.keys());
    const streams:Record<string,MediaStream>={...peerStreams.current,__me:localStream||new MediaStream()};
    for(const [k,s] of Object.entries(streams)){const t=s.getAudioTracks()[0];if(t&&!have.has(k+t.id)){try{const src=r.ctx.createMediaStreamSource(new MediaStream([t]));src.connect(r.dest);r.sources.set(k+t.id,src)}catch{}}}};
  useEffect(()=>{if(!recording)return;const h=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',h);return()=>window.removeEventListener('beforeunload',h)},[recording]);
  const autoRec=useRef<null|(()=>void)>(null);const screenRef=useRef<null|(()=>void)>(null);
  const startRecording=async(auto?:boolean)=>{
    if(!isHost||rec.current)return;
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
    const nodes=new Map<string,{track:string;an:AnalyserNode;src:MediaStreamAudioSourceNode}>();const buf=new Uint8Array(512);let last='';
    const level=(id:string,stream:MediaStream|null|undefined)=>{
      const t=stream?.getAudioTracks()[0];const cur=nodes.get(id);
      if(!t||t.readyState!=='live'){if(cur){try{cur.src.disconnect()}catch{}nodes.delete(id)}return 0}
      if(!cur||cur.track!==t.id){if(cur){try{cur.src.disconnect()}catch{}}try{const src=ctx.createMediaStreamSource(new MediaStream([t]));const an=ctx.createAnalyser();an.fftSize=512;src.connect(an);nodes.set(id,{track:t.id,an,src})}catch{return 0}}
      const n=nodes.get(id);if(!n)return 0;n.an.getByteTimeDomainData(buf);let sum=0;for(let i=0;i<buf.length;i++){const v=(buf[i]-128)/128;sum+=v*v}return Math.sqrt(sum/buf.length)};
    const tick=()=>{
      if(ctx.state==='suspended')ctx.resume().catch(()=>{});
      const live=new Set<string>(['__me',...Object.keys(peersRef.current)]);for(const id of Array.from(nodes.keys()))if(!live.has(id)){try{nodes.get(id)!.src.disconnect()}catch{}nodes.delete(id)}
      let best='',top=0.02;
      const me=localRef.current;if(me&&local.current.audio?.enabled){const l=level('__me',me);if(l>top){top=l;best='__me'}}
      for(const id of Object.keys(peersRef.current)){const l=level(id,peersRef.current[id].stream);if(l>top){top=l;best=id}}
      if(best!==last){last=best;setSpeaking(best)}};
    const iv=setInterval(tick,250);
    return()=>{clearInterval(iv);nodes.forEach(n=>{try{n.src.disconnect()}catch{}});try{ctx.close()}catch{}};
  },[phase]);
  useEffect(()=>{if(!groupEnds)return;const iv=setInterval(()=>tickClock(x=>x+1),1000);return()=>clearInterval(iv)},[groupEnds]);
  useEffect(()=>{if(banner){const t=setTimeout(()=>setBanner(null),25000);return()=>clearTimeout(t)}},[banner]);

  // ---------- views ----------
  if(err&&phase!=='ended'&&!info)return <div className="rm-center"><div className="rm-card"><h1>Meeting not available</h1><p>{err}</p><button className="primary" onClick={onLeave}>Back to the app</button></div></div>;
  if(phase==='ended')return <div className="rm-center"><div className="rm-card"><h1>{err?'You left the meeting':'This meeting has ended'}</h1><p>{err||'Thanks for joining.'}</p><button className="primary" onClick={onLeave}>{token?'Back to the app':'Close'}</button></div></div>;
  if(!info)return <div className="rm-center"><div className="rm-card">Loading…</div></div>;
  if(phase==='lobby')return <div className="rm-center"><div className="rm-card lobby"><button type="button" className="rm-x" aria-label="Close and leave this meeting" title="Close" onClick={()=>{leaveLocal();onLeave()}}><X size={20}/></button>
    <h1>{info.title}</h1><p className="muted">Hosted by {info.host||'the organizer'} · {info.people_now} {info.people_now===1?'person':'people'} in the meeting</p>
    <div className="rm-preview"><VideoTile stream={localStream} name={name||'You'} muted off={!cam||!localStream?.getVideoTracks().length} self/></div>
    {mediaNote&&<p className="muted">{mediaNote}</p>}
    <label>Your name<input value={name} onChange={e=>setName(e.target.value)} maxLength={60} placeholder="Your name" autoFocus/></label>
    {!info.signed_in&&!info.you_are_host&&info.access!=='signed_in'&&<p className="rm-guest" role="note"><b>Joining as a guest.</b> No account is needed: enter your name and join.{onSignIn&&<> Have an account? <button type="button" className="linkbtn" onClick={()=>{leaveLocal();onSignIn()}}>Sign in</button></>}</p>}
    {info.you_are_host&&<div className="rm-hostbox"><b>Share this meeting</b>
      {[['Link',`${location.origin}${location.pathname}#/room/${code}`,'l'],['Meeting ID',code,'i'],...(hostInfo?.passcode?[['Passcode',hostInfo.passcode,'p']]:[])].map(([lab,val,id])=><div key={id} className="mc-row"><span>{lab}</span><input readOnly value={val} aria-label={lab} onFocus={e=>e.currentTarget.select()}/><button type="button" className="secondary" onClick={()=>copyText(id,val)}>{copied===id?'Copied':'Copy'}</button></div>)}
      <div className="rm-hostactions"><button type="button" className="secondary" onClick={()=>copyText('all',`${info.title}\nJoin: ${location.origin}${location.pathname}#/room/${code}\nMeeting ID: ${code}${hostInfo?.passcode?`\nPasscode: ${hostInfo.passcode}`:''}`)}>{copied==='all'?'Invitation copied':'Copy invitation'}</button><button type="button" className="end-btn" onClick={endMeeting}>End meeting</button></div></div>}
    {info.access==='passcode'&&!info.you_are_host&&<label>Meeting passcode<input value={passcode} onChange={e=>setPasscode(e.target.value)} maxLength={12} placeholder="Passcode from your invitation" autoComplete="off"/></label>}
    {info.access==='signed_in'&&!info.signed_in&&<p className="syncerr" role="alert">This meeting is only open to people with an account. Sign in to join.{onSignIn&&<> <button type="button" className="primary" onClick={()=>{leaveLocal();onSignIn()}}>Sign in</button></>}</p>}
    {info.waiting_room&&!info.you_are_host&&<p className="muted small">The host will let you in when they are ready.</p>}
    <div className="rm-lobbyctl"><button type="button" className={`secondary${!mic?' off':''}`} onClick={toggleMic} disabled={!local.current.audio}>{mic?<Mic size={16}/>:<MicOff size={16}/>} {mic?'Mic on':'Mic off'}</button><button type="button" className={`secondary${!cam?' off':''}`} onClick={toggleCam} disabled={!local.current.cam}>{cam?<Video size={16}/>:<VideoOff size={16}/>} {cam?'Camera on':'Camera off'}</button></div>
    <p className="muted small">The host may record this meeting. You will see a clear “Recording” banner if they do, and you can leave at any time.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <button className="primary join" onClick={join} disabled={!name.trim()||(info.access==="passcode"&&!info.you_are_host&&passcode.trim().length<4)||(info.access==="signed_in"&&!info.signed_in)}>{!info.signed_in&&!info.you_are_host&&info.access!=='signed_in'?(info.waiting_room?"Ask to join as guest":"Join as guest"):(info.waiting_room&&!info.you_are_host?"Ask to join":"Join meeting")}</button>
  </div></div>;
  if(phase==='waiting')return <div className="rm-center"><div className="rm-card"><h1>Waiting for the host</h1><p>The host will let you in shortly. You can leave this page at any time.</p><button className="secondary" onClick={()=>{ws.current?.close();onLeave()}}>Cancel</button></div></div>;
  const list=Object.values(peers);const tiles=list.length+1;
  const rankOf=(h?:boolean,c?:boolean)=>!h?0:c?1:2;const myRank=rankOf(isHost,cohost);const primary=myRank===2;
  type Row={id:string;self?:boolean;name:string;host?:boolean;cohost?:boolean;mic:boolean;cam:boolean;screen:boolean;stream:MediaStream|null};
  const ordered:Row[]=[{id:'__me',self:true,name:name||'You',host:isHost,cohost,mic,cam,screen,stream:localStream},...list.map(p=>({id:p.id,name:p.name,host:p.host,cohost:p.cohost,mic:p.mic,cam:p.cam,screen:p.screen,stream:p.stream||null}))]
    .map((r,i)=>({r,i})).sort((a,b)=>rankOf(b.r.host,b.r.cohost)-rankOf(a.r.host,a.r.cohost)||a.i-b.i).map(x=>x.r);     // the host first, then co-hosts, then everyone else
  const curG=group?.id||'main';const sharing=ordered.some(r=>r.screen);
  const pinnedRow=pin?ordered.find(r=>r.id===pin):undefined;const togglePin=(id:string)=>setPin(p=>p===id?'':id);
  const spotTile=(r:Row)=>r.self?<VideoTile stream={localStream} name={r.name} muted off={!cam&&!screen} self host={isHost} cohost={cohost} screen={screen} speaking={speaking==='__me'} onDouble={()=>togglePin('__me')}/>:<VideoTile stream={r.stream} name={r.name} off={!r.cam&&!r.screen} host={r.host} cohost={r.cohost} screen={r.screen} speaking={speaking===r.id} onDouble={()=>togglePin(r.id)}/>;
  const tableOk=vrOn&&tiles<=TABLE_MAX&&!sharing&&wide;const mode:'table'|'gallery'=tableOk?'table':'gallery';
  {const here=new Set(list.map(p=>p.id));seatIds.current=seatIds.current.filter(id=>here.has(id));list.forEach(p=>{if(!seatIds.current.includes(p.id))seatIds.current.push(p.id)})}
  const seatRows:Row[]=[ordered.find(r=>r.self)!,...seatIds.current.map(id=>ordered.find(r=>r.id===id)).filter(Boolean) as Row[]];
  const seats=seatPoints(seatRows.length,shape);const seatW=tiles<=2?22:tiles<=4?19:tiles<=6?17:14;
  const secsLeft=groupEnds?Math.max(0,Math.round((new Date(groupEnds).getTime()-Date.now())/1000)):null;
  const clock=secsLeft===null?'':`${Math.floor(secsLeft/60)}:${String(secsLeft%60).padStart(2,'0')}`;
  const hostRow=ordered.find(r=>rankOf(r.host,r.cohost)===2);const hostName=hostRow?(hostRow.self?'you':hostRow.name):(info.host||'');
  const canAct=(r:Row)=>!r.self&&myRank>rankOf(r.host,r.cohost);
  const togglePeople=()=>{setPeopleOpen(o=>!o);setChatOpen(false);setMenuFor('')};
  return <div className="rm-shell">
    <header className="rm-top"><b className="rm-title">{info.title}</b>{hostName&&<span className="muted rm-hostname">Host: {hostName}</span>}{recording&&<span className="rm-rec"><Circle size={10} fill="currentColor"/> Recording</span>}{group&&<span className="rm-group"><Group size={13}/> {group.name}</span>}{clock&&<span className="rm-clock" title="Time left in the discussion groups"><Timer size={13}/> {clock}</span>}<span className="muted"><Users size={14}/> {tiles}</span>{notice&&<span className="rm-notice" role="status">{notice}</span>}</header>
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
    <div className="rm-main">{pinnedRow?<div className="rm-spot"><div className="rm-spot-main">{spotTile(pinnedRow)}<div className="rm-spot-tag"><b>Highlighted: {pinnedRow.name}{pinnedRow.self?' (you)':''}</b><button type="button" onClick={()=>setPin('')}>Back to everyone</button></div></div><div className="rm-spot-strip">{ordered.filter(r=>r.id!==pin).map(r=><div key={r.id} className="rm-wrap">{spotTile(r)}{!r.mic&&<span className="rm-muted" title="Muted"><MicOff size={13}/></span>}</div>)}</div></div>:mode==='table'?<div className="rm-table-stage"><div ref={gridRef} className={`rm-room ${shape}`} aria-label={`Boardroom table with ${tiles} ${tiles===1?'person':'people'}`}>
      <div className="rm-table" aria-hidden="true"/><div className="rm-cam" aria-hidden="true" title="Everyone is seen from the centre of the table"/>
      {seatRows.map((r,i)=>{const pt=seats[i];return <div key={r.id} className={`rm-seat ${pt.y<35?'top':pt.y>65?'bot':pt.x<50?'lft':'rgt'}${speaking===r.id||(r.self&&speaking==='__me')?' speaking':''}`} style={{left:`${pt.x}%`,top:`${pt.y}%`,width:`${seatW}%`,zIndex:Math.round(pt.y),['--ry' as any]:`${(Math.max(-1,Math.min(1,(50-pt.x)/38))*28).toFixed(1)}deg`,['--rx' as any]:`${(Math.max(-1,Math.min(1,(pt.y-50)/30))*14).toFixed(1)}deg`,['--sc' as any]:'0.96'}}>
        <VideoTile stream={r.self?localStream:r.stream} name={r.name} muted={r.self} off={r.self?(!cam&&!screen):(!r.cam&&!r.screen)} self={r.self} host={r.host} cohost={r.cohost} screen={r.screen} speaking={speaking===(r.self?'__me':r.id)} plate onDouble={()=>togglePin(r.id)}/>
        <div className="rm-plate" title={r.name}><span className="rm-plname">{r.name}{r.self?' (you)':''}</span>{r.host&&<em>{r.cohost?'co-host':'host'}</em>}{r.screen&&<em>sharing</em>}<span className="rm-plstate">{(r.self?mic:r.mic)?null:<MicOff size={12} className="off" aria-label="Muted"/>}{(r.self?cam:r.cam)?null:<VideoOff size={12} className="off" aria-label="Camera off"/>}</span></div></div>})}
    </div></div>:<div ref={gridRef} className={`rm-grid n${Math.min(tiles,9)}${tiles>TABLE_MAX?' big':''}`}>
      {ordered.map(r=>r.self?<VideoTile key="__me" stream={localStream} name={r.name} muted off={!cam&&!screen} self host={isHost} cohost={cohost} screen={screen} speaking={speaking==='__me'} onDouble={()=>togglePin('__me')}/>:<div key={r.id} className="rm-wrap">
        <VideoTile stream={r.stream} name={r.name} off={!r.cam&&!r.screen} host={r.host} cohost={r.cohost} screen={r.screen} speaking={speaking===r.id} onDouble={()=>togglePin(r.id)}/>
        {!r.mic&&<span className="rm-muted" title="Muted"><MicOff size={13}/></span>}
        {isHost&&canAct(r)&&<button className="rm-kick" title={`Remove ${r.name}`} onClick={()=>window.confirm(`Remove ${r.name} from the meeting?`)&&send({type:'kick',id:r.id})}><UserX size={14}/></button>}
      </div>)}
    </div>}
    {peopleOpen&&<aside className="rm-chat rm-people" aria-label="Participants"><div className="rm-chathead"><b>Participants ({tiles})</b><button className="iconbtn" onClick={()=>setPeopleOpen(false)} aria-label="Hide participants" title="Hide participants"><X size={16}/></button></div>
      <ul className="rm-plist">{ordered.map(r=><li key={r.id}>
        <div className="rm-prow"><span className="rm-pname"><b>{r.name}</b>{r.self?' (me)':''}{r.host?<em className="rm-badge">{r.cohost?'Co-host':'Host'}</em>:null}</span>
          <span className="rm-pstate">
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
    {chatOpen&&<aside className="rm-chat" aria-label="Meeting chat"><div className="rm-chathead"><b>Chat</b><button className="iconbtn" onClick={()=>setChatOpen(false)} aria-label="Hide chat" title="Hide chat"><X size={16}/></button></div>
      <div className="rm-threads" role="tablist" aria-label="Conversations">{threadKeys.map(k=><button key={k} role="tab" aria-selected={chatKey===k} className={chatKey===k?'on':''} onClick={()=>openThread(k)} title={threadLabel(k)}>{k==='all'?'Everyone':threadLabel(k)}{!!unread[k]&&<i className="rm-dot">{unread[k]}</i>}</button>)}<button className="rm-newpriv" onClick={()=>{setPicking(p=>!p);setPickSel([])}} aria-label="Chat privately with someone" title="Chat privately with one person or a group"><Plus size={14}/></button></div>
      {picking&&<div className="rm-pick"><small>Choose one person, or several for a group:</small>{list.length?list.map(pe=><label key={pe.id}><input type="checkbox" checked={pickSel.includes(pe.id)} onChange={e=>setPickSel(x=>e.target.checked?[...x,pe.id]:x.filter(y=>y!==pe.id))}/> {pe.name}{pe.host?' (host)':''}</label>):<small className="muted">No one else has joined yet.</small>}<div><button className="primary" disabled={!pickSel.length} onClick={startPrivate}>Start chat</button> <button className="secondary" onClick={()=>setPicking(false)}>Cancel</button></div></div>}
      {chatKey!=='all'&&<p className="rm-private"><LockKeyhole size={12}/> Private: only {threadLabel(chatKey)} and you can see this.</p>}
      <div className="rm-msgs">{curChat.filter(c=>c.key===chatKey).map((c,i)=><div key={i} className={`rm-msg${c.me?' me':''}`}><b>{c.me?'You':c.name}</b><p>{c.text}</p></div>)}{!curChat.some(c=>c.key===chatKey)&&<p className="muted">No messages yet.</p>}</div>
      <form onSubmit={sendChat}><label className="rm-to"><span>To:</span><select value={chatKey} onChange={e=>{const v=e.target.value;if(v==='all'||v.includes(','))openThread(v);else{const k=[myId.current,v].sort().join(',');setExtraKeys(x=>x.includes(k)?x:[...x,k]);openThread(k)}}} aria-label="Send to"><option value="all">Everyone</option>{chatKey!=='all'&&!list.some(pe=>[myId.current,pe.id].sort().join(',')===chatKey)&&<option value={chatKey}>{threadLabel(chatKey)}</option>}{list.map(pe=><option key={pe.id} value={[myId.current,pe.id].sort().join(',')}>{pe.name}{pe.host?(pe.cohost?' (co-host)':' (host)'):''}</option>)}</select></label><input value={chatText} onChange={e=>setChatText(e.target.value)} placeholder={chatKey==='all'?'Message everyone':`Message ${threadLabel(chatKey)}`} maxLength={2000}/><button className="primary" aria-label="Send"><Send size={15}/></button></form></aside>}
    </div>
    <footer className="rm-bar">
      <button className={`rm-btn${!mic?' off':''}`} onClick={toggleMic} disabled={!local.current.audio} aria-label={mic?'Mute microphone':'Unmute microphone'}>{mic?<Mic size={18}/>:<MicOff size={18}/>}<span>{mic?'Mute':'Unmute'}</span></button>
      <button className={`rm-btn${!cam?' off':''}`} onClick={toggleCam} disabled={!local.current.cam} aria-label={cam?'Turn camera off':'Turn camera on'}>{cam?<Video size={18}/>:<VideoOff size={18}/>}<span>{cam?'Camera':'Camera off'}</span></button>
      <button className={`rm-btn${screen?' on':''}`} onClick={toggleScreen} aria-label="Share screen"><MonitorUp size={18}/><span>{screen?'Stop sharing':'Share'}</span></button>
      <button className={`rm-btn${peopleOpen?' on':''}`} onClick={togglePeople} aria-label="Participants"><Users size={18}/><span>People ({tiles})</span></button>
      <button className={`rm-btn${chatOpen?' on':''}`} onClick={()=>{setChatOpen(o=>!o);setPeopleOpen(false);if(!chatOpen)setUnread(u=>({...u,[chatKey]:0}))}} aria-label="Chat"><MessageSquare size={18}/><span>Chat</span>{Object.values(unread).reduce((a,b)=>a+b,0)>0&&<i className="rm-dot">{Object.values(unread).reduce((a,b)=>a+b,0)}</i>}</button>
      {isHost&&vrAllowed&&<button className={`rm-btn${vrOn?' on':''}`} onClick={()=>{const v=!vrOn;setVrOn(v);if(v)setView('table');send({type:'vroom',on:v})}} aria-pressed={vrOn} aria-label={vrOn?'Switch the virtual room off for everyone':'Switch the virtual room on for everyone'} title={vrOn?'Virtual room is on: everyone sees the boardroom table. Press to switch it off for everyone.':'Virtual room is off: everyone sees the gallery. Press to switch it on for everyone.'}><Armchair size={18}/><span>Virtual room: {vrOn?'On':'Off'}</span></button>}
      <button className={`rm-btn${inviteOpen?' on':''}`} onClick={()=>inviteOpen?setInviteOpen(false):openInvite()} aria-label="Invite people"><Link2 size={18}/><span>Invite</span></button>
      {mode==='table'&&tiles>2&&<button className="rm-btn" onClick={()=>setShape(shape==='rect'?'round':'rect')} aria-label={shape==='rect'?'Use a round table':'Use a rectangular table'} title={shape==='rect'?'Use a round table':'Use a rectangular table'}>{shape==='rect'?<Circle size={18}/>:<RectangleHorizontal size={18}/>}<span>{shape==='rect'?'Round':'Rectangle'}</span></button>}
      {isHost&&<button className={`rm-btn${groupsOpen||roster?.groups?' on':''}`} onClick={()=>setGroupsOpen(o=>!o)} aria-label="Discussion groups" aria-expanded={groupsOpen}><Group size={18}/><span>Groups</span></button>}
      {primary&&<button className={`rm-btn${secOpen?' on':''}`} onClick={()=>{loadHostInfo();setSecOpen(o=>!o)}} aria-label="Meeting security"><ShieldCheck size={18}/><span>Security</span></button>}
      {primary&&(recording?<button className="rm-btn rec" disabled={recBusy} onClick={()=>stopRecording()} aria-label="Stop recording"><Square size={18}/><span>{recBusy?'Saving…':'Stop rec'}</span></button>:<button className="rm-btn" onClick={startRecording} aria-label="Start recording"><Circle size={18}/><span>Record</span></button>)}
      {primary&&<label className="rm-cloud" title={recPlan==='basic'?'On the Basic plan a cloud copy is kept for 2 days. Your own computer always gets a copy.':'Your own computer always gets a copy. Tick to also keep one in the cloud.'}><input type="checkbox" checked={cloud} disabled={recBusy} onChange={e=>setCloud(e.target.checked)}/> Also store in cloud{recPlan==='basic'?' (2 days)':''}</label>}
      <button className="rm-btn leave" onClick={leave} aria-label="Leave meeting"><PhoneOff size={18}/><span>Leave</span></button>
      {primary&&<button className="rm-btn leave" onClick={endAll} aria-label="End meeting for everyone"><X size={18}/><span>End all</span></button>}
    </footer>
  </div>;
}
