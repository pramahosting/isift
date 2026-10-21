import React from 'react';
import {Check,X,Minus,Layers,ListChecks,ShieldCheck,CalendarClock,FileSignature,Armchair,Lock,Phone,BadgeDollarSign,ArrowRight,LayoutGrid,MonitorUp,PlayCircle} from 'lucide-react';
import {useLivePlans,money} from './Pricing';

/** Landing page sections: what happens after a meeting, why iSift, an honest comparison, and how data is handled. */

export function OutcomeSection(){
  return <section className="landing-section" id="outcome"><p className="eyebrow">THE DIFFERENCE</p><h2>The meeting ends. The work is already sorted.</h2>
    <div className="ba-grid">
      <div className="ba-card before"><h3>With most meeting tools</h3><ul>
        <li>The call ends and you are left with a recording.</li><li>You write the minutes from memory, an hour later.</li><li>Actions live in someone’s notebook and get chased by email.</li><li>Booking, mail, documents and PDFs are four other apps.</li></ul></div>
      <div className="ba-arrow" aria-hidden="true"><ArrowRight size={26}/></div>
      <div className="ba-card after"><h3>With iSift</h3><ul>
        <li><Check size={15}/> Minutes are drafted from the transcript, and a person reviews them before they go out.</li>
        <li><Check size={15}/> Every action item has an owner and a due date, and shows up where the work happens.</li>
        <li><Check size={15}/> A morning briefing tells you what is on today and what is still open.</li>
        <li><Check size={15}/> Booking, mail, calendar, notes, whiteboard and PDF signing sit beside the meeting.</li></ul></div>
    </div></section>;
}

const WHY=[
 {i:Layers,t:'One workspace, not six tabs',d:'Video meetings, a Calendly-style booking page, mail, calendar and contacts, notes, whiteboard and PDF signing, all signed in once and all linked to the meeting they belong to.'},
 {i:ListChecks,t:'Follow-through, not just a summary',d:'Most tools stop at a recap. iSift turns the conversation into minutes, owned action items and a briefing before your next meeting.'},
 {i:ShieldCheck,t:'AI-empowered, human-approved',d:'Draft minutes and actions are marked for review. Nothing is sent as final until someone checks it, which matters for clients, boards and regulated work.'},
 {i:CalendarClock,t:'Booking pages built in',d:'Share a link and let people pick a free time. Each booking lands in your calendar with a meeting room attached. No second subscription.'},
 {i:FileSignature,t:'Edit and sign PDFs in the browser',d:'Change text, add shapes, draw a signature, sign with your own certificate. The file is not stored on our servers.'},
 {i:LayoutGrid,t:'A meeting screen that feels like Zoom',d:'A clean toolbar with only what you need, and a More menu for the rest: pin the tools you use. Reactions, raise hand, live captions with a saveable transcript, waiting room, lock meeting and hide profile pictures. On a phone you are large on the first screen and everyone else swipes in after.'},
 {i:MonitorUp,t:'Share together, point and draw',d:'Share a whole screen, one window or one browser tab, with its sound. Let several people share at once, side by side, and hand someone the pen to point and draw on your screen, then take it back.'},
 {i:PlayCircle,t:'Watch a video together',d:'Paste a YouTube link and everyone watches in sync on their own device, phones included. You play, pause and skip for the whole meeting.'},
 {i:Armchair,t:'Meeting rooms people enjoy',d:'A virtual boardroom with a wooden table, name plates, windows and your own background, or a simple gallery view. Switch with one button.'},
 {i:Phone,t:'Call a teammate in one click',d:'Ring another iSift user like a phone call. They accept and you are in a private room together.'},
 {i:Lock,t:'You stay in control',d:'Recordings save on the host’s own computer by default. Administrators set what each person may use: call time, recording, documents, Commbox and more.'},
 {i:BadgeDollarSign,t:'Plain, local pricing',d:'Free, Standard and Business. Pick how many participants you need from a dropdown, in your currency, and yearly saves you money. No per-feature add-ons to work out.'},
];
export function WhySection(){
  return <section className="landing-section" id="why-isift"><p className="eyebrow">WHY ISIFT</p><h2>Everything around the meeting, in one calm place.</h2>
    <p className="why-lead">iSift is built for people whose work happens in meetings: advisers, consultants, small teams and anyone who is tired of stitching tools together.</p>
    <div className="why-grid">{WHY.map(w=><article key={w.t} className="why-card"><span className="why-ic"><w.i size={20}/></span><h3>{w.t}{/AI/.test(w.t)&&<i className="ai-tag">AI</i>}</h3><p>{w.d}</p></article>)}</div></section>;
}

