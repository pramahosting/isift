/* Shape library for the whiteboard: flowchart, ER, UML, BPMN 2.0, containers and callouts, quadrant chart, cloud service tiles (AWS, Azure,
   Google Cloud) and agentic-AI building blocks, plus connector presets and ready-made workflow templates. The cloud tiles are generic glyphs in each
   provider's colour with the service name; they are not the providers' official logos. */

export type LibItem={id:string;cat:string;label:string;k:string;w:number;h:number;text:string;[x:string]:any};
export const CATS:{id:string;label:string}[]=[
 {id:'basic',label:'Basic'},{id:'er',label:'ER'},{id:'uml',label:'UML'},{id:'bpmn',label:'BPMN 2.0'},{id:'frames',label:'Containers & callouts'},{id:'conn',label:'Connectors'},
 {id:'aws',label:'AWS'},{id:'azure',label:'Azure'},{id:'gcp',label:'Google Cloud'},{id:'ai',label:'Agentic AI'}];

const L=(id:string,cat:string,label:string,k:string,w:number,h:number,text:string,extra:any={}):LibItem=>({id,cat,label,k,w,h,text,...extra});
const svc=(prov:string,cat:string,items:[string,string,string][]):LibItem[]=>items.map(([id,name,gl])=>L(`${prov}-${id}`,cat,name,'svc',96,86,name,{prov,gl}));

export const LIB:LibItem[]=[
 L('rect','basic','Process','rect',130,70,'Process'),L('round','basic','Start / End','round',130,54,'Start'),L('diamond','basic','Decision','diamond',150,96,'Decision?'),
 L('ellipse','basic','Ellipse','ellipse',130,76,''),L('para','basic','Input / Output','para',150,64,'Input / Output'),L('cyl','basic','Database','cyl',100,90,'Database'),
 L('entity','er','Entity (table)','entity',170,120,'Entity\n*id\nname\nemail'),L('rel','er','Relationship','rel',150,90,'relates'),
 L('uclass','uml','Class','uclass',180,130,'ClassName\n---\n- attribute: Type\n---\n+ method(): void'),L('uiface','uml','Interface','uclass',180,100,'«interface»\nName\n---\n+ method(): void'),
 L('uactor','uml','Actor','uactor',60,100,'Actor'),L('usecase','uml','Use case','usecase',150,76,'Use case'),L('ustart','uml','Initial state','ustart',30,30,''),L('uend','uml','Final state','uend',34,34,''),
 L('ustate','uml','State','round',130,60,'State'),L('upackage','uml','Package','upackage',180,120,'Package'),L('ucomp','uml','Component','ucomp',150,76,'Component'),L('usys','uml','System boundary','container',260,200,'System'),
 L('bstart','bpmn','Start event','bstart',44,44,'Start'),L('bint','bpmn','Intermediate event','bint',44,44,'Wait'),L('bend','bpmn','End event','bend',44,44,'End'),
 L('btask','bpmn','Task','btask',130,70,'Task'),L('bsub','bpmn','Sub-process','bsub',150,80,'Sub-process'),
 L('bgx','bpmn','Exclusive gateway (X)','bgx',56,56,'Condition?'),L('bgp','bpmn','Parallel gateway (+)','bgp',56,56,''),L('bgo','bpmn','Inclusive gateway (O)','bgo',56,56,''),
 L('bdata','bpmn','Data object','bdata',48,64,'Data'),L('bpool','bpmn','Pool / lane','bpool',560,170,'Pool'),L('bann','bpmn','Text annotation','bann',140,56,'Note'),
 L('container','frames','Container / group','container',280,200,'Group'),L('callout','frames','Callout','callout',160,84,'Callout'),L('note','frames','Sticky note','note',130,100,'Note',{f:'#fff3c4'}),
 L('quad','frames','Quadrant chart','quad',380,320,'Priority matrix\nLow effort|High effort\nLow impact|High impact\nQuick wins\nBig bets\nFill-ins\nMoney pits'),
 ...svc('aws','aws',[['ec2','EC2','compute'],['lambda','Lambda','fn'],['s3','S3','storage'],['rds','RDS','db'],['dynamo','DynamoDB','db'],['apigw','API Gateway','api'],['sqs','SQS','queue'],['sns','SNS','notify'],
   ['cf','CloudFront','cdn'],['vpc','VPC','net'],['elb','ELB','lb'],['iam','IAM','sec'],['eks','EKS / ECS','container'],['cw','CloudWatch','monitor'],['r53','Route 53','dns'],['sfn','Step Functions','flow'],
   ['kin','Kinesis','stream'],['bedrock','Bedrock','ai'],['sage','SageMaker','brain'],['user','Users','user']]),
 ...svc('azure','azure',[['vm','Virtual Machine','compute'],['fn','Functions','fn'],['blob','Blob Storage','storage'],['sql','SQL Database','db'],['cosmos','Cosmos DB','db'],['apim','API Management','api'],
   ['sb','Service Bus','queue'],['eh','Event Hubs','stream'],['fd','Front Door','cdn'],['vnet','Virtual Network','net'],['lb','Load Balancer','lb'],['entra','Entra ID','sec'],['aks','AKS','container'],
   ['mon','Monitor','monitor'],['logic','Logic Apps','flow'],['app','App Service','compute'],['kv','Key Vault','sec'],['oai','Azure OpenAI','ai'],['ml','Machine Learning','brain'],['user','Users','user']]),
 ...svc('gcp','gcp',[['gce','Compute Engine','compute'],['gcf','Cloud Functions','fn'],['gcs','Cloud Storage','storage'],['sql','Cloud SQL','db'],['bq','BigQuery','db'],['fs','Firestore','db'],
   ['ps','Pub/Sub','queue'],['run','Cloud Run','container'],['gke','GKE','container'],['lb','Load Balancing','lb'],['vpc','VPC','net'],['iam','IAM','sec'],['cdn','Cloud CDN','cdn'],['apigee','Apigee / API Gateway','api'],
   ['df','Dataflow','stream'],['log','Cloud Logging','monitor'],['wf','Workflows','flow'],['vertex','Vertex AI','ai'],['gem','Gemini','brain'],['user','Users','user']]),
 ...svc('ai','ai',[['agent','Agent','brain'],['llm','LLM','ai'],['tool','Tool','gear'],['mem','Memory','memory'],['plan','Planner','flow'],['orch','Orchestrator','net'],['rag','Retriever (RAG)','search'],
   ['kb','Knowledge base','db'],['prompt','Prompt','doc'],['guard','Guardrail','sec'],['human','Human in the loop','user'],['mcp','MCP server','plug'],['eval','Evaluator','check'],['trig','Trigger / event','bolt'],
   ['api','External API','api'],['out','Output','doc']]),
];
export const libOf=(id:string)=>LIB.find(l=>l.id===id);

