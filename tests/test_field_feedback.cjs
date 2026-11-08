// Run: node tests/test_field_feedback.cjs. Uses dummy forms; no live requests/GPS.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../modules/field_intake.js'),'utf8');
function setup({valid=true,response,fetcher}={}){
 const nodes={},handlers={},timers=[];let requests=0,destination;
 function node(id){return nodes[id]??=( {hidden:false,disabled:false,value:'',textContent:'',type:'button',attrs:{},classList:{toggle(){}},addEventListener:(event,fn)=>{handlers[id+':'+event]=fn},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},focus(){this.focused=true},scrollIntoView(){this.scrolled=true},replaceChildren(){},add(){}} );}
 for(const id of ['field-form','field-message','find-business','field-picker','business-select','field-registration','business-search','visit-form-title','selected-business','business-help','show-registration','choose-existing','field-submit-message'])node(id);
 const start=node('submit');start.type='submit';start.textContent='START VISIT';
 const back=node('back');const form=nodes['field-form'];form.action='/field/start';form.reportValidity=()=>valid;form.querySelectorAll=()=>[start,back];
 form.elements=Object.fromEntries(Object.entries({latitude:'23',longitude:'72',client_id:'1',submission:'same-idempotent-key'}).map(([k,value])=>[k,{value}]));
 const context={document:{getElementById:node},navigator:{},Option:class{},encodeURIComponent,AbortController,
  fetch:async(url,options)=>{requests++;return fetcher?fetcher(url,options):response;},
  FormData:class{constructor(f){this.values=Object.fromEntries(Object.entries(f.elements).map(([k,v])=>[k,v.value]));}},
  setTimeout(fn){timers.push(fn);return timers.length;},clearTimeout(){},location:{assign:url=>destination=url},
  DOMParser:class{parseFromString(){return {querySelectorAll:()=>[],body:{textContent:'Service unavailable. Try again.'}};}}};
 vm.runInNewContext(source,context);
 return {submit:()=>handlers['field-form:submit']({preventDefault(){}}),nodes,start,back,form,timers,get requests(){return requests},get destination(){return destination}};
}
const reply=(status,text,type='text/html')=>({status,ok:status>=200&&status<300,redirected:false,text:async()=>text,headers:{get:()=>type}});
const tests=[
 ['409 duplicate is visible beside submit and focused with next step',async()=>{const t=setup({response:reply(409,'A business with this name or mobile already exists.')});await t.submit();const m=t.nodes['field-submit-message'];assert.equal(m.hidden,false);assert(m.focused&&m.scrolled);assert.match(m.textContent,/BACK TO BUSINESS LIST/);assert.equal(t.start.disabled,false);assert.equal(t.start.textContent,'START VISIT');}],
 ['GPS mismatch is visible without relaxing location checks',async()=>{const t=setup({response:reply(409,'Location mismatch. Check your location again.')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/GPS does not match/);assert.equal(t.form.elements.latitude.value,'23');}],
 ['403 explains reload/sign-in',async()=>{const t=setup({response:reply(403,'Please reload the form and try again.')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/sign in again/);}],
 ['JSON validation errors are readable',async()=>{const t=setup({response:reply(422,JSON.stringify({detail:[{loc:['body','latitude'],msg:'Invalid number'}]}),'application/json')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/latitude: Invalid number/);}],
 ['HTML server error is shown as text',async()=>{const t=setup({response:reply(503,'<h1>Service unavailable. Try again.</h1>')});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/Service unavailable/);assert(!t.nodes['field-submit-message'].textContent.includes('<h1>'));}],
 ['invalid required fields show explanation and send no request',async()=>{const t=setup({valid:false});await t.submit();assert.equal(t.requests,0);assert.match(t.nodes['field-submit-message'].textContent,/required business name and mobile/);}],
 ['network failure re-enables controls and retains submission key',async()=>{const t=setup({fetcher:async()=>{throw Error('offline')}});await t.submit();assert.match(t.nodes['field-submit-message'].textContent,/Connection interrupted/);assert.equal(t.start.disabled,false);assert.equal(t.back.disabled,false);assert.equal(t.form.elements.submission.value,'same-idempotent-key');}],
 ['timeout re-enables controls safely',async()=>{const t=setup({fetcher:(_,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('aborted'))))});const pending=t.submit();t.timers[0]();await pending;assert.match(t.nodes['field-submit-message'].textContent,/timed out/);assert.equal(t.start.disabled,false);}],
 ['second tap cannot issue a duplicate in-flight request',async()=>{let release;const gate=new Promise(r=>release=r);const t=setup({fetcher:async()=>{await gate;return reply(409,'Try again.')}});const first=t.submit();assert.equal(t.start.textContent,'Starting visit…');assert.equal(t.form.attrs['aria-busy'],'true');await t.submit();assert.equal(t.requests,1);release();await first;assert.equal(t.form.attrs['aria-busy'],undefined);}],
 ['successful visit redirects to details',async()=>{const t=setup({response:{ok:true,redirected:true,url:'https://esone.example.test/visits/101'}});await t.submit();assert.equal(t.destination,'https://esone.example.test/visits/101');}]
];
(async()=>{for(const [name,test] of tests){await test();console.log('PASS '+name)}console.log(tests.length+' field-feedback tests passed');})().catch(error=>{console.error(error);process.exitCode=1});
