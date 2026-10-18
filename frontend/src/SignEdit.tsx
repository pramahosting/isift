import {useCallback,useEffect,useRef,useState} from 'react';
import {Plus,ChevronsLeft,ChevronsRight,FileSignature,Move,Upload,Type,Eraser,PenLine,Check,Download,Trash2,X,Pencil,FilePlus2,Undo2,ShieldCheck,KeyRound,FolderOpen,FileText,Redo2} from 'lucide-react';

/* Sign & Edit PDF: upload a PDF or Word file, add or delete text, place a drawn signature, then Apply, Revert or Download.
   The file is never kept on the server. Changes are staged here, and Apply sends the current file plus the staged changes to be edited. */

type Sig={id?:string;name?:string;png:string};
type Doc={name:string;kind:'pdf'|'docx';b64:string;info:any};
const MIME:Record<string,string>={pdf:'application/pdf',docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'};
const toB64=(f:File,onP?:(p:number)=>void)=>new Promise<string>((ok,no)=>{const r=new FileReader();if(onP)r.onprogress=e=>{if(e.lengthComputable)onP(e.loaded/e.total)};r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(new Error('The file could not be read.'));r.readAsDataURL(f)});
const uid=()=>Math.random().toString(36).slice(2,9);
const COLORS=['#111827','#1d4ed8','#b91c1c'];

/* The list of files you have uploaded and edited. It lives in this browser only (IndexedDB), never on the server, so the files stay private. */
type Meta={id:string;name:string;kind:'pdf'|'docx';applied:number;uploaded:number;edited:number;size:number};
type Blobs={id:string;orig:string;cur:string};
const KEEP=20;
const dbp=(u:string)=>new Promise<IDBDatabase>((ok,no)=>{try{const r=indexedDB.open('isift-signedit-'+(u||'me'),1);r.onupgradeneeded=()=>{const d=r.result;d.createObjectStore('meta',{keyPath:'id'});d.createObjectStore('blob',{keyPath:'id'})};r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)}catch(e){no(e)}});
const idb=<T,>(u:string,store:string,mode:IDBTransactionMode,f:(s:IDBObjectStore)=>IDBRequest<T>)=>dbp(u).then(d=>new Promise<T>((ok,no)=>{const t=d.transaction(store,mode);const rq=f(t.objectStore(store));t.oncomplete=()=>{d.close();ok(rq.result)};t.onerror=t.onabort=()=>{d.close();no(t.error)}}));
const histList=(u:string)=>idb<Meta[]>(u,'meta','readonly',s=>s.getAll()).then(a=>a.sort((x,y)=>y.edited-x.edited)).catch(()=>[] as Meta[]);
const histBlobs=(u:string,id:string)=>idb<Blobs|undefined>(u,'blob','readonly',s=>s.get(id));
const histSave=async(u:string,m:Meta,b:{orig?:string;cur:string})=>{try{const old=await histBlobs(u,m.id);await idb(u,'blob','readwrite',s=>s.put({id:m.id,orig:b.orig??old?.orig??b.cur,cur:b.cur}));await idb(u,'meta','readwrite',s=>s.put(m));
  const all=await histList(u);for(const x of all.slice(KEEP)){await idb(u,'meta','readwrite',s=>s.delete(x.id));await idb(u,'blob','readwrite',s=>s.delete(x.id))}}catch{/* storage unavailable: editing still works, the list just is not kept */}};
const histDelete=async(u:string,id:string)=>{try{await idb(u,'meta','readwrite',s=>s.delete(id));await idb(u,'blob','readwrite',s=>s.delete(id))}catch{}};
const saveFile=(b64:string,kind:'pdf'|'docx',name:string)=>{const bin=atob(b64),u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);const url=URL.createObjectURL(new Blob([u],{type:MIME[kind]}));const a=document.createElement('a');a.href=url;a.download=name.replace(/(\.[^.]+)$/,'-edited$1');document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000)};
const when=(t:number)=>new Date(t).toLocaleString(undefined,{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});

/* Draw a signature with the mouse, finger or pen. Returns a PNG cropped to the ink, with a transparent background. */
function SignaturePad({onDone,saved,onDelete,onUse,canSave}:{onDone:(s:Sig,keep:boolean,name:string)=>void;saved:Sig[];onDelete:(s:Sig)=>void;onUse:(s:Sig)=>void;canSave:boolean}){
  const cv=useRef<HTMLCanvasElement>(null);const down=useRef(false);const [ink,setInk]=useState(false);const [keep,setKeep]=useState(canSave);const [name,setName]=useState('My signature');const [color,setColor]=useState(COLORS[1]);
  const pos=(e:React.PointerEvent)=>{const c=cv.current!,r=c.getBoundingClientRect();return [(e.clientX-r.left)*c.width/r.width,(e.clientY-r.top)*c.height/r.height]};
  const start=(e:React.PointerEvent)=>{const c=cv.current!,g=c.getContext('2d')!;c.setPointerCapture(e.pointerId);down.current=true;const [x,y]=pos(e);g.strokeStyle=color;g.lineWidth=3;g.lineCap='round';g.lineJoin='round';g.beginPath();g.moveTo(x,y);g.lineTo(x+.1,y+.1);g.stroke();setInk(true)};
  const move=(e:React.PointerEvent)=>{if(!down.current)return;const g=cv.current!.getContext('2d')!;const [x,y]=pos(e);g.lineTo(x,y);g.stroke()};
  const end=()=>{down.current=false};
  const clear=()=>{const c=cv.current!;c.getContext('2d')!.clearRect(0,0,c.width,c.height);setInk(false)};
  const finish=()=>{const c=cv.current!,g=c.getContext('2d')!,d=g.getImageData(0,0,c.width,c.height).data;let x0=c.width,y0=c.height,x1=0,y1=0;
    for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++)if(d[(y*c.width+x)*4+3]>8){if(x<x0)x0=x;if(x>x1)x1=x;if(y<y0)y0=y;if(y>y1)y1=y}
    if(x1<=x0||y1<=y0)return;const p=6,w=x1-x0+1+p*2,h=y1-y0+1+p*2,o=document.createElement('canvas');o.width=w;o.height=h;o.getContext('2d')!.drawImage(c,x0-p,y0-p,w,h,0,0,w,h);
    onDone({png:o.toDataURL('image/png'),name},keep,name);clear()};
  return <div className="se-sigpad"><b>Draw your signature</b><canvas ref={cv} width={560} height={180} className="se-canvas" aria-label="Signature drawing area" onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={end}/>
    <div className="se-row"><span className="muted small">Ink</span>{COLORS.map(c=><button key={c} type="button" className={`se-swatch${color===c?' on':''}`} style={{background:c}} aria-label={'Ink colour '+c} onClick={()=>setColor(c)}/>)}<button type="button" className="textbtn" onClick={clear}><Eraser size={14}/> Clear</button></div>
    {canSave&&<div className="se-row"><label className="check"><input type="checkbox" checked={keep} onChange={e=>setKeep(e.target.checked)}/> Save this signature for future use</label>{keep&&<input aria-label="Signature name" value={name} maxLength={40} onChange={e=>setName(e.target.value)} placeholder="Name it"/>}</div>}
    <div className="se-row"><button type="button" className="primary" disabled={!ink} onClick={finish}><Check size={15}/> Use this signature</button></div>
    {saved.length>0&&<div className="se-saved"><b>Saved signatures</b>{saved.map(s=><div key={s.id} className="se-savedrow"><img src={s.png} alt={s.name||'Saved signature'}/><span>{s.name}</span><button type="button" className="secondary" onClick={()=>onUse(s)}>Use</button><button type="button" className="iconbtn" aria-label={'Delete saved signature '+s.name} onClick={()=>onDelete(s)}><Trash2 size={15}/></button></div>)}</div>}
  </div>;
}