export type LinePreset={id:string;label:string;k:string;ma:string;mb:string;dash?:boolean};
export const LINE_PRESETS:LinePreset[]=[
 {id:'seq',label:'Sequence flow',k:'straight',ma:'none',mb:'arrow'},{id:'msg',label:'Message flow (BPMN)',k:'straight',ma:'dot',mb:'open',dash:true},{id:'assoc',label:'Association (dotted)',k:'straight',ma:'none',mb:'none',dash:true},
 {id:'inherit',label:'Inheritance (UML)',k:'elbow',ma:'none',mb:'tri'},{id:'compose',label:'Composition (UML)',k:'straight',ma:'fdia',mb:'none'},{id:'aggr',label:'Aggregation (UML)',k:'straight',ma:'hdia',mb:'none'},
 {id:'depend',label:'Dependency (UML)',k:'straight',ma:'none',mb:'open',dash:true},{id:'onemany',label:'One to many (ER)',k:'straight',ma:'one',mb:'many'},{id:'manymany',label:'Many to many (ER)',k:'straight',ma:'many',mb:'many'}];

/* ---- shape kinds ---- */
export const ELLIPSEISH=['ellipse','usecase','bstart','bint','bend','ustart','uend','bgo'];
export const DIAMONDISH=['diamond','rel','bgx','bgp'];
export const FRAME_KINDS=['container','bpool'];
export const LABEL_BELOW=['bstart','bint','bend','uactor','ustart','uend','bdata','svc'];
export const PROV:Record<string,{c:string;name:string}>={aws:{c:'#ec7211',name:'AWS'},azure:{c:'#0078d4',name:'Azure'},gcp:{c:'#4285f4',name:'Google Cloud'},ai:{c:'#7c3aed',name:'AI'}};

export const TEXT_HINT:Record<string,string>={entity:'Entity (first line = name, then attributes, * marks the key)',uclass:'Class (first line = name; a line of --- starts the next section)',quad:'Quadrant chart (title; x axis low|high; y axis low|high; then four quadrant names: top-left, top-right, bottom-left, bottom-right)',
 container:'Title',bpool:'Pool name',svc:'Service name'};

function rr(g:CanvasRenderingContext2D,x:number,y:number,w:number,h:number,r:number){r=Math.max(0,Math.min(r,w/2,h/2));g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);g.arcTo(x+w,y+h,x,y+h,r);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath()}
const FONT='Inter, system-ui, sans-serif';

