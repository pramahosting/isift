import React,{useEffect,useReducer,useRef,useState} from 'react';
import {MousePointer2,Pencil,Eraser,Type,Sigma,Undo2,Redo2,Download,Copy,ArrowUpToLine,Trash2,Hand,ZoomIn,ZoomOut,Maximize2} from 'lucide-react';
import {LIB,CATS,LINE_PRESETS,TEMPLATES,libOf,ELLIPSEISH,DIAMONDISH,FRAME_KINDS,LABEL_BELOW,TEXT_HINT,drawLibShape,drawLibMarker,PROV} from './WbLib';

/* A whiteboard that mixes free-hand drawing with diagram parts: flowchart shapes, ER entities and relationships, connectors with
   arrow / crow's-foot ends that stay attached to shapes, plain text and typeset equations. The board is a list of items stored as JSON
   ({v:2,items}); boards saved by the earlier free-hand-only version ({strokes}) open as stroke items. */

export const COLORS=['#172033','#2b62f0','#f0642f','#1c9a5b','#c026d3','#f5b301'];
const FILLS:{v:string;label:string}[]=[{v:'',label:'No fill'},{v:'#ffffff',label:'White'},{v:'#dbe7ff',label:'Light blue'},{v:'#d9f3e4',label:'Light green'},{v:'#ffe6d6',label:'Light orange'},{v:'#fff3c4',label:'Light yellow'},{v:'#f3dcff',label:'Light purple'}];
const MARKERS:{v:string;label:string}[]=[{v:'none',label:'No end'},{v:'arrow',label:'Arrow'},{v:'open',label:'Open arrow'},{v:'tri',label:'Hollow triangle (inheritance)'},{v:'hdia',label:'Hollow diamond (aggregation)'},{v:'fdia',label:'Filled diamond (composition)'},{v:'dot',label:'Circle'},{v:'one',label:'One (|)'},{v:'many',label:'Many (crow’s foot)'},{v:'zone',label:'Zero or one'},{v:'zmany',label:'Zero or many'}];
const SHAPES=LIB;
const SYM:Record<string,string>={alpha:'α',beta:'β',gamma:'γ',delta:'δ',epsilon:'ε',theta:'θ',lambda:'λ',mu:'μ',pi:'π',sigma:'σ',phi:'φ',omega:'ω',Delta:'Δ',Sigma:'Σ',Omega:'Ω',Pi:'Π',infty:'∞',le:'≤',ge:'≥',ne:'≠',pm:'±',times:'×',div:'÷',cdot:'·',to:'→',approx:'≈',partial:'∂',nabla:'∇',in:'∈',cup:'∪',cap:'∩',forall:'∀',exists:'∃',rightarrow:'→',leftarrow:'←',Rightarrow:'⇒',sum:'∑',int:'∫',prod:'∏',ldots:'…',degree:'°'};
const EQ_BUTTONS:[string,string][]=[['a⁄b','\\frac{a}{b}'],['√','\\sqrt{x}'],['x²','^{2}'],['xₙ','_{n}'],['∑','\\sum_{i=1}^{n}'],['∫','\\int_{a}^{b}'],['π','\\pi '],['∞','\\infty '],['≤','\\le '],['≥','\\ge '],['≠','\\ne '],['±','\\pm '],['×','\\times '],['÷','\\div '],['α','\\alpha '],['β','\\beta '],['θ','\\theta '],['λ','\\lambda '],['μ','\\mu '],['σ','\\sigma '],['Δ','\\Delta '],['→','\\to '],['≈','\\approx '],['∂','\\partial ']];
const FONT='Inter, system-ui, sans-serif',SERIF='"Times New Roman", Georgia, serif';
const uid=()=>Math.random().toString(36).slice(2,9);

/* ---------------- equations: a small LaTeX subset (\frac \sqrt ^ _ greek and symbols) ---------------- */
type MNode={t:'txt';s:string;big?:boolean}|{t:'seq';c:MNode[]}|{t:'frac';n:MNode;d:MNode}|{t:'sqrt';c:MNode}|{t:'scr';b:MNode;sup?:MNode;sub?:MNode};
export function parseMath(src:string):MNode{
  let i=0;
  const atom=():MNode=>{const ch=src[i];
    if(ch==='{'){i++;const s=seq(true);if(src[i]==='}')i++;return s}
    if(ch==='\\'){i++;let name='';while(i<src.length&&/[A-Za-z]/.test(src[i]))name+=src[i++];
      if(!name){const c=src[i++]||'';return {t:'txt',s:c}}
      if(name==='frac'){const n=atom(),d=atom();return {t:'frac',n,d}}
      if(name==='sqrt')return {t:'sqrt',c:atom()};
      return {t:'txt',s:SYM[name]??name,big:name==='sum'||name==='int'||name==='prod'}}
    i++;return {t:'txt',s:ch||''}};
  const seq=(stop:boolean):MNode=>{const out:MNode[]=[];
    while(i<src.length){const ch=src[i];
      if(ch==='}'){if(stop)break;i++;continue}
      if(ch==='{'){i++;out.push(seq(true));if(src[i]==='}')i++;continue}
      if(ch==='^'||ch==='_'){i++;const arg=atom();const last=out.pop()||({t:'txt',s:''} as MNode);const w:any=last.t==='scr'?last:{t:'scr',b:last};if(ch==='^')w.sup=arg;else w.sub=arg;out.push(w);continue}
      out.push(atom())}
    return {t:'seq',c:out}};
  return seq(false);
}
type Box={w:number;a:number;d:number;draw:(g:CanvasRenderingContext2D,x:number,y:number)=>void};
function mlayout(g:CanvasRenderingContext2D,n:MNode,size:number):Box{
  if(n.t==='txt'){const sz=n.big?size*1.5:size;const runs:{s:string;it:boolean}[]=[];
    for(const ch of n.s){const it=!n.big&&/[A-Za-zα-ω]/.test(ch);const l=runs[runs.length-1];if(l&&l.it===it)l.s+=ch;else runs.push({s:ch,it})}
    const font=(it:boolean)=>`${it?'italic ':''}${sz}px ${SERIF}`;let w=0;for(const r of runs){g.font=font(r.it);w+=g.measureText(r.s).width}
    return {w,a:sz*(n.big?0.85:0.78),d:sz*(n.big?0.35:0.22),draw:(g2,x,y)=>{let cx=x;for(const r of runs){g2.font=font(r.it);g2.textBaseline='alphabetic';g2.fillText(r.s,cx,y);cx+=g2.measureText(r.s).width}}}}
  if(n.t==='seq'){const ch=n.c.map(c=>mlayout(g,c,size));let w=0;const xs=ch.map(c=>{const x=w;w+=c.w+1;return x});
    return {w,a:Math.max(size*0.78,...ch.map(c=>c.a)),d:Math.max(size*0.22,...ch.map(c=>c.d)),draw:(g2,x,y)=>ch.forEach((c,k)=>c.draw(g2,x+xs[k],y))}}
  if(n.t==='frac'){const fs=size*0.88,nu=mlayout(g,n.n,fs),de=mlayout(g,n.d,fs),axis=size*0.3,w=Math.max(nu.w,de.w)+8;
    return {w,a:axis+3+nu.d+nu.a,d:Math.max(size*0.22,de.a+de.d+3-axis),draw:(g2,x,y)=>{nu.draw(g2,x+(w-nu.w)/2,y-axis-3-nu.d);de.draw(g2,x+(w-de.w)/2,y-axis+3+de.a);g2.lineWidth=Math.max(1,size/16);g2.beginPath();g2.moveTo(x+2,y-axis);g2.lineTo(x+w-2,y-axis);g2.stroke()}}}
  if(n.t==='sqrt'){const inn=mlayout(g,n.c,size),pad=size*0.75,top=inn.a+3;
    return {w:inn.w+pad+3,a:top+3,d:inn.d,draw:(g2,x,y)=>{g2.lineWidth=Math.max(1,size/16);g2.beginPath();g2.moveTo(x,y-size*0.3);g2.lineTo(x+pad*0.22,y-size*0.37);g2.lineTo(x+pad*0.52,y+inn.d);g2.lineTo(x+pad,y-top);g2.lineTo(x+inn.w+pad+3,y-top);g2.stroke();inn.draw(g2,x+pad+1,y)}}}
  const b=mlayout(g,n.b,size),sup=n.sup?mlayout(g,n.sup,size*0.7):null,sub=n.sub?mlayout(g,n.sub,size*0.7):null;
  const up=Math.max(size*0.42,b.a*0.55),dn=Math.max(size*0.22,b.d+size*0.1);
  return {w:b.w+1+Math.max(sup?.w||0,sub?.w||0),a:Math.max(b.a,sup?up+sup.a:0),d:Math.max(b.d,sub?dn+sub.d:0),draw:(g2,x,y)=>{b.draw(g2,x,y);if(sup)sup.draw(g2,x+b.w+1,y-up);if(sub)sub.draw(g2,x+b.w+1,y+dn)}};
}
function eqLayout(g:CanvasRenderingContext2D,it:any){
  const lines=String(it.text||'').split('\n').map(l=>mlayout(g,parseMath(l),it.size||26));let h=0,w=0;const ys:number[]=[];
  lines.forEach(l=>{ys.push(h+l.a);h+=l.a+l.d+6;w=Math.max(w,l.w)});
  return {w:Math.max(w,12),h:Math.max(h-6,12),lines,ys};
}