type Op={id:string;t:'text'|'delete'|'sign'|'replace'|'add';page?:number;rect?:number[];x?:number;y?:number;size?:number;track?:number;cover?:number[];fill?:string;color?:string;text?:string;png?:string;i?:number;after?:number;width?:number};

/* Look at the page picture itself to find exactly where a line of text is drawn, how big it is, how widely its letters are spaced, its colour and the colour of the paper behind it.
   This works whether the text is real text or part of a picture, so the replacement can match the original and the old text can be covered. */
const imgCache=new Map<string,Promise<HTMLImageElement>>();
const loadImg=(src:string)=>{let p=imgCache.get(src);if(!p){p=new Promise<HTMLImageElement>((ok,no)=>{const i=new Image();i.onload=()=>ok(i);i.onerror=no;i.src=src});imgCache.set(src,p);if(imgCache.size>6)imgCache.delete(imgCache.keys().next().value as string)}return p};
const hex=(r:number,g:number,b:number)=>'#'+[r,g,b].map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('');
const med=(a:number[])=>{if(!a.length)return 255;const b=[...a].sort((x,y)=>x-y);return b[b.length>>1]};
async function analyse(pg:any,l:any){
  try{const img=await loadImg(pg.image);const s=img.naturalWidth/pg.w;const [x0,y0,x1,y1]=l.bbox as number[];const h=Math.max(6,y1-y0);
    const wx0=Math.max(0,Math.floor((x0-3)*s)),wx1=Math.min(img.naturalWidth,Math.ceil((x1+3)*s)),wy0=Math.max(0,Math.floor((y0-2.2*h)*s)),wy1=Math.min(img.naturalHeight,Math.ceil((y1+2.2*h)*s));
    const W=wx1-wx0,H=wy1-wy0;if(W<4||H<4)return null;const cv=document.createElement('canvas');cv.width=W;cv.height=H;const g=cv.getContext('2d',{willReadFrequently:true})!;g.drawImage(img,wx0,wy0,W,H,0,0,W,H);const d=g.getImageData(0,0,W,H).data;
    const luma=(k:number)=>.299*d[k]+.587*d[k+1]+.114*d[k+2];const dark=(x:number,y:number)=>luma((y*W+x)*4)<120;
    const rows=new Array(H).fill(0);for(let y=0;y<H;y++)for(let x=0;x<W;x++)if(dark(x,y))rows[y]++;
    /* the band of rows with the most ink is the text; thin tick marks and neighbouring lines count for less */
    let best:[number,number,number]|null=null;let y=0;while(y<H){if(rows[y]>0){let a=y,e=y,sum=0;while(e<H&&(rows[e]>0||(e+1<H&&rows[e+1]>0))){sum+=rows[e];e++}e--;const ht=e-a+1;if(ht>=.35*h*s&&ht<=3*h*s&&(!best||sum>best[2]))best=[a,e,sum];y=e+1}else y++}
    if(!best)return null;const [ra,rb]=best;let ca=W,cb=-1;for(let x=0;x<W;x++)for(let yy=ra;yy<=rb;yy++)if(dark(x,yy)){if(x<ca)ca=x;if(x>cb)cb=x;break}
    if(cb<ca)return null;
    const L=(wx0+ca)/s,R=(wx0+cb+1)/s,T=(wy0+ra)/s,B=(wy0+rb+1)/s;
    const ring:number[][]=[[],[],[]];const take=(x:number,yy:number)=>{if(x<0||yy<0||x>=W||yy>=H)return;const k=(yy*W+x)*4;if(luma(k)>150){ring[0].push(d[k]);ring[1].push(d[k+1]);ring[2].push(d[k+2])}};
    for(let x=ca-3;x<=cb+3;x++){take(x,ra-3);take(x,rb+3)}for(let yy=ra-3;yy<=rb+3;yy++){take(ca-3,yy);take(cb+3,yy)}
    const inkPx:number[][]=[];for(let yy=ra;yy<=rb;yy++)for(let x=ca;x<=cb;x++){const k=(yy*W+x)*4;if(luma(k)<120)inkPx.push([luma(k),d[k],d[k+1],d[k+2]])}
    inkPx.sort((p,q)=>p[0]-q[0]);const dk=inkPx.slice(0,Math.max(1,Math.floor(inkPx.length*.3)));
    const color=hex(med(dk.map(p=>p[1])),med(dk.map(p=>p[2])),med(dk.map(p=>p[3])));const fill=hex(med(ring[0]),med(ring[1]),med(ring[2]));
    const txt:string=String(l.text||'');const desc=/[gjpqy,;()]/.test(txt);const ink=B-T;const size=Math.max(6,Math.min(72,ink/(desc?.93:.716)));const base=desc?B-.21*size:B;
    const m=document.createElement('canvas').getContext('2d')!;m.font=`${size}px Helvetica, Arial, sans-serif`;const nat=m.measureText(txt).width;const n=[...txt].length;
    const track=n>1?Math.max(0,((R-L)-(nat-.12*size))/(n-1)):0;
    return {rect:[L-1.5,T-1.5,R+1.5,B+1.5] as number[],x:L-.07*size,base,size:Math.round(size*10)/10,track:track>.4?Math.round(track*100)/100:0,color,fill}
  }catch{return null}
}

