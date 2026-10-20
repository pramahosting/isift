// A small spreadsheet engine for SpreadTable: cell names (A1), ranges (A1:B3), + - * / ^ & comparisons, and common functions.
export type Cells=Record<string,string>;
export const colName=(i:number)=>{let s='';i++;while(i>0){const m=(i-1)%26;s=String.fromCharCode(65+m)+s;i=Math.floor((i-1)/26)}return s};
export const colIndex=(s:string)=>{let n=0;for(const ch of s)n=n*26+ch.charCodeAt(0)-64;return n-1};
type Val=number|string|boolean|null;
class Err{constructor(public code:string){}}
const FN:Record<string,(a:any[])=>Val>={
  SUM:a=>nums(a).reduce((x,y)=>x+y,0),AVERAGE:a=>{const n=nums(a);if(!n.length)throw new Err('#DIV/0!');return n.reduce((x,y)=>x+y,0)/n.length},
  MIN:a=>{const n=nums(a);return n.length?Math.min(...n):0},MAX:a=>{const n=nums(a);return n.length?Math.max(...n):0},COUNT:a=>nums(a).length,COUNTA:a=>flat(a).filter(v=>v!==null&&v!=='').length,
  ABS:a=>Math.abs(num(a[0])),ROUND:a=>{const d=a[1]===undefined?0:num(a[1]);const f=Math.pow(10,d);return Math.round(num(a[0])*f)/f},SQRT:a=>{const v=num(a[0]);if(v<0)throw new Err('#NUM!');return Math.sqrt(v)},
  IF:a=>truthy(a[0])?(a[1]??''):(a[2]??false),AND:a=>flat(a).every(truthy),OR:a=>flat(a).some(truthy),NOT:a=>!truthy(a[0]),
  CONCAT:a=>flat(a).map(v=>v??'').join(''),LEN:a=>String(a[0]??'').length,UPPER:a=>String(a[0]??'').toUpperCase(),LOWER:a=>String(a[0]??'').toLowerCase(),
  POWER:a=>Math.pow(num(a[0]),num(a[1])),MOD:a=>{if(num(a[1])===0)throw new Err('#DIV/0!');return num(a[0])%num(a[1])},PRODUCT:a=>nums(a).reduce((x,y)=>x*y,1),
};
const flat=(a:any[]):Val[]=>a.flatMap(v=>Array.isArray(v)?flat(v):[v]);
const nums=(a:any[])=>flat(a).filter(v=>typeof v==='number'||(typeof v==='string'&&v.trim()!==''&&!isNaN(Number(v)))).map(Number);
const num=(v:any):number=>{if(v===null||v==='')return 0;if(typeof v==='boolean')return v?1:0;const n=Number(v);if(isNaN(n))throw new Err('#VALUE!');return n};
const truthy=(v:any)=>typeof v==='string'?v.length>0:!!v;
export function evaluate(cells:Cells){
  const cache:Record<string,Val>={};const busy=new Set<string>();
  const get=(ref:string):Val=>{
    if(ref in cache)return cache[ref];
    if(busy.has(ref))throw new Err('#CIRC!');
    busy.add(ref);let v:Val;
    try{const raw=cells[ref];v=raw===undefined||raw===''?null:raw[0]==='='?calc(raw.slice(1)):raw!==''&&!isNaN(Number(raw))&&raw.trim()!==''?Number(raw):raw}
    catch(e){v=e instanceof Err?e.code:'#ERROR!'}
    finally{busy.delete(ref)}
    cache[ref]=v;return v};
  const calc=(src:string):Val=>{
    const toks=src.match(/"[^"]*"|[A-Za-z_]+[0-9]*(?::[A-Za-z]+[0-9]+)?|\d+\.?\d*|<=|>=|<>|[-+*\/^&(),=<>%]/g)||[];let i=0;
    const peek=()=>toks[i],next=()=>toks[i++];
    const cmp=():any=>{let l=cat();while(['=','<','>','<=','>=','<>'].includes(peek()||'')){const o=next();const r=cat();const a=l as any,b=r as any;l=o==='='?a==b:o==='<>'?a!=b:o==='<'?a<b:o==='>'?a>b:o==='<='?a<=b:a>=b}return l};
    const cat=():any=>{let l=add();while(peek()==='&'){next();l=String(l??'')+String(add()??'')}return l};
    const add=():any=>{let l=mul();while(peek()==='+'||peek()==='-'){const o=next();const r=mul();l=o==='+'?num(l)+num(r):num(l)-num(r)}return l};
    const mul=():any=>{let l=pow();while(peek()==='*'||peek()==='/'){const o=next();const r=pow();if(o==='/'){if(num(r)===0)throw new Err('#DIV/0!');l=num(l)/num(r)}else l=num(l)*num(r)}return l};
    const pow=():any=>{let l=unary();while(peek()==='^'){next();l=Math.pow(num(l),num(unary()))}return l};
    const unary=():any=>{if(peek()==='-'){next();return -num(unary())}if(peek()==='+'){next();return unary()}return atom()};
    const atom=():any=>{
      const t=next();if(t===undefined)throw new Err('#ERROR!');
      if(t==='('){const v=cmp();if(next()!==')')throw new Err('#ERROR!');return v}
      if(t[0]==='"')return t.slice(1,-1);
      if(/^\d/.test(t)){let v=Number(t);if(peek()==='%'){next();v/=100}return v}
      if(/^[A-Za-z]+[0-9]+:[A-Za-z]+[0-9]+$/.test(t)){const [a,b]=t.toUpperCase().split(':');return range(a,b)}
      if(/^[A-Za-z]+[0-9]+$/.test(t)){const v=get(t.toUpperCase());if(typeof v==='string'&&v.startsWith('#'))throw new Err(v);return v}
      if(peek()==='('){next();const args:any[]=[];if(peek()!==')'){for(;;){args.push(cmp());if(peek()===','){next();continue}break}}if(next()!==')')throw new Err('#ERROR!');const f=FN[t.toUpperCase()];if(!f)throw new Err('#NAME?');return f(args)}
      if(/^(TRUE|FALSE)$/i.test(t))return t.toUpperCase()==='TRUE';
      throw new Err('#NAME?')};
    const out=cmp();if(i<toks.length)throw new Err('#ERROR!');return out};
  const range=(a:string,b:string):Val[]=>{const ma=/^([A-Z]+)(\d+)$/.exec(a)!,mb=/^([A-Z]+)(\d+)$/.exec(b)!;const c1=Math.min(colIndex(ma[1]),colIndex(mb[1])),c2=Math.max(colIndex(ma[1]),colIndex(mb[1]));const r1=Math.min(+ma[2],+mb[2]),r2=Math.max(+ma[2],+mb[2]);
    if((c2-c1+1)*(r2-r1+1)>20000)throw new Err('#REF!');const o:Val[]=[];for(let r=r1;r<=r2;r++)for(let c=c1;c<=c2;c++){const v=get(colName(c)+r);if(typeof v==='string'&&v.startsWith('#'))throw new Err(v);o.push(v)}return o};
  return (ref:string):Val=>get(ref);
}
export const show=(v:Val)=>v===null?'':typeof v==='number'?String(Math.round(v*1e10)/1e10):typeof v==='boolean'?(v?'TRUE':'FALSE'):String(v);
export function toCsv(cells:Cells,rows:number,cols:number){const val=evaluate(cells);const q=(s:string)=>/[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;const o:string[]=[];for(let r=1;r<=rows;r++){const line:string[]=[];for(let c=0;c<cols;c++)line.push(q(show(val(colName(c)+r))));o.push(line.join(','))}return o.join('\n')}
export function fromCsv(text:string):Cells{const cells:Cells={};let r=1,c=0,cur='',q=false;const push=()=>{if(cur!=='')cells[colName(c)+r]=cur;cur='';c++};
  for(let i=0;i<text.length;i++){const ch=text[i];if(q){if(ch==='"'){if(text[i+1]==='"'){cur+='"';i++}else q=false}else cur+=ch}else if(ch==='"')q=true;else if(ch===','||ch==='\t')push();else if(ch==='\n'||ch==='\r'){if(ch==='\r'&&text[i+1]==='\n')i++;push();r++;c=0}else cur+=ch}
  if(cur!==''||c>0)push();return cells}