/** Small white pictures inside the cloud / AI tiles. */
export function glyph(g:CanvasRenderingContext2D,kind:string,cx:number,cy:number,r:number){
  g.save();g.strokeStyle='#fff';g.fillStyle='#fff';g.lineWidth=Math.max(1.6,r/9);g.lineCap='round';g.lineJoin='round';g.setLineDash([]);g.textAlign='center';g.textBaseline='middle';
  const t=(s:string,sz:number)=>{g.font=`700 ${sz}px ${FONT}`;g.fillText(s,cx,cy+sz*0.04)};
  const line=(a:number,b:number,c:number,d:number)=>{g.beginPath();g.moveTo(cx+a*r,cy+b*r);g.lineTo(cx+c*r,cy+d*r);g.stroke()};
  const circ=(x:number,y:number,rad:number,fill=false)=>{g.beginPath();g.arc(cx+x*r,cy+y*r,rad*r,0,Math.PI*2);fill?g.fill():g.stroke()};
  const cylinder=(w:number,top:number,bot:number)=>{g.beginPath();g.ellipse(cx,cy+top*r,w*r,.22*r,0,0,Math.PI*2);g.stroke();g.beginPath();g.moveTo(cx-w*r,cy+top*r);g.lineTo(cx-w*r,cy+bot*r);g.ellipse(cx,cy+bot*r,w*r,.22*r,0,Math.PI,0,true);g.lineTo(cx+w*r,cy+top*r);g.stroke();g.beginPath();g.ellipse(cx,cy+(top+bot)/2*r,w*r,.2*r,0,0,Math.PI,false);g.stroke()};
  switch(kind){
   case 'compute':g.strokeRect(cx-.5*r,cy-.5*r,r,r);g.fillRect(cx-.22*r,cy-.22*r,.44*r,.44*r);for(const s of [-.28,.28]){line(s,-.5,s,-.78);line(s,.5,s,.78);line(-.5,s,-.78,s);line(.5,s,.78,s)}break;
   case 'fn':t('λ',r*1.7);break;
   case 'storage':g.beginPath();g.moveTo(cx-.7*r,cy-.4*r);g.lineTo(cx-.5*r,cy+.7*r);g.lineTo(cx+.5*r,cy+.7*r);g.lineTo(cx+.7*r,cy-.4*r);g.stroke();g.beginPath();g.ellipse(cx,cy-.4*r,.7*r,.24*r,0,0,Math.PI*2);g.stroke();break;
   case 'db':cylinder(.6,-.5,.5);break;
   case 'api':t('{ }',r*1.25);break;
   case 'queue':for(const x of [-.75,-.1,.55])g.strokeRect(cx+x*r-.05*r,cy-.28*r,.42*r,.56*r);line(-.9,.75,.9,.75);line(.6,.6,.9,.75);line(.6,.9,.9,.75);break;
   case 'notify':g.beginPath();g.moveTo(cx-.6*r,cy+.35*r);g.quadraticCurveTo(cx-.6*r,cy-.7*r,cx,cy-.7*r);g.quadraticCurveTo(cx+.6*r,cy-.7*r,cx+.6*r,cy+.35*r);g.closePath();g.stroke();line(-.8,.38,.8,.38);circ(0,.7,.14,true);break;
   case 'cdn':circ(0,0,.8);g.beginPath();g.ellipse(cx,cy,.36*r,.8*r,0,0,Math.PI*2);g.stroke();line(-.8,0,.8,0);line(-.65,-.4,.65,-.4);line(-.65,.4,.65,.4);break;
   case 'net':circ(0,-.62,.2,true);circ(-.62,.5,.2,true);circ(.62,.5,.2,true);line(0,-.62,-.62,.5);line(0,-.62,.62,.5);line(-.62,.5,.62,.5);break;
   case 'lb':circ(-.7,0,.17,true);for(const y of [-.6,0,.6]){circ(.7,y,.17,true);line(-.7,0,.7,y)}break;
   case 'sec':g.beginPath();g.moveTo(cx,cy-.85*r);g.lineTo(cx+.7*r,cy-.55*r);g.lineTo(cx+.7*r,cy+.1*r);g.quadraticCurveTo(cx+.6*r,cy+.6*r,cx,cy+.9*r);g.quadraticCurveTo(cx-.6*r,cy+.6*r,cx-.7*r,cy+.1*r);g.lineTo(cx-.7*r,cy-.55*r);g.closePath();g.stroke();line(-.3,.05,-.05,.3);line(-.05,.3,.35,-.2);break;
   case 'ai':{const star=(x:number,y:number,s:number)=>{g.beginPath();g.moveTo(cx+x*r,cy+(y-s)*r);g.quadraticCurveTo(cx+x*r,cy+y*r,cx+(x+s)*r,cy+y*r);g.quadraticCurveTo(cx+x*r,cy+y*r,cx+x*r,cy+(y+s)*r);g.quadraticCurveTo(cx+x*r,cy+y*r,cx+(x-s)*r,cy+y*r);g.quadraticCurveTo(cx+x*r,cy+y*r,cx+x*r,cy+(y-s)*r);g.fill()};star(-.12,.1,.7);star(.55,-.5,.3);star(.5,.55,.22);break}
   case 'container':g.beginPath();g.moveTo(cx,cy-.8*r);g.lineTo(cx+.75*r,cy-.4*r);g.lineTo(cx+.75*r,cy+.4*r);g.lineTo(cx,cy+.8*r);g.lineTo(cx-.75*r,cy+.4*r);g.lineTo(cx-.75*r,cy-.4*r);g.closePath();g.stroke();line(0,0,0,.8);line(0,0,.75,-.4);line(0,0,-.75,-.4);break;
   case 'monitor':g.strokeRect(cx-.8*r,cy-.6*r,1.6*r,1.2*r);g.beginPath();g.moveTo(cx-.6*r,cy+.3*r);g.lineTo(cx-.2*r,cy-.05*r);g.lineTo(cx+.1*r,cy+.15*r);g.lineTo(cx+.55*r,cy-.35*r);g.stroke();break;
   case 'dns':t('@',r*1.6);break;
   case 'flow':for(const [x,y] of [[-.5,-.6],[.3,0],[-.5,.6]])g.strokeRect(cx+x*r-.2*r,cy+y*r-.17*r,.6*r,.34*r);line(-.2,-.43,.4,-.17);line(.3,.17,-.2,.43);break;
   case 'stream':for(const y of [-.35,.35]){g.beginPath();for(let i=-8;i<=8;i++){const x=i/8*.85;const yy=y+Math.sin(i/8*Math.PI*2)*.2;i===-8?g.moveTo(cx+x*r,cy+yy*r):g.lineTo(cx+x*r,cy+yy*r)}g.stroke()}break;
   case 'user':circ(0,-.4,.3);g.beginPath();g.arc(cx,cy+.85*r,.7*r,Math.PI*1.12,Math.PI*1.88);g.stroke();break;
   case 'brain':circ(0,0,.85);for(const [x,y] of [[-.4,-.35],[.4,-.35],[0,.1],[-.35,.5],[.35,.5]])circ(x,y,.1,true);line(-.4,-.35,0,.1);line(.4,-.35,0,.1);line(0,.1,-.35,.5);line(0,.1,.35,.5);break;
   case 'gear':circ(0,0,.36);circ(0,0,.62);for(let i=0;i<8;i++){const a=i*Math.PI/4;g.beginPath();g.moveTo(cx+Math.cos(a)*.62*r,cy+Math.sin(a)*.62*r);g.lineTo(cx+Math.cos(a)*.85*r,cy+Math.sin(a)*.85*r);g.stroke()}break;
   case 'doc':g.beginPath();g.moveTo(cx-.55*r,cy-.8*r);g.lineTo(cx+.2*r,cy-.8*r);g.lineTo(cx+.55*r,cy-.45*r);g.lineTo(cx+.55*r,cy+.8*r);g.lineTo(cx-.55*r,cy+.8*r);g.closePath();g.stroke();line(-.3,-.1,.3,-.1);line(-.3,.2,.3,.2);line(-.3,.5,.1,.5);break;
   case 'search':circ(-.15,-.15,.5);line(.2,.2,.75,.75);break;
   case 'check':circ(0,0,.8);line(-.38,.02,-.1,.3);line(-.1,.3,.42,-.28);break;
   case 'bolt':g.beginPath();g.moveTo(cx+.2*r,cy-.9*r);g.lineTo(cx-.5*r,cy+.1*r);g.lineTo(cx-.02*r,cy+.1*r);g.lineTo(cx-.2*r,cy+.9*r);g.lineTo(cx+.5*r,cy-.1*r);g.lineTo(cx+.02*r,cy-.1*r);g.closePath();g.fill();break;
   case 'plug':g.strokeRect(cx-.45*r,cy-.1*r,.9*r,.7*r);line(-.2,-.1,-.2,-.6);line(.2,-.1,.2,-.6);line(0,.6,0,.9);break;
   case 'memory':for(const y of [-.55,0,.55]){g.beginPath();rr(g,cx-.7*r,cy+y*r-.17*r,1.4*r,.34*r,.1*r);g.stroke()}break;
   default:circ(0,0,.6)}
  g.restore();
}

