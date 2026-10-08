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
form.addEventListener('submit',async event=> {
 event.preventDefault();if(!form.reportValidity())return;
 const buttons=Array.from(form.querySelectorAll('button'));buttons.forEach(b=>b.disabled=true);
 message.textContent='Saving and starting visit…';
 try {
 const response=await fetch(form.action,{method:'POST',body:new FormData(form)});
 if(response.redirected&&response.ok){location.assign(response.url);return;}
 message.textContent=await response.text();
 }catch(error){message.textContent='Connection interrupted. Try again; the same submission will not create a duplicate visit.';}
 buttons.forEach(b=>b.disabled=false);
});
})();
