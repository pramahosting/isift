import React,{useEffect,useMemo,useRef,useState,useCallback,forwardRef,useImperativeHandle} from 'react';
import {shapePng} from './Whiteboard';
import {libOf} from './WbLib';
import {Bold,Italic,Underline,Strikethrough,List,ListOrdered,AlignLeft,AlignCenter,AlignRight,AlignJustify,Link2,Table2,Undo2,Redo2,Eraser,Upload,Download,Printer,Plus,Trash2,Copy,ArrowUp,ArrowDown,Play,X,ChevronLeft,ChevronRight,Shapes} from 'lucide-react';
import {evaluate,show,colName,toCsv,fromCsv,Cells} from './sheetcalc';
import {DownloadMenu} from './DownloadMenu';
import {convertDownload,deckShapes,sheetShown} from './docConvert';

type EdProps={request?:any;content:string;onChange:(c:string)=>void;readOnly?:boolean;title:string;shelf?:boolean;onShelf?:()=>void};
export type ShapeApi={insertShape:(lib:any)=>void};
const download=(name:string,text:string,type:string)=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)};
const safeName=(t:string,ext:string)=>`${(t||'file').replace(/[^\w\- ]+/g,'').trim()||'file'}.${ext}`;
const esc=(s:string)=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

/* ---------------- WordPerfect: documents ---------------- */
function cleanHtml(html:string):string{ // for files brought in from outside: no scripts, no event handlers, no script links
  const d=new DOMParser().parseFromString(html,'text/html');d.querySelectorAll('script,style,iframe,object,embed,svg,form,link,meta').forEach(n=>n.remove());
  d.body.querySelectorAll('*').forEach(el=>{for(const a of Array.from(el.attributes)){const n=a.name.toLowerCase();if(n.startsWith('on')||(n==='href'&&!/^(https?:|mailto:)/i.test(a.value.trim()))||(n!=='href'&&n!=='style'&&n!=='colspan'&&n!=='rowspan'&&!(el.tagName==='IMG'&&((n==='src'&&/^data:image\/png;base64,/i.test(a.value))||n==='width'||n==='height'||n==='alt'))))el.removeAttribute(a.name)}});
  d.body.querySelectorAll('img').forEach(i=>{if(!/^data:image\/png;base64,/i.test(i.getAttribute('src')||''))i.remove()});
  return d.body.innerHTML}
