(() => {
const form=document.getElementById('field-form'), message=document.getElementById('field-message'), find=document.getElementById('find-business'), select=document.getElementById('business-select'), existing=document.getElementById('existing-business'), registration=document.getElementById('field-registration'), search=document.getElementById('business-search');
let entries=[];
function register(show) {
 registration.hidden=!show; registration.disabled=!show;
 existing.hidden=show || !entries.length;
 select.disabled=show || !entries.length; select.required=!select.disabled;
 form.action='/field/start';
}
function render() {
 const term=search.value.trim().toLowerCase();
 const matches=entries.filter(c=>[c.name,c.phone,c.area,c.type].join(' ').toLowerCase().includes(term));
 const old=select.value;
 select.replaceChildren(new Option(matches.length?'Select registered business':'No matching business — change search or register new',''));
 matches.forEach(c=>select.add(new Option(`${c.name} · ${c.type} · ${c.area} ${c.distance_m===undefined?'(GPS not registered)':`(${c.distance_m}m)`}`,String(c.id))));
 if(matches.some(c=>String(c.id)===old)) select.value=old;
 document.getElementById('business-help').textContent='Businesses without GPS can be selected for their first visit. This location will be saved when you start.';
}
find.addEventListener('click',()=> {
 form.hidden=true; find.disabled=true; message.textContent='Getting location…';
 if(!navigator.geolocation) {message.textContent='GPS is not supported by this browser.';find.disabled=false;return;}
 navigator.geolocation.getCurrentPosition(async position=> {
 try {
 const lat=position.coords.latitude,lon=position.coords.longitude;
 const response=await fetch(`/field/nearby?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}`);
 if(!response.ok) throw new Error(await response.text());
 const data=await response.json(); entries=[...data.nearby,...data.unmapped];
 form.elements.latitude.value=lat; form.elements.longitude.value=lon;
 search.value='';render();form.hidden=false;
 message.textContent=data.nearby.length?`${data.nearby.length} registered businesses found within ${data.radius_m}m.`:'No registered business with GPS found nearby. Choose an existing business without GPS, or register a new salon, distributor or academy.';
 register(!entries.length);
 } catch(error) {message.textContent='Could not check businesses. '+error.message;}
 finally {find.disabled=false;}
 },error=> {message.textContent='Allow location permission and turn on GPS, then try again. '+error.message;find.disabled=false;},{enableHighAccuracy:true,timeout:20000,maximumAge:0});
});
search.addEventListener('input',render);
document.getElementById('show-registration').addEventListener('click',()=>register(true));
document.getElementById('choose-existing').addEventListener('click',()=>register(false));
form.addEventListener('submit',async event=> {
 event.preventDefault();if(!form.reportValidity())return;
 const buttons=Array.from(form.querySelectorAll('button'));buttons.forEach(b=>b.disabled=true);find.disabled=true;
 message.textContent='Saving business and starting visit…';
 try {
 const response=await fetch(form.action,{method:'POST',body:new FormData(form)});
 if(response.redirected&&response.ok){location.assign(response.url);return;}
 message.textContent=await response.text();
 } catch(error){message.textContent='Connection interrupted. Try again; the same submission will not create a duplicate visit.';}
 buttons.forEach(b=>b.disabled=false);find.disabled=false;
});
})();
