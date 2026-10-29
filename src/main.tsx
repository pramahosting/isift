import React from 'react';
import { createRoot } from 'react-dom/client';
import { PublicClientApplication } from '@azure/msal-browser';
import App from './App.tsx';
import './style.css';
import {HelpToaster} from './notify.tsx';
import InstallCallout from './InstallCallout.tsx';
import {applyPrefs} from './prefs.ts';
applyPrefs();
// A meeting link handed over from the browser arrives as /?isift=web+isift://room/CODE (or a shortcut /#/start): open that meeting.
try{const q=new URLSearchParams(location.search).get('isift')||'';const m=decodeURIComponent(q).match(/room\/([A-Za-z0-9]+)/);if(m){history.replaceState(null,'',location.pathname+'#/room/'+m[1])}}catch{}

const cfg={auth:{clientId:import.meta.env.VITE_ENTRA_CLIENT_ID||'00000000-0000-0000-0000-000000000000',authority:`https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID||'common'}`,redirectUri:window.location.origin},cache:{cacheLocation:'sessionStorage'}};
const msal=new PublicClientApplication(cfg);
// One iSift tab: a meeting link opened while iSift is already open in another tab is handed to that tab instead of keeping a second one.
const TAB_ID=Math.random().toString(36).slice(2);
let chan:BroadcastChannel|null=null;try{chan=new BroadcastChannel('isift-tabs')}catch{}
const isRoomHash=(h:string)=>/^#\/room\//.test(h);
function listenForHandoff(){
  if(!chan)return;
  chan.onmessage=e=>{const m=e.data||{};if(isApp()||m.type!=='open'||m.from===TAB_ID||!isRoomHash(m.hash))return;
    if(document.documentElement.classList.contains('in-room'))return;      // this tab is in a meeting: do not take over
    setTimeout(()=>{try{const c=localStorage.getItem('isift.claim')||'';const [cid,ct]=c.split('|');if(cid&&cid!==m.from&&Date.now()-Number(ct)<2000&&cid!==TAB_ID&&localStorage.getItem('isift.claim.for')===m.from)return;localStorage.setItem('isift.claim',TAB_ID+'|'+Date.now());localStorage.setItem('isift.claim.for',m.from)}catch{}
      chan!.postMessage({type:'taken',to:m.from,by:TAB_ID});location.hash=m.hash;try{window.focus()}catch{}},Math.random()*60)}
}
const isApp=()=>{try{return window.matchMedia('(display-mode: standalone)').matches||(navigator as any).standalone===true}catch{return false}};
async function handedOver():Promise<boolean>{
  if(isApp())return false;      // the installed app keeps its meeting; it never hands it back to a browser tab
  if(!chan||!isRoomHash(location.hash))return false;
  try{if(sessionStorage.getItem('isift.tabseen'))return false;sessionStorage.setItem('isift.tabseen','1')}catch{return false}
  const nav:any=performance.getEntriesByType?.('navigation')?.[0];if(nav&&nav.type&&nav.type!=='navigate')return false;
  return await new Promise<boolean>(res=>{const to=setTimeout(()=>{chan!.removeEventListener('message',f);res(false)},450);
    const f=(e:MessageEvent)=>{const m=e.data||{};if(m.type==='taken'&&m.to===TAB_ID){clearTimeout(to);chan!.removeEventListener('message',f);res(true)}};
    chan!.addEventListener('message',f);chan!.postMessage({type:'open',hash:location.hash,from:TAB_ID})})
}
function protocolLaunch(){
  try{const u=new URLSearchParams(location.search).get('isift');if(!u)return;
    const m=decodeURIComponent(u).match(/^web\+isift:\/*room\/([A-Za-z0-9]+)/i);
    history.replaceState(null,'',location.pathname+(m?'#/room/'+m[1]:''))}catch{}
}
function openTarget(t:string){
  try{const u=new URL(t,location.origin);let code='';
    const p=u.searchParams.get('isift');
    if(p){const m=decodeURIComponent(p).match(/room\/([A-Za-z0-9]+)/i);if(m)code=m[1]}
    else{const m=u.hash.match(/^#\/room\/([A-Za-z0-9]+)/);if(m)code=m[1]}
    if(code){location.hash='#/room/'+code;setTimeout(()=>{if(!location.hash.includes(code))location.hash='#/room/'+code},50)}
  }catch{}
}
try{(window as any).launchQueue?.setConsumer((p:any)=>{if(p&&p.targetURL)openTarget(p.targetURL)})}catch{}
async function start(){
 protocolLaunch();
 if(await handedOver()){
  document.body.innerHTML='<div style="font-family:system-ui,sans-serif;max-width:420px;margin:18vh auto;padding:0 20px;text-align:center;color:#193348"><h2>Your meeting is open in your other iSift tab</h2><p>Switch to that tab to continue. You can close this one.</p></div>';
  try{window.close()}catch{}
  return}
 listenForHandoff();
 let token='';
 if(import.meta.env.VITE_DEMO_MODE!=='true' && import.meta.env.VITE_ENTRA_CLIENT_ID){
  await msal.initialize();const redirect=await msal.handleRedirectPromise();const account=redirect?.account||msal.getAllAccounts()[0];
  if(account){try{token=(await msal.acquireTokenSilent({account,scopes:[import.meta.env.VITE_ENTRA_API_SCOPE||`api://${import.meta.env.VITE_ENTRA_CLIENT_ID}/access_as_user`]})).accessToken}catch{}}
 }
 createRoot(document.getElementById('root')).render(<React.StrictMode><><App initialToken={token} msal={msal}/><HelpToaster/><InstallCallout/></></React.StrictMode>);
}
start();