export const WordEditor=forwardRef<ShapeApi,EdProps>(function WordEditor({content,onChange,readOnly,title,shelf,onShelf,request},api){
  const ref=useRef<HTMLDivElement>(null);const saved=useRef<Range|null>(null);const [pic,setPic]=useState<HTMLImageElement|null>(null);const file=useRef<HTMLInputElement>(null);const [words,setWords]=useState(0);
  const count=()=>setWords(((ref.current?.innerText||'').trim().match(/\S+/g)||[]).length);
  useEffect(()=>{if(ref.current){ref.current.innerHTML=content||'<p><br></p>';count()}},[]);
  const remember=()=>{const sel=window.getSelection();if(sel&&sel.rangeCount&&ref.current?.contains(sel.anchorNode))saved.current=sel.getRangeAt(0).cloneRange()};
  useImperativeHandle(api,()=>({insertShape:(lib:any)=>{const el=ref.current;if(!el||readOnly)return;const p=shapePng(lib);const w=Math.min(p.w,360),h=Math.round(p.h*w/p.w);el.focus();const sel=window.getSelection()!;
    if(saved.current&&el.contains(saved.current.startContainer)){sel.removeAllRanges();sel.addRange(saved.current)}else{const r=document.createRange();r.selectNodeContents(el);r.collapse(false);sel.removeAllRanges();sel.addRange(r)}
    document.execCommand('insertHTML',false,`<img src="${p.url}" width="${w}" height="${h}" alt="${(lib.label||'Shape').replace(/[^\w ]/g,'')}">`);remember();changed()}}));
  const resizePic=(f:number)=>{if(!pic)return;const w=Math.max(30,Math.min(700,Math.round((pic.width||100)*f))),h=Math.round(w*(pic.naturalHeight||pic.height)/(pic.naturalWidth||pic.width||1));pic.setAttribute('width',String(w));pic.setAttribute('height',String(h));changed()};
  const pickPic=(e:React.MouseEvent)=>{const t=e.target as HTMLElement;ref.current?.querySelectorAll('img.sel').forEach(i=>i.classList.remove('sel'));if(t.tagName==='IMG'&&!readOnly){t.classList.add('sel');setPic(t as HTMLImageElement)}else setPic(null);remember()};
  const cmd=(c:string,v?:string)=>{ref.current?.focus();document.execCommand(c,false,v);changed()};
  const changed=()=>{if(readOnly||!ref.current)return;ref.current.querySelectorAll('img.sel').forEach(i=>i.classList.remove('sel'));const h=ref.current.innerHTML;if(pic)pic.classList.add('sel');onChange(h);count()};
  const tb=(label:string,icon:React.ReactNode,fn:()=>void)=><button type="button" className="iconbtn" title={label} aria-label={label} onMouseDown={e=>e.preventDefault()} onClick={fn}>{icon}</button>;
  const link=()=>{const u=window.prompt('Link address (https://…)');if(u&&/^(https?:\/\/|mailto:)/i.test(u.trim()))cmd('createLink',u.trim())};
  const table=()=>cmd('insertHTML','<table border="1"><tbody>'+'<tr><td><br></td><td><br></td><td><br></td></tr>'.repeat(3)+'</tbody></table><p><br></p>');
  const imp=async(f?:File)=>{if(!f||!ref.current)return;const t=await f.text();const html=/\.html?$/i.test(f.name)?cleanHtml(t):t.split(/\r?\n/).map(l=>`<p>${l?esc(l):'<br>'}</p>`).join('');ref.current.innerHTML=html;changed()};
  const curHtml=()=>{const el=ref.current;if(!el)return content||'';const c=el.cloneNode(true) as HTMLElement;c.querySelectorAll('img.sel').forEach(i=>i.classList.remove('sel'));return c.innerHTML};
  const exportHtml=()=>download(safeName(title,'html'),`<!doctype html><meta charset="utf-8"><title>${esc(title)}</title><body>${ref.current?.innerHTML||''}`,'text/html');
  const print=()=>{const w=window.open('','_blank');if(!w)return;w.document.write(`<!doctype html><meta charset="utf-8"><title>${esc(title)}</title><style>body{font:12pt Georgia,serif;margin:2cm}table{border-collapse:collapse}td,th{border:1px solid #888;padding:4px 8px}</style><body>${cleanHtml(ref.current?.innerHTML||'')}`);w.document.close();w.focus();w.print()};
  return <div className="wp">
    {!readOnly&&<div className="ws-tools wp-tools" role="toolbar" aria-label="Document formatting">
      <select aria-label="Paragraph style" defaultValue="p" onChange={e=>{cmd('formatBlock',e.target.value);e.target.value='p'}}><option value="p">Paragraph</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option><option value="h3">Heading 3</option><option value="blockquote">Quote</option></select>
      {tb('Bold (Ctrl+B)',<Bold size={16}/>,()=>cmd('bold'))}{tb('Italic (Ctrl+I)',<Italic size={16}/>,()=>cmd('italic'))}{tb('Underline (Ctrl+U)',<Underline size={16}/>,()=>cmd('underline'))}{tb('Strikethrough',<Strikethrough size={16}/>,()=>cmd('strikeThrough'))}
      <span className="wb-sep"/>{tb('Bulleted list',<List size={16}/>,()=>cmd('insertUnorderedList'))}{tb('Numbered list',<ListOrdered size={16}/>,()=>cmd('insertOrderedList'))}
      <span className="wb-sep"/>{tb('Align left',<AlignLeft size={16}/>,()=>cmd('justifyLeft'))}{tb('Centre',<AlignCenter size={16}/>,()=>cmd('justifyCenter'))}{tb('Align right',<AlignRight size={16}/>,()=>cmd('justifyRight'))}{tb('Justify',<AlignJustify size={16}/>,()=>cmd('justifyFull'))}
      <span className="wb-sep"/>{tb('Link',<Link2 size={16}/>,link)}{tb('Insert a 3 by 3 table',<Table2 size={16}/>,table)}{tb('Clear formatting',<Eraser size={16}/>,()=>cmd('removeFormat'))}
      <span className="wb-sep"/>{tb('Undo',<Undo2 size={16}/>,()=>cmd('undo'))}{tb('Redo',<Redo2 size={16}/>,()=>cmd('redo'))}
      {pic&&<><span className="wb-sep"/><span className="small muted">Shape</span><button type="button" className="textbtn" onMouseDown={e=>e.preventDefault()} onClick={()=>resizePic(0.8)}>Smaller</button><button type="button" className="textbtn" onMouseDown={e=>e.preventDefault()} onClick={()=>resizePic(1.25)}>Larger</button></>}
      {tb('Open a text or HTML file into this document',<Upload size={16}/>,()=>file.current?.click())}<input ref={file} type="file" accept=".txt,.md,.html,.htm,text/plain,text/html" hidden onChange={e=>{imp(e.target.files?.[0]);e.target.value=''}}/><span className="wb-sep"/>{onShelf&&<button type="button" className={`textbtn se-shapesbtn${shelf?' on':''}`} title={shelf?'Hide the shape library':'Show the shape library'} aria-pressed={!!shelf} onMouseDown={e=>e.preventDefault()} onClick={onShelf}><Shapes size={16}/> Shapes</button>}
    </div>}
    <div className="wp-page" ref={ref} contentEditable={!readOnly} suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Document" aria-readonly={!!readOnly} onInput={changed} onKeyUp={remember} onMouseUp={pickPic} onBlur={remember} spellCheck/>
    <div className="wp-foot"><small className="muted">{words} {words===1?'word':'words'}{readOnly?' · read only':''}</small>
      <span>{request?<DownloadMenu label="Download this document" items={[{label:'PDF',run:()=>convertDownload(request,'wp','pdf',title,curHtml())},{label:'Word (.docx)',run:()=>convertDownload(request,'wp','docx',title,curHtml())},{label:'Web page (.html)',run:async()=>exportHtml()}]}/>:tb('Download as a web page',<Download size={16}/>,exportHtml)}{tb('Print or save as PDF',<Printer size={16}/>,print)}</span></div>
  </div>});