/** Draws the kinds that are not in Whiteboard.tsx's own switch. Returns true when it handled the shape. */
export function drawLibShape(g:CanvasRenderingContext2D,s:any,wrapFn:(g:CanvasRenderingContext2D,t:string,w:number)=>string[],ink:string):boolean{
  const {x,y,w,h}=s,k=s.k,size=s.size||16,lh=size*1.25,cx=x+w/2,cy=y+h/2;
  const stroke=()=>{if(s.f)g.fill();g.stroke()};
  const below=(text:string,top:number)=>{if(!text)return;g.save();g.setLineDash([]);g.fillStyle=ink;g.font=`${size}px ${FONT}`;g.textAlign='center';g.textBaseline='top';wrapFn(g,text,Math.max(w+40,110)).forEach((l,i)=>g.fillText(l,cx,top+i*lh));g.restore()};
  const inner=(text:string,ox=0,oy=0,maxW=w-16)=>{if(!text)return;g.save();g.setLineDash([]);g.fillStyle=ink;g.font=`${size}px ${FONT}`;g.textAlign='center';g.textBaseline='middle';const ls=wrapFn(g,text,maxW);ls.forEach((l,i)=>g.fillText(l,cx+ox,cy+oy-(ls.length-1)*lh/2+i*lh,maxW));g.restore()};
  if(k==='svc'){
    const P=PROV[s.prov]||PROV.ai,tile=Math.max(8,Math.min(w,h-26)),tx=x+(w-tile)/2;
    g.save();g.setLineDash([]);g.fillStyle=P.c;g.beginPath();rr(g,tx,y,tile,tile,tile*.18);g.fill();glyph(g,s.gl,tx+tile/2,y+tile/2,tile*.3);
    g.fillStyle=P.c;g.globalAlpha=.9;g.font=`700 ${Math.max(9,tile*.12)}px ${FONT}`;g.textAlign='left';g.textBaseline='top';g.fillStyle='#fff';g.fillText(P.name,tx+5,y+4);g.restore();
    below(s.text,y+tile+4);return true}
  if(k==='container'){
    g.beginPath();rr(g,x,y,w,h,14);stroke();g.save();g.setLineDash([]);g.fillStyle=ink;g.font=`600 ${size}px ${FONT}`;g.textAlign='left';g.textBaseline='middle';g.fillText(s.text||'',x+14,y+16,w-28);g.restore();return true}
  if(k==='bpool'){
    g.beginPath();g.rect(x,y,w,h);stroke();const bw=Math.min(34,w/4);g.beginPath();g.moveTo(x+bw,y);g.lineTo(x+bw,y+h);g.stroke();
    g.save();g.setLineDash([]);g.fillStyle=ink;g.translate(x+bw/2,cy);g.rotate(-Math.PI/2);g.font=`600 ${size}px ${FONT}`;g.textAlign='center';g.textBaseline='middle';g.fillText(s.text||'',0,0,h-12);g.restore();return true}
  if(k==='callout'){const r=12,tx=x+w*.2;g.beginPath();g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);g.arcTo(x+w,y+h,x,y+h,r);g.lineTo(tx+34,y+h);g.lineTo(tx-4,y+h+26);g.lineTo(tx+8,y+h);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath();stroke();inner(s.text);return true}
  if(k==='note'||k==='unote'){const c=Math.min(18,w/4);g.beginPath();g.moveTo(x,y);g.lineTo(x+w-c,y);g.lineTo(x+w,y+c);g.lineTo(x+w,y+h);g.lineTo(x,y+h);g.closePath();if(!s.f){g.save();g.fillStyle='#fff3c4';g.fill();g.restore()}stroke();g.beginPath();g.moveTo(x+w-c,y);g.lineTo(x+w-c,y+c);g.lineTo(x+w,y+c);g.stroke();inner(s.text);return true}
  if(k==='quad'){
    const ls=String(s.text||'').split('\n'),title=ls[0]||'',xa=(ls[1]||'').split('|'),ya=(ls[2]||'').split('|'),q=[ls[3]||'',ls[4]||'',ls[5]||'',ls[6]||''];
    const top=y+34,pw=w-40,ph=h-34-26,px=x+34,mx=px+pw/2,my=top+ph/2;
    g.save();g.setLineDash([]);const tints=['#d9f3e4','#dbe7ff','#f4f6fa','#ffe6d6'];
    [[px,top],[mx,top],[px,my],[mx,my]].forEach(([qx,qy],i)=>{g.fillStyle=tints[i];g.fillRect(qx,qy,pw/2,ph/2)});
    g.strokeStyle=s.c||ink;g.lineWidth=s.lw||2;g.strokeRect(px,top,pw,ph);g.beginPath();g.moveTo(mx,top);g.lineTo(mx,top+ph);g.moveTo(px,my);g.lineTo(px+pw,my);g.stroke();
    g.fillStyle=ink;g.textBaseline='middle';g.textAlign='center';g.font=`700 ${size+2}px ${FONT}`;g.fillText(title,x+w/2,y+16,w-16);
    g.font=`600 ${size-2}px ${FONT}`;[[px+pw/4,top+16],[mx+pw/4,top+16],[px+pw/4,my+16],[mx+pw/4,my+16]].forEach(([qx,qy],i)=>g.fillText(q[i],qx,qy,pw/2-10));
    g.font=`${size-3}px ${FONT}`;g.fillStyle='#5b6577';g.textAlign='left';g.fillText(xa[0]||'',px,top+ph+14,pw/2);g.textAlign='right';g.fillText(xa[1]||'',px+pw,top+ph+14,pw/2);
    g.save();g.translate(x+12,top+ph/2);g.rotate(-Math.PI/2);g.textAlign='left';g.fillText(ya[0]||'',-ph/2,0,ph/2);g.textAlign='right';g.fillText(ya[1]||'',ph/2,0,ph/2);g.restore();g.restore();return true}
  if(k==='uclass'){
    const secs:string[][]=[[]];for(const l of String(s.text||'').split('\n')){if(l.trim()==='---')secs.push([]);else secs[secs.length-1].push(l)}
    g.beginPath();g.rect(x,y,w,h);stroke();const rows=secs.map(sc=>Math.max(1,sc.length)),total=rows.reduce((a,b)=>a+b,0);let yy=y;
    g.save();g.setLineDash([]);g.fillStyle=ink;g.textBaseline='middle';
    secs.forEach((sc,i)=>{const hh=h*rows[i]/total;if(i>0){g.beginPath();g.moveTo(x,yy);g.lineTo(x+w,yy);g.stroke()}
      sc.forEach((l,j)=>{const ty=yy+(hh/Math.max(1,sc.length))*(j+.5);if(i===0){g.font=`${/^«/.test(l)?'italic ':'600 '}${size}px ${FONT}`;g.textAlign='center';g.fillText(l,x+w/2,ty,w-10)}else{g.font=`${size-1}px ${FONT}`;g.textAlign='left';g.fillText(l,x+8,ty,w-14)}});yy+=hh});g.restore();return true}
  if(k==='uactor'){const hx=cx,hr=Math.min(w,h)*.16,top=y+2;g.beginPath();g.arc(hx,top+hr,hr,0,Math.PI*2);g.moveTo(hx,top+hr*2);g.lineTo(hx,top+h*.55);g.moveTo(x+4,top+h*.32);g.lineTo(x+w-4,top+h*.32);g.moveTo(hx,top+h*.55);g.lineTo(x+6,top+h*.78);g.moveTo(hx,top+h*.55);g.lineTo(x+w-6,top+h*.78);g.stroke();below(s.text,y+h*.8+4);return true}
  if(k==='usecase'){g.beginPath();g.ellipse(cx,cy,w/2,h/2,0,0,Math.PI*2);stroke();inner(s.text,0,0,w*.7);return true}
  if(k==='ustart'){g.beginPath();g.arc(cx,cy,Math.min(w,h)/2,0,Math.PI*2);g.save();g.fillStyle=s.c||ink;g.fill();g.restore();g.stroke();return true}
  if(k==='uend'){const r=Math.min(w,h)/2;g.beginPath();g.arc(cx,cy,r,0,Math.PI*2);g.stroke();g.beginPath();g.arc(cx,cy,r*.6,0,Math.PI*2);g.save();g.fillStyle=s.c||ink;g.fill();g.restore();return true}
  if(k==='upackage'){const tw=Math.min(70,w*.4),th=Math.min(22,h*.2);g.beginPath();g.moveTo(x,y+th);g.lineTo(x,y+h);g.lineTo(x+w,y+h);g.lineTo(x+w,y+th);g.lineTo(x+tw,y+th);g.lineTo(x+tw,y);g.lineTo(x,y);g.closePath();stroke();g.beginPath();g.moveTo(x,y+th);g.lineTo(x+tw,y+th);g.stroke();g.save();g.setLineDash([]);g.fillStyle=ink;g.font=`600 ${size}px ${FONT}`;g.textAlign='center';g.textBaseline='middle';g.fillText(s.text||'',x+w/2,y+th+(h-th)/2,w-12);g.restore();return true}
  if(k==='ucomp'){g.beginPath();g.rect(x,y,w,h);stroke();for(const yy of [y+h*.25,y+h*.55]){g.beginPath();g.rect(x-9,yy,18,10);g.save();g.fillStyle='#fff';g.fill();g.restore();g.stroke()}inner(s.text,6);return true}
  if(k==='bstart'||k==='bint'||k==='bend'){const r=Math.min(w,h)/2;g.beginPath();g.arc(cx,cy,r,0,Math.PI*2);if(s.f)g.fill();g.save();if(k==='bend')g.lineWidth=(s.lw||2)*2.6;g.stroke();g.restore();
    if(k==='bint'){g.beginPath();g.arc(cx,cy,r-5,0,Math.PI*2);g.stroke()}below(s.text,y+h+4);return true}
  if(k==='btask'||k==='bsub'){g.beginPath();rr(g,x,y,w,h,12);stroke();inner(s.text);if(k==='bsub'){g.save();g.setLineDash([]);g.strokeRect(cx-8,y+h-19,16,14);g.beginPath();g.moveTo(cx-4,y+h-12);g.lineTo(cx+4,y+h-12);g.moveTo(cx,y+h-16);g.lineTo(cx,y+h-8);g.stroke();g.restore()}return true}
  if(k==='bgx'||k==='bgp'||k==='bgo'){const r=Math.min(w,h)/2;
    if(k==='bgo'){g.beginPath();g.arc(cx,cy,r,0,Math.PI*2);stroke()}else{g.beginPath();g.moveTo(cx,y);g.lineTo(x+w,cy);g.lineTo(cx,y+h);g.lineTo(x,cy);g.closePath();stroke()}
    g.save();g.setLineDash([]);g.lineWidth=(s.lw||2)*1.6;const a=r*.38;g.beginPath();
    if(k==='bgx'){g.moveTo(cx-a,cy-a);g.lineTo(cx+a,cy+a);g.moveTo(cx+a,cy-a);g.lineTo(cx-a,cy+a)}
    else if(k==='bgp'){g.moveTo(cx-a,cy);g.lineTo(cx+a,cy);g.moveTo(cx,cy-a);g.lineTo(cx,cy+a)}
    else g.arc(cx,cy,a*1.1,0,Math.PI*2);g.stroke();g.restore();below(s.text,y+h+4);return true}
  if(k==='bdata'){const c=Math.min(14,w/3);g.beginPath();g.moveTo(x,y);g.lineTo(x+w-c,y);g.lineTo(x+w,y+c);g.lineTo(x+w,y+h);g.lineTo(x,y+h);g.closePath();stroke();g.beginPath();g.moveTo(x+w-c,y);g.lineTo(x+w-c,y+c);g.lineTo(x+w,y+c);g.stroke();below(s.text,y+h+4);return true}
  if(k==='bann'){g.beginPath();g.moveTo(x+14,y);g.lineTo(x,y);g.lineTo(x,y+h);g.lineTo(x+14,y+h);g.stroke();inner(s.text,8,0,w-30);return true}
  return false;
}

