(() => {
 const box=document.getElementById('permission-setup');if(!box)return;
 const status=name=>document.getElementById(name+'-status'),message=document.getElementById('setup-message'),next=document.getElementById('setup-continue');
 const fieldRequired=box.dataset.fieldRequired!=='false';
 const identity=box.dataset.device,key='esone-permissions:'+identity;let memory={};try{memory=JSON.parse(localStorage.getItem(key)||'{}')}catch(_){}
 let locationReady=false,cameraReady=false,notificationReady=false,registration;
 function save(){try{localStorage.setItem(key,JSON.stringify(memory))}catch(_){}}
 function update(){next.disabled=!((!fieldRequired||locationReady&&cameraReady)&&(notificationReady||memory.skipNotifications));}
 async function state(name){try{return (await navigator.permissions.query({name})).state}catch(_){return 'unknown'}}
 async function post(path,data={}){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf:box.querySelector('[name=csrf]').value,...data})});if(!response.ok||response.redirected)throw Error('Could not save notification setup. Sign in on an approved browser and retry.');return response.json();}
 function supported(){return 'serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window;}
 function publicKey(){return Uint8Array.from(atob(box.dataset.key.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-box.dataset.key.length%4)%4)),c=>c.charCodeAt(0));}
 async function connect(){
  registration=await navigator.serviceWorker.register('/assets/push-worker.js',{scope:'/'});await navigator.serviceWorker.ready;
  let subscription=await registration.pushManager.getSubscription();let owner;try{owner=localStorage.getItem('esone-push-owner')}catch(_){}
  if(subscription&&owner!==identity){await subscription.unsubscribe();subscription=null;}
  if(!subscription)subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:publicKey()});
  await post('/push/subscribe',{subscription:subscription.toJSON()});try{localStorage.setItem('esone-push-owner',identity)}catch(_){}
  notificationReady=true;memory.notificationsOff=false;memory.skipNotifications=false;save();status('notification').textContent='✅ Notifications enabled';document.getElementById('test-notification').hidden=false;document.getElementById('disable-notifications').hidden=false;update();
 }
 document.getElementById('allow-location').addEventListener('click',()=>{
  status('location').textContent='Checking location…';
  if(!navigator.geolocation){status('location').textContent='Location is unsupported in this browser.';return;}
  navigator.geolocation.getCurrentPosition(()=>{locationReady=true;memory.location=true;save();status('location').textContent='✅ Location allowed';update();},()=>{locationReady=false;status('location').textContent='Location unavailable. Turn on GPS and allow location in site settings, then retry.';update();},{enableHighAccuracy:true,maximumAge:0,timeout:20000});
 });
 document.getElementById('allow-camera').addEventListener('click',async()=>{
  let stream;status('camera').textContent='Checking camera…';
  try{stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'}}});cameraReady=true;memory.camera=true;save();status('camera').textContent='✅ Camera allowed — camera is now off';}
  catch(_){cameraReady=false;status('camera').textContent='Camera unavailable. Allow it in site settings and retry.';}
  finally{stream?.getTracks().forEach(track=>track.stop());update();}
 });
 document.getElementById('allow-notifications').addEventListener('click',async()=>{
  if(!supported()){status('notification').textContent='Push unsupported here. On iPhone, open ESONE from its Home Screen icon.';return;}
  try{const permission=await Notification.requestPermission();if(permission!=='granted'){notificationReady=false;status('notification').textContent='Notifications not allowed. Enable them in site settings, or skip for now.';update();return;}await connect();}
  catch(error){status('notification').textContent=error.message;}
 });
 document.getElementById('skip-notifications').addEventListener('click',()=>{memory.skipNotifications=true;save();status('notification').textContent=notificationReady?'✅ Notifications enabled':'Notifications skipped — updates remain in ESONE.';update();});
 document.getElementById('disable-notifications').addEventListener('click',async()=>{try{await post('/push/unsubscribe');if(registration){const sub=await registration.pushManager.getSubscription();if(sub)await sub.unsubscribe();}notificationReady=false;memory.notificationsOff=true;memory.skipNotifications=true;save();status('notification').textContent='Notifications off — updates remain in ESONE.';document.getElementById('test-notification').hidden=true;document.getElementById('disable-notifications').hidden=true;update();}catch(_){message.textContent='Could not turn off notifications. Retry.';}});
 document.getElementById('test-notification').addEventListener('click',async()=>{try{const result=await post('/push/test');message.textContent=result.sent?'Test sent. Check your notification panel. Delivery can depend on phone settings.':'Could not send the test. Retry shortly.';}catch(_){message.textContent='Could not send test. Wait 30 seconds and retry.';}});
 next.addEventListener('click',()=>{if(!next.disabled)location.assign('/workspace');});
 async function check(){
  document.getElementById('push-install').hidden=supported();
  const geo=fieldRequired?await state('geolocation'):'not-needed',camera=fieldRequired?await state('camera'):'not-needed';
  locationReady=geo==='granted'||geo==='unknown'&&memory.location===true;cameraReady=camera==='granted'||camera==='unknown'&&memory.camera===true;
  status('location').textContent=geo==='granted'?'✅ Location allowed':locationReady?'Previously checked — browser cannot confirm permission.':'Permission needed';
  status('camera').textContent=camera==='granted'?'✅ Camera allowed':cameraReady?'Previously checked — browser cannot confirm permission.':'Permission needed';
  if(supported()&&Notification.permission==='granted'&&!memory.notificationsOff){try{await connect()}catch(_){status('notification').textContent='Permission allowed, but push setup needs retry.';}}
  else status('notification').textContent=memory.skipNotifications?'Notifications skipped':supported()?'Permission needed':'Push unsupported here. iPhone: install ESONE on Home Screen.';
  update();if(!next.disabled&&!new URLSearchParams(location.search).has('manage'))location.replace('/workspace');
 }
 check();
})();