/* ---------------- SpreadTable: workbooks ---------------- */
type Sheet={name:string;cells:Cells;rows:number;cols:number};
export const parseBook=(c:string):{v:number;sheets:Sheet[]}=>{try{const v=JSON.parse(c);if(v&&Array.isArray(v.sheets)&&v.sheets.length)return {v:1,sheets:v.sheets.map((s:any)=>({name:String(s.name||'Sheet'),cells:s.cells||{},rows:Math.min(1000,Math.max(20,s.rows||100)),cols:Math.min(52,Math.max(6,s.cols||26))}))}}catch{}return {v:1,sheets:[{name:'Sheet1',cells:{},rows:100,cols:26}]}};
export function SheetEditor({content,onChange,readOnly,title,request}:EdProps){
  const [book,setBook]=useState(()=>parseBook(content));const [si,setSi]=useState(0);const [sel,setSel]=useState({r:1,c:0});const [edit,setEdit]=useState<string|null>(null);const grid=useRef<HTMLDivElement>(null);const file=useRef<HTMLInputElement>(null);
  const sh=book.sheets[Math.min(si,book.sheets.length-1)];const val=useMemo(()=>evaluate(sh.cells),[sh.cells]);
  const save=(b:typeof book)=>{setBook(b);if(!readOnly)onChange(JSON.stringify(b))};
  const setCells=(fn:(c:Cells)=>Cells,extra:Partial<Sheet>={})=>save({...book,sheets:book.sheets.map((s,i)=>i===si?{...s,...extra,cells:fn({...s.cells})}:s)});
  const ref=(r:number,c:number)=>colName(c)+r;const cur=ref(sel.r,sel.c);
  const commit=(text:string)=>{setEdit(null);setCells(c=>{if(text==='')delete c[cur];else c[cur]=text;return c})};
  const move=(dr:number,dc:number)=>setSel(s=>({r:Math.min(sh.rows,Math.max(1,s.r+dr)),c:Math.min(sh.cols-1,Math.max(0,s.c+dc))}));
  const key=(e:React.KeyboardEvent)=>{if(edit!==null)return;
    if(e.key==='ArrowDown'){e.preventDefault();move(1,0)}else if(e.key==='ArrowUp'){e.preventDefault();move(-1,0)}else if(e.key==='ArrowLeft'){e.preventDefault();move(0,-1)}else if(e.key==='ArrowRight'||e.key==='Tab'){e.preventDefault();move(0,e.shiftKey&&e.key==='Tab'?-1:1)}
    else if(e.key==='Enter'){e.preventDefault();readOnly?move(1,0):setEdit(sh.cells[cur]??'')}
    else if(!readOnly&&(e.key==='Delete'||e.key==='Backspace')){e.preventDefault();setCells(c=>{delete c[cur];return c})}
    else if(!readOnly&&e.key.length===1&&!e.ctrlKey&&!e.metaKey&&!e.altKey){setEdit(e.key);e.preventDefault()}};
  const paste=(e:React.ClipboardEvent)=>{if(readOnly||edit!==null)return;const t=e.clipboardData.getData('text');if(!t)return;e.preventDefault();const rows=t.replace(/\r/g,'').replace(/\n$/,'').split('\n').map(l=>l.split('\t'));setCells(c=>{rows.forEach((row,i)=>row.forEach((v,j)=>{const r=sel.r+i,cc=sel.c+j;if(r<=sh.rows&&cc<sh.cols){if(v==='')delete c[ref(r,cc)];else c[ref(r,cc)]=v}}));return c})};
  const copy=(e:React.ClipboardEvent)=>{if(edit!==null)return;e.preventDefault();e.clipboardData.setData('text',sh.cells[cur]??'')};
  const imp=async(f?:File)=>{if(!f||readOnly)return;const cells=fromCsv(await f.text());let mr=20,mc=6;for(const k of Object.keys(cells)){const m=/^([A-Z]+)(\d+)$/.exec(k)!;mr=Math.max(mr,+m[2]);mc=Math.max(mc,[...m[1]].reduce((n,ch)=>n*26+ch.charCodeAt(0)-64,0))}setCells(()=>cells,{rows:Math.min(1000,Math.max(sh.rows,mr)),cols:Math.min(52,Math.max(sh.cols,mc))})};
  useEffect(()=>{grid.current?.querySelector('.on')?.scrollIntoView({block:'nearest',inline:'nearest'})},[sel]);
  const shown=(r:number,c:number)=>{const raw=sh.cells[ref(r,c)];if(raw===undefined)return '';const v=val(ref(r,c));return show(v)};
  const num=(r:number,c:number)=>{const raw=sh.cells[ref(r,c)];return raw!==undefined&&typeof val(ref(r,c))==='number'};
  const addSheet=()=>{save({...book,sheets:[...book.sheets,{name:`Sheet${book.sheets.length+1}`,cells:{},rows:100,cols:26}]});setSi(book.sheets.length)};
  const rename=()=>{const n=window.prompt('Sheet name',sh.name);if(n&&n.trim())save({...book,sheets:book.sheets.map((s,i)=>i===si?{...s,name:n.trim().slice(0,40)}:s)})};
  const del=()=>{if(book.sheets.length<2||!window.confirm(`Delete sheet "${sh.name}"?`))return;save({...book,sheets:book.sheets.filter((_,i)=>i!==si)});setSi(0)};
  return <div className="st">
    <div className="ws-tools st-bar">
      <input className="st-name" readOnly value={cur} aria-label="Selected cell"/>
      <input className="st-formula" aria-label="Formula bar" placeholder={readOnly?'':'Type a value or a formula such as =SUM(A1:A5)'} value={edit!==null?edit:(sh.cells[cur]??'')} readOnly={!!readOnly} onChange={e=>setEdit(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();commit(edit??'');move(1,0);grid.current?.focus()}else if(e.key==='Escape'){setEdit(null);grid.current?.focus()}}} onBlur={()=>{if(edit!==null&&!readOnly)commit(edit)}}/>
      {!readOnly&&<><button type="button" className="iconbtn" title="Open a CSV file into this sheet" aria-label="Import CSV" onClick={()=>file.current?.click()}><Upload size={16}/></button><input ref={file} type="file" accept=".csv,.tsv,text/csv" hidden onChange={e=>{imp(e.target.files?.[0]);e.target.value=''}}/>
        <button type="button" className="textbtn" onClick={()=>setCells(c=>c,{rows:Math.min(1000,sh.rows+50)})}>+ 50 rows</button><button type="button" className="textbtn" onClick={()=>setCells(c=>c,{cols:Math.min(52,sh.cols+6)})}>+ 6 columns</button></>}
      {request?<DownloadMenu label="Download this workbook" items={[{label:'Excel (.xlsx)',run:()=>convertDownload(request,'sheet','xlsx',title,JSON.stringify(book))},{label:'PDF',run:()=>convertDownload(request,'sheet','pdf',title,JSON.stringify(book),{shown:sheetShown(book)})},{label:'CSV (this sheet)',run:async()=>download(safeName(`${title} ${sh.name}`,'csv'),toCsv(sh.cells,sh.rows,sh.cols),'text/csv')}]}/>:<button type="button" className="iconbtn" title="Download this sheet as CSV" aria-label="Download CSV" onClick={()=>download(safeName(`${title} ${sh.name}`,'csv'),toCsv(sh.cells,sh.rows,sh.cols),'text/csv')}><Download size={16}/></button>}
    </div>
    <div className="st-grid" ref={grid} tabIndex={0} role="grid" aria-label={`Sheet ${sh.name}`} onKeyDown={key} onPaste={paste} onCopy={copy}>
      <table><thead><tr><th className="st-corner"/>{Array.from({length:sh.cols},(_,c)=><th key={c} className={sel.c===c?'on':''}>{colName(c)}</th>)}</tr></thead>
        <tbody>{Array.from({length:sh.rows},(_,i)=>{const r=i+1;return <tr key={r}><th className={sel.r===r?'on':''}>{r}</th>{Array.from({length:sh.cols},(_,c)=>{const on=sel.r===r&&sel.c===c;const t=shown(r,c);
          return <td key={c} role="gridcell" aria-selected={on} className={`${on?'on':''}${num(r,c)?' num':''}${t.startsWith('#')?' err':''}`} onMouseDown={()=>{if(edit!==null&&!on)commit(edit);setSel({r,c});grid.current?.focus()}} onDoubleClick={()=>{if(!readOnly)setEdit(sh.cells[ref(r,c)]??'')}}>
            {on&&edit!==null?<input autoFocus value={edit} onChange={e=>setEdit(e.target.value)} onBlur={()=>commit(edit)} onKeyDown={e=>{e.stopPropagation();if(e.key==='Enter'){e.preventDefault();commit(edit);move(1,0);grid.current?.focus()}else if(e.key==='Tab'){e.preventDefault();commit(edit);move(0,1);grid.current?.focus()}else if(e.key==='Escape'){setEdit(null);grid.current?.focus()}}} aria-label={`Cell ${ref(r,c)}`}/>:t}</td>})}</tr>})}</tbody></table>
    </div>
    <div className="st-tabs" role="tablist" aria-label="Sheets">{book.sheets.map((s,i)=><button key={i} type="button" role="tab" aria-selected={i===si} className={`wb-cat${i===si?' on':''}`} onClick={()=>{setSi(i);setSel({r:1,c:0});setEdit(null)}} onDoubleClick={()=>!readOnly&&rename()}>{s.name}</button>)}
      {!readOnly&&<><button type="button" className="iconbtn" title="Add a sheet" aria-label="Add sheet" onClick={addSheet}><Plus size={16}/></button><button type="button" className="textbtn" onClick={rename}>Rename</button><button type="button" className="textbtn danger" onClick={del}>Delete sheet</button></>}
      <small className="muted">Formulas: + − * / ^ &amp; and SUM, AVERAGE, MIN, MAX, COUNT, IF, AND, OR, ROUND, ABS and more.{readOnly?' Read only.':''}</small></div>
  </div>}