function PdfView({info,ops,setOps,tool,sig,size,color,locked}:{info:any;ops:Op[];setOps:(f:(o:Op[])=>Op[])=>void;tool:string;sig:Sig|null;size:number;color:string;locked:boolean}){
  const [editing,setEditing]=useState<string|null>(null);
  /* Drag text in any direction. A click without movement edits it. */
  const dragText=(o:Op,f:number)=>(e:React.PointerEvent)=>{const grab=!!(e.target as HTMLElement).closest('.se-grab');if(locked||(editing===o.id&&!grab)||(e.target as HTMLElement).closest('button'))return;e.stopPropagation();if(grab)e.preventDefault();const sx=e.clientX,sy=e.clientY,x0=o.x!,y0=o.y!;let moved=false;
    const mv=(ev:PointerEvent)=>{const dx=ev.clientX-sx,dy=ev.clientY-sy;if(!moved&&Math.hypot(dx,dy)<4)return;moved=true;setOps(all=>all.map(a=>a.id===o.id?{...a,x:Math.max(0,x0+dx/f),y:Math.max(0,y0+dy/f)}:a))};
    const up=()=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',up);if(!moved&&!grab)setEditing(o.id)};
    window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up);window.addEventListener('pointercancel',up)};
  /* Finish typing: empty text is dropped; a changed line that was left as it was goes back to the original. */
  const finishText=(o:Op)=>{setEditing(null);setOps(a=>{const pair=o.id.endsWith('r')?a.find(x=>x.id===o.id.slice(0,-1)&&x.t==='delete'):undefined;
    if(!(o.text||'').trim())return a.filter(x=>x.id!==o.id);
    if(pair&&pair.text===o.text&&pair.rect&&Math.abs((o.x||0)-pair.rect[0])<.5&&Math.abs((o.y||0)-pair.rect[1])<.5)return a.filter(x=>x.id!==o.id&&x.id!==pair.id);return a})};
  return <div className="se-pages">{info.pages.map((pg:any,pi:number)=>{
    const W=Math.min(760,pg.w*1.25),f=W/pg.w;const mine=ops.filter(o=>o.page===pi);
    const clickPage=(e:React.MouseEvent<HTMLDivElement>)=>{if(locked||e.target!==e.currentTarget&&!(e.target as HTMLElement).classList.contains('se-img'))return;const r=e.currentTarget.getBoundingClientRect(),x=(e.clientX-r.left)/f,y=(e.clientY-r.top)/f;
      if(tool==='text'){const id=uid();setOps(o=>[...o,{id,t:'text',page:pi,x,y,size,color,text:''}]);setEditing(id)}
      else if(tool==='sign'&&sig){const img=new Image();img.onload=()=>{const w=150,h=w*img.height/img.width;setOps(o=>[...o,{id:uid(),t:'sign',page:pi,rect:[x,y,x+w,y+h],png:sig.png}])};img.src=sig.png}};
    const lineClick=async(l:any)=>{if(locked)return;
      if(tool==='delete'){const had=ops.find(o=>o.t==='delete'&&o.page===pi&&o.rect![0]===l.bbox[0]&&o.rect![1]===l.bbox[1]);if(had){setOps(o=>o.filter(x=>x!==had));return}}
      const a=await analyse(pg,l);const del:Op={id:uid(),t:'delete',page:pi,rect:l.bbox,text:l.text,...(a?{cover:a.rect,fill:a.fill}:{})};
      if(tool==='delete')setOps(o=>[...o,del]);
      else if(tool==='replace'){const size=a?a.size:l.size;setOps(o=>[...o,del,{id:del.id+'r',t:'text',page:pi,x:a?a.x:l.bbox[0],y:(a?a.base:(l.base??l.bbox[3]))-size*.9465,size,color:a?a.color:'#111827',text:l.text,track:a?a.track:(l.track||0)}]);setEditing(del.id+'r')}};
    const drag=(o:Op,mode:'move'|'size')=>(e:React.PointerEvent)=>{e.stopPropagation();e.preventDefault();const sx=e.clientX,sy=e.clientY,r0=[...o.rect!];const t=e.currentTarget as HTMLElement;t.setPointerCapture(e.pointerId);
      const mv=(ev:PointerEvent)=>{const dx=(ev.clientX-sx)/f,dy=(ev.clientY-sy)/f;setOps(all=>all.map(a=>{if(a.id!==o.id)return a;if(mode==='move')return {...a,rect:[r0[0]+dx,r0[1]+dy,r0[2]+dx,r0[3]+dy]};const nw=Math.max(30,r0[2]-r0[0]+dx),nh=(r0[3]-r0[1])*nw/(r0[2]-r0[0]);return {...a,rect:[r0[0],r0[1],r0[0]+nw,r0[1]+nh]}}))};
      const up=()=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up)};window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)};
    return <div key={pi} className="se-pagewrap"><small className="muted">Page {pi+1} of {info.pages.length}</small>
      <div className={`se-page tool-${locked?'none':tool}`} style={{width:W,height:pg.h*f}} onClick={clickPage}><img className="se-img" src={pg.image} alt={`Page ${pi+1}`} draggable={false} style={{width:W,height:pg.h*f}}/>
        {(tool==='delete'||tool==='replace')&&!locked&&pg.lines.length===0&&<div className="se-nolines" role="status">No text you can select was found on this page. It may be a scanned picture. Use Add text to write over it.</div>}
        {(tool==='delete'||tool==='replace')&&!locked&&pg.lines.map((l:any,k:number)=><button key={k} type="button" className="se-line" title={tool==='delete'?'Delete this text':'Change this text'} aria-label={(tool==='delete'?'Delete: ':'Change: ')+l.text} style={{left:l.bbox[0]*f-2,top:l.bbox[1]*f-1,width:(l.bbox[2]-l.bbox[0])*f+4,height:(l.bbox[3]-l.bbox[1])*f+2}} onClick={()=>lineClick(l)}/>)}
        {mine.map(o=>o.t==='delete'?<div key={o.id} className={`se-del${mine.some(x=>x.id===o.id+'r')||o.fill?' cover':''}`} title={mine.some(x=>x.id===o.id+'r')?'Being changed':'Will be deleted'} style={{left:(o.cover||o.rect!)[0]*f-2,top:(o.cover||o.rect!)[1]*f-1,width:((o.cover||o.rect!)[2]-(o.cover||o.rect!)[0])*f+4,height:((o.cover||o.rect!)[3]-(o.cover||o.rect!)[1])*f+2,...(o.fill?{background:o.fill}:{})}}><button type="button" className="se-x" aria-label="Keep this text" onClick={e=>{e.stopPropagation();setOps(a=>a.filter(x=>x.id!==o.id&&x.id!==o.id+'r'))}}><X size={11}/></button></div>
          :o.t==='text'?<div key={o.id} className={`se-text${editing===o.id?' editing':''}`} style={{left:o.x!*f,top:o.y!*f}} onPointerDown={dragText(o,f)}>{editing===o.id?<textarea autoFocus rows={1} value={o.text} style={{fontSize:o.size!*f,color:o.color,height:o.size!*f*1.3,letterSpacing:(o.track||0)*f,width:Math.max(60,(o.text||'').length*(o.size!*.62+(o.track||0))*f+12)}} aria-label="Text to add" onFocus={e=>{if(o.id.endsWith('r'))e.currentTarget.select()}} onChange={e=>setOps(a=>a.map(x=>x.id===o.id?{...x,text:e.target.value}:x))} onKeyDown={e=>{if(e.key==='Escape'||(e.key==='Enter'&&!e.shiftKey)){e.preventDefault();(e.target as HTMLElement).blur()}}} onBlur={()=>finishText(o)}/>:<span style={{fontSize:o.size!*f,color:o.color,letterSpacing:(o.track||0)*f}} title="Drag to move, click to edit">{o.text}</span>}<span className="se-grab" title="Drag to move this text anywhere" aria-label="Move this text"><Move size={11}/></span><button type="button" className="se-x" aria-label="Remove this text" onMouseDown={e=>e.preventDefault()} onClick={e=>{e.stopPropagation();setOps(a=>a.filter(x=>x.id!==o.id))}}><X size={11}/></button></div>
          :<div key={o.id} className="se-sig" style={{left:o.rect![0]*f,top:o.rect![1]*f,width:(o.rect![2]-o.rect![0])*f,height:(o.rect![3]-o.rect![1])*f}} onPointerDown={drag(o,'move')} onClick={e=>e.stopPropagation()}><img src={o.png} alt="Signature" draggable={false}/><button type="button" className="se-x" aria-label="Remove this signature" onPointerDown={e=>e.stopPropagation()} onClick={e=>{e.stopPropagation();setOps(a=>a.filter(x=>x.id!==o.id))}}><X size={11}/></button><span className="se-grip" aria-label="Resize signature" onPointerDown={drag(o,'size')}/></div>)}
      </div></div>})}</div>;
}

