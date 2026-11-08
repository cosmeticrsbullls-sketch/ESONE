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
 const matches=document.getElementById('field-existing-matches');if(matches){matches.hidden=true;matches.replaceChildren();}
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
 message.textContent=`${data.nearby.length} registered businesses found within ${data.radius_m}m. Select your business, or use Add New Visit if it is not registered. Businesses without GPS are listed separately for their first verified visit.`;
 }catch(error){message.textContent='Could not check businesses. '+error.message;}
 finally{find.disabled=false;}
 },error=>{message.textContent='Allow location permission and turn on GPS, then try again. '+error.message;find.disabled=false;},{enableHighAccuracy:true,timeout:20000,maximumAge:0});
});
search.addEventListener('input',render);
select.addEventListener('change',()=>{const business=entries.find(c=>String(c.id)===select.value);if(business)openForm(business);});
document.getElementById('show-registration').addEventListener('click',()=>openForm(null));
document.getElementById('choose-existing').addEventListener('click',()=>{form.hidden=true;picker.hidden=false;select.value='';message.textContent='Select your business or add a new visit.';});
const submitMessage=document.getElementById('field-submit-message'),existingMatches=document.getElementById('field-existing-matches');
let submitting=false;
function showSubmitMessage(text,isError=false){
 submitMessage.hidden=false;submitMessage.textContent=text;
 submitMessage.classList.toggle('has-error',isError);
 if(isError){submitMessage.focus({preventScroll:true});submitMessage.scrollIntoView({block:'center'});}
}
function offerRegisteredBusinesses(matches){
 existingMatches.replaceChildren();existingMatches.hidden=false;
 for(const business of matches){
  const choice=document.createElement('button');choice.type='button';choice.disabled=!business.active;choice.setAttribute('data-action-icon','sales');
  choice.textContent=(business.active?'Start visit at ':'Inactive — ')+[business.name,business.phone,business.area].filter(Boolean).join(' · ');
  choice.addEventListener('click',()=>{
   if(submitting||!business.active)return;
   // Reuse the record only after the employee explicitly chooses it. Keep GPS,
   // notes, visit type and submission key; the server still checks location.
   form.elements.client_id.value=String(business.id);
   registration.hidden=true;registration.disabled=true;
   document.getElementById('selected-business').textContent=[business.name,business.type,business.phone,business.area].filter(Boolean).join(' · ');
   document.getElementById('visit-form-title').textContent='Visit details';
   existingMatches.hidden=true;form.requestSubmit();
  });
  existingMatches.appendChild(choice);
 }
}
async function responseMessage(response){
 const text=await response.text();
 if((response.headers.get('content-type')||'').includes('application/json')){
  try{const data=JSON.parse(text);
   if(data.code==='BUSINESS_ALREADY_EXISTS'&&Array.isArray(data.matches))return {text:data.detail,matches:data.matches};
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
  showSubmitMessage('Complete the required business name and mobile fields before starting the visit.');return;
 }
 submitting=true;form.setAttribute('aria-busy','true');
 const buttons=Array.from(form.querySelectorAll('button'));
 const start=buttons.find(b=>b.type==='submit');const original=start?.textContent;
 const disabledStates=buttons.map(b=>[b,b.disabled]);
 buttons.forEach(b=>b.disabled=true);if(start)start.textContent='Starting visit…';
 showSubmitMessage('Saving and starting visit…');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try {
 const response=await fetch(form.action,{method:'POST',body:new FormData(form),signal:controller.signal});
 if(response.redirected&&response.ok){location.assign(response.url);return;}
 const failure=await responseMessage(response),detail=failure.text;
 if(response.status===409&&failure.matches?.length){
  offerRegisteredBusinesses(failure.matches);
  showSubmitMessage(detail,true);return;
 }
 let help='';
 if(response.status===409&&/already exists/i.test(detail))help=' Tap BACK TO BUSINESS LIST to select the registered business. Do not register it again.';
 else if(response.status===409&&/location mismatch/i.test(detail))help=' The current GPS does not match this business. Recheck your location; do not register a duplicate business.';
 else if(response.status===403)help=' Reload this page and sign in again if requested.';
 showSubmitMessage('Could not start visit ('+response.status+'): '+detail+help,true);
 }catch(error){
 showSubmitMessage('Connection interrupted or timed out. Try again; the same submission will not create a duplicate visit.',true);
 }finally{
 clearTimeout(timer);submitting=false;form.removeAttribute('aria-busy');
 disabledStates.forEach(([b,disabled])=>b.disabled=disabled);if(start)start.textContent=original;
 }
});
})();