/* ---------------- PowerPresentation: slides ---------------- */
type Slide={layout:'title'|'content'|'two'|'section'|'blank';title:string;body:string[];body2?:string[];notes:string;bg?:string;shapes?:SShape[]};
type SShape={id:string;lib:string;text:string;x:number;y:number;w:number};
export const THEMES:Record<string,{bg:string;fg:string;accent:string}>={light:{bg:'#ffffff',fg:'#172033',accent:'#2b62f0'},dark:{bg:'#172033',fg:'#f4f6fb',accent:'#7da2ff'},warm:{bg:'#fff7ed',fg:'#3b2a1a',accent:'#e0561f'},green:{bg:'#f0fbf4',fg:'#12301f',accent:'#1c9a5b'}};
export const parseDeck=(c:string):{v:number;theme:string;slides:Slide[]}=>{try{const v=JSON.parse(c);if(v&&Array.isArray(v.slides)&&v.slides.length)return {v:1,theme:THEMES[v.theme]?v.theme:'light',slides:v.slides.map((s:any)=>({layout:['title','content','two','section','blank'].includes(s.layout)?s.layout:'content',title:String(s.title||''),body:Array.isArray(s.body)?s.body.map(String):[],body2:Array.isArray(s.body2)?s.body2.map(String):[],notes:String(s.notes||''),bg:typeof s.bg==='string'?s.bg:undefined,shapes:Array.isArray(s.shapes)?s.shapes.filter((q:any)=>q&&typeof q.lib==='string'&&libOf(q.lib)&&[q.x,q.y,q.w].every((n:any)=>Number.isFinite(n))).slice(0,60).map((q:any)=>({id:String(q.id||Math.random().toString(36).slice(2,8)),lib:q.lib,text:String(q.text??'').slice(0,300),x:+q.x,y:+q.y,w:Math.max(20,Math.min(960,+q.w))})):[]}))}}catch{}return {v:1,theme:'light',slides:[{layout:'title',title:'Presentation title',body:['Subtitle or presenter'],notes:''}]}};
function SlideView({s,theme,w}:{s:Slide;theme:string;w:number}){
  const t=THEMES[theme]||THEMES.light;const k=w/960;const list=(a:string[]|undefined)=><ul>{(a||[]).filter(x=>x.trim()).map((x,i)=><li key={i}>{x}</li>)}</ul>;
  return <div className="pp-slide" style={{width:w,height:w*9/16}}><div style={{width:960,height:540,transform:`scale(${k})`,transformOrigin:'top left',background:s.bg||t.bg,color:t.fg,['--ac' as any]:t.accent}} className={`pp-in pp-${s.layout}`}>
    {s.layout!=='blank'&&<h2>{s.title}</h2>}{s.layout==='two'?<div className="pp-cols">{list(s.body)}{list(s.body2)}</div>:s.layout==='blank'?null:list(s.body)}
    {(s.shapes||[]).map(q=>{const lib=libOf(q.lib);if(!lib)return null;const p=shapePng(lib,q.text);return <img key={q.id} className="pp-shape" src={p.url} alt={lib.label} draggable={false} style={{left:q.x,top:q.y,width:q.w,height:q.w*p.h/p.w}}/>})}</div></div>}