function WordView({info,ops,setOps,sig,locked}:{info:any;ops:Op[];setOps:(f:(o:Op[])=>Op[])=>void;sig:Sig|null;locked:boolean}){
  const [edit,setEdit]=useState<number|null>(null);const [adding,setAdding]=useState<number|null>(null);const [draft,setDraft]=useState('');
  const rep=(i:number)=>ops.find(o=>o.t==='replace'&&o.i===i);const del=(i:number)=>ops.find(o=>o.t==='delete'&&o.i===i);
  const set=(o:Op)=>setOps(a=>[...a.filter(x=>!(x.t===o.t&&x.i===o.i&&(o.t==='replace'||o.t==='delete'))),o]);
  const drop=(id:string)=>setOps(a=>a.filter(x=>x.id!==id));
  const extras=(i:number)=>ops.filter(o=>(o.t==='add'||o.t==='sign')&&o.after===i).map(o=>o.t==='add'?<div key={o.id} className="se-wadd"><span>{o.text}</span><button type="button" className="iconbtn" aria-label="Remove added text" onClick={()=>drop(o.id)}><X size={14}/></button></div>
    :<div key={o.id} className="se-wadd"><img src={o.png} alt="Signature" style={{width:o.width!*48}}/><label className="small muted">Size <input type="range" min={0.8} max={4} step={0.1} value={o.width} aria-label="Signature size" onChange={e=>setOps(a=>a.map(x=>x.id===o.id?{...x,width:+e.target.value}:x))}/></label><button type="button" className="iconbtn" aria-label="Remove signature" onClick={()=>drop(o.id)}><X size={14}/></button></div>);
  const tools=(i:number,label:string)=>!locked&&<span className="se-wtools">{adding===i?<span className="se-wform"><textarea autoFocus rows={2} aria-label="Text to add" value={draft} onChange={e=>setDraft(e.target.value)}/><button type="button" className="secondary" onClick={()=>{if(draft.trim())setOps(a=>[...a,{id:uid(),t:'add',after:i,text:draft}]);setDraft('');setAdding(null)}}>Add</button><button type="button" className="textbtn" onClick={()=>{setAdding(null);setDraft('')}}>Cancel</button></span>
    :<><button type="button" className="textbtn" onClick={()=>{setAdding(i);setDraft('')}}><FilePlus2 size={13}/> Add text {label}</button><button type="button" className="textbtn" disabled={!sig} title={sig?'':'Draw or choose a signature first'} onClick={()=>sig&&setOps(a=>[...a,{id:uid(),t:'sign',after:i,png:sig.png,width:2}])}><PenLine size={13}/> Sign {label}</button></>}</span>;
  return <div className="se-word">{info.tables>0&&<p className="muted small">This document has {info.tables} table{info.tables===1?'':'s'}. Text inside tables is kept as it is and cannot be changed here.</p>}
    {info.paragraphs.map((p:any)=>{const d=del(p.i),r=rep(p.i);return <div key={p.i} className={`se-wp${d?' gone':''}`}>
      {edit===p.i?<span className="se-wform"><textarea autoFocus rows={3} aria-label="New text for this paragraph" value={draft} onChange={e=>setDraft(e.target.value)}/><button type="button" className="secondary" onClick={()=>{set({id:uid(),t:'replace',i:p.i,text:draft});setEdit(null)}}>Keep change</button><button type="button" className="textbtn" onClick={()=>setEdit(null)}>Cancel</button></span>
        :<p className={p.style.startsWith('Heading')||p.style==='Title'?'se-h':''}>{r?<><span className="se-new">{r.text||'(empty)'}</span></>:p.text||(p.pic?<em className="muted">(picture)</em>:<em className="muted">(blank line)</em>)}</p>}
      {!locked&&edit!==p.i&&<span className="se-wtools">{d?<button type="button" className="textbtn" onClick={()=>drop(d.id)}><Undo2 size={13}/> Keep this paragraph</button>:<><button type="button" className="textbtn" onClick={()=>{setEdit(p.i);setDraft(r?.text??p.text)}}><Pencil size={13}/> Change</button><button type="button" className="textbtn" onClick={()=>set({id:uid(),t:'delete',i:p.i})}><Trash2 size={13}/> Delete</button></>}{r&&<button type="button" className="textbtn" onClick={()=>drop(r.id)}><Undo2 size={13}/> Undo change</button>}</span>}
      {tools(p.i,'below')}{extras(p.i)}</div>})}
    <div className="se-wp"><b>End of document</b>{tools(-1,'at the end')}{extras(-1)}</div></div>;
}