/* ---------------- geometry ---------------- */
const shapeOf=(it:any)=>SHAPES.find(s=>s.k===it.k)||SHAPES[0];
const isFrame=(it:any)=>it.t==='shape'&&FRAME_KINDS.includes(it.k);
function inside(s:any,x:number,y:number){
  const cx=s.x+s.w/2,cy=s.y+s.h/2,dx=Math.abs(x-cx),dy=Math.abs(y-cy);
  if(ELLIPSEISH.includes(s.k))return (dx/(s.w/2))**2+(dy/(s.h/2))**2<=1;
  if(DIAMONDISH.includes(s.k))return dx/(s.w/2)+dy/(s.h/2)<=1;
  return dx<=s.w/2&&dy<=s.h/2;
}
function edgePoint(s:any,tx:number,ty:number):[number,number]{
  const cx=s.x+s.w/2,cy=s.y+s.h/2;let dx=tx-cx,dy=ty-cy;const L=Math.hypot(dx,dy);if(L<1)return [cx,cy];dx/=L;dy/=L;
  let lo=0,hi=Math.max(s.w,s.h)*2;for(let k=0;k<24;k++){const m=(lo+hi)/2;if(inside(s,cx+dx*m,cy+dy*m))lo=m;else hi=m}
  return [cx+dx*lo,cy+dy*lo];
}
type Pt=[number,number];
function endPos(it:any,which:'a'|'b',items:any[],g:CanvasRenderingContext2D):Pt{
  const e=it[which],o=it[which==='a'?'b':'a'];
  const center=(x:any):Pt=>{const s=x.id?items.find(i=>i.id===x.id&&i.t==='shape'):null;return s?[s.x+s.w/2,s.y+s.h/2]:[x.x,x.y]};
  const s=e.id?items.find((i:any)=>i.id===e.id&&i.t==='shape'):null;
  if(!s)return [e.x,e.y];
  const t=center(o);return edgePoint(s,t[0],t[1]);
}
function linePts(it:any,items:any[],g:CanvasRenderingContext2D):Pt[]{
  const a=endPos(it,'a',items,g),b=endPos(it,'b',items,g);
  if(it.k!=='elbow')return [a,b];
  const dx=b[0]-a[0],dy=b[1]-a[1];
  if(Math.abs(dx)>=Math.abs(dy)){const m=(a[0]+b[0])/2;return [a,[m,a[1]],[m,b[1]],b]}
  const m=(a[1]+b[1])/2;return [a,[a[0],m],[b[0],m],b];
}
function distSeg(px:number,py:number,a:Pt,b:Pt){const dx=b[0]-a[0],dy=b[1]-a[1],l2=dx*dx+dy*dy;let t=l2?((px-a[0])*dx+(py-a[1])*dy)/l2:0;t=Math.max(0,Math.min(1,t));return Math.hypot(px-(a[0]+t*dx),py-(a[1]+t*dy))}
function wrap(g:CanvasRenderingContext2D,text:string,maxW:number){
  const out:string[]=[];for(const para of String(text).split('\n')){let line='';for(const word of para.split(/\s+/)){const t=line?line+' '+word:word;if(line&&g.measureText(t).width>maxW){out.push(line);line=word}else line=t}out.push(line)}return out;
}
function bboxOf(it:any,g:CanvasRenderingContext2D):[number,number,number,number]{
  if(it.t==='shape')return [it.x,it.y,it.w,it.h];
  if(it.t==='text'){g.font=`${it.size||20}px ${FONT}`;const ls=String(it.text||' ').split('\n');const w=Math.max(20,...ls.map(l=>g.measureText(l).width));return [it.x,it.y,w,ls.length*(it.size||20)*1.3]}
  if(it.t==='eq'){const e=eqLayout(g,it);return [it.x,it.y,e.w,e.h]}
  if(it.t==='stroke'){const xs=it.p.map((p:Pt)=>p[0]),ys=it.p.map((p:Pt)=>p[1]);const x=Math.min(...xs),y=Math.min(...ys);return [x,y,Math.max(...xs)-x,Math.max(...ys)-y]}
  return [0,0,0,0];
}

