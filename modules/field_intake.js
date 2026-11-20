(() => {
const form=document.getElementById('field-form'),message=document.getElementById('field-message'),find=document.getElementById('find-business'),picker=document.getElementById('field-picker'),select=document.getElementById('business-select'),search=document.getElementById('business-search');
let entries=[];
function openForm(business) {
 form.dispatchEvent(new Event('businesschange'));
 form.elements.client_id.value=business?business.id:'';
 document.getElementById('visit-form-title').textContent='Visit details';
 document.getElementById('selected-business').textContent=business?[business.name,business.type,business.phone,business.area].filter(Boolean).join(' · '):'Register this business and record your first visit.';
 picker.hidden=true;form.hidden=false;message.textContent='Fill the visit details below.';
}
function render() {
 const term=search.value.trim().toLowerCase();
 const matches=entries.filter(c=>[c.name,c.phone,c.area,c.type].join(' ').toLowerCase().includes(term));
 select.replaceChildren(new Option(matches.length?'Select business to open visit form':'No matching entries',''));
 for(const [label,groupEntries] of [
  ['Nearby registered businesses',matches.filter(c=>c.distance_m!==undefined)],
  ['Registered without GPS — first verified visit',matches.filter(c=>c.distance_m===undefined)]
 ]){
  if(!groupEntries.length)continue;
  const group=document.createElement('optgroup');group.label=label;
  groupEntries.forEach(c=>group.appendChild(new Option(`${c.name} · ${c.type} · ${c.area} ${c.distance_m===undefined?'(no registered GPS)':`(${c.distance_m}m)`}`,String(c.id))));
  select.appendChild(group);
 }
 select.disabled=!matches.length;
 select.dispatchEvent(new Event('businessoptionschange'));
 document.getElementById('business-help').textContent=matches.length?'Select the registered business to record your visit.':'No matching business. Use Add Business on Home to register it first.';
}
find.addEventListener('click',()=> {
 form.hidden=true;picker.hidden=true;find.disabled=true;message.textContent='Checking your location…';
 if(!navigator.geolocation){message.textContent='GPS is not supported by this browser.';find.disabled=false;return;}
 navigator.geolocation.getCurrentPosition(async position=> {
 try {
 const lat=position.coords.latitude,lon=position.coords.longitude;
 const response=await fetch(`/field/nearby?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}`);
 if(!response.ok)throw new Error(await response.text());
 const data=await response.json();entries=[...data.nearby,...data.unmapped];
 form.elements.latitude.value=lat;form.elements.longitude.value=lon;
 search.value='';render();find.hidden=true;picker.hidden=false;
 message.textContent='';
 }catch(error){message.textContent='Could not check businesses. '+error.message;}
 finally{find.disabled=false;}
 },error=>{message.textContent='Allow location permission and turn on GPS, then try again. '+error.message;find.disabled=false;},{enableHighAccuracy:true,timeout:20000,maximumAge:0});
});
if(location.pathname==='/field/intake')find.click();

select.addEventListener('change',()=>{const business=entries.find(c=>String(c.id)===select.value);if(business)openForm(business);});

document.getElementById('choose-existing').addEventListener('click',()=>{form.dispatchEvent(new Event('businesschange'));form.hidden=true;picker.hidden=false;select.value='';select.dispatchEvent(new Event('businessoptionschange'));message.textContent='Select your registered business.';});
const submitMessage=document.getElementById('field-submit-message');
let submitting=false;
function showSubmitMessage(text,isError=false){
 submitMessage.hidden=false;submitMessage.textContent=text;
 submitMessage.classList.toggle('has-error',isError);
 if(isError){submitMessage.focus({preventScroll:true});submitMessage.scrollIntoView({block:'center'});}
}
async function responseMessage(response){
 const text=await response.text();
 if((response.headers.get('content-type')||'').includes('application/json')){
  try{const data=JSON.parse(text);
   if(typeof data.detail==='string')return {text:data.detail};
   if(Array.isArray(data.detail))return {text:data.detail.map(e=>String(e.loc?.at(-1)||'Field')+': '+e.msg).join('; ')};
  }catch(error){}
 }
 if(text.includes('<')){
  const doc=new DOMParser().parseFromString(text,'text/html');
  doc.querySelectorAll('script,style').forEach(node=>node.remove());
  return {text:doc.body.textContent.trim().slice(0,600)||'Please try again.'};
 }
 return {text:text.trim().slice(0,600)||'Please try again.'};
}
form.addEventListener('submit',async event=> {
 event.preventDefault();if(submitting)return;
 if(!form.reportValidity()){
  showSubmitMessage('Enter the visit details / outcome before finishing.');return;
 }
 submitting=true;form.setAttribute('aria-busy','true');
 const buttons=Array.from(form.querySelectorAll('button'));
 const start=buttons.find(b=>b.type==='submit');const original=start?.textContent;
 const disabledStates=buttons.map(b=>[b,b.disabled]);
 buttons.forEach(b=>b.disabled=true);if(start)start.textContent='Saving visit…';
 showSubmitMessage('Saving completed visit…');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try {
 const response=await fetch(form.action,{method:'POST',body:new FormData(form),signal:controller.signal});
 if(response.redirected){location.assign(response.url);return;}
 if(response.ok){const result=await response.json();if(result.redirect==='/workspace'){location.assign(result.redirect);return;}}
 const failure=await responseMessage(response),detail=failure.text;
 let help='';
 if(response.status===409&&/location mismatch/i.test(detail))help=' The current GPS does not match this business. Recheck your location; do not register a duplicate business.';
 else if(response.status===403)help=' Reload this page and sign in again if requested.';
 showSubmitMessage('Could not save visit ('+response.status+'): '+detail+help,true);
 }catch(error){
 showSubmitMessage('Connection interrupted or timed out. Try again; the same submission will not create a duplicate visit.',true);
 }finally{
 clearTimeout(timer);submitting=false;form.removeAttribute('aria-busy');
 disabledStates.forEach(([b,disabled])=>b.disabled=disabled);if(start)start.textContent=original;
 }
});
})();