export const DeckEditor=forwardRef<ShapeApi,EdProps>(function DeckEditor({content,onChange,readOnly,title,shelf,onShelf,request},api){
  const [deck,setDeck]=useState(()=>parseDeck(content));const [i,setI]=useState(0);const [show_,setShow]=useState(false);const stage=useRef<HTMLDivElement>(null);const [w,setW]=useState(560);
  useEffect(()=>{const el=stage.current;if(!el)return;const f=()=>setW(Math.max(240,Math.min(900,el.clientWidth)));f();const ro=new ResizeObserver(f);ro.observe(el);return()=>ro.disconnect()},[]);
  const idx=Math.min(i,deck.slides.length-1);const s=deck.slides[idx];
  const save=(d:typeof deck)=>{setDeck(d);if(!readOnly)onChange(JSON.stringify(d))};
  const patch=(p:Partial<Slide>)=>save({...deck,slides:deck.slides.map((x,j)=>j===idx?{...x,...p}:x)});
  const [pick,setPick]=useState('');const shapes=s.shapes||[];const chosen=shapes.find(q=>q.id===pick);
  const setShape=(id:string,p:Partial<SShape>)=>patch({shapes:shapes.map(q=>q.id===id?{...q,...p}:q)});
  useImperativeHandle(api,()=>({insertShape:(lib:any)=>{if(readOnly)return;const p=shapePng(lib);const w=Math.min(p.w*1.4,300),h=w*p.h/p.w;const id=Math.random().toString(36).slice(2,8);
    patch({shapes:[...shapes,{id,lib:lib.id,text:lib.text||'',x:Math.round(480-w/2),y:Math.round(270-h/2),w:Math.round(w)}]});setPick(id)}}));
  useEffect(()=>{setPick('')},[idx]);
  const drag=(q:SShape,mode:'move'|'size')=>(e:React.PointerEvent)=>{if(readOnly)return;e.stopPropagation();e.preventDefault();setPick(q.id);const k=w/960,sx=e.clientX,sy=e.clientY,q0={...q};(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const mv=(ev:PointerEvent)=>{const dx=(ev.clientX-sx)/k,dy=(ev.clientY-sy)/k;setDeck(d=>({...d,slides:d.slides.map((x,j)=>j!==idx?x:{...x,shapes:(x.shapes||[]).map(r=>r.id!==q.id?r:mode==='move'?{...r,x:Math.round(q0.x+dx),y:Math.round(q0.y+dy)}:{...r,w:Math.max(30,Math.round(q0.w+dx))})})}))};
    const up=()=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);setDeck(d=>{onChange(JSON.stringify(d));return d})};window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up)};
  const add=()=>{const n:Slide={layout:'content',title:'New slide',body:[''],notes:''};const sl=[...deck.slides];sl.splice(idx+1,0,n);save({...deck,slides:sl});setI(idx+1)};
  const dup=()=>{const sl=[...deck.slides];sl.splice(idx+1,0,JSON.parse(JSON.stringify(s)));save({...deck,slides:sl});setI(idx+1)};
  const del=()=>{if(deck.slides.length<2||!window.confirm('Delete this slide?'))return;save({...deck,slides:deck.slides.filter((_,j)=>j!==idx)});setI(Math.max(0,idx-1))};
  const mv=(d:number)=>{const j=idx+d;if(j<0||j>=deck.slides.length)return;const sl=[...deck.slides];[sl[idx],sl[j]]=[sl[j],sl[idx]];save({...deck,slides:sl});setI(j)};
  const lines=(t:string)=>t.split('\n');
  const [pw,setPw]=useState(900);
  useEffect(()=>{if(!show_)return;const f=()=>setPw(Math.min(window.innerWidth-40,(window.innerHeight-80)*16/9));f();const k=(e:KeyboardEvent)=>{if(e.key==='Escape')setShow(false);else if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();setI(x=>Math.min(deck.slides.length-1,x+1))}else if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){e.preventDefault();setI(x=>Math.max(0,x-1))}};window.addEventListener('keydown',k);window.addEventListener('resize',f);return()=>{window.removeEventListener('keydown',k);window.removeEventListener('resize',f)}},[show_,deck.slides.length]);
  const exportJson=()=>download(safeName(title,'json'),JSON.stringify(deck,null,1),'application/json');
  const printAll=()=>{const wn=window.open('','_blank');if(!wn)return;const t=THEMES[deck.theme];wn.document.write(`<!doctype html><meta charset="utf-8"><title>${esc(title)}</title><style>@page{size:landscape}body{margin:0;font-family:Arial,sans-serif}section{page-break-after:always;height:100vh;padding:7vh 7vw;box-sizing:border-box}h2{font-size:5vw;margin:0 0 4vh}li{font-size:2.6vw;margin:1vh 0}.c{display:flex;gap:4vw}</style><body>${deck.slides.map(x=>`<section style="position:relative;background:${x.bg||t.bg};color:${t.fg}">${x.layout==='blank'?'':`<h2>${esc(x.title)}</h2>`}${x.layout==='two'?`<div class="c"><ul>${(x.body||[]).map(l=>`<li>${esc(l)}</li>`).join('')}</ul><ul>${(x.body2||[]).map(l=>`<li>${esc(l)}</li>`).join('')}</ul></div>`:`<ul>${(x.body||[]).filter(l=>l.trim()).map(l=>`<li>${esc(l)}</li>`).join('')}</ul>`}${(x.shapes||[]).map(q=>{const lb=libOf(q.lib);if(!lb)return '';const p=shapePng(lb,q.text);return `<img src="${p.url}" style="position:absolute;left:${q.x/9.6}%;top:${q.y/5.4}%;width:${q.w/9.6}%">`}).join('')}</section>`).join('')}`);wn.document.close();wn.focus();wn.print()};
  return <div className="pp">
    <div className="ws-tools pp-bar">
      <button type="button" className="primary" onClick={()=>setShow(true)}><Play size={15}/> Present</button>
      {!readOnly&&<><button type="button" className="textbtn" onClick={add}><Plus size={14}/> New slide</button><button type="button" className="iconbtn" title="Duplicate slide" aria-label="Duplicate slide" onClick={dup}><Copy size={16}/></button>
        <button type="button" className="iconbtn" title="Move up" aria-label="Move slide up" onClick={()=>mv(-1)}><ArrowUp size={16}/></button><button type="button" className="iconbtn" title="Move down" aria-label="Move slide down" onClick={()=>mv(1)}><ArrowDown size={16}/></button>
        <button type="button" className="iconbtn" title="Delete slide" aria-label="Delete slide" onClick={del}><Trash2 size={16}/></button>
        <label className="wb-boardsz">Theme <select value={deck.theme} onChange={e=>save({...deck,theme:e.target.value})} aria-label="Theme">{Object.keys(THEMES).map(t=><option key={t} value={t}>{t[0].toUpperCase()+t.slice(1)}</option>)}</select></label></>}
      <button type="button" className="iconbtn" title="Print all slides or save as PDF" aria-label="Print slides" onClick={printAll}><Printer size={16}/></button>
      {request?<DownloadMenu label="Download this presentation" items={[{label:'PowerPoint (.pptx)',run:()=>convertDownload(request,'deck','pptx',title,JSON.stringify(deck),{shapes:deckShapes(deck)})},{label:'PDF',run:()=>convertDownload(request,'deck','pdf',title,JSON.stringify(deck),{shapes:deckShapes(deck)})},{label:'iSift file (.json)',run:async()=>exportJson()}]}/>:<button type="button" className="iconbtn" title="Download the presentation as a file" aria-label="Download presentation" onClick={exportJson}><Download size={16}/></button>}
      {onShelf&&<button type="button" className={`textbtn se-shapesbtn${shelf?' on':''}`} title={shelf?'Hide the shape library':'Show the shape library'} aria-pressed={!!shelf} onClick={onShelf}><Shapes size={16}/> Shapes</button>}
    </div>
    <div className="pp-main">
      <div className="pp-strip" role="listbox" aria-label="Slides">{deck.slides.map((x,j)=><button key={j} type="button" role="option" aria-selected={j===idx} className={`pp-thumb${j===idx?' on':''}`} onClick={()=>setI(j)}><span>{j+1}</span><SlideView s={x} theme={deck.theme} w={150}/></button>)}</div>
      <div className="pp-work"><div ref={stage} className="pp-stage"><div className="pp-edit" style={{width:w,height:w*9/16}} onPointerDown={()=>setPick('')}><SlideView s={s} theme={deck.theme} w={w}/>
          {!readOnly&&shapes.map(q=>{const lib=libOf(q.lib);if(!lib)return null;const p=shapePng(lib,q.text),k=w/960;return <div key={q.id} className={`pp-handle${pick===q.id?' on':''}`} style={{left:q.x*k,top:q.y*k,width:q.w*k,height:q.w*p.h/p.w*k}} onPointerDown={drag(q,'move')} role="button" tabIndex={0} aria-label={`Shape: ${lib.label}`} onKeyDown={e=>{if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();patch({shapes:shapes.filter(r=>r.id!==q.id)})}}}>{pick===q.id&&<span className="pp-grip" aria-label="Resize shape" onPointerDown={drag(q,'size')}/>}</div>})}</div></div>
        {!readOnly?<div className="pp-form">
          <label>Layout<select value={s.layout} onChange={e=>patch({layout:e.target.value as any})} aria-label="Slide layout"><option value="title">Title</option><option value="content">Title and bullets</option><option value="two">Two columns</option><option value="section">Section heading</option><option value="blank">Blank</option></select></label>
          {s.layout!=='blank'&&<label>Title<input value={s.title} onChange={e=>patch({title:e.target.value})} aria-label="Slide title"/></label>}
          {s.layout!=='blank'&&<label>{s.layout==='two'?'Left column':'Text'} (one line per bullet)<textarea rows={5} value={s.body.join('\n')} onChange={e=>patch({body:lines(e.target.value)})} aria-label="Slide text"/></label>}
          {s.layout==='two'&&<label>Right column<textarea rows={5} value={(s.body2||[]).join('\n')} onChange={e=>patch({body2:lines(e.target.value)})} aria-label="Right column text"/></label>}
          {chosen&&<div className="pp-shapebox" role="group" aria-label="Selected shape"><b>Selected shape</b>{libOf(chosen.lib)?.text!==''&&<label>Shape text<textarea rows={libOf(chosen.lib)?.k==='quad'||libOf(chosen.lib)?.k==='uclass'||libOf(chosen.lib)?.k==='entity'?5:2} value={chosen.text} onChange={e=>setShape(chosen.id,{text:e.target.value})} aria-label="Shape text"/></label>}
            <span className="pp-shapebtns"><button type="button" className="textbtn" onClick={()=>setShape(chosen.id,{w:Math.max(30,Math.round(chosen.w*0.8))})}>Smaller</button><button type="button" className="textbtn" onClick={()=>setShape(chosen.id,{w:Math.min(960,Math.round(chosen.w*1.25))})}>Larger</button><button type="button" className="textbtn danger" onClick={()=>{patch({shapes:shapes.filter(r=>r.id!==chosen.id)});setPick('')}}><Trash2 size={13}/> Remove shape</button></span></div>}
          <label>Background<input type="color" value={s.bg||THEMES[deck.theme].bg} onChange={e=>patch({bg:e.target.value})} aria-label="Slide background"/></label>
          <label>Speaker notes<textarea rows={3} value={s.notes} onChange={e=>patch({notes:e.target.value})} aria-label="Speaker notes"/></label></div>
        :s.notes&&<p className="muted pad"><b>Speaker notes:</b> {s.notes}</p>}</div></div>
    {show_&&<div className="pp-present" role="dialog" aria-label="Presentation"><button type="button" className="iconbtn pp-x" aria-label="End presentation" onClick={()=>setShow(false)}><X size={20}/></button>
      <button type="button" className="iconbtn pp-prev" aria-label="Previous slide" onClick={()=>setI(Math.max(0,idx-1))}><ChevronLeft size={26}/></button><SlideView s={s} theme={deck.theme} w={pw}/><button type="button" className="iconbtn pp-next" aria-label="Next slide" onClick={()=>setI(Math.min(deck.slides.length-1,idx+1))}><ChevronRight size={26}/></button>
      <small>{idx+1} / {deck.slides.length} · arrow keys to move, Esc to end</small></div>}
  </div>});
