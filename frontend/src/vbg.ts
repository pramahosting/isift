// Per-person video background: blur or replace, like Zoom. Runs entirely in the browser
// (MediaPipe selfie segmentation, files served from /mediapipe) and the processed video is
// what everyone else receives.
export type BgMode={kind:'none'}|{kind:'blur',level:number}|{kind:'image',id:string,url:string};
const svg=(body:string)=>'data:image/svg+xml;utf8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" preserveAspectRatio="xMidYMid slice">${body}</svg>`);
export const PRESETS:{id:string,name:string,url:string}[]=[
 {id:'office',name:'Bright office',url:svg('<rect width="1280" height="720" fill="#eef1f4"/><rect y="470" width="1280" height="250" fill="#c9b79c"/><rect x="90" y="90" width="300" height="300" fill="#bfe3f7" stroke="#fff" stroke-width="14"/><path d="M240 90v300M90 240h300" stroke="#fff" stroke-width="8"/><rect x="820" y="140" width="330" height="190" fill="#fff" stroke="#8a6a45" stroke-width="12"/><path d="M830 320l90-110 70 70 60-60 80 100z" fill="#7aa874"/><rect x="900" y="420" width="260" height="60" rx="8" fill="#8a6a45"/><rect x="960" y="360" width="40" height="60" fill="#5a7d5a"/><circle cx="980" cy="345" r="38" fill="#6aa06a"/>')},
 {id:'beach',name:'Beach',url:svg('<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5eb7ee"/><stop offset="1" stop-color="#d7f0fb"/></linearGradient></defs><rect width="1280" height="720" fill="url(#s)"/><rect y="360" width="1280" height="140" fill="#2f95c9"/><rect y="470" width="1280" height="250" fill="#ecd9a8"/><circle cx="1050" cy="150" r="60" fill="#fff6c8"/><path d="M0 480q160-30 320 0t320 0 320 0 320 0v30H0z" fill="#fff" opacity=".7"/>')},
 {id:'mountain',name:'Mountains',url:svg('<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8cc4ef"/><stop offset="1" stop-color="#e6f3fb"/></linearGradient></defs><rect width="1280" height="720" fill="url(#s)"/><path d="M0 520L240 250l160 180 200-300 260 330 160-150 260 280v130H0z" fill="#7f95ab"/><path d="M0 600l300-150 280 130 300-170 400 190v120H0z" fill="#4f7d56"/><path d="M600 130l50 60h-100zM240 250l40 50h-80z" fill="#fff"/>')},
 {id:'forest',name:'Forest',url:svg('<rect width="1280" height="720" fill="#cfe8d0"/><g fill="#3f7a4a"><path d="M100 720V300l-80 160h60L0 600h80v120zM100 300l80 160h-60l80 140h-100v120z"/></g><g fill="#2d6a3d"><path d="M420 720V220l-110 190h80l-110 190h140v120zM420 220l110 190h-80l110 190H420z"/><path d="M900 720V260l-90 160h70l-100 170h120v130zM900 260l90 160h-70l100 170H900z"/></g><rect y="640" width="1280" height="80" fill="#4a8a52"/>')},
 {id:'sunset',name:'Sunset',url:svg('<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b4a8a"/><stop offset=".55" stop-color="#e97d6a"/><stop offset="1" stop-color="#ffd27a"/></linearGradient></defs><rect width="1280" height="720" fill="url(#s)"/><circle cx="640" cy="470" r="110" fill="#fff0b8"/><path d="M0 520q160-40 320-10t320-10 320 10 320-10v220H0z" fill="#2a3560"/>')},
 {id:'library',name:'Bookshelf',url:svg('<rect width="1280" height="720" fill="#6d4f35"/><g fill="#4b3523"><rect x="0" y="210" width="1280" height="16"/><rect x="0" y="440" width="1280" height="16"/><rect x="0" y="670" width="1280" height="16"/></g><g><rect x="60" y="90" width="40" height="120" fill="#b5534a"/><rect x="104" y="110" width="34" height="100" fill="#3e6d9c"/><rect x="142" y="80" width="46" height="130" fill="#d5b04a"/><rect x="560" y="100" width="40" height="110" fill="#4e8a5e"/><rect x="604" y="90" width="50" height="120" fill="#a8574f"/><rect x="900" y="110" width="44" height="100" fill="#c9a24c"/><rect x="300" y="320" width="50" height="120" fill="#3e6d9c"/><rect x="354" y="340" width="36" height="100" fill="#b5534a"/><rect x="800" y="330" width="46" height="110" fill="#d5b04a"/><rect x="1000" y="310" width="44" height="130" fill="#4e8a5e"/><rect x="150" y="550" width="40" height="120" fill="#a8574f"/><rect x="620" y="560" width="50" height="110" fill="#3e6d9c"/><rect x="1100" y="540" width="44" height="130" fill="#d5b04a"/></g>')},
];
declare global{interface Window{SelfieSegmentation?:any}}
let loading:Promise<any>|null=null;
function loadLib():Promise<any>{
  if(window.SelfieSegmentation)return Promise.resolve(window.SelfieSegmentation);
  return loading||(loading=new Promise((res,rej)=>{const s=document.createElement('script');s.src='/mediapipe/selfie_segmentation.js';s.onload=()=>window.SelfieSegmentation?res(window.SelfieSegmentation):rej(new Error('lib'));s.onerror=()=>{loading=null;rej(new Error('lib'))};document.head.appendChild(s)}));
}
export class BgProcessor{
  track:MediaStreamTrack;mode:BgMode={kind:'none'};private v=document.createElement('video');private c=document.createElement('canvas');private x:CanvasRenderingContext2D;
  private seg:any;private stopped=false;private busy=false;private img:HTMLImageElement|null=null;private imgUrl='';private timer=0;onfail?:()=>void;onready?:()=>void;private first=true;
  constructor(raw:MediaStreamTrack){
    const st=raw.getSettings();this.c.width=st.width||1280;this.c.height=st.height||720;this.x=this.c.getContext('2d')!;
    this.v.muted=true;this.v.playsInline=true;this.v.srcObject=new MediaStream([raw]);this.v.play().catch(()=>{});
    this.track=this.c.captureStream(30).getVideoTracks()[0];this.init();
  }
  private async init(){
    try{
      const S=await loadLib();this.seg=new (S.SelfieSegmentation||S)({locateFile:(f:string)=>'/mediapipe/'+f});
      this.seg.setOptions({modelSelection:1,selfieMode:false});this.seg.onResults((r:any)=>this.draw(r));await this.seg.initialize();
      this.timer=window.setInterval(()=>this.tick(),33);
    }catch(e){if(!this.stopped)this.onfail?.()}
  }
  private async tick(){
    if(this.stopped||this.busy||this.v.readyState<2)return;this.busy=true;
    try{if(this.c.width!==this.v.videoWidth&&this.v.videoWidth){this.c.width=this.v.videoWidth;this.c.height=this.v.videoHeight}await this.seg.send({image:this.v})}catch{}
    this.busy=false;
  }
  private mc=document.createElement('canvas');
  private softMask(mask:any,w:number,h:number){const m=this.mc;if(m.width!==256){m.width=256;m.height=Math.max(1,Math.round(256*h/w))}const g=m.getContext('2d')!;g.clearRect(0,0,m.width,m.height);g.imageSmoothingEnabled=true;g.drawImage(mask,0,0,m.width,m.height);this.x.imageSmoothingEnabled=true;this.x.imageSmoothingQuality='high';this.x.drawImage(m,0,0,w,h)}
  setMode(m:BgMode){this.mode=m;if(m.kind==='image'&&m.url!==this.imgUrl){this.imgUrl=m.url;const i=new Image();i.onload=()=>{this.img=i};i.src=m.url}}
  private draw(r:any){
    const {x,c}=this,w=c.width,h=c.height;x.save();x.clearRect(0,0,w,h);
    this.softMask(r.segmentationMask,w,h);      // soft edges from a small, smoothed copy of the mask: far cheaper than blurring the full-size picture every frame
    x.globalCompositeOperation='source-in';x.drawImage(r.image,0,0,w,h);
    x.globalCompositeOperation='destination-over';
    if(this.mode.kind==='image'&&this.img){const iw=this.img.width,ih=this.img.height,k=Math.max(w/iw,h/ih);x.drawImage(this.img,(w-iw*k)/2,(h-ih*k)/2,iw*k,ih*k)}
    else{x.filter=`blur(${this.mode.kind==='blur'?this.mode.level:10}px)`;x.drawImage(r.image,0,0,w,h);x.filter='none'}
    x.restore();if(this.first){this.first=false;this.onready?.()}
  }
  stop(){this.stopped=true;clearInterval(this.timer);try{this.seg?.close()}catch{}this.track.stop();this.v.srcObject=null}
}
export function loadSaved():BgMode{try{const j=JSON.parse(localStorage.getItem('isift.bg')||'null');if(j&&j.kind==='blur')return {kind:'blur',level:j.level||10};if(j&&j.kind==='image'){const p=PRESETS.find(p=>p.id===j.id);if(p)return {kind:'image',id:p.id,url:p.url};const u=localStorage.getItem('isift.bg.custom');if(j.id==='custom'&&u)return {kind:'image',id:'custom',url:u}}}catch{}return {kind:'none'}}
export function save(m:BgMode){try{localStorage.setItem('isift.bg',JSON.stringify(m.kind==='image'?{kind:'image',id:m.id}:m))}catch{}}
export function readImage(f:File):Promise<string>{return new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>{const i=new Image();i.onload=()=>{const k=Math.min(1,1280/i.width),c=document.createElement('canvas');c.width=i.width*k;c.height=i.height*k;c.getContext('2d')!.drawImage(i,0,0,c.width,c.height);const u=c.toDataURL('image/jpeg',.82);try{localStorage.setItem('isift.bg.custom',u)}catch{}res(u)};i.onerror=rej;i.src=String(r.result)};r.onerror=rej;r.readAsDataURL(f)})}