/* ---------------- drawing ---------------- */
function rr(g:CanvasRenderingContext2D,x:number,y:number,w:number,h:number,r:number){r=Math.max(0,Math.min(r,w/2,h/2));g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);g.arcTo(x+w,y+h,x,y+h,r);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath()}
function drawShape(g:CanvasRenderingContext2D,s:any){
  const {x,y,w,h}=s;g.save();g.lineWidth=s.lw||2;g.strokeStyle=s.c||COLORS[0];g.setLineDash(s.dash||s.k==='container'?[8,6]:[]);g.fillStyle=s.f||'rgba(0,0,0,0)';
  if(drawLibShape(g,s,wrap,s.c||COLORS[0])){g.restore();return}
  g.beginPath();
  if(s.k==='round')rr(g,x,y,w,h,h/2);
  else if(s.k==='diamond'||s.k==='rel'){g.moveTo(x+w/2,y);g.lineTo(x+w,y+h/2);g.lineTo(x+w/2,y+h);g.lineTo(x,y+h/2);g.closePath()}
  else if(s.k==='ellipse')g.ellipse(x+w/2,y+h/2,w/2,h/2,0,0,Math.PI*2);
  else if(s.k==='para'){const o=Math.min(w*0.2,30);g.moveTo(x+o,y);g.lineTo(x+w,y);g.lineTo(x+w-o,y+h);g.lineTo(x,y+h);g.closePath()}
  else if(s.k==='cyl'){const ry=Math.min(h*0.15,16),cx=x+w/2;g.moveTo(x,y+ry);g.lineTo(x,y+h-ry);g.ellipse(cx,y+h-ry,w/2,ry,0,Math.PI,0,true);g.lineTo(x+w,y+ry);g.ellipse(cx,y+ry,w/2,ry,0,0,Math.PI,true);g.closePath()}
  else g.rect(x,y,w,h);
  if(s.f)g.fill();g.stroke();
  const size=s.size||16;g.fillStyle=s.c||COLORS[0];g.setLineDash([]);g.textBaseline='middle';
  if(s.k==='cyl'){const ry=Math.min(h*0.15,16);g.beginPath();g.ellipse(x+w/2,y+ry,w/2,ry,0,0,Math.PI*2);g.stroke()}
  if(s.k==='entity'){
    const lines=String(s.text||'').split('\n'),hh=size+16;g.save();g.globalAlpha=.16;g.fillStyle=s.c||COLORS[0];g.fillRect(x+1,y+1,w-2,hh-1);g.restore();
    g.beginPath();g.moveTo(x,y+hh);g.lineTo(x+w,y+hh);g.stroke();
    g.fillStyle=s.c||COLORS[0];g.font=`600 ${size}px ${FONT}`;g.textAlign='center';g.fillText(lines[0]||'',x+w/2,y+hh/2,w-12);
    g.textAlign='left';let yy=y+hh+size*0.95;
    for(const raw of lines.slice(1)){const pk=raw.startsWith('*');const t=pk?raw.slice(1):raw;g.font=`${pk?'600 ':''}${size-1}px ${FONT}`;g.fillText(t,x+10,yy,w-20);
      if(pk){const tw=Math.min(g.measureText(t).width,w-20);g.beginPath();g.moveTo(x+10,yy+size*0.55);g.lineTo(x+10+tw,yy+size*0.55);g.lineWidth=1.2;g.stroke()}yy+=size*1.4}
  }else if(s.text){
    g.font=`${size}px ${FONT}`;g.textAlign='center';const maxW=(s.k==='diamond'||s.k==='rel'||s.k==='ellipse'?w*0.62:w-16);const ls=wrap(g,s.text,maxW);const lh=size*1.25;
    let y0=y+h/2-(ls.length-1)*lh/2+(s.k==='cyl'?Math.min(h*0.1,10):0);ls.forEach((l,k)=>g.fillText(l,x+w/2,y0+k*lh,w-8));
  }
  g.restore();
}
function drawMarker(g:CanvasRenderingContext2D,kind:string,p:Pt,from:Pt){
  if(kind==='none'||!kind)return;
  if(drawLibMarker(g,kind,p,from))return;
  let dx=p[0]-from[0],dy=p[1]-from[1];const L=Math.hypot(dx,dy)||1;dx/=L;dy/=L;const nx=-dy,ny=dx;const at=(d:number,s=0):Pt=>[p[0]-dx*d+nx*s,p[1]-dy*d+ny*s];
  g.save();g.setLineDash([]);
  if(kind==='arrow'){g.beginPath();g.moveTo(p[0],p[1]);const a=at(13,6),b=at(13,-6);g.lineTo(a[0],a[1]);g.lineTo(b[0],b[1]);g.closePath();g.fill()}
  else{
    const bar=(d:number)=>{const a=at(d,8),b=at(d,-8);g.beginPath();g.moveTo(a[0],a[1]);g.lineTo(b[0],b[1]);g.stroke()};
    const crow=()=>{const q=at(14);for(const s of [8,0,-8]){const e=at(0,s);g.beginPath();g.moveTo(q[0],q[1]);g.lineTo(e[0],e[1]);g.stroke()}};
    const ring=(d:number)=>{const c=at(d);g.beginPath();g.arc(c[0],c[1],5,0,Math.PI*2);g.save();g.fillStyle='#fff';g.fill();g.restore();g.stroke()};
    if(kind==='one'){bar(10);bar(15)}
    if(kind==='many')crow();
    if(kind==='zone'){bar(10);ring(20)}
    if(kind==='zmany'){crow();ring(22)}
  }
  g.restore();
}
function drawLine(g:CanvasRenderingContext2D,it:any,items:any[]){
  const pts=linePts(it,items,g);g.save();g.lineWidth=it.lw||2;g.strokeStyle=it.c||COLORS[0];g.fillStyle=it.c||COLORS[0];g.setLineDash(it.dash?[8,6]:[]);g.lineJoin='round';
  g.beginPath();pts.forEach((p,i)=>i?g.lineTo(p[0],p[1]):g.moveTo(p[0],p[1]));g.stroke();
  const n=pts.length;drawMarker(g,it.mb,pts[n-1],pts[n-2]);drawMarker(g,it.ma,pts[0],pts[1]);
  if(it.text){const m=pts.length===4?[(pts[1][0]+pts[2][0])/2,(pts[1][1]+pts[2][1])/2]:[(pts[0][0]+pts[n-1][0])/2,(pts[0][1]+pts[n-1][1])/2];
    g.font=`${it.size||14}px ${FONT}`;g.textAlign='center';g.textBaseline='middle';const tw=g.measureText(it.text).width;g.fillStyle='#fff';g.fillRect(m[0]-tw/2-3,m[1]-9,tw+6,18);g.fillStyle=it.c||COLORS[0];g.fillText(it.text,m[0],m[1])}
  g.restore();
}
function drawItem(g:CanvasRenderingContext2D,it:any,items:any[]){
  if(it.t==='stroke'){g.save();g.strokeStyle=it.c;g.lineWidth=it.w;g.lineCap='round';g.lineJoin='round';g.beginPath();it.p.forEach(([x,y]:Pt,i:number)=>i?g.lineTo(x,y):g.moveTo(x,y));if(it.p.length===1)g.lineTo(it.p[0][0]+.1,it.p[0][1]);g.stroke();g.restore()}
  else if(it.t==='shape')drawShape(g,it);
  else if(it.t==='line')drawLine(g,it,items);
  else if(it.t==='text'){g.save();g.fillStyle=it.c||COLORS[0];g.font=`${it.size||20}px ${FONT}`;g.textBaseline='top';g.textAlign='left';String(it.text||'').split('\n').forEach((l,k)=>g.fillText(l,it.x,it.y+k*(it.size||20)*1.3));g.restore()}
  else if(it.t==='eq'){g.save();g.fillStyle=g.strokeStyle=it.c||COLORS[0];const e=eqLayout(g,it);e.lines.forEach((l,k)=>l.draw(g,it.x,it.y+e.ys[k]));g.restore()}
}
function hit(items:any[],x:number,y:number,g:CanvasRenderingContext2D,erase=false,z=1):any{
  for(let k=items.length-1;k>=0;k--){const it=items[k];
    if(isFrame(it)){const m=12*z,band=it.k==='bpool'?Math.min(34,it.w/4):30;const onEdge=x>=it.x-m&&x<=it.x+it.w+m&&y>=it.y-m&&y<=it.y+it.h+m&&(x<it.x+m||x>it.x+it.w-m||y<it.y+m||y>it.y+it.h-m);const onTitle=x>=it.x&&x<=it.x+(it.k==='bpool'?band:it.w)&&y>=it.y&&y<=it.y+(it.k==='bpool'?it.h:band);if(onEdge||(!erase&&onTitle))return it;continue}
    if(it.t==='shape'){if(erase){const o=inside({...it,x:it.x-6,y:it.y-6,w:it.w+12,h:it.h+12},x,y),i2=inside({...it,x:it.x+8,y:it.y+8,w:Math.max(2,it.w-16),h:Math.max(2,it.h-16)},x,y);if(o&&!i2)return it}else if(inside(it,x,y))return it}
    else if(it.t==='line'){const p=linePts(it,items,g);for(let i=1;i<p.length;i++)if(distSeg(x,y,p[i-1],p[i])<8*z)return it}
    else if(it.t==='stroke'){const r=Math.max(7*z,it.w/2+4);for(let i=0;i<it.p.length;i++){const a=it.p[i],b=it.p[i+1]||a;if(distSeg(x,y,a,b)<r)return it}}
    else{const [bx,by,bw,bh]=bboxOf(it,g);if(x>=bx-4&&x<=bx+bw+4&&y>=by-4&&y<=by+bh+4)return it}
  }
  return null;
}