/* Certified digital signature (PDF): signs with the person's own certificate. The certificate file and password are used once and never stored. */
function CertPanel({request,doc,onSigned,onClose,notify}:{request:any;doc:Doc;onSigned:(d:Doc)=>void;onClose:()=>void;notify:(m:string)=>void}){
  const [p12,setP12]=useState<{name:string;b64:string}|null>(null);const [pw,setPw]=useState('');const [reason,setReason]=useState('');const [place,setPlace]=useState('');const [visible,setVisible]=useState(true);const [lock,setLock]=useState(true);const [page,setPage]=useState(doc.info.pages.length-1);
  const [mk,setMk]=useState(true);const top=useRef<HTMLDivElement>(null);useEffect(()=>{top.current?.scrollIntoView({behavior:'smooth',block:'center'})},[]);const [nm,setNm]=useState('');const [em,setEm]=useState('');const [npw,setNpw]=useState('');const [err,setErr]=useState('');const [busy,setBusy]=useState('');
  const pick=async(f?:File|null)=>{if(!f)return;setErr('');if(f.size>200000){setErr('That file is too large to be a certificate.');return}setP12({name:f.name,b64:await toB64(f)})};
  const save=(b64:string,name:string)=>{const bin=atob(b64),u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);const url=URL.createObjectURL(new Blob([u],{type:'application/x-pkcs12'}));const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000)};
  const create=async()=>{setErr('');setBusy('Creating your certificate…');try{const r=await request('/docedit/certificate',{method:'POST',body:JSON.stringify({name:nm,email:em,password:npw})});save(r.data,r.name);setP12({name:r.name,b64:r.data});setPw(npw);setNpw('');setMk(false);notify('Certificate created and downloaded. Keep that file and its password safe: you need both to sign in future.')}catch(e:any){setErr(e.message)}setBusy('')};
  const sign=async()=>{if(!p12)return;setErr('');setBusy('Signing…');try{const r=await request('/docedit/certify',{method:'POST',body:JSON.stringify({name:doc.name,data:doc.b64,p12:p12.b64,password:pw,reason,location:place,visible,page,lock})});
      const info=await request('/docedit/inspect',{method:'POST',body:JSON.stringify({name:doc.name,data:r.data})});setPw('');onSigned({...doc,b64:r.data,info});notify('The PDF is digitally signed. Download it now.')}catch(e:any){setErr(e.message)}setBusy('')};
  return <div className="se-sigpad se-cert" ref={top}><div className="se-row"><b><ShieldCheck size={16}/> Certified digital signature</b><button type="button" className="iconbtn" aria-label="Close" onClick={onClose}><X size={16}/></button></div>
    <p className="muted small">This seals the PDF with your own certificate. It shows who signed and when, and any change made afterwards is detected. Do this last: once signed, the file cannot be edited without breaking the signature. The certificate file and password are used once and are not kept.</p>
    <label className="se-field">Certificate file (.p12 or .pfx)<input type="file" accept=".p12,.pfx,application/x-pkcs12" aria-label="Certificate file" onChange={e=>{pick(e.target.files?.[0]);e.target.value=''}}/></label>
    {p12&&<small className="muted">Using {p12.name}</small>}
    <label className="se-field">Certificate password<input type="password" autoComplete="off" value={pw} onChange={e=>setPw(e.target.value)} aria-label="Certificate password"/></label>
    <button type="button" className="textbtn" onClick={()=>setMk(!mk)}><KeyRound size={14}/> {mk?'Hide':'I do not have a certificate: create one'}</button>
    {mk&&<div className="se-mk"><p className="muted small">This makes a certificate in your name and downloads it as a file protected by a password you choose. Programs such as Adobe Reader will show it as “signer not verified” until the person opening the file chooses to trust it. For a signature that shows as verified, use a certificate from a recognised certificate authority and upload it above.</p>
      <label className="se-field">Name on the certificate<input value={nm} maxLength={64} onChange={e=>setNm(e.target.value)} aria-label="Name on the certificate"/></label>
      <label className="se-field">Email (optional)<input value={em} maxLength={120} onChange={e=>setEm(e.target.value)} aria-label="Email on the certificate"/></label>
      <label className="se-field">Choose a password (8 or more characters)<input type="password" autoComplete="new-password" value={npw} onChange={e=>setNpw(e.target.value)} aria-label="New certificate password"/></label>
      <button type="button" className="secondary" disabled={!nm.trim()||npw.length<8||!!busy} onClick={create}>Create and download certificate</button></div>}
    <div className="se-row"><label className="check"><input type="checkbox" checked={visible} onChange={e=>setVisible(e.target.checked)}/> Show a signature stamp on the page</label>
      {visible&&doc.info.pages.length>1&&<label className="small muted">Page <select value={page} aria-label="Page for the stamp" onChange={e=>setPage(+e.target.value)}>{doc.info.pages.map((_:any,i:number)=><option key={i} value={i}>{i+1}</option>)}</select></label>}</div>
    <div className="se-row"><label className="check"><input type="checkbox" checked={lock} onChange={e=>setLock(e.target.checked)}/> Certify: no further changes allowed after signing</label></div>
    <label className="se-field">Reason (optional)<input value={reason} maxLength={200} onChange={e=>setReason(e.target.value)} aria-label="Reason for signing"/></label>
    <label className="se-field">Location (optional)<input value={place} maxLength={200} onChange={e=>setPlace(e.target.value)} aria-label="Location of signing"/></label>
    {err&&<p className="error" role="alert">{err}</p>}{busy&&<p className="muted" role="status">{busy}</p>}
    <div className="se-row"><button type="button" className="primary" disabled={!p12||!pw||!!busy} onClick={sign}><ShieldCheck size={15}/> Sign digitally</button>{!busy&&(!p12?<span className="muted small">First choose a certificate file, or create one above.</span>:!pw?<span className="muted small">Enter the certificate password.</span>:null)}</div></div>;
}

