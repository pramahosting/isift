// node print.js  (after python3 build.py): turns docs/manuals/html/*.html into PDFs in frontend/public/manuals
const {chromium}=require('playwright');const fs=require('fs'),path=require('path');
(async()=>{const dir=path.join(__dirname,'html'),out=path.join(__dirname,'..','..','frontend','public','manuals');fs.mkdirSync(out,{recursive:true});
const b=await chromium.launch();for(const f of fs.readdirSync(dir).filter(x=>x.endsWith('.html'))){const p=await b.newPage();await p.goto('file://'+path.join(dir,f));
await p.pdf({path:path.join(out,f.replace('.html','.pdf')),format:'A4',printBackground:true,displayHeaderFooter:true,headerTemplate:'<span></span>',footerTemplate:'<div style="font-size:8px;width:100%;text-align:center;color:#778">Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',margin:{top:'16mm',bottom:'18mm',left:'14mm',right:'14mm'}});console.log('pdf',f)}await b.close()})()
