const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../modules/permissions.js'),'utf8');
const flush=()=>new Promise(r=>setImmediate(r));
function setup({denyCamera=false,denyLocation=false,supported=true,geo='prompt',camera='prompt'}={}){
 const nodes={},store=new Map(),requests=[];let cameraCalls=0,locationCalls=0,notificationCalls=0,stopped=0,destination;
 const node=id=>nodes[id]??={hidden:false,disabled:false,handlers:{},addEventListener(e,f){this.handlers[e]=f}};
 const box=node('permission-setup');box.dataset={device:'2:5',key:'AAAA'};box.querySelector=()=>({value:'csrf'});
 const subscription={toJSON:()=>({endpoint:'https://fcm.googleapis.com/test',keys:{p256dh:'fake',auth:'fake'}}),unsubscribe:async()=>true};
 const registration={pushManager:{getSubscription:async()=>null,subscribe:async()=>subscription}};
 const Notification={permission:'default',requestPermission:async()=>{notificationCalls++;Notification.permission='granted';return 'granted'}};
 const window=supported?{PushManager:class{},Notification}:{};
 const navigator={permissions:{query:async({name})=>({state:name==='camera'?camera:geo})},geolocation:{getCurrentPosition(ok,bad){locationCalls++;denyLocation?bad():ok({coords:{latitude:23,longitude:72}})}},mediaDevices:{getUserMedia:async options=>{cameraCalls++;assert.equal(options.audio,false);if(denyCamera)throw Error('denied');return {getTracks:()=>[{stop(){stopped++}}]}}}};
 if(supported)navigator.serviceWorker={register:async()=>registration,ready:Promise.resolve(registration)};
 vm.runInNewContext(source,{document:{getElementById:node},window,navigator,Notification,URLSearchParams,Uint8Array,atob:s=>Buffer.from(s,'base64').toString('binary'),localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},fetch:async(path,options)=>{requests.push({path,body:JSON.parse(options.body)});return {ok:true,json:async()=>({sent:true})}},location:{search:'?manage=1',assign:u=>destination=u,replace:u=>destination=u}});
 return {node,requests,store,click:id=>node(id).handlers.click(),get cameraCalls(){return cameraCalls},get locationCalls(){return locationCalls},get notificationCalls(){return notificationCalls},get stopped(){return stopped},get destination(){return destination}};
}
(async()=>{
 let t=setup();await flush();assert.equal(t.cameraCalls,0);assert.equal(t.locationCalls,0);assert.equal(t.notificationCalls,0);assert.equal(t.node('setup-continue').disabled,true);
 t.click('allow-location');await t.click('allow-camera');assert.equal(t.stopped,1);assert.match(t.node('camera-status').textContent,/now off/);assert.equal(t.node('setup-continue').disabled,true);t.click('skip-notifications');assert.equal(t.node('setup-continue').disabled,false);t.click('setup-continue');assert.equal(t.destination,'/workspace');assert.equal(t.requests.length,0);
 t=setup({denyCamera:true,denyLocation:true});await flush();t.click('allow-location');await t.click('allow-camera');t.click('skip-notifications');assert.equal(t.node('setup-continue').disabled,true);assert.equal(t.stopped,0);assert.match(t.node('camera-status').textContent,/unavailable/);
 t=setup();await flush();await t.click('allow-notifications');assert.equal(t.notificationCalls,1);assert.equal(t.requests[0].path,'/push/subscribe');assert.equal(t.requests[0].body.csrf,'csrf');assert.equal(t.node('test-notification').hidden,false);await t.click('test-notification');assert.equal(t.requests[1].path,'/push/test');await t.click('disable-notifications');assert.equal(t.requests[2].path,'/push/unsubscribe');assert.equal(t.node('test-notification').hidden,true);
 t=setup({supported:false});await flush();await t.click('allow-notifications');assert.equal(t.notificationCalls,0);assert.match(t.node('notification-status').textContent,/Home Screen/);
 console.log('PASS first-login user gestures, no automatic permission prompts, required gating, camera track cleanup, denied permissions, optional notifications, authenticated subscription/test/off, and iPhone unsupported guidance');
})().catch(e=>{console.error(e);process.exitCode=1});