export function SignEdit({request,requestUp,notify,userId}:{request:any;requestUp?:any;notify:(m:string)=>void;userId?:string}){
  const [cur,setCur]=useState<Doc|null>(null);const [ops,setOps]=useState<Op[]>([]);const [tool,setTool]=useState<'text'|'delete'|'replace'|'sign'>('text');
  const [sig,setSig]=useState<Sig|null>(null);const [saved,setSaved]=useState<Sig[]>([]);const [busy,setBusy]=useState('');const [err,setErr]=useState('');const [size,setSize]=useState(12);const [color,setColor]=useState(COLORS[0]);const [applied,setApplied]=useState(0);const [pad,setPad]=useState(false);const [certOpen,setCertOpen]=useState(false);const [docId,setDocId]=useState('');const [up,setUp]=useState<{name:string;size:number;pct:number;label:string}|null>(null);const upTok=useRef(0);const [hist,setHist]=useState<Meta[]>([]);const uidk=String(userId||'');const [scope,setScope]=useState<'mine'|'with'|'by'>('mine');const [paneOff,setPaneOff]=useState(()=>{try{return localStorage.getItem('isift.pane.sign')==='1'}catch{return false}});const flipPane=()=>setPaneOff(v=>{try{localStorage.setItem('isift.pane.sign',v?'0':'1')}catch{}return !v});
  const loadSaved=useCallback(()=>request('/docedit/signatures').then((r:any)=>setSaved(r.items)).catch(()=>{}),[request]);
  useEffect(()=>{loadSaved()},[loadSaved]);
  const loadHist=useCallback(()=>histList(uidk).then(setHist),[uidk]);
  useEffect(()=>{loadHist()},[loadHist]);
  const keep=(id:string,d:Doc,n:number,blobs:{orig?:string;cur:string},up?:number)=>histSave(uidk,{id,name:d.name,kind:d.kind,applied:n,uploaded:up??hist.find(h=>h.id===id)?.uploaded??Date.now(),edited:Date.now(),size:Math.round(blobs.cur.length*.75)},blobs).then(loadHist);
  const mb=(n:number)=>n>=1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB';
  const cancelUp=()=>{upTok.current++;setUp(null);setBusy('')};
  const upload=async(f?:File|null)=>{if(!f)return;if(ops.length&&!window.confirm('You have changes that are not applied yet. Leave without applying them?'))return;setErr('');const tok=++upTok.current;
    setUp({name:f.name,size:f.size,pct:0,label:'Reading the file…'});   // the chosen file shows at once, with its progress
    const bad=!/\.(pdf|docx)$/i.test(f.name)?(/\.doc$/i.test(f.name)?'Old .doc files are not supported. Save it as .docx in Word and upload that.':'Upload a PDF (.pdf) or Word (.docx) file.'):f.size>12*1024*1024?'The file is larger than 12 MB.':'';
    if(bad){setErr(bad);setUp(null);return}
    setBusy('Opening your file…');
    try{const b64=await toB64(f,p=>{if(tok===upTok.current)setUp(u=>u&&{...u,pct:Math.round(p*20),label:'Reading the file…'})});
      const body=JSON.stringify({name:f.name,data:b64});const send=requestUp||(async(path:string,b:string)=>request(path,{method:'POST',body:b}));
      const info=await send('/docedit/inspect',body,(sent:number,total:number,phase:string)=>{if(tok!==upTok.current)return;setUp(u=>u&&(phase==='wait'?{...u,pct:90,label:'Processing the pages…'}:{...u,pct:20+Math.round(sent/total*68),label:'Uploading…'}))});
      if(tok!==upTok.current)return;setUp(u=>u&&{...u,pct:100,label:'Done'});
      const d:Doc={name:f.name,kind:info.kind,b64,info};const e0:Op[]=[];setCur(d);setOps(e0);setApplied(0);resetHist(d,e0,0);setTool('text');const id=uid()+uid();setDocId(id);keep(id,d,0,{orig:b64,cur:b64},Date.now())}
    catch(e:any){if(tok===upTok.current)setErr(e.message)}
    if(tok===upTok.current){setUp(null);setBusy('')}};
  /* Undo and redo: every change (text added, moved, deleted, a round applied, a signature placed) is a step. Quick changes such as a drag count as one. */
  const hs=useRef<{past:any[];future:any[];last:any;pending:any;timer:any}>({past:[],future:[],last:null,pending:null,timer:null});const [hn,setHn]=useState<[number,number]>([0,0]);
  const syncHn=()=>setHn([hs.current.past.length,hs.current.future.length]);
  const resetHist=(d:Doc,e0:Op[],n:number)=>{const h=hs.current;clearTimeout(h.timer);hs.current={past:[],future:[],last:{cur:d,ops:e0,applied:n},pending:null,timer:null};syncHn()};
  const commitHist=()=>{const h=hs.current;clearTimeout(h.timer);if(!h.pending)return;h.past.push(h.last);if(h.past.length>40)h.past.shift();h.last=h.pending;h.pending=null;h.future=[];syncHn()};
  useEffect(()=>{const h=hs.current;if(!cur||!h.last)return;if(h.last.cur===cur&&h.last.ops===ops&&h.last.applied===applied){h.pending=null;return}
    h.pending={cur,ops,applied};clearTimeout(h.timer);h.timer=setTimeout(commitHist,350)},[cur,ops,applied]);
  const goto=(t:any,from:any)=>{setCur(t.cur);setOps(t.ops);setApplied(t.applied);setErr('');setCertOpen(false);if(t.cur!==from.cur)keep(docId,t.cur,t.applied,{cur:t.cur.b64})};
  const undo=()=>{if(busy)return;commitHist();const h=hs.current;if(!h.past.length)return;const prev=h.past.pop(),was=h.last;h.future.push(was);h.last=prev;syncHn();goto(prev,was)};
  const redo=()=>{if(busy)return;commitHist();const h=hs.current;if(!h.future.length)return;const nx=h.future.pop(),was=h.last;h.past.push(was);h.last=nx;syncHn();goto(nx,was)};
  const undoRef=useRef({undo,redo});undoRef.current={undo,redo};
  useEffect(()=>{const k=(e:KeyboardEvent)=>{if(!(e.ctrlKey||e.metaKey)||(e.target as HTMLElement)?.closest?.('textarea,input,select'))return;const z=e.key.toLowerCase();if(z==='z'&&!e.shiftKey){e.preventDefault();undoRef.current.undo()}else if(z==='y'||(z==='z'&&e.shiftKey)){e.preventDefault();undoRef.current.redo()}};window.addEventListener('keydown',k);return()=>window.removeEventListener('keydown',k)},[]);
  const apply=async()=>{if(!cur||!ops.length)return;setErr('');setBusy('Applying your changes…');
    const send=ops.filter(o=>!(o.t==='text'&&!(o.text||'').trim())).map(({id,...o})=>o);
    try{const r=await request('/docedit/apply',{method:'POST',body:JSON.stringify({name:cur.name,data:cur.b64,ops:send})});const info=await request('/docedit/inspect',{method:'POST',body:JSON.stringify({name:cur.name,data:r.data})});const nd={...cur,b64:r.data,info};setCur(nd);setOps([]);setApplied(n=>n+1);keep(docId,nd,applied+1,{cur:r.data});notify(r.warnings?.length?r.warnings[0]:'Changes applied. Download the file when you are ready.')}catch(e:any){setErr(e.message)}setBusy('')};
  const download=()=>{if(cur)saveFile(cur.b64,cur.kind,cur.name)};
  const onSig=async(s:Sig,keep:boolean,name:string)=>{setSig(s);setPad(false);setTool('sign');if(keep){try{const r=await request('/docedit/signatures',{method:'POST',body:JSON.stringify({name,png:s.png})});setSig(r);loadSaved();notify('Signature saved for future use.')}catch(e:any){setErr(e.message)}}};
  const delSig=async(s:Sig)=>{if(!window.confirm('Delete this saved signature?'))return;try{await request('/docedit/signatures/'+s.id,{method:'DELETE'});if(sig?.id===s.id)setSig(null);loadSaved()}catch(e:any){setErr(e.message)}};
  const reset=()=>{if(ops.length&&!window.confirm('You have changes that are not applied yet. Leave without applying them?'))return;setCur(null);setOps([]);setApplied(0);setErr('');setDocId('');setCertOpen(false);setPad(false);loadHist()};
  const openRec=async(m:Meta)=>{setErr('');setBusy('Opening your file…');try{const b=await histBlobs(uidk,m.id);if(!b)throw new Error('That file is no longer stored in this browser.');
      const info=await request('/docedit/inspect',{method:'POST',body:JSON.stringify({name:m.name,data:b.cur})});
      const d:Doc={name:m.name,kind:m.kind,b64:b.cur,info};const e0:Op[]=[];setCur(d);setOps(e0);setApplied(m.applied);resetHist(d,e0,m.applied);setTool('text');setDocId(m.id)}catch(e:any){setErr(e.message)}setBusy('')};
  const getRec=async(m:Meta)=>{try{const b=await histBlobs(uidk,m.id);if(b)saveFile(b.cur,m.kind,m.name)}catch(e:any){setErr(e.message)}};
  const delRec=async(m:Meta)=>{if(!window.confirm('Remove "'+m.name+'" from your list? The copy kept in this browser is deleted.'))return false;await histDelete(uidk,m.id);loadHist();return true};
  const pdf=cur?.kind==='pdf';const sigs:any[]=(cur?.info?.signatures)||[];const signed=sigs.length>0;const changed=ops.length>0;const note=pdf?'Click the page where the text should go.':'Use the buttons beside each paragraph.';
  const pane=<section className="panel ws-pane" aria-hidden={paneOff}><div className="panelhead"><h2><FileSignature size={18}/> Sign &amp; Edit PDF</h2><span className="ws-pane-btns"><label className="primary se-new" title="Upload a PDF or Word file"><Plus size={15}/> New<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" aria-label="Upload a new PDF or Word file" onChange={e=>{upload(e.target.files?.[0]);e.target.value=''}}/></label><button type="button" className="iconbtn" aria-label="Hide this panel" title="Hide this panel to give the work area more room" onClick={flipPane}><ChevronsLeft size={18}/></button></span></div>
    <div className="notes-scope" role="tablist" aria-label="Which files">{([['mine','My files'],['with','Shared with me'],['by','Shared by me']] as const).map(([v,l])=><button key={v} type="button" role="tab" aria-selected={scope===v} className={`wb-cat${scope===v?' on':''}`} onClick={()=>setScope(v)}>{l}</button>)}</div>
    {scope==='mine'&&up&&<div className="ws-ch shared-row on se-uprow"><div className="ws-main"><b>{up.name}</b><small className="muted">{up.label} {up.pct}%</small></div></div>}
    {scope!=='mine'?<p className="muted pad">{scope==='with'?'Nothing has been shared with you yet.':'You have not shared anything yet.'}</p>:hist.length||up?hist.map(m=><button key={m.id} type="button" className={`ws-ch shared-row${docId===m.id?' on':''}`} disabled={!!busy} onClick={()=>{if(m.id!==docId)openRec(m)}}><div className="ws-main"><b>{m.name}</b><small className="muted">{m.kind==='pdf'?'PDF':'Word'} · {m.applied?`${m.applied} round${m.applied===1?'':'s'} of changes`:'not changed yet'} · edited {when(m.edited)}</small></div></button>):<p className="muted pad">Nothing here yet. Press New.</p>}
    <small className="muted pad">Private to you, kept in this browser only and never on the server. Press New to upload the next file.</small></section>;
  return <div className={`ws-two notes${paneOff?' pane-off':''}`}>{pane}<section className="panel ws-editor se">{paneOff&&<button type="button" className="textbtn ws-pane-open" aria-label="Show the files panel" onClick={flipPane}><ChevronsRight size={16}/> Show Sign &amp; Edit PDF panel</button>}
    {up?<div className="se-up" role="status" aria-live="polite"><FileText size={34}/><div className="se-upbody"><b>{up.name}</b><small className="muted">{mb(up.size)}</small>
      <div className={`se-bar${up.pct>=90&&up.pct<100?' wait':''}`} role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={up.pct}><i style={{width:up.pct+'%'}}/></div>
      <small>{up.label} <b>{up.pct}%</b>{up.pct>=20&&up.pct<90?` · ${mb(Math.round(up.size*(up.pct-20)/68))} of ${mb(up.size)} sent`:''}</small></div><button type="button" className="textbtn" onClick={cancelUp}>Cancel</button></div>
    :!cur?<div className="se-start"><h2>Upload a file to edit or sign</h2><p className="muted">Choose a PDF or a Word (.docx) file. You can add text, delete text and sign it with a signature you draw. Your original file stays untouched until you download the edited copy.</p>
      <label className="primary se-upload"><Upload size={16}/> Choose a PDF or Word file<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" aria-label="Upload a PDF or Word file" onChange={e=>{upload(e.target.files?.[0]);e.target.value=''}}/></label>
      <p className="muted small">PDF or .docx, up to 12 MB (PDFs up to 30 pages). Files are not stored on the server. Every file you open is kept in the list on the left, in this browser only.</p>
      {saved.length>0&&<p className="muted small">You have {saved.length} saved signature{saved.length===1?'':'s'}, ready to use once a file is open.</p>}</div>
    :<>
      <div className="panelhead se-head"><h2>{cur.name}</h2><span className="muted small">{pdf?'PDF':'Word'} · saved in your list · {applied?`${applied} round${applied===1?'':'s'} of changes applied`:'as uploaded'}{changed?` · ${ops.length} not yet applied`:''}</span>
        <span className="se-actions"><span className="se-undo" role="group" aria-label="Undo and redo"><button type="button" className="secondary iconbtn" disabled={!hn[0]||!!busy} onClick={undo} title="Undo (Ctrl+Z)" aria-label="Undo"><Undo2 size={17}/></button><button type="button" className="secondary iconbtn" disabled={!hn[1]||!!busy} onClick={redo} title="Redo (Ctrl+Y)" aria-label="Redo"><Redo2 size={17}/></button></span><button type="button" className="primary" disabled={!changed||!!busy} onClick={apply}><Check size={15}/> Apply changes</button>{pdf&&!signed&&<button type="button" className="secondary" disabled={changed||!!busy} title={changed?'Apply your changes first, then sign':'Add a certified digital signature'} onClick={()=>setCertOpen(!certOpen)}><ShieldCheck size={15}/> Digital signature</button>}<button type="button" className="secondary" disabled={!(applied||signed)||!!busy} title={applied||signed?'':'Apply your changes first'} onClick={download}><Download size={15}/> Download</button><button type="button" className="textbtn" onClick={reset}>Close file</button><button type="button" className="iconbtn" aria-label="Remove this file from the list" title="Remove this file from the list" onClick={async()=>{const m=hist.find(h=>h.id===docId);if(m&&await delRec(m)){setCur(null);setOps([]);setDocId('')}}}><Trash2 size={16}/></button></span></div>
      {changed&&<div className="shared-banner" role="status">You have changes that are not applied yet. Press Apply changes to put them in the file, then Download.</div>}
      {sigs.map((g,i)=><div key={i} className={`shared-banner se-signed${g.intact?'':' bad'}`} role={g.intact?'status':'alert'}><ShieldCheck size={15}/> {g.intact?<>Digitally signed{g.signer?` by ${g.signer}`:''}. The file has not changed since it was signed.{!g.trusted&&' The signer’s identity is not verified by a recognised authority.'}{g.certified&&' No further changes are allowed.'} Editing is switched off: press Undo to go back to the file before it was signed.</>:<>This PDF has a digital signature that is no longer valid: the file was changed after it was signed.</>}</div>)}
      {certOpen&&pdf&&!signed&&<CertPanel request={request} doc={cur} notify={notify} onClose={()=>setCertOpen(false)} onSigned={d=>{setCur(d);setApplied(n=>n+1);keep(docId,d,applied+1,{cur:d.b64});setCertOpen(false);setOps([])}}/>}
      <div className={`se-tools${signed?' off':''}`} role="toolbar" aria-label="Editing tools" aria-disabled={signed}>
        <button type="button" className={`wb-cat${tool==='text'?' on':''}`} aria-pressed={tool==='text'} onClick={()=>setTool('text')}><Type size={14}/> Add text</button>
        {pdf&&<><button type="button" className={`wb-cat${tool==='replace'?' on':''}`} aria-pressed={tool==='replace'} onClick={()=>setTool('replace')}><Pencil size={14}/> Change text</button><button type="button" className={`wb-cat${tool==='delete'?' on':''}`} aria-pressed={tool==='delete'} onClick={()=>setTool('delete')}><Trash2 size={14}/> Delete text</button></>}
        <button type="button" className={`wb-cat${tool==='sign'?' on':''}`} aria-pressed={tool==='sign'} onClick={()=>{setTool('sign');if(!sig&&!saved.length)setPad(true)}}><PenLine size={14}/> Sign</button>
        {pdf&&tool==='text'&&<span className="se-opts"><label className="small muted">Size <select value={size} aria-label="Text size" onChange={e=>setSize(+e.target.value)}>{[9,10,11,12,14,16,18,24,32].map(n=><option key={n} value={n}>{n}</option>)}</select></label>{COLORS.map(c=><button key={c} type="button" className={`se-swatch${color===c?' on':''}`} style={{background:c}} aria-label={'Text colour '+c} onClick={()=>setColor(c)}/>)}</span>}
        <span className="muted small se-hint">{tool==='delete'?'Click a line of text to delete it. Click the red box again to keep it.':tool==='replace'?'Click a line of text, then type the new words.':tool==='sign'?(sig?(pdf?'Click the page where the signature should go. Drag it to move; drag the corner to resize.':'Use "Sign below" beside a paragraph.'):'Draw a signature, or choose a saved one.'):note}</span></div>
      {tool==='sign'&&!signed&&<div className="se-sigbar">{sig?<><img src={sig.png} alt="Signature in use" className="se-siguse"/><span className="small muted">Signature ready.</span></>:<span className="small muted">No signature chosen yet.</span>}<button type="button" className="secondary" onClick={()=>setPad(!pad)}>{pad?'Close signature box':sig?'Draw a new one or pick another':'Draw or pick a signature'}</button></div>}
      {tool==='sign'&&pad&&!signed&&<SignaturePad onDone={onSig} saved={saved} canSave onDelete={delSig} onUse={s=>{setSig(s);setPad(false)}}/>}
      {err&&<p className="error" role="alert">{err}</p>}{busy&&<p className="muted" role="status">{busy}</p>}
      {pdf?<PdfView info={cur.info} ops={ops} setOps={setOps} tool={tool} sig={sig} size={size} color={color} locked={!!busy||signed}/>:<WordView info={cur.info} ops={ops} setOps={setOps} sig={sig} locked={!!busy}/>}
      <p className="muted small">A drawn signature is a picture. For a sealed, tamper-evident signature on a PDF use Digital signature. {pdf?'Deleting text removes it from the PDF itself, not just from view.':'Word formatting that you do not touch stays as it was.'}</p></>}
    {!cur&&err&&<p className="error" role="alert">{err}</p>}{!cur&&busy&&<p className="muted" role="status">{busy}</p>}
  </section></div>;
}
