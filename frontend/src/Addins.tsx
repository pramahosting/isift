import React,{useEffect,useState} from 'react';
import {Copy,Download,Trash2} from 'lucide-react';

const GUID='6f1c2a9e-5b7d-4c3e-9a41-1d5e0b7a2c88';
const x=(s:string)=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

export function outlookManifest(origin:string,api:string){
  const pane=`${origin}/addin/outlook/taskpane.html?api=${encodeURIComponent(api)}`;
  const ic=(n:number)=>`${origin}/addin/icon-${n}.png`;
  const host=(kind:'Message'|'Appointment')=>`<ExtensionPoint xsi:type="${kind}ComposeCommandSurface"><OfficeTab id="Tab${kind}"><Group id="${kind}Group"><Label resid="Group"/><Control xsi:type="Button" id="${kind}Btn"><Label resid="Btn"/><Supertip><Title resid="Btn"/><Description resid="Tip"/></Supertip><Icon><bt:Image size="16" resid="I16"/><bt:Image size="32" resid="I32"/><bt:Image size="80" resid="I80"/></Icon><Action xsi:type="ShowTaskpane"><SourceLocation resid="Pane"/></Action></Control></Group></OfficeTab></ExtensionPoint>`;
  return `<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:bt="http://schemas.microsoft.com/office/officeappbasictypes/1.0" xmlns:mailappor="http://schemas.microsoft.com/office/mailappversionoverrides/1.0" xsi:type="MailApp">
  <Id>${GUID}</Id>
  <Version>1.0.0.0</Version>
  <ProviderName>iSift</ProviderName>
  <DefaultLocale>en-US</DefaultLocale>
  <DisplayName DefaultValue="iSift"/>
  <Description DefaultValue="Add iSift video meetings and booking links to your email and calendar invitations."/>
  <IconUrl DefaultValue="${x(ic(64))}"/>
  <HighResolutionIconUrl DefaultValue="${x(ic(128))}"/>
  <SupportUrl DefaultValue="${x(origin)}"/>
  <AppDomains><AppDomain>${x(origin)}</AppDomain></AppDomains>
  <Hosts><Host Name="Mailbox"/></Hosts>
  <Requirements><Sets><Set Name="Mailbox" MinVersion="1.5"/></Sets></Requirements>
  <FormSettings><Form xsi:type="ItemEdit"><DesktopSettings><SourceLocation DefaultValue="${x(pane)}"/></DesktopSettings></Form></FormSettings>
  <Permissions>ReadWriteItem</Permissions>
  <Rule xsi:type="RuleCollection" Mode="Or"><Rule xsi:type="ItemIs" ItemType="Message" FormType="Edit"/><Rule xsi:type="ItemIs" ItemType="Appointment" FormType="Edit"/></Rule>
  <VersionOverrides xmlns="http://schemas.microsoft.com/office/mailappversionoverrides" xsi:type="VersionOverridesV1_0">
    <VersionOverrides xmlns="http://schemas.microsoft.com/office/mailappversionoverrides/1.1" xsi:type="VersionOverridesV1_1">
      <Requirements><bt:Sets DefaultMinVersion="1.5"><bt:Set Name="Mailbox"/></bt:Sets></Requirements>
      <Hosts><Host xsi:type="MailHost"><DesktopFormFactor>
        ${host('Message')}
        ${host('Appointment')}
      </DesktopFormFactor></Host></Hosts>
      <Resources>
        <bt:Images><bt:Image id="I16" DefaultValue="${x(ic(16))}"/><bt:Image id="I32" DefaultValue="${x(ic(32))}"/><bt:Image id="I80" DefaultValue="${x(ic(80))}"/></bt:Images>
        <bt:Urls><bt:Url id="Pane" DefaultValue="${x(pane)}"/></bt:Urls>
        <bt:ShortStrings><bt:String id="Group" DefaultValue="iSift"/><bt:String id="Btn" DefaultValue="iSift meeting"/></bt:ShortStrings>
        <bt:LongStrings><bt:String id="Tip" DefaultValue="Add an iSift video meeting or a booking link."/></bt:LongStrings>
      </Resources>
    </VersionOverrides>
  </VersionOverrides>
</OfficeApp>
`;
}

function download(name:string,text:string,type='application/xml'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;document.body.appendChild(a);a.click();a.remove()}

