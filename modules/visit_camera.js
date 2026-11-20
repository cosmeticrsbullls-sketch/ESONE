(() => {
 document.querySelectorAll('.visit-camera').forEach(box=>{
 const form=box.closest('form'), video=box.querySelector('video'), preview=box.querySelector('img'), open=box.querySelector('[data-camera-open]'), capture=box.querySelector('[data-camera-capture]'), msg=box.querySelector('[data-camera-message]');
 let stream=null, busy=false, generation=0;
 function stop(){stream?.getTracks().forEach(t=>t.stop());stream=null;video.srcObject=null;video.hidden=true;capture.hidden=true;}
 function reset(){generation++;stop();form.elements.photo_data.value='';form.elements.photo_nonce.value='';preview.hidden=true;open.textContent='Open Camera';msg.textContent='';}
 form.addEventListener('businesschange',reset);
 window.addEventListener('pagehide',reset);
 open.addEventListener('click',async()=>{
  if(busy)return;reset();const attempt=generation;busy=true;open.disabled=true;
  try {
   if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera requires HTTPS and a supported browser.');
   const openedStream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:'environment'},width:{ideal:960},height:{ideal:720}}});
   if(attempt!==generation){openedStream.getTracks().forEach(t=>t.stop());return;}
   stream=openedStream;video.srcObject=stream;video.hidden=false;await video.play();if(attempt!==generation){stop();return;}capture.hidden=false;open.textContent='Retake';msg.textContent='Frame the salon and tap Capture.';
  }catch(error){stop();open.textContent='Open Camera';msg.textContent='Allow camera permission, then retry. '+error.message;}
  finally{busy=false;open.disabled=false;}
 });
 capture.addEventListener('click',async()=>{
  if(busy)return;const attempt=generation;busy=true;capture.disabled=true;open.disabled=true;msg.textContent='Getting fresh GPS and preparing photo…';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try {
   if(!stream?.active||!video.videoWidth||!video.videoHeight)throw new Error('Open the camera again.');
   const p=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,maximumAge:0,timeout:20000}));
   if(attempt!==generation)return;
   const f=new FormData();for(const key of ['csrf','client_id'])f.set(key,form.elements[key].value);
   f.set('latitude',p.coords.latitude);f.set('longitude',p.coords.longitude);f.set('accuracy',p.coords.accuracy);
   const r=await fetch('/visit-camera/challenge',{method:'POST',body:f,signal:controller.signal});if(r.redirected){location.assign(r.url);throw new Error('Sign in on an approved browser and retry.');}
   if(!(r.headers.get('content-type')||'').includes('application/json'))throw new Error('Punch In, then reopen this form.');
   const result=await r.json();if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'Sign in and retry.');
   if(attempt!==generation)return;
   const canvas=document.createElement('canvas'),ratio=Math.min(1,960/Math.max(video.videoWidth,video.videoHeight));
   canvas.width=Math.round(video.videoWidth*ratio);canvas.height=Math.round(video.videoHeight*ratio);canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
   const data=canvas.toDataURL('image/jpeg',0.8);form.elements.photo_data.value=data;form.elements.photo_nonce.value=result.nonce;
   form.elements.latitude.value=p.coords.latitude;form.elements.longitude.value=p.coords.longitude;
   preview.src=data;preview.hidden=false;stop();msg.textContent='Photo ready. Submit within 5 minutes, or retake.';
  }catch(error){form.elements.photo_data.value='';form.elements.photo_nonce.value='';msg.textContent='Could not capture photo. '+error.message;}
  finally{clearTimeout(timer);busy=false;capture.disabled=false;open.disabled=false;}
 });
 form.addEventListener('submit',event=>{
  if(!form.elements.photo_data.value||!form.elements.photo_nonce.value){event.preventDefault();event.stopImmediatePropagation();msg.textContent='Capture a fresh salon photo before finishing.';box.scrollIntoView({block:'center'});}
 },true);
 });
})();
