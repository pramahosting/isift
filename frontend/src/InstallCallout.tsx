import React,{useEffect,useState} from 'react';
import {ArrowUpRight,Check} from 'lucide-react';
import {installReady,runInstall,runningAsApp,InstallHelp} from './HomeWorkspace';

// Shown to anyone whose browser can install iSift but has not yet: a box, bottom right, that points up and to the right at the browser's install button.
// (Bottom right, not top right: the top of every page holds buttons that a box with no close button would cover for good.)
// Hover (or tab to) the box to see what installing gives them. It has no close button; it goes away on its own once iSift is installed,
// and it never appears in the installed app, in a meeting, or on a phone.
const BENEFITS=['Opens in its own window, with no browser tabs','The iSift logo on your taskbar and Start menu, one click away','Meeting links open straight in the app','Starts faster and remembers you'];

export default function InstallCallout(){
  const [ready,setReady]=useState(()=>installReady());      // the browser only offers installation when iSift is not installed on this computer
  const [done,setDone]=useState(false);const [help,setHelp]=useState(false);
  const [inRoom,setInRoom]=useState(()=>/^#\/room\//.test(location.hash));
  useEffect(()=>{
    const on=()=>setReady(true);const gone=()=>{setReady(false);setDone(true)};const hash=()=>setInRoom(/^#\/room\//.test(location.hash));
    window.addEventListener('isift:installable',on);window.addEventListener('appinstalled',gone);window.addEventListener('hashchange',hash);
    return()=>{window.removeEventListener('isift:installable',on);window.removeEventListener('appinstalled',gone);window.removeEventListener('hashchange',hash)}},[]);
  useEffect(()=>{if(!done)return;const t=setTimeout(()=>setDone(false),15000);return()=>clearTimeout(t)},[done]);
  if(done)return <div className="inst-done" role="status"><span className="inst-done-ic"><Check size={16}/></span><span><b>iSift is installed</b><small>Its logo is now in your Start menu and on the taskbar while it is open. To keep it there, right-click the logo on the taskbar and choose Pin to taskbar.</small></span></div>;
  if(!ready||inRoom||runningAsApp())return null;
  const go=async()=>{if(!(await runInstall()))setHelp(true)};
  return <aside className="inst-callout" aria-label="Install iSift">
    <div className="inst-co-box" tabIndex={0} aria-describedby="inst-co-tip">
      <span className="inst-co-head"><span className="inst-co-pt" aria-hidden="true"><ArrowUpRight size={18}/></span><b>Install iSift on this computer</b></span>
      <span className="inst-co-text">Press <b>Install</b>, or use the install icon at the top right of your browser, at the end of the address bar.</span>
      <button type="button" className="primary" onClick={go}>Install</button>
      <div className="inst-co-tip" id="inst-co-tip" role="tooltip"><b>Why install iSift?</b><ul>{BENEFITS.map(b=><li key={b}>{b}</li>)}</ul></div>
    </div>
    {help&&<InstallHelp onClose={()=>setHelp(false)}/>}
  </aside>;
}