/** Extra connector ends (UML and BPMN); returns true when handled. */
export function drawLibMarker(g:CanvasRenderingContext2D,kind:string,p:[number,number],from:[number,number]):boolean{
  let dx=p[0]-from[0],dy=p[1]-from[1];const L=Math.hypot(dx,dy)||1;dx/=L;dy/=L;const nx=-dy,ny=dx;const at=(d:number,s=0):[number,number]=>[p[0]-dx*d+nx*s,p[1]-dy*d+ny*s];
  g.save();g.setLineDash([]);
  const poly=(pts:[number,number][],fill:string)=>{g.beginPath();pts.forEach((q,i)=>i?g.lineTo(q[0],q[1]):g.moveTo(q[0],q[1]));g.closePath();g.fillStyle=fill;g.fill();g.stroke()};
  let ok=true;
  if(kind==='tri')poly([p,at(16,8),at(16,-8)],'#fff');
  else if(kind==='hdia')poly([p,at(9,6),at(18,0),at(9,-6)],'#fff');
  else if(kind==='fdia')poly([p,at(9,6),at(18,0),at(9,-6)],g.strokeStyle as string);
  else if(kind==='open'){g.beginPath();const a=at(13,7),b=at(13,-7);g.moveTo(a[0],a[1]);g.lineTo(p[0],p[1]);g.lineTo(b[0],b[1]);g.stroke()}
  else if(kind==='dot'){const c=at(5);g.beginPath();g.arc(c[0],c[1],5,0,Math.PI*2);g.fillStyle='#fff';g.fill();g.stroke()}
  else ok=false;
  g.restore();return ok;
}

