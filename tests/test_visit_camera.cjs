// Browser camera lifecycle tests with fake APIs. Physical mobile camera remains a manual check.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../modules/visit_camera.js'),'utf8');
function setup({denyCamera=false,denyGps=false,challengeStatus=200}={}){
 const handlers={},elements=Object.fromEntries(['photo_data','photo_nonce','latitude','longitude','csrf','client_id'].map(k=>[k,{value:k==='client_id'?'1':k==='csrf'?'csrf-value':''}]));
 const node=()=>({hidden:false,disabled:false,textContent:'',addEventListener(type,fn){this.handlers??={};this.handlers[type]=fn;},scrollIntoView(){this.scrolled=true;}});
 const video=node(),preview=node(),open=node(),capture=node(),msg=node();open.textContent='Open Camera';capture.hidden=true;let stopped=0,requests=0;
 video.videoWidth=1280;video.videoHeight=720;video.play=async()=>{};
 const stream={active:true,getTracks:()=>[{stop:()=>stopped++}]};
 const form={elements,addEventListener:(key,fn)=>handlers[key]=fn};
 const box={closest:()=>form,querySelector:key=>({'video':video,'img':preview,'[data-camera-open]':open,'[data-camera-capture]':capture,'[data-camera-message]':msg})[key],scrollIntoView(){this.scrolled=true;}};
 const context={AbortController,setTimeout,clearTimeout,document:{querySelectorAll:()=>[box],createElement:()=>({getContext:()=>({drawImage(){}}),toDataURL:()=> 'data:image/jpeg;base64,FAKE'})},window:{addEventListener:(key,fn)=>handlers[key]=fn},
 navigator:{mediaDevices:{getUserMedia:async()=>{if(denyCamera)throw Error('permission denied');return stream;}},geolocation:{getCurrentPosition:(resolve,reject)=>denyGps?reject(Error('location denied')):resolve({coords:{latitude:23,longitude:72,accuracy:12}})}},
 fetch:async()=>{requests++;return {ok:challengeStatus===200,headers:{get:()=> 'application/json'},json:async()=> challengeStatus===200?{nonce:'fresh-nonce'}:{detail:'GPS accuracy is too low'}};},FormData:class{set(){}},location:{assign(){}}};
 vm.runInNewContext(source,context);
 return {elements,video,preview,msg,box,open,capture,handlers,openCamera:()=>open.handlers.click(),snap:()=>capture.handlers.click(),get stopped(){return stopped},get requests(){return requests}};
}
(async()=>{
 let t=setup();let prevented=false;t.handlers.submit({preventDefault(){prevented=true;},stopImmediatePropagation(){}});assert(prevented);assert.match(t.msg.textContent,/fresh salon photo/);
 assert.equal(t.open.textContent,'Open Camera');assert.equal(t.capture.hidden,true);await t.openCamera();assert.equal(t.video.hidden,false);assert.equal(t.open.textContent,'Retake');assert.equal(t.capture.hidden,false);await t.snap();assert.equal(t.open.textContent,'Retake');assert.equal(t.capture.hidden,true);assert.equal(t.elements.photo_nonce.value,'fresh-nonce');assert.equal(t.elements.latitude.value,23);assert.equal(t.preview.hidden,false);assert.equal(t.stopped,1);
 prevented=false;t.handlers.submit({preventDefault(){prevented=true;},stopImmediatePropagation(){}});assert.equal(prevented,false);
 t.handlers.businesschange();assert.equal(t.elements.photo_data.value,'');assert.equal(t.elements.photo_nonce.value,'');assert.equal(t.preview.hidden,true);assert.equal(t.open.textContent,'Open Camera');
 await t.openCamera();t.handlers.pagehide();assert.equal(t.stopped,2);
 t=setup({denyCamera:true});await t.openCamera();assert.equal(t.elements.photo_data.value,'');assert.match(t.msg.textContent,/Allow camera permission/);assert.equal(t.open.disabled,false);assert.equal(t.open.textContent,'Open Camera');assert.equal(t.capture.hidden,true);
 t=setup({denyGps:true});await t.openCamera();await t.snap();assert.equal(t.requests,0);assert.equal(t.elements.photo_nonce.value,'');assert.equal(t.capture.disabled,false);
 t=setup({challengeStatus:400});await t.openCamera();await t.snap();assert.equal(t.elements.photo_data.value,'');assert.match(t.msg.textContent,/GPS accuracy/);
 console.log('PASS camera capture, GPS, photo-required, business-change reset, permission denial, failed challenge, and stream cleanup');
})().catch(e=>{console.error(e);process.exitCode=1;});
