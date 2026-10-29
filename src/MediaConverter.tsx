import React,{useEffect,useRef,useState} from 'react';
import {Image as ImageIcon,Film,FileUp,Download,Trash2,LoaderCircle,CheckCircle2,CircleAlert,ArrowRight,Clock} from 'lucide-react';

type Kind='image'|'video';
type Row={key:string;name:string;state:'wait'|'up'|'run'|'done'|'err';pct?:number;msg?:string;blob?:Blob;out?:string;job?:string};
const size=(n:number)=>n>=1073741824?`${(n/1073741824).toFixed(1)} GB`:n>=1048576?`${(n/1048576).toFixed(1)} MB`:n>=1024?`${Math.round(n/1024)} KB`:`${n} bytes`;
const IMG_LABEL:Record<string,string>={jpg:'JPG',jpeg:'JPEG',png:'PNG',gif:'GIF',webp:'WebP',bmp:'BMP',tif:'TIFF',tiff:'TIFF',ico:'ICO',heic:'HEIC',avif:'AVIF',pdf:'PDF'};
const VID_LABEL:Record<string,string>={mp4:'MP4',mov:'MOV',webm:'WebM',mkv:'MKV',avi:'AVI',m4v:'M4V',wmv:'WMV',flv:'FLV',mpg:'MPG',mpeg:'MPEG','3gp':'3GP',ts:'TS',gif:'Animated GIF',mp3:'Audio only (MP3)',hevc:'MP4, compressed (H.265)',av1:'MP4, compressed (AV1)'};
const IMG_IN=['jpg','png','gif','webp','bmp','tiff','ico'];const IMG_OUT=['jpg','png','gif','webp','bmp','tiff','ico','pdf'];
const VID_IN=['mp4','mov','webm','mkv','avi','m4v','wmv','flv','mpg','3gp'];const VID_OUT=['mp4','mov','webm','mkv','avi','gif','mp3','hevc','av1'];
const PARALLEL=3;