/* ---------------- toolbar icons ---------------- */
function ShapeIcon({k}:{k:string}){
  const p={fill:'none',stroke:'currentColor',strokeWidth:1.6} as any;
  return <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">{k==='rect'?<rect x="2.5" y="5" width="15" height="10" {...p}/>:k==='round'?<rect x="2" y="6" width="16" height="8" rx="4" {...p}/>:k==='diamond'?<path d="M10 2.5 17.5 10 10 17.5 2.5 10Z" {...p}/>:k==='ellipse'?<ellipse cx="10" cy="10" rx="7.5" ry="5" {...p}/>:k==='para'?<path d="M6 5h11l-3 10H3z" {...p}/>:k==='cyl'?<g {...p}><path d="M4 5v10c0 1.5 2.7 2.5 6 2.5s6-1 6-2.5V5"/><ellipse cx="10" cy="5" rx="6" ry="2.3"/></g>:k==='entity'?<g {...p}><rect x="3" y="3" width="14" height="14"/><path d="M3 7.5h14M3 12h14"/></g>:k==='rel'?<g {...p}><path d="M10 2.5 17.5 10 10 17.5 2.5 10Z"/><path d="M10 6 14 10 10 14 6 10Z"/></g>:k==='line'?<path d="M3 16 17 4" {...p}/>:k==='arrow'?<g {...p}><path d="M3 16 16 5"/><path d="M11 4.5h5.5V10" /></g>:<g {...p}><path d="M3 15h7V5h7"/><path d="M14 2.5 17 5l-3 2.5"/></g>}</svg>;
}

