// Run: node tests/test_field_feedback.cjs. Uses dummy forms; no live requests/GPS.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../modules/field_intake.js'),'utf8');
function setup({valid=true,response,fetcher,gpsData}={}){
 const nodes={},handlers={},timers=[];let requests=0,destination,created=0;
 function node(id){return nodes[id]??=( {hidden:false,disabled:false,value:'',textContent:'',type:'button',attrs:{},children:[],classList:{toggle(){}},addEventListener:(event,fn)=>{handlers[id+':'+event]=fn},dispatchEvent(event){handlers[id+':'+event.type]?.(event)},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},focus(){this.focused=true},scrollIntoView(){this.scrolled=true},replaceChildren(){this.children=[]},appendChild(child){this.children.push(child)},add(){}} );}
 for(const id of ['field-form','field-message','find-business','field-picker','business-select','field-registration','business-search','visit-form-title','selected-business','business-help','show-registration','choose-existing','field-submit-message','field-existing-matches'])node(id);
 const start=node('submit');start.type='submit';start.textContent='Finish';
 const back=node('back');const form=nodes['field-form'];form.action='/field/start';form.reportValidity=()=>valid;form.querySelectorAll=()=>[start,back];
 form.elements=Object.fromEntries(Object.entries({latitude:'23',longitude:'72',client_id:'1',submission:'same-idempotent-key'}).map(([k,value])=>[k,{value}]));
 form.dispatchEvent=()=>{};
 const context={Event:class{constructor(type){this.type=type}},document:{getElementById:node,createElement:()=>node('created-'+(++created))},navigator:gpsData?{geolocation:{getCurrentPosition(success){return success({coords:{latitude:23,longitude:72}})}}}:{},Option:class{constructor(text,value){this.text=text;this.value=value;}},encodeURIComponent,AbortController,
  fetch:async(url,options)=>{requests++;if(url.startsWith('/field/nearby')&&gpsData)return {ok:true,json:async()=>gpsData};return fetcher?fetcher(url,options):response;},
  FormData:class{constructor(f){this.values=Object.fromEntries(Object.entries(f.elements).map(([k,v])=>[k,v.value]));}},
  setTimeout(fn){timers.push(fn);return timers.length;},clearTimeout(){},location:{assign:url=>destination=url},
  DOMParser:class{parseFromString(){return {querySelectorAll:()=>[],body:{textContent:'Service unavailable. Try again.'}};}}};
 vm.runInNewContext(source,context);
 form.requestSubmit=()=>{form.pending=handlers['field-form:submit']({preventDefault(){}})};
 return {find:()=>handlers['find-business:click'](),select:id=>{nodes['business-select'].value=id;handlers['business-select:change']()},register:()=>handlers['show-registration:click'](),submit:()=>handlers['field-form:submit']({preventDefault(){}}),nodes,start,back,form,timers,click:button=>handlers[Object.keys(nodes).find(k=>nodes[k]===button)+':click'](),get requests(){return requests},get destination(){return destination}};
}
const reply=(status,text,type='text/html')=>({status,ok:status>=200&&status<300,redirected:false,text:async()=>text,headers:{get:()=>type}});
const tests=[
 ['GPS lookup separates nearby registered businesses from records without GPS',async()=>{
  const t=setup({gpsData:{nearby:[{id:9,name:'Near Salon',phone:'111',type:'SALON',area:'Here',distance_m:0}],unmapped:[{id:11,name:'Unmapped Salon',type:'SALON',area:'Unknown'}],radius_m:200}});
  t.find();await new Promise(r=>setImmediate(r));
  const groups=t.nodes['business-select'].children;
  assert.equal(groups.length,2);assert.match(groups[0].label,/Nearby registered/);assert.match(groups[1].label,/without GPS/);
  assert.equal(t.nodes['field-picker'].hidden,false);t.select('9');
  assert.equal(t.form.elements.client_id.value,9);assert.equal(t.requests,1);
 }],
 ['missing businesses direct employees to Add Business on Home',async()=>{
  const t=setup({gpsData:{nearby:[],unmapped:[],radius_m:200}});t.find();await new Promise(r=>setImmediate(r));
  assert.match(t.nodes['business-help'].textContent,/Add Business on Home/);assert.equal(t.nodes['business-select'].disabled,true);
 }],
 ['GPS mismatch is visible without relaxing location checks',async()=>{const t=setup({response:reply(409,'Location mismatch. Check your location again.')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/GPS does not match/);assert.equal(t.form.elements.latitude.value,'23');}],
 ['403 explains reload/sign-in',async()=>{const t=setup({response:reply(403,'Please reload the form and try again.')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/sign in again/);}],
 ['JSON validation errors are readable',async()=>{const t=setup({response:reply(422,JSON.stringify({detail:[{loc:['body','latitude'],msg:'Invalid number'}]}),'application/json')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/latitude: Invalid number/);}],
 ['HTML server error is shown as text',async()=>{const t=setup({response:reply(503,'<h1>Service unavailable. Try again.</h1>')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/Service unavailable/);assert(!t.nodes['field-submit-message'].textContent.includes('<h1>'));}],
 ['invalid required fields show explanation and send no request',async()=>{const t=setup({valid:false});await t.submit();assert.equal(t.requests,0);assert.match(t.nodes['field-submit-message'].textContent,/visit details \/ outcome/);}],
 ['network failure re-enables controls and retains submission key',async()=>{const t=setup({fetcher:async()=>{throw Error('offline')}});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/Connection interrupted/);assert.equal(t.start.disabled,false);assert.equal(t.back.disabled,false);assert.equal(t.form.elements.submission.value,'same-idempotent-key');}],
 ['timeout re-enables controls safely',async()=>{const t=setup({fetcher:(_,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted'))))});const pending=t.submit();t.timers[0]();await pending;assert.match(t.nodes['field-submit-message'].textContent,/timed out/);assert.equal(t.start.disabled,false);}],
 ['second tap cannot issue a duplicate in-flight request',async()=>{let release;const gate=new Promise(r=>release=r);const t=setup({fetcher:async()=>{await gate;return reply(409,'Try again.')}});const first=t.submit();assert.equal(t.start.textContent,'Saving visit…');assert.equal(t.form.attrs['aria-busy'],'true');await t.submit();assert.equal(t.requests,1);release();await first;assert.equal(t.form.attrs['aria-busy'],undefined);}],
 ['successful Finish redirects to Home',async()=>{const t=setup({response:{ok:true,redirected:false,json:async()=>({redirect:'/workspace'})}});await t.submit();assert.equal(t.destination,'/workspace');}]
];
(async()=>{for(const [name,test] of tests){await test();console.log('PASS '+name)}console.log(tests.length+' field-feedback tests passed');})().catch(error=>{console.error(error);process.exitCode=1});