/** Docs > Media Converter: pictures (JPG, PNG, GIF, WebP…) and videos (MP4, MOV, WebM…). Upload, pick the formats, download. Videos live only in blob storage. */
export function MediaConverter({request,requestRaw}:{request:any;requestRaw:(path:string,body:Blob,onProgress:(p:number)=>void,mode:'json'|'blob')=>Promise<any>}){
  const [kind,setKind]=useState<Kind>('image');
  const [from,setFrom]=useState('any'),[to,setTo]=useState('png'),[q,setQ]=useState('balanced');
  const [files,setFiles]=useState<File[]>([]);const [rows,setRows]=useState<Row[]>([]);const [st,setSt]=useState<any>(null);const [past,setPast]=useState<any[]>([]);
  const fileIn=useRef<HTMLInputElement>(null);const busy=rows.some(r=>r.state==='wait'||r.state==='up'||r.state==='run');
  useEffect(()=>{request('/media/status').then(setSt).catch(()=>{})},[]);
  useEffect(()=>{setFrom('any');setTo(kind==='image'?'png':'mp4');setFiles([]);setRows([])},[kind]);
  const loadPast=()=>request('/media/jobs').then((d:any)=>setPast((d.items||[]).filter((x:any)=>x.state==='done'))).catch(()=>{});
  useEffect(()=>{if(kind==='video')loadPast()},[kind]);
  const ins=kind==='image'?IMG_IN:VID_IN,outs=(kind==='image'?IMG_OUT:VID_OUT),L=kind==='image'?IMG_LABEL:VID_LABEL;
  const accept=from==='any'?(kind==='image'?'image/*,.tif,.tiff,.ico,.heic,.avif':'video/*,.mkv,.avi,.wmv,.flv,.3gp,.ts'):'.'+from+(from==='jpg'?',.jpeg':from==='tiff'?',.tif':from==='mpg'?',.mpeg':'');
  const ext=(n:string)=>(n.split('.').pop()||'').toLowerCase();
  const patch=(key:string,p:Partial<Row>)=>setRows(r=>r.map(x=>x.key===key?{...x,...p}:x));
  const choose=(e:React.ChangeEvent<HTMLInputElement>)=>{const l=Array.from(e.target.files||[]);e.target.value='';setRows([]);
    if(from!=='any'){const ok=l.filter(f=>{const x=ext(f.name);return x===from||(from==='jpg'&&x==='jpeg')||(from==='tiff'&&x==='tif')||(from==='mpg'&&x==='mpeg')});if(ok.length!==l.length)setRows([{key:'x',name:'Some files were skipped',state:'err',msg:`They are not ${L[from]||from.toUpperCase()} files. Choose "Any" to convert every type.`}]);setFiles(ok)}else setFiles(l)};
  const save=(blob:Blob,name:string)=>{const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),30000)};
  const wait=(ms:number)=>new Promise(r=>setTimeout(r,ms));
  const one=async(f:File,key:string)=>{
    patch(key,{state:'up',pct:0});
    if(kind==='image'){const r=await requestRaw(`/media/image?filename=${encodeURIComponent(f.name)}&to=${to}`,f,p=>patch(key,{pct:p}),'blob');patch(key,{state:'done',blob:r.blob,out:r.filename||f.name.replace(/\.[^.]+$/,'')+'.'+to,msg:size(r.blob.size)});save(r.blob,r.filename||f.name.replace(/\.[^.]+$/,'')+'.'+to);return}
    const r=await requestRaw(`/media/video?filename=${encodeURIComponent(f.name)}&to=${to}&quality=${q}`,f,p=>patch(key,{pct:p}),'json');
    patch(key,{state:'run',pct:0,job:r.id});
    let fails=0;for(;;){await wait(3000);let d:any;try{d=await request('/media/jobs');fails=0}catch{fails++;patch(key,{msg:'Waiting for the server…'});if(fails>40){patch(key,{state:'err',msg:'The server stopped answering. The conversion may have been interrupted. Check “Your converted videos” below, or try again.'});loadPast();return}continue}const j=(d.items||[]).find((x:any)=>x.id===r.id);if(!j){patch(key,{state:'err',msg:'The server restarted during the conversion, so it was lost. Please try again.'});return}
      if(j.state==='error'){patch(key,{state:'err',msg:j.error||'The conversion failed.'});return}
      if(j.state==='done'){patch(key,{state:'done',job:r.id,out:j.out_name,msg:size(j.out_size||0)});loadPast();return}
      patch(key,{pct:j.progress||0,msg:j.state==='saving'?'Saving…':''})}};
  const start=async()=>{const list=files.map((f,i)=>({f,key:'f'+i+Date.now()}));setRows(list.map(x=>({key:x.key,name:x.f.name,state:'wait' as const})));
    let n=0;const w=async()=>{while(n<list.length){const x=list[n++];try{await one(x.f,x.key)}catch(e:any){patch(x.key,{state:'err',msg:e?.message||'The conversion did not finish.'})}}};
    await Promise.all(Array.from({length:Math.min(kind==='video'?1:PARALLEL,list.length)},w))};
  const dlJob=async(id:string)=>{try{const d=await request(`/media/${id}/url`);const a=document.createElement('a');a.href=d.url;a.download=d.name;document.body.appendChild(a);a.click();a.remove()}catch(e:any){alert(e.message)}};
  const rmJob=async(id:string)=>{try{await request(`/media/${id}`,{method:'DELETE'});setRows(r=>r.filter(x=>x.job!==id));loadPast()}catch{}};
  const blocked=kind==='video'&&st&&!st.r2;
  const Ic=(r:Row)=>r.state==='done'?<CheckCircle2 size={15} className="ok"/>:r.state==='err'?<CircleAlert size={15} className="bad"/>:r.state==='wait'?<Clock size={15}/>:<LoaderCircle size={15} className="spin"/>;
  return <div className="dconv mconv">
    <div className="dconv-modes" role="tablist" aria-label="Media type">
      <button type="button" role="tab" aria-selected={kind==='image'} className={`dconv-mode${kind==='image'?' on':''}`} onClick={()=>setKind('image')}><ImageIcon size={16}/> Image converter</button>
      <button type="button" role="tab" aria-selected={kind==='video'} className={`dconv-mode${kind==='video'?' on':''}`} onClick={()=>setKind('video')}><Film size={16}/> Video converter</button></div>
    <section className="panel dconv-panel">
      <h2>{kind==='image'?'Convert pictures':'Convert videos'}</h2>
      <p className="muted">{kind==='image'?'Choose the format you have and the format you want, upload your pictures, and each converted picture downloads straight away. Pictures are not kept on the server.':'Choose the format you have and the format you want, upload your video, and download the result when it is ready. Videos are kept only in blob storage and removed after 3 days.'}</p>
      {blocked&&<p className="syncerr" role="alert">Videos are kept only in blob storage and it is not set up yet. An administrator can set up Cloudflare R2 in Admin Console, API and Settings.</p>}
      <div className="mconv-row">
        <label>From<select value={from} onChange={e=>{setFrom(e.target.value);setFiles([]);setRows([])}}><option value="any">Any {kind==='image'?'picture':'video'}</option>{ins.map(x=><option key={x} value={x}>{L[x]||x.toUpperCase()}</option>)}</select></label>
        <ArrowRight size={18} className="mconv-arrow"/>
        <label>To<select value={to} onChange={e=>setTo(e.target.value)}>{outs.map(x=><option key={x} value={x}>{L[x]||x.toUpperCase()}</option>)}</select></label>
        {kind==='video'&&(to==='hevc'||to==='av1')&&<label>Quality<select value={q} onChange={e=>setQ(e.target.value)}><option value="small">Smallest file</option><option value="balanced">Balanced (recommended)</option><option value="high">Highest quality</option></select></label>}</div>
      {kind==='video'&&(to==='hevc'||to==='av1')&&<p className="muted small">{to==='hevc'?'H.265 (HEVC) keeps the picture sharp at roughly half the size of a normal MP4 (H.264), and plays on current phones, Macs and browsers on Apple devices; some older Windows players need an extra codec.':'AV1 is the newest codec and compresses very well for web streaming. It plays in current Chrome, Edge and Firefox and on newer phones; older devices may not play it. Converting can take longer.'} The result is saved as {`<name>-compressed.mp4`}.</p>}
      <div className="actions"><button type="button" className="secondary" disabled={busy||!!blocked} onClick={()=>fileIn.current?.click()}><FileUp size={15}/> {files.length?(files.length===1?files[0].name:`${files.length} files chosen`):`Upload ${kind==='image'?'pictures':'videos'} from your computer`}</button>
        <input ref={fileIn} type="file" multiple={kind==='image'} accept={accept} hidden onChange={choose}/>{files.length>0&&!busy&&<button type="button" className="textbtn" onClick={()=>{setFiles([]);setRows([])}}>Clear</button>}
        <button type="button" className="primary" disabled={busy||!files.length||!!blocked} onClick={start}><Download size={15}/> Convert to {L[to]||to.toUpperCase()}</button></div>
      {rows.length>0&&<ul className="dconv-jobs" aria-live="polite">{rows.map(r=><li key={r.key} className={r.state}><span className="dconv-ic">{Ic(r)}</span><span className="dconv-nm">{r.name}</span>
        <small className={r.state==='err'?'syncerr':'muted'}>{r.state==='wait'?'Waiting':r.state==='up'?`Uploading ${Math.round((r.pct||0)*100)}%`:r.state==='run'?`Converting ${Math.round((r.pct||0)*100)}%${r.msg?' · '+r.msg:''}`:r.state==='done'?`${r.out} · ${r.msg}`:r.msg||''}</small>
        {r.state==='done'&&kind==='image'&&r.blob&&<button type="button" className="textbtn" onClick={()=>save(r.blob!,r.out||'picture')}><Download size={13}/> Download</button>}
        {r.state==='done'&&kind==='video'&&r.job&&<><button type="button" className="textbtn" onClick={()=>dlJob(r.job!)}><Download size={13}/> Download</button></>}</li>)}</ul>}
      {kind==='video'&&past.length>0&&<><h3 className="mconv-h">Your converted videos</h3><ul className="dconv-jobs">{past.map(p=><li key={p.id} className="done"><span className="dconv-ic"><CheckCircle2 size={15} className="ok"/></span><span className="dconv-nm">{p.out_name}</span><small className="muted">{size(p.out_size||0)} · kept for 3 days</small>
        <button type="button" className="textbtn" onClick={()=>dlJob(p.id)}><Download size={13}/> Download</button><button type="button" className="textbtn" aria-label={`Delete ${p.out_name}`} onClick={()=>rmJob(p.id)}><Trash2 size={13}/> Delete</button></li>)}</ul></>}
    </section></div>;
}