/* ---- ready-made workflows (added to the board at the centre of the view; everything stays editable) ---- */
type TNode=[string,string,number,number,string?];type TEdge=[string,string,string?,string?];
export const TEMPLATES:{id:string;label:string;nodes:TNode[];edges:TEdge[]}[]=[
 {id:'ai-react',label:'Agentic AI: reason and act loop',nodes:[['u','ai-human',0,80,'User'],['a','ai-agent',200,80,'Agent'],['l','ai-llm',400,0,'LLM'],['t','ai-tool',400,160,'Tool'],['m','ai-mem',200,240,'Memory']],
  edges:[['u','a','task'],['a','l','reason'],['l','t','tool call'],['t','m','result'],['m','a','context'],['a','u','answer']]},
 {id:'ai-rag',label:'Agentic AI: retrieval (RAG) pipeline',nodes:[['u','ai-human',0,60,'User'],['p','ai-prompt',170,60,'Prompt'],['r','ai-rag',340,60,'Retriever'],['k','ai-kb',340,200,'Knowledge base'],['l','ai-llm',510,60,'LLM'],['g','ai-guard',680,60,'Guardrail'],['o','ai-out',850,60,'Answer']],
  edges:[['u','p','question'],['p','r','query'],['r','k','search'],['k','r','passages'],['r','l','context'],['l','g','draft'],['g','o','approved']]},
 {id:'ai-multi',label:'Agentic AI: multi-agent team',nodes:[['h','ai-human',0,110,'Human review'],['o','ai-orch',210,110,'Orchestrator'],['r','ai-agent',430,0,'Research agent'],['c','ai-agent',430,110,'Coding agent'],['v','ai-eval',430,220,'Evaluator'],['t','ai-tool',650,0,'Web search'],['x','ai-mcp',650,110,'MCP server']],
  edges:[['h','o','goal'],['o','r','assign'],['o','c','assign'],['o','v','check'],['r','t'],['c','x'],['v','o','score']]},
 {id:'aws',label:'AWS: serverless web app',nodes:[['u','aws-user',0,60,'Users'],['c','aws-cf',160,60,'CloudFront'],['a','aws-apigw',320,60,'API Gateway'],['l','aws-lambda',480,60,'Lambda'],['d','aws-dynamo',640,0,'DynamoDB'],['s','aws-s3',640,130,'S3']],
  edges:[['u','c'],['c','a'],['a','l'],['l','d'],['l','s']]},
 {id:'azure',label:'Azure: event-driven processing',nodes:[['u','azure-user',0,0,'Devices'],['e','azure-eh',160,0,'Event Hubs'],['f','azure-fn',320,0,'Functions'],['c','azure-cosmos',480,0,'Cosmos DB'],['q','azure-sb',320,130,'Service Bus'],['m','azure-mon',480,130,'Monitor']],
  edges:[['u','e'],['e','f'],['f','c'],['f','q'],['q','m']]},
 {id:'gcp',label:'Google Cloud: data pipeline',nodes:[['s','gcp-gcs',0,130,'Cloud Storage'],['p','gcp-ps',0,0,'Pub/Sub'],['d','gcp-df',170,60,'Dataflow'],['b','gcp-bq',340,60,'BigQuery'],['v','gcp-vertex',510,60,'Vertex AI']],
  edges:[['s','d'],['p','d'],['d','b'],['b','v']]},
 {id:'bpmn',label:'BPMN: order process',nodes:[['pool','bpool',0,0,'Order fulfilment'],['s','bstart',60,67,'Order placed'],['t1','btask',150,50,'Check stock'],['g','bgx',320,60,'In stock?'],['t2','btask',430,10,'Ship order'],['t3','btask',430,100,'Notify customer'],['e','bend',600,67,'Done']],
  edges:[['s','t1'],['t1','g'],['g','t2','yes'],['g','t3','no'],['t2','e'],['t3','e']]},
 {id:'uml',label:'UML: class diagram',nodes:[['a','uclass',100,0,'Animal\n---\n- name: String\n---\n+ speak(): void'],['d','uclass',0,190,'Dog\n---\n- breed: String\n---\n+ speak(): void'],['c','uclass',230,190,'Cat\n---\n- indoor: Boolean\n---\n+ speak(): void']],
  edges:[['d','a','','inherit'],['c','a','','inherit']]},
 {id:'er',label:'ER: customers, orders, products',nodes:[['c','entity',0,40,'Customer\n*id\nname\nemail'],['o','entity',260,40,'Order\n*id\ncustomer_id\ndate'],['p','entity',520,40,'Product\n*id\nname\nprice']],
  edges:[['c','o','places','onemany'],['o','p','contains','manymany']]},
];
