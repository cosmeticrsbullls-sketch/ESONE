(() => {
const form=document.getElementById('field-form'),message=document.getElementById('field-message'),find=document.getElementById('find-business'),picker=document.getElementById('field-picker'),select=document.getElementById('business-select'),registration=document.getElementById('field-registration'),search=document.getElementById('business-search');
let entries=[];
function openForm(business) {
 const isNew=!business;
 registration.hidden=!isNew;registration.disabled=!isNew;
 form.elements.client_id.value=business?business.id:'';
 document.getElementById('visit-form-title').textContent=isNew?'New business visit':'Visit details';
 document.getElementById('selected-business').textContent=business?[business.name,business.type,business.phone,business.area].filter(Boolean).join(' · '):'Register this business and start your first visit.';
 picker.hidden=true;form.hidden=false;message.textContent='Fill the visit details below.';
}
function render() {
 const term=search.value.trim().toLowerCase();
 const matches=entries.filter(c=>[c.name,c.phone,c.area,c.type].join(' ').toLowerCase().includes(term));
 select.replaceChildren(new Option(matches.length?'Select business to open visit form':'No matching entries',''));
 matches.forEach(c=>select.add(new Option(`${c.name} · ${c.type} · ${c.area} ${c.distance_m===undefined?'(first GPS visit)':`(${c.distance_m}m)`}`,String(c.id))));
 select.disabled=!matches.length;
 document.getElementById('business-help').textContent=matches.length?'Select your business. If your target is missing, use Add New Visit.':'Your target is not in the list? Use Add New Visit below.';
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
 message.textContent=data.nearby.length?`${data.nearby.length} businesses found within ${data.radius_m}m.`:'No business with a registered GPS location found nearby. Select a first-time entry or add a new visit.';
 }catch(error){message.textContent='Could not check businesses. '+error.message;}
 finally{find.disabled=false;}
 },error=>{message.textContent='Allow location permission and turn on GPS, then try again. '+error.message;find.disabled=false;},{enableHighAccuracy:true,timeout:20000,maximumAge:0});
});
search.addEventListener('input',render);
select.addEventListener('change',()=>{const business=entries.find(c=>String(c.id)===select.value);if(business)openForm(business);});
document.getElementById('show-registration').addEventListener('click',()=>openForm(null));
document.getElementById('choose-existing').addEventListener('click',()=>{form.hidden=true;picker.hidden=false;select.value='';message.textContent='Select your business or add a new visit.';});
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
  try{const data=JSON.parse(text);if(typeof data.detail==='string')return data.detail;
   if(Array.isArray(data.detail))return data.detail.map(e=>String(e.loc?.at(-1)||'Field')+': '+e.msg).join('; ');
  }catch(error){}
 }
 if(text.includes('<')){
  const doc=new DOMParser().parseFromString(text,'text/html');
  doc.querySelectorAll('script,style').forEach(node=>node.remove());
  return doc.body.textContent.trim().slice(0,600)||'Please try again.';
 }
 return text.trim().slice(0,600)||'Please try again.';
}
form.addEventListener('submit',async event=> {
 event.preventDefault();if(submitting)return;
 if(!form.reportValidity()){
  showSubmitMessage('Complete the required business name and mobile fields before starting the visit.');return;
 }
 submitting=true;form.setAttribute('aria-busy','true');
 const buttons=Array.from(form.querySelectorAll('button'));
 const start=buttons.find(b=>b.type==='submit');const original=start?.textContent;
 buttons.forEach(b=>b.disabled=true);if(start)start.textContent='Starting visit…';
 showSubmitMessage('Saving and starting visit…');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try {
 const response=await fetch(form.action,{method:'POST',body:new FormData(form),signal:controller.signal});
 if(response.redirected&&response.ok){location.assign(response.url);return;}
 const detail=await responseMessage(response);
 let help='';
 if(response.status===409&&/already exists/i.test(detail))help=' Tap BACK TO BUSINESS LIST to select the registered business. Do not register it again.';
 else if(response.status===409&&/location mismatch/i.test(detail))help=' The current GPS does not match this business. Recheck your location; do not register a duplicate business.';
 else if(response.status===403)help=' Reload this page and sign in again if requested.';
 showSubmitMessage('Could not start visit ('+response.status+'): '+detail+help,true);
 }catch(error){
 showSubmitMessage('Connection interrupted or timed out. Try again; the same submission will not create a duplicate visit.',true);
 }finally{
 clearTimeout(timer);submitting=false;form.removeAttribute('aria-busy');
 buttons.forEach(b=>b.disabled=false);if(start)start.textContent=original;
 }
});
})();