type Cell=string|true|false|null;
const Y=true,N=false;
const COLS=['iSift','Zoom','Calendly','Cal.com','Microsoft Teams','Google Meet','PDF editors'];
const SUB=['','','','','','','Sejda, Adobe Acrobat'];
const ROWS:{label:string;cells:Cell[]}[]=[
 {label:'Video meetings in the browser',cells:[Y,Y,'Uses other tools',Y,Y,Y,N]},
 {label:'Free plan: group meeting length',cells:['70 minutes','40 minutes',null,null,'60 minutes','60 minutes',null]},
 {label:'Booking pages, like Calendly',cells:[Y,Y,Y,Y,'Paid plans (Bookings)','Via Google Calendar',N]},
 {label:'AI minutes and action items',cells:['Yes, AI drafts and a person reviews','Yes (paid plans)','Recaps and actions','Credits on paid plans','Needs Copilot add-on','Gemini, paid plans',null]},
 {label:'PDF edit and sign inside the product',cells:[Y,'Separate app',N,N,'Separate app','Separate app',Y]},
 {label:'Mail, calendar and contacts in the same app',cells:['Yes (paid plans)','Some','No','No','Outlook, separate','Gmail, separate',N]},
 {label:'Whiteboard and documents',cells:[Y,Y,N,N,'Paid plans','Separate app',N]},
 {label:'Reactions, raise hand and live captions',cells:[Y,Y,N,N,Y,Y,N]},
 {label:'Several people sharing at once, with pointer and pen',cells:['Yes (paid plans)','Yes (host option)',N,N,null,null,N]},
 {label:'Watch a YouTube video together, in sync',cells:['Yes (paid plans)',null,N,N,null,null,N]},
 {label:'Take control of someone’s computer',cells:['Not yet (pointer and pen instead)',Y,N,N,Y,null,N]},
 {label:'Call another user inside the app',cells:['Yes (paid plans)',Y,N,N,Y,Y,N]},
 {label:'Calls to real phone numbers',cells:['Not yet','Zoom Phone (extra)',N,N,'Teams Phone (extra)','Google Voice (extra)',N]},
];
function Mark({v}:{v:Cell}){
  if(v===true)return <span className="cmp-yes" aria-label="Yes"><Check size={16}/></span>;
  if(v===false)return <span className="cmp-no" aria-label="No"><X size={15}/></span>;
  if(v===null)return <span className="cmp-na" aria-label="Not stated"><Minus size={14}/></span>;
  return <span className="cmp-txt">{v}</span>;
}
export function CompareSection(){
  const live=useLivePlans();const lo=live.tiersOf('individual')[0]?.n||10;const ind=live.prices('individual',lo);
  const price:Cell[]=[`${money(ind.perMonthYearly,live.currency)} a month (${lo} people)`,'US$14.16 (Pro)','US$10 (Standard)','US$15 (Teams)','Part of Microsoft 365','US$7 (Workspace Starter)','Varies'];
  return <section className="landing-section" id="compare"><p className="eyebrow">HOW ISIFT COMPARES</p><h2>Where iSift fits next to the tools you already know.</h2>
    <p className="why-lead">Zoom, Teams and Meet are strongest for large meetings. Calendly and Cal.com are strongest for scheduling. PDF editors do one job well. iSift brings the everyday parts of all of them together for one person or a small team.</p>
    <div className="cmp-wrap" role="region" aria-label="Comparison table" tabIndex={0}><table className="cmp">
      <thead><tr><th scope="col"></th>{COLS.map((c,i)=><th key={c} scope="col" className={i===0?'me':''}>{c}{SUB[i]&&<small>{SUB[i]}</small>}</th>)}</tr></thead>
      <tbody>{ROWS.map(r=><tr key={r.label}><th scope="row">{r.label}</th>{r.cells.map((c,i)=><td key={i} className={i===0?'me':''}><Mark v={c}/></td>)}</tr>)}
        <tr><th scope="row">Paid plan from (billed yearly, per host)</th>{price.map((c,i)=><td key={i} className={i===0?'me':''}><Mark v={c}/></td>)}</tr></tbody></table></div>
    <p className="cmp-note">Based on each product’s published plans, checked in October 2026. Competitor prices are in US dollars; iSift’s price is in {live.currency}. Plans and features change, so check each vendor before you decide. “Separate app” means it is not part of the core product. iSift does not do webinars, very large meetings, calls to phone numbers or remote control of another computer yet.</p></section>;
}

export function TrustSection(){
  const items=[
   ['Encrypted connection','All traffic uses HTTPS. Passwords are stored as salted hashes, and saved API keys are encrypted.'],
   ['Recordings stay with you','Recordings save on the host’s own computer by default. A cloud copy is only made if the host chooses it.'],
   ['Your files are not kept','PDFs you edit or sign are processed for your request and sent straight back. They are not stored.'],
   ['A person approves the AI','Minutes and action items are drafts until someone reviews them. The Privacy page lists every provider we use and what it does.'],
  ];
  return <section className="landing-section" id="trust"><p className="eyebrow">TRUST</p><h2>Clear about your data.</h2>
    <div className="why-grid four">{items.map(([t,d])=><article key={t} className="why-card"><span className="why-ic"><ShieldCheck size={20}/></span><h3>{t}</h3><p>{d}</p></article>)}</div></section>;
}
