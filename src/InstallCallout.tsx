import React,{useEffect,useState} from 'react';
import {ArrowUp,Check} from 'lucide-react';
import {installReady,runInstall,runningAsApp,InstallHelp} from './HomeWorkspace';

// Shown to anyone whose browser can install iSift but has not yet: a small one-line box, top right, just under the browser's install button, with an arrow pointing up at it.
// Hover (or tab to) the box to see what installing gives them. It has no close button; it goes away on its own once iSift is installed,
// and it never appears in the installed app, in a meeting, or on a phone.
const BENEFITS=['Opens in its own window, with no browser tabs','The iSift logo on your taskbar and Start menu, one click away','Meeting links open straight in the app','Starts faster and remembers you'];

// iSift is already installed on this person's computer or account (a browser cannot see apps installed through another browser, so the account remembers it too).
const wasInstalled=()=>{try{return localStorage.getItem('isift.installed')==='1'}catch{return false}};

export default function InstallCallout(){
  const [ready,setReady]=useState(()=>installReady());      // the browser only offers installation when iSift is not installed on this computer
  const [done,setDone]=useState(false);const [help,setHelp]=useState(false);
  const [inRoom,setInRoom]=useState(()=>/^#\/room\//.test(location.hash));
  useEffect(()=>{
    const on=()=>setReady(true);const gone=()=>{setReady(false);setDone(true);setKnown(true)};const hash=()=>setInRoom(/^#\/room\//.test(location.hash));
    window.addEventListener('isift:installable',on);window.addEventListener('appinstalled',gone);window.addEventListener('hashchange',hash);
    return()=>{window.removeEventListener('isift:installable',on);window.removeEventListener('appinstalled',gone);window.removeEventListener('hashchange',hash)}},[]);
  useEffect(()=>{if(!done)return;const t=setTimeout(()=>setDone(false),15000);return()=>clearTimeout(t)},[done]);
  const [known,setKnown]=useState(()=>wasInstalled());
  useEffect(()=>{const f=()=>setKnown(wasInstalled());window.addEventListener('isift:installed-known',f);window.addEventListener('storage',f);return()=>{window.removeEventListener('isift:installed-known',f);window.removeEventListener('storage',f)}},[]);
  const show=!done&&ready&&!known&&!inRoom&&!runningAsApp();
  // While the box is showing, the page makes room for it (see .inst-on in style.css) so it never covers a button.
  useEffect(()=>{document.documentElement.classList.toggle('inst-on',show);return()=>document.documentElement.classList.remove('inst-on')},[show]);
  if(done)return <div className="inst-done" role="status"><span className="inst-done-ic"><Check size={16}/></span><span><b>iSift is installed</b><small>Its logo is now in your Start menu and on the taskbar while it is open. To keep it there, right-click the logo on the taskbar and choose Pin to taskbar.</small></span></div>;
  if(!show)return null;
  const go=async()=>{if(!(await runInstall()))setHelp(true)};
  return <aside className="inst-callout" aria-label="Install iSift">
    <div className="inst-co-box" tabIndex={0} aria-describedby="inst-co-tip">
      <span className="inst-co-arrow" aria-hidden="true"/>
      <button type="button" className="inst-co-link" onClick={go}><ArrowUp size={14} aria-hidden="true"/>Install iSift</button>
      <div className="inst-co-tip" id="inst-co-tip" role="tooltip"><b>Why install iSift?</b><ul>{BENEFITS.map(b=><li key={b}>{b}</li>)}</ul></div>
    </div>
    {help&&<InstallHelp onClose={()=>setHelp(false)}/>}
  </aside>;
}