export function AddinsTab({request,run}:{request:any;run:any}){
  const origin=location.origin;const api=origin+'/api/v1';
  const [keys,setKeys]=useState<any[]>([]);const [name,setName]=useState('Outlook');const [fresh,setFresh]=useState('');
  const [pages,setPages]=useState<any[]>([]);const [slug,setSlug]=useState('');const [mode,setMode]=useState<'inline'|'popup'>('inline');
  const load=()=>request('/account/access-keys').then((d:any)=>setKeys(d.keys||[])).catch(()=>{});
  useEffect(()=>{load();request('/booking-types').then((l:any)=>{const a=(l||[]).filter((p:any)=>p.active);setPages(a);if(a[0])setSlug(a[0].slug)}).catch(()=>{})},[]);
  const make=()=>run(async()=>{const r=await request('/account/access-keys',{method:'POST',body:JSON.stringify({name})});setFresh(r.key);load();return r},'Key created. Copy it now; it is shown only once.');
  const del=(id:string)=>run(async()=>{await request('/account/access-keys/'+id,{method:'DELETE'});load()},'Key removed.');
  const copy=(t:string)=>{try{navigator.clipboard.writeText(t)}catch{}};
  const snippet=!slug?'':mode==='inline'
    ?`<script src="${origin}/embed.js" async></script>\n<div data-isift-book="${slug}"></div>`
    :`<script src="${origin}/embed.js" async></script>\n<button data-isift-popup="${slug}">Book a meeting</button>`;
  const link=slug?`${origin}/#/book/${slug}`:'';
  return <div className="acct-body">
    <section className="panel"><h2>Put scheduling on your own website or in another application</h2>
      <p className="hint">Pick one of your booking pages. Paste the code into any web page, or use the plain link in an email or a button.</p>
      {pages.length===0?<p className="hint">You have no active booking pages yet. Create one under Meetings, Booking.</p>:<>
        <div className="grid2"><label>Booking page<select value={slug} onChange={e=>setSlug(e.target.value)}>{pages.map(p=><option key={p.id} value={p.slug}>{p.title} ({p.duration_minutes} min)</option>)}</select></label>
        <label>Style<select value={mode} onChange={e=>setMode(e.target.value as any)}><option value="inline">Inline on the page</option><option value="popup">Pop-up from a button</option></select></label></div>
        <pre className="code" aria-label="Embed code">{snippet}</pre>
        <div className="btnrow"><button onClick={()=>copy(snippet)}><Copy size={14}/> Copy code</button><button onClick={()=>copy(link)}><Copy size={14}/> Copy plain link</button></div>
        <p className="hint">Optional: add data-name and data-email to fill in the visitor's details. A page can listen for the booking with <code>window.addEventListener('isift:booked', e =&gt; …)</code>. The site that shows it must be allowed to frame iSift (see the setup guide).</p></>}
    </section>
    <section className="panel"><h2>Access keys</h2>
      <p className="hint">A key lets an add-in or another application list your booking pages and create meetings as you. It cannot change your account, password or billing. Remove it at any time.</p>
      <div className="btnrow"><input aria-label="Key name" value={name} onChange={e=>setName(e.target.value)} maxLength={80} placeholder="Name, for example Outlook"/><button className="primary" onClick={make}>Create key</button></div>
      {fresh&&<div className="notice" role="status"><b>Your new key (copy it now):</b><pre className="code">{fresh}</pre><button onClick={()=>copy(fresh)}><Copy size={14}/> Copy key</button></div>}
      <ul className="keylist">{keys.map(k=><li key={k.id}><span><b>{k.name}</b> <small>ends …{k.last4} · created {String(k.created||'').slice(0,10)}</small></span><button aria-label={'Remove key '+k.name} onClick={()=>del(k.id)}><Trash2 size={14}/> Remove</button></li>)}{keys.length===0&&<li className="hint">No keys yet.</li>}</ul>
    </section>
    <section className="panel"><h2>Microsoft Outlook add-in</h2>
      <ol className="hint"><li>Create an access key above and keep it.</li><li><button onClick={()=>download('isift-outlook-manifest.xml',outlookManifest(origin,api))}><Download size={14}/> Download the Outlook add-in file</button></li>
        <li>In Outlook on the web open <b>Get Add-ins &gt; My add-ins &gt; Custom add-ins &gt; Add from file</b> and choose the file. In Outlook for Windows use <b>Get Add-ins</b> in the same way. Your administrator can instead deploy it to everyone from the Microsoft 365 admin centre, Integrated apps.</li>
        <li>Write a new email or meeting, click <b>iSift meeting</b>, and paste your key once.</li></ol>
      <p className="hint">Outlook only loads add-ins from an HTTPS address, so iSift must be reached through https:// (not http://localhost).</p>
    </section>
  </div>;
}
