// Run with: node tests/test_pdf_share.cjs (no browser or external messages).
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=readFileSync(require('node:path').join(__dirname,'../modules/pdf_reports.py'),'utf8');
const script=source.split("SHARE_SCRIPT='''<script>")[1].split("</script>'''")[0];
function setup({share,canShare=true,fetchResult,fetchGate,native=true}={}){
 let click,fetches=0,shares=0,downloads=0;const attrs={};
 const button={disabled:false,textContent:'Share',addEventListener:(event,fn)=>click=fn};
 const status={textContent:''},progress={hidden:true};
 const box={dataset:{pdf:'/test.pdf',filename:'test.pdf'},querySelector:s=>s==='button'?button:s==='progress'?progress:status,setAttribute:(k,v)=>attrs[k]=v,removeAttribute:k=>delete attrs[k]};
 const navigator=native?{canShare:()=>canShare,share:(data)=>{shares++;return share?share(data):Promise.resolve();}}:{};
 const context={document:{querySelectorAll:()=>[box],createElement:()=>({click:()=>downloads++})},navigator,
  fetch:async()=>{fetches++;if(fetchGate)await fetchGate;return fetchResult?fetchResult():{ok:true,headers:{get:()=> 'application/pdf'},blob:async()=> 'dummy pdf'};},
  File:class {constructor(parts,name,opts){this.name=name;this.type=opts.type;}},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},setTimeout(){}};
 vm.runInNewContext(script,context);
 return {click:()=>click(),button,status,progress,attrs,counts:()=>({fetches,shares,downloads})};
}
function namedError(name){const e=new Error();e.name=name;return e;}
const tests=[
 ['single tap fetches PDF and directly opens share',async()=>{const t=setup();await t.click();assert.deepEqual(t.counts(),{fetches:1,shares:1,downloads:0});assert.match(t.status.textContent,/Shared/);assert.equal(t.button.disabled,false);assert.equal(t.progress.hidden,true);assert.equal(t.attrs['aria-busy'],undefined);}],
 ['loading bar and duplicate tap guard while preparing',async()=>{let release;const gate=new Promise(r=>release=r);const t=setup({fetchGate:gate});const first=t.click();assert.equal(t.progress.hidden,false);assert.equal(t.button.disabled,true);assert.equal(t.attrs['aria-busy'],'true');await t.click();assert.equal(t.counts().fetches,1);release();await first;assert.equal(t.counts().shares,1);}],
 ['expired browser activation keeps PDF for synchronous retry',async()=>{let attempt=0;const t=setup({share:()=>++attempt===1?Promise.reject(namedError('NotAllowedError')):Promise.resolve()});await t.click();assert.match(t.status.textContent,/PDF ready — Tap to share/);assert.equal(t.counts().downloads,0);const second=t.click();assert.equal(t.counts().shares,2);await second;assert.equal(t.counts().fetches,1);assert.match(t.status.textContent,/Shared/);}],
 ['user cancellation preserves PDF without downloading',async()=>{const t=setup({share:()=>Promise.reject(namedError('AbortError'))});await t.click();assert.match(t.status.textContent,/cancelled/);assert.equal(t.counts().downloads,0);await t.click();assert.equal(t.counts().fetches,1);}],
 ['missing native share downloads PDF on first tap',async()=>{const t=setup({native:false});await t.click();assert.deepEqual(t.counts(),{fetches:1,shares:0,downloads:1});}],
 ['unsupported file share downloads PDF',async()=>{const t=setup({canShare:false});await t.click();assert.equal(t.counts().downloads,1);assert.equal(t.counts().shares,0);}],
 ['network failure allows a fresh retry',async()=>{let failed=false;const t=setup({fetchResult:()=>{if(!failed){failed=true;throw Error('offline');}return {ok:true,headers:{get:()=> 'application/pdf'},blob:async()=> 'pdf'};}});await t.click();assert.match(t.status.textContent,/Unable/);assert.equal(t.button.disabled,false);assert.equal(t.progress.hidden,true);await t.click();assert.equal(t.counts().shares,1);assert.equal(t.counts().fetches,2);}],
 ['HTML login response is never shared as PDF',async()=>{const t=setup({fetchResult:()=>({ok:true,headers:{get:()=> 'text/html'}})});await t.click();assert.equal(t.counts().shares,0);assert.equal(t.counts().downloads,0);assert.match(t.status.textContent,/Unable/);}],
 ['server error is never shared',async()=>{const t=setup({fetchResult:()=>({ok:false,headers:{get:()=> 'application/pdf'}})});await t.click();assert.equal(t.counts().shares,0);assert.equal(t.button.disabled,false);}],
 ['repeat taps while share menu pending do not open another menu',async()=>{let release;const pending=new Promise(r=>release=r);const t=setup({share:()=>pending});const first=t.click();await new Promise(r=>setImmediate(r));await t.click();assert.equal(t.counts().shares,1);release();await first;}]
];
(async()=>{for(const [name,test] of tests){await test();console.log('PASS '+name);}console.log(tests.length+' share tests passed');})().catch(e=>{console.error(e);process.exitCode=1;});