type Tool='select'|'pen'|'eraser'|'text'|'eq'|'line'|'arrow'|'elbow'|'hand'|string;
const FIT_PAD=60;
const BOARDS:{id:string;label:string;w:number;h:number}[]=[{id:'std',label:'Standard 1200 × 700',w:1200,h:700},{id:'wide',label:'Wide 1800 × 700',w:1800,h:700},{id:'tall',label:'Tall 900 × 1200',w:900,h:1200},{id:'sq',label:'Square 1000 × 1000',w:1000,h:1000},{id:'big',label:'Large 2400 × 1400',w:2400,h:1400}];
const mkShape=(lib:any,x:number,y:number,color=COLORS[0],w=lib.w,h=lib.h)=>{const {id,cat,label,w:_w,h:_h,...rest}=lib;return {id:uid(),t:'shape',lib:id,x,y,w,h,c:color,f:'',lw:2,size:16,...rest}};
function clone<T>(o:T):T{return JSON.parse(JSON.stringify(o))}
function moveItem(it:any,o:any,dx:number,dy:number){
  if(it.t==='stroke')it.p=o.p.map(([x,y]:Pt)=>[x+dx,y+dy]);
  else if(it.t==='line'){for(const wh of ['a','b'] as const)if(!o[wh].id)it[wh]={x:o[wh].x+dx,y:o[wh].y+dy}}
  else{it.x=o.x+dx;it.y=o.y+dy}
}
function Preview({item}:{item:any}){
  const r=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{const c=r.current;if(!c)return;const g=c.getContext('2d')!;g.clearRect(0,0,c.width,c.height);const sc=Math.min(46/item.w,34/item.h,1);
    g.save();g.translate(c.width/2,c.height/2);g.scale(sc,sc);g.translate(-item.w/2,-item.h/2);
    drawShape(g,{...item,x:0,y:0,text:item.k==='quad'||item.k==='uclass'?item.text:item.k==='svc'?item.text:'',lw:1.6/sc,size:item.k==='quad'?12:item.k==='svc'?15:13,c:item.prov?'#172033':'#172033',f:item.f||''});g.restore()},[item.id]);
  return <canvas ref={r} width={56} height={40} aria-hidden="true"/>;
}
export function Board({content,onChange,name,pictureRef}:{content:string;onChange:(c:string)=>void;name?:string;pictureRef?:React.MutableRefObject<(()=>string|null)|null>}){
  const cv=useRef<HTMLCanvasElement>(null);const items=useRef<any[]>([]);const hist=useRef<string[]>([]);const hidx=useRef(0);
  const [tool,setTool]=useState<Tool>('pen');const [color,setColor]=useState(COLORS[0]);const [w,setW]=useState(3);const [snap,setSnap]=useState(false);
  const [sel,setSel]=useState<string>('');const [,force]=useReducer((x:number)=>x+1,0);
  const [cat,setCat]=useState('basic');const [libOpen,setLibOpen]=useState(true);const [bsz,setBsz]=useState({w:1200,h:700});
  const view=useRef({s:1,x:0,y:0});const spaceDown=useRef(false);const viewTimer=useRef<any>(null);const bszRef=useRef(bsz);bszRef.current=bsz;
  const drag=useRef<any>(null);const draft=useRef<any>(null);const typing=useRef<any>(null);const taRef=useRef<HTMLTextAreaElement>(null);const wrapRef=useRef<HTMLDivElement>(null);
  const selItem=()=>items.current.find(i=>i.id===sel)||null;
  const ctx=()=>cv.current!.getContext('2d')!;
  const draw=(noUi=false)=>{const c=cv.current;if(!c)return;const g=c.getContext('2d')!;const v=view.current;g.setTransform(1,0,0,1,0,0);g.fillStyle='#fff';g.fillRect(0,0,c.width,c.height);g.setTransform(v.s,0,0,v.s,v.x,v.y);
    const all=draft.current?[...items.current,draft.current]:items.current;const k=1/v.s;
    if(snap&&!noUi&&v.s>=0.4){g.fillStyle='#d9dfeb';const x0=Math.floor(-v.x/v.s/20)*20,x1=(c.width-v.x)/v.s,y0=Math.floor(-v.y/v.s/20)*20,y1=(c.height-v.y)/v.s;for(let x=x0;x<x1;x+=20)for(let y=y0;y<y1;y+=20)g.fillRect(x,y,1.5*k,1.5*k)}
    for(const it of all)drawItem(g,it,all);
    const s=!noUi&&all.find((i:any)=>i.id===selRef.current);
    if(s){g.save();g.strokeStyle='#2b62f0';g.fillStyle='#fff';g.lineWidth=1.4*k;g.setLineDash([5*k,4*k]);const hs=5*k;
      if(s.t==='line'){const a=endPos(s,'a',all,g),b=endPos(s,'b',all,g);g.setLineDash([]);for(const p of [a,b]){g.beginPath();g.arc(p[0],p[1],6*k,0,Math.PI*2);g.fill();g.stroke()}}
      else{const [x,y,bw,bh]=bboxOf(s,g);g.strokeRect(x-4*k,y-4*k,bw+8*k,bh+8*k);g.setLineDash([]);if(s.t==='shape')for(const [hx,hy] of [[x,y],[x+bw,y],[x,y+bh],[x+bw,y+bh]]){g.fillRect(hx-hs,hy-hs,hs*2,hs*2);g.strokeRect(hx-hs,hy-hs,hs*2,hs*2)}}
      g.restore()}};
  const selRef=useRef('');selRef.current=sel;
  const save=()=>onChange(JSON.stringify({v:2,items:items.current,board:bszRef.current,view:view.current}));
  const saveView=()=>{clearTimeout(viewTimer.current);viewTimer.current=setTimeout(save,600)};
  const commit=()=>{const j=JSON.stringify(items.current);hist.current=hist.current.slice(0,hidx.current+1);if(hist.current[hidx.current]===j){return}hist.current.push(j);if(hist.current.length>100)hist.current.shift();hidx.current=hist.current.length-1;save();draw();force()};
  const restore=(i:number)=>{if(i<0||i>=hist.current.length)return;hidx.current=i;items.current=JSON.parse(hist.current[i]);if(!items.current.some(x=>x.id===selRef.current))setSel('');save();draw();force()};
  useEffect(()=>{let data:any={};try{data=JSON.parse(content||'{}')}catch{}
    items.current=Array.isArray(data.items)?data.items:(data.strokes||[]).map((s:any)=>({id:uid(),t:'stroke',c:s.c,w:s.w,p:s.p}));
    if(data.board&&data.board.w>=300&&data.board.h>=300){const b={w:Math.min(4000,data.board.w),h:Math.min(4000,data.board.h)};setBsz(b);bszRef.current=b}
    if(data.view&&data.view.s>0)view.current={s:Math.min(4,Math.max(0.2,data.view.s)),x:Number(data.view.x)||0,y:Number(data.view.y)||0};
    hist.current=[JSON.stringify(items.current)];hidx.current=0;setTimeout(draw,0)},[]);
  useEffect(()=>{draw()},[sel,snap,tool,bsz]);
  /* ---- zoom and pan ---- */
  const zoomTo=(ns:number,cx:number,cy:number)=>{const v=view.current;ns=Math.min(4,Math.max(0.2,ns));v.x=cx-(cx-v.x)*(ns/v.s);v.y=cy-(cy-v.y)*(ns/v.s);v.s=ns;draw();force();saveView()};
  const zoomBy=(f:number)=>{const c=cv.current!;zoomTo(view.current.s*f,c.width/2,c.height/2)};
  const fitAll=()=>{const c=cv.current!;const g=ctx();const list=items.current;if(!list.length){view.current={s:1,x:0,y:0};draw();force();saveView();return}
    let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;for(const it of list){if(it.t==='line'){for(const wh of ['a','b'] as const){const q=endPos(it,wh,list,g);x0=Math.min(x0,q[0]);y0=Math.min(y0,q[1]);x1=Math.max(x1,q[0]);y1=Math.max(y1,q[1])}}else{const [bx,by,bw,bh]=bboxOf(it,g);x0=Math.min(x0,bx);y0=Math.min(y0,by);x1=Math.max(x1,bx+bw);y1=Math.max(y1,by+bh+(LABEL_BELOW.includes(it.k)?36:0))}}
    const s=Math.min(4,Math.max(0.2,Math.min((c.width-FIT_PAD*2)/Math.max(40,x1-x0),(c.height-FIT_PAD*2)/Math.max(40,y1-y0))));
    view.current={s,x:c.width/2-(x0+x1)/2*s,y:c.height/2-(y0+y1)/2*s};draw();force();saveView()};
  useEffect(()=>{const c=cv.current;if(!c)return;const fn=(e:WheelEvent)=>{if(!(e.ctrlKey||e.metaKey))return;e.preventDefault();const r=c.getBoundingClientRect();const cx=(e.clientX-r.left)*c.width/r.width,cy=(e.clientY-r.top)*c.height/r.height;zoomTo(view.current.s*Math.exp(-e.deltaY*0.0015*(e.deltaMode?30:1)),cx,cy)};c.addEventListener('wheel',fn,{passive:false});return()=>c.removeEventListener('wheel',fn)},[]);
  const cpx=(e:{clientX:number;clientY:number}):Pt=>{const r=cv.current!.getBoundingClientRect();return [(e.clientX-r.left)*cv.current!.width/r.width,(e.clientY-r.top)*cv.current!.height/r.height]};
  const pt=(e:{clientX:number;clientY:number}):Pt=>{const [sx,sy]=cpx(e);const v=view.current;let x=Math.round((sx-v.x)/v.s),y=Math.round((sy-v.y)/v.s);if(snap){x=Math.round(x/10)*10;y=Math.round(y/10)*10}return [x,y]};
  const bindAt=(p:Pt,skip?:string)=>{for(let k=items.current.length-1;k>=0;k--){const s=items.current[k];if(s.t==='shape'&&s.id!==skip&&!isFrame(s)&&s.k!=='quad'&&inside({...s,x:s.x-8,y:s.y-8,w:s.w+16,h:s.h+16},p[0],p[1]))return s}return null};
  const addItem=(it:any)=>{items.current.push(it);setSel(it.id);selRef.current=it.id};
  const focusText=()=>setTimeout(()=>{taRef.current?.focus();taRef.current?.select()},30);
  const onDown=(e:React.PointerEvent)=>{
    (e.target as Element).setPointerCapture(e.pointerId);wrapRef.current?.focus({preventScroll:true});
    if(tool==='hand'||spaceDown.current||e.button===1){const [sx,sy]=cpx(e);drag.current={mode:'pan',sx,sy,ox:view.current.x,oy:view.current.y};return}
    const p=pt(e);const g=ctx();const z=1/view.current.s;
    if(tool==='pen'){draft.current={id:uid(),t:'stroke',c:color,w,p:[p]};draw();return}
    if(tool==='eraser'){drag.current={mode:'erase',changed:false};const h=hit(items.current,p[0],p[1],g,true,z);if(h){items.current=items.current.filter(i=>i!==h);drag.current.changed=true;draw()}return}
    if(tool==='text'||tool==='eq'){const it=tool==='text'?{id:uid(),t:'text',x:p[0],y:p[1]-10,text:'Text',c:color,size:20}:{id:uid(),t:'eq',x:p[0],y:p[1]-16,text:'x^{2}+y^{2}=r^{2}',c:color,size:28};addItem(it);setTool('select');commit();focusText();return}
    const lp=tool.startsWith('lp:')?LINE_PRESETS.find(l=>l.id===tool.slice(3)):null;
    if(tool==='line'||tool==='arrow'||tool==='elbow'||lp){const s=bindAt(p);draft.current={id:uid(),t:'line',k:lp?lp.k:tool==='elbow'?'elbow':'straight',a:s?{id:s.id,x:p[0],y:p[1]}:{x:p[0],y:p[1]},b:{x:p[0],y:p[1]},ma:lp?lp.ma:'none',mb:lp?lp.mb:tool==='line'?'none':'arrow',dash:lp?!!lp.dash:false,c:color,lw:Math.min(w,4)||2};drag.current={mode:'newline'};draw();return}
    const lib=libOf(tool);
    if(lib){drag.current={mode:'create',start:p,lib};draft.current=mkShape({...lib,text:''},p[0],p[1],color,1,1);draft.current.f=lib.f||'';draw();return}
    // select tool: handles first, then bodies
    const s=selItem();
    if(s&&s.t==='line'){for(const wh of ['a','b'] as const){const q=endPos(s,wh,items.current,g);if(Math.hypot(q[0]-p[0],q[1]-p[1])<10*z){drag.current={mode:'end',which:wh,id:s.id};return}}}
    if(s&&s.t==='shape'){const [x,y,bw,bh]=bboxOf(s,g);for(const [hx,hy,ax,ay] of [[x,y,x+bw,y+bh],[x+bw,y,x,y+bh],[x,y+bh,x+bw,y],[x+bw,y+bh,x,y]] as number[][])if(Math.abs(hx-p[0])<9*z&&Math.abs(hy-p[1])<9*z){drag.current={mode:'resize',id:s.id,ax,ay};return}}
    const h=hit(items.current,p[0],p[1],g,false,z);
    if(h){setSel(h.id);selRef.current=h.id;
      const group=isFrame(h)?items.current.filter(i=>i!==h&&(i.t==='line'?(!i.a.id&&!i.b.id&&inside(h,(i.a.x+i.b.x)/2,(i.a.y+i.b.y)/2)):(()=>{const [bx,by,bw,bh]=bboxOf(i,g);return inside(h,bx+bw/2,by+bh/2)}))).map(i=>({id:i.id,orig:clone(i)})):[];
      drag.current={mode:'move',id:h.id,start:p,orig:clone(h),group,moved:false}}else{setSel('');selRef.current=''}
    draw();force();
  };
  const onMove=(e:React.PointerEvent)=>{
    const d0=drag.current;
    if(d0?.mode==='pan'){const [sx,sy]=cpx(e);view.current.x=d0.ox+(sx-d0.sx);view.current.y=d0.oy+(sy-d0.sy);draw();return}
    const p=pt(e);const g=ctx();const z=1/view.current.s;
    if(draft.current&&draft.current.t==='stroke'){draft.current.p.push(p);draw();return}
    const d=drag.current;if(!d)return;
    if(d.mode==='erase'){const h=hit(items.current,p[0],p[1],g,true,z);if(h){items.current=items.current.filter(i=>i!==h);d.changed=true;draw()}return}
    if(d.mode==='create'){const dr=draft.current;dr.x=Math.min(d.start[0],p[0]);dr.y=Math.min(d.start[1],p[1]);dr.w=Math.abs(p[0]-d.start[0]);dr.h=Math.abs(p[1]-d.start[1]);draw();return}
    if(d.mode==='newline'){const dr=draft.current;const s=bindAt(p,dr.a.id);dr.b=s?{id:s.id,x:p[0],y:p[1]}:{x:p[0],y:p[1]};draw();return}
    const it=items.current.find(i=>i.id===d.id);if(!it)return;
    if(d.mode==='end'){const s=bindAt(p,it[d.which==='a'?'b':'a'].id);it[d.which]=s?{id:s.id,x:p[0],y:p[1]}:{x:p[0],y:p[1]};draw();return}
    if(d.mode==='resize'){it.x=Math.min(d.ax,p[0]);it.y=Math.min(d.ay,p[1]);it.w=Math.max(30,Math.abs(p[0]-d.ax));it.h=Math.max(24,Math.abs(p[1]-d.ay));draw();return}
    if(d.mode==='move'){const dx=p[0]-d.start[0],dy=p[1]-d.start[1];if(!d.moved&&Math.hypot(dx,dy)<3*z)return;d.moved=true;moveItem(it,d.orig,dx,dy);for(const gi of d.group||[]){const t=items.current.find(i=>i.id===gi.id);if(t)moveItem(t,gi.orig,dx,dy)}
      draw()}
  };
  const onUp=()=>{
    if(draft.current&&draft.current.t==='stroke'){items.current.push(draft.current);draft.current=null;commit();return}
    const d=drag.current;drag.current=null;
    if(d?.mode==='pan'){saveView();return}
    if(d?.mode==='erase'){if(d.changed)commit();return}
    if(d?.mode==='create'){const dr=draft.current;draft.current=null;const sp=d.lib;
      if(dr.w<8&&dr.h<8){dr.w=sp.w;dr.h=sp.h;dr.x=d.start[0]-sp.w/2;dr.y=d.start[1]-sp.h/2}else{dr.w=Math.max(dr.w,30);dr.h=Math.max(dr.h,24)}
      dr.text=sp.text;addItem(dr);setTool('select');commit();focusText();return}
    if(d?.mode==='newline'){const dr=draft.current;draft.current=null;
      if(Math.hypot(dr.b.x-dr.a.x,dr.b.y-dr.a.y)<8&&!dr.b.id){draw();return}
      addItem(dr);setTool('select');commit();return}
    if(d?.mode==='move'&&!d.moved){return}
    if(d)commit();
  };
  const onDouble=(e:React.MouseEvent)=>{if(tool!=='select')return;const [x,y]=pt(e);const h=hit(items.current,x,y,ctx(),false,1/view.current.s);if(h){setSel(h.id);selRef.current=h.id;force();focusText()}};
  const patch=(p:any,keep=false)=>{const it=selItem();if(!it)return;Object.assign(it,p);draw();force();if(keep){save();clearTimeout(typing.current);typing.current=setTimeout(commit,600)}else commit()};
  const remove=()=>{const it=selItem();if(!it)return;items.current=items.current.filter(i=>i!==it&&!(i.t==='line'&&(i.a.id===it.id||i.b.id===it.id)));setSel('');selRef.current='';commit()};
  const dup=()=>{const it=selItem();if(!it)return;const c=clone(it);c.id=uid();if(c.t==='stroke')c.p=c.p.map(([x,y]:Pt)=>[x+20,y+20]);else if(c.t==='line'){for(const wh of ['a','b']){const q=c[wh].id?endPos(it,wh as any,items.current,ctx()):[c[wh].x,c[wh].y];c[wh]={x:q[0]+20,y:q[1]+20}}}else{c.x+=20;c.y+=20}items.current.push(c);setSel(c.id);selRef.current=c.id;commit()};
  const toFront=()=>{const it=selItem();if(!it)return;items.current=[...items.current.filter(i=>i!==it),it];commit()};
  const toBack=()=>{const it=selItem();if(!it)return;items.current=[it,...items.current.filter(i=>i!==it)];commit()};
  const key=(e:React.KeyboardEvent)=>{const tag=(e.target as HTMLElement).tagName;if(tag==='TEXTAREA'||tag==='INPUT'||tag==='SELECT')return;
    if(e.key===' '){e.preventDefault();spaceDown.current=true;return}
    if((e.ctrlKey||e.metaKey)&&(e.key==='+'||e.key==='=')){e.preventDefault();zoomBy(1.25);return}
    if((e.ctrlKey||e.metaKey)&&e.key==='-'){e.preventDefault();zoomBy(0.8);return}
    if((e.ctrlKey||e.metaKey)&&e.key==='0'){e.preventDefault();zoomTo(1,cv.current!.width/2,cv.current!.height/2);return}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();restore(hidx.current+(e.shiftKey?1:-1));return}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();restore(hidx.current+1);return}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='d'){e.preventDefault();dup();return}
    if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();remove();return}
    if(e.key==='Escape'){setSel('');selRef.current='';setTool('select');draw()}};
  const keyUp=(e:React.KeyboardEvent)=>{if(e.key===' ')spaceDown.current=false};
  const renderAll=():HTMLCanvasElement|null=>{const list=items.current;const g0=ctx();if(!list.length)return null;
    let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;for(const it of list){if(it.t==='line'){for(const wh of ['a','b'] as const){const q=endPos(it,wh,list,g0);x0=Math.min(x0,q[0]);y0=Math.min(y0,q[1]);x1=Math.max(x1,q[0]);y1=Math.max(y1,q[1])}}else{const [bx,by,bw,bh]=bboxOf(it,g0);x0=Math.min(x0,bx);y0=Math.min(y0,by);x1=Math.max(x1,bx+bw);y1=Math.max(y1,by+bh+(LABEL_BELOW.includes(it.k)?36:0))}}
    const pad=30,sc=Math.min(2,3800/Math.max(1,x1-x0+pad*2),3800/Math.max(1,y1-y0+pad*2));const o=document.createElement('canvas');o.width=Math.ceil((x1-x0+pad*2)*sc);o.height=Math.ceil((y1-y0+pad*2)*sc);const g=o.getContext('2d')!;g.fillStyle='#fff';g.fillRect(0,0,o.width,o.height);g.setTransform(sc,0,0,sc,(pad-x0)*sc,(pad-y0)*sc);for(const it of list)drawItem(g,it,list);
    return o};
  const exportPng=()=>{const o=renderAll();if(!o)return;
    o.toBlob(b=>{if(b){const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=`${(name||'whiteboard').replace(/[^\w\- ]+/g,'')||'whiteboard'}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}})};
  if(pictureRef)pictureRef.current=()=>{const o=renderAll();if(!o)return null;const k=Math.min(1,2400/Math.max(o.width,o.height));if(k<1){const q=document.createElement('canvas');q.width=Math.round(o.width*k);q.height=Math.round(o.height*k);const g=q.getContext('2d')!;g.fillStyle='#fff';g.fillRect(0,0,q.width,q.height);g.drawImage(o,0,0,q.width,q.height);return q.toDataURL('image/jpeg',0.88)}return o.toDataURL('image/jpeg',0.88)};
  const addTemplate=(id:string)=>{const t=TEMPLATES.find(x=>x.id===id);if(!t)return;const v=view.current,c=cv.current!;const cxw=(c.width/2-v.x)/v.s,cyw=(c.height/2-v.y)/v.s;
    const ids:Record<string,string>={};let mx=0,my=0;const made:any[]=[];
    const dims=t.nodes.map(([key,lid,x,y])=>{const l=libOf(lid)!;mx=Math.max(mx,x+(key==='pool'?l.w:l.w));my=Math.max(my,y+l.h);return l});
    const ox=Math.round(cxw-mx/2),oy=Math.round(cyw-my/2);
    t.nodes.forEach(([key,lid,x,y,text],i)=>{const l=dims[i];const it=mkShape(l,ox+x,oy+y,COLORS[0]);if(text!==undefined)it.text=text;if(l.f)it.f=l.f;ids[key]=it.id;made.push(it)});
    for(const [a,b,label,pre] of t.edges){const lp=LINE_PRESETS.find(l=>l.id===pre);made.push({id:uid(),t:'line',k:lp?lp.k:'straight',a:{id:ids[a],x:0,y:0},b:{id:ids[b],x:0,y:0},ma:lp?lp.ma:'none',mb:lp?lp.mb:'arrow',dash:lp?!!lp.dash:false,c:COLORS[0],lw:2,text:label||'',size:13})}
    items.current.push(...made);setSel('');selRef.current='';setTool('select');commit()};
  const s=selItem();const isShape=s?.t==='shape',isLine=s?.t==='line',isText=s?.t==='text',isEq=s?.t==='eq';
  const insertEq=(snip:string)=>{const ta=taRef.current;if(!ta||!s)return;const a=ta.selectionStart,b=ta.selectionEnd;const v=String(s.text||'');patch({text:v.slice(0,a)+snip+v.slice(b)},true);setTimeout(()=>{ta.focus();const pos=a+snip.length;ta.setSelectionRange(pos,pos)},0)};
  const tb=(t:Tool,label:string,icon:React.ReactNode)=><button key={t} type="button" className={`iconbtn${tool===t?' on':''}`} title={label} aria-label={label} aria-pressed={tool===t} onClick={()=>{setTool(t);if(t==='pen'||t==='eraser'||t==='hand'){setSel('');selRef.current=''}}}>{icon}</button>;
  const cls=tool==='pen'?'':tool==='eraser'?'erasing':tool==='hand'?'tool-hand':tool==='select'?'tool-select':'tool-shape';
  const setBoard=(b:{w:number;h:number})=>{const nb={w:Math.min(4000,Math.max(300,Math.round(b.w)||1200)),h:Math.min(4000,Math.max(300,Math.round(b.h)||700))};setBsz(nb);bszRef.current=nb;setTimeout(()=>{draw();save()},0)};
  const preset=BOARDS.find(b=>b.w===bsz.w&&b.h===bsz.h)?.id||'custom';
  const libItems=LIB.filter(l=>l.cat===cat);
  return <div className="ws-board wb2" ref={wrapRef} tabIndex={0} onKeyDown={key} onKeyUp={keyUp}>
    <div className="ws-tools" role="toolbar" aria-label="Whiteboard tools">
      {tb('select','Select, move and resize',<MousePointer2 size={16}/>)}{tb('pen','Pencil (free hand)',<Pencil size={16}/>)}{tb('eraser','Eraser (removes what you touch)',<Eraser size={16}/>)}{tb('hand','Hand: drag to move around the board (or hold the space bar)',<Hand size={16}/>)}
      <span className="wb-sep"/>
      {tb('line','Line',<ShapeIcon k="line"/>)}{tb('arrow','Arrow',<ShapeIcon k="arrow"/>)}{tb('elbow','Elbow connector',<ShapeIcon k="elbow"/>)}
      <span className="wb-sep"/>
      {tb('text','Text',<Type size={16}/>)}{tb('eq','Equation',<Sigma size={16}/>)}
      <span className="wb-sep"/>
      {COLORS.map(c=><button key={c} type="button" className={`ws-sw${(s?s.c:color)===c?' on':''}`} style={{background:c}} aria-label={`Colour ${c}`} onClick={()=>{setColor(c);if(s)patch({c})}}/>)}
      <select value={s?(s.lw||s.w||2):w} onChange={e=>{const v=Number(e.target.value);setW(v);if(s&&(s.t==='stroke'))patch({w:v});else if(s&&(isShape||isLine))patch({lw:Math.min(v,8)})}} aria-label="Line width"><option value={2}>Thin</option><option value={3}>Medium</option><option value={7}>Thick</option><option value={16}>Marker</option></select>
      <label className="check wb-snap"><input type="checkbox" checked={snap} onChange={e=>setSnap(e.target.checked)}/> Snap to grid</label>
      <button type="button" className="iconbtn" title="Undo (Ctrl+Z)" aria-label="Undo" onClick={()=>restore(hidx.current-1)}><Undo2 size={16}/></button>
      <button type="button" className="iconbtn" title="Redo (Ctrl+Y)" aria-label="Redo" onClick={()=>restore(hidx.current+1)}><Redo2 size={16}/></button>
      <button type="button" className="iconbtn" title="Download the whole board as a picture" aria-label="Download as picture" onClick={exportPng}><Download size={16}/></button>
      <button type="button" className="textbtn danger" onClick={()=>{if(window.confirm('Clear the whole board?')){items.current=[];setSel('');selRef.current='';commit()}}}>Clear</button></div>
    <div className="ws-tools wb-view" role="toolbar" aria-label="Zoom and board shape">
      <button type="button" className="iconbtn" title="Zoom out (Ctrl and minus)" aria-label="Zoom out" onClick={()=>zoomBy(0.8)}><ZoomOut size={16}/></button>
      <button type="button" className="textbtn wb-zoom" title="Back to 100%" aria-label="Zoom level, press for 100 percent" onClick={()=>zoomTo(1,cv.current!.width/2,cv.current!.height/2)}>{Math.round(view.current.s*100)}%</button>
      <button type="button" className="iconbtn" title="Zoom in (Ctrl and plus)" aria-label="Zoom in" onClick={()=>zoomBy(1.25)}><ZoomIn size={16}/></button>
      <button type="button" className="iconbtn" title="Fit everything on the screen" aria-label="Fit everything" onClick={fitAll}><Maximize2 size={16}/></button>
      <span className="wb-sep"/>
      <label className="wb-boardsz">Board shape <select value={preset} onChange={e=>{const b=BOARDS.find(x=>x.id===e.target.value);if(b)setBoard(b);else setBoard({w:bsz.w,h:bsz.h+1})}} aria-label="Board shape">{BOARDS.map(b=><option key={b.id} value={b.id}>{b.label}</option>)}<option value="custom">Custom…</option></select></label>
      {preset==='custom'&&<><label className="wb-boardsz">W <input type="number" min={300} max={4000} step={50} value={bsz.w} onChange={e=>setBoard({w:Number(e.target.value),h:bsz.h})} aria-label="Board width"/></label><label className="wb-boardsz">H <input type="number" min={300} max={4000} step={50} value={bsz.h} onChange={e=>setBoard({w:bsz.w,h:Number(e.target.value)})} aria-label="Board height"/></label></>}
      <span className="wb-sep"/>
      <label className="wb-boardsz">Insert a workflow <select value="" onChange={e=>{if(e.target.value)addTemplate(e.target.value)}} aria-label="Insert a ready-made workflow"><option value="">Choose…</option>{TEMPLATES.map(t=><option key={t.id} value={t.id}>{t.label}</option>)}</select></label>
      <button type="button" className="textbtn" onClick={()=>setLibOpen(!libOpen)} aria-expanded={libOpen}>{libOpen?'Hide shapes':'Show shapes'}</button></div>
    {libOpen&&<div className="wb-lib" aria-label="Shape library">
      <div className="wb-cats" role="tablist" aria-label="Shape categories">{CATS.map(c=><button key={c.id} type="button" role="tab" aria-selected={cat===c.id} className={`wb-cat${cat===c.id?' on':''}`} onClick={()=>setCat(c.id)}>{c.label}</button>)}</div>
      <div className="wb-items">{cat==='conn'?LINE_PRESETS.map(l=><button key={l.id} type="button" className={`wb-item${tool==='lp:'+l.id?' on':''}`} title={l.label} aria-pressed={tool==='lp:'+l.id} onClick={()=>setTool('lp:'+l.id)}><LinePreview p={l}/><span>{l.label}</span></button>)
        :libItems.map(l=><button key={l.id} type="button" className={`wb-item${tool===l.id?' on':''}`} title={l.label} aria-pressed={tool===l.id} onClick={()=>{setTool(l.id);setSel('');selRef.current=''}}><Preview item={l}/><span>{l.label}</span></button>)}</div>
      {['aws','azure','gcp','ai'].includes(cat)&&<small className="muted">Generic service tiles in {PROV[cat]?.name||'each'} colours, not official logos. Pick one, then click or drag on the board. Link them with Arrow or Sequence flow.</small>}</div>}
    <div className="wb-stage"><canvas ref={cv} className={cls} width={bsz.w} height={bsz.h} aria-label="Whiteboard" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onDoubleClick={onDouble}/></div>
    {s&&s.t!=='stroke'&&<div className="wb-inspect" role="group" aria-label="Selected item">
      {(isShape||isText||isEq||isLine)&&<label className="wb-text">{isEq?'Equation':isLine?'Label':isShape?(TEXT_HINT[s.k]||'Text'):'Text'}
        <textarea ref={taRef} rows={isShape&&(s.k==='entity'||s.k==='uclass'||s.k==='quad')?5:2} value={s.text||''} onChange={e=>patch({text:e.target.value},true)} spellCheck={false} aria-label="Item text"/></label>}
      {isEq&&<div className="wb-eqbar" aria-label="Equation symbols">{EQ_BUTTONS.map(([l,snip])=><button key={snip} type="button" className="eqbtn" title={snip.trim()} onClick={()=>insertEq(snip)}>{l}</button>)}<small className="muted">Type like LaTeX: \frac{'{a}{b}'}, \sqrt{'{x}'}, x^{'{2}'}, x_{'{n}'}</small></div>}
      {isShape&&<label>Fill<select value={s.f||''} onChange={e=>patch({f:e.target.value})}>{FILLS.map(f=><option key={f.v} value={f.v}>{f.label}</option>)}</select></label>}
      {(isShape||isLine)&&<label className="check"><input type="checkbox" checked={!!s.dash} onChange={e=>patch({dash:e.target.checked})}/> Dashed</label>}
      {isLine&&<><label>Style<select value={s.k||'straight'} onChange={e=>patch({k:e.target.value})}><option value="straight">Straight</option><option value="elbow">Elbow</option></select></label>
        <label>Start<select value={s.ma||'none'} onChange={e=>patch({ma:e.target.value})}>{MARKERS.map(m=><option key={m.v} value={m.v}>{m.label}</option>)}</select></label>
        <label>End<select value={s.mb||'none'} onChange={e=>patch({mb:e.target.value})}>{MARKERS.map(m=><option key={m.v} value={m.v}>{m.label}</option>)}</select></label></>}
      {(isShape||isText||isEq||isLine)&&<label>Size<select value={s.size||(isEq?28:isText?20:isLine?14:16)} onChange={e=>patch({size:Number(e.target.value)})}>{[12,14,16,18,20,24,28,32,40].map(n=><option key={n} value={n}>{n}</option>)}</select></label>}
      <button type="button" className="iconbtn" title="Duplicate (Ctrl+D)" aria-label="Duplicate" onClick={dup}><Copy size={16}/></button>
      <button type="button" className="iconbtn" title="Bring to front" aria-label="Bring to front" onClick={toFront}><ArrowUpToLine size={16}/></button>
      <button type="button" className="textbtn" onClick={toBack}>Send to back</button>
      <button type="button" className="iconbtn" title="Delete (Delete key)" aria-label="Delete item" onClick={remove}><Trash2 size={16}/></button></div>}
    <small className="muted wb-help">Pencil for free hand, mixed freely with shapes, text and equations. Pick a shape from the library, then click or drag on the board; double-click anything to edit its text. Drag a connector’s end onto a shape to attach it. Zoom with the buttons or Ctrl and the mouse wheel; move around with the Hand tool, the space bar or the middle mouse button. Moving a container or pool moves what is inside it.</small>
  </div>;
}
function LinePreview({p}:{p:{k:string;ma:string;mb:string;dash?:boolean}}){
  const r=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{const c=r.current;if(!c)return;const g=c.getContext('2d')!;g.clearRect(0,0,c.width,c.height);g.strokeStyle=g.fillStyle='#172033';g.lineWidth=1.6;g.setLineDash(p.dash?[4,3]:[]);g.beginPath();g.moveTo(8,20);g.lineTo(48,20);g.stroke();drawMarker(g,p.mb,[48,20],[8,20]);drawMarker(g,p.ma,[8,20],[48,20])},[]);
  return <canvas ref={r} width={56} height={40} aria-hidden="true"/>;
}
