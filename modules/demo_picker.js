(() => {
 const form=document.getElementById('demo-booking');if(!form)return;
 const picker=form.querySelector('[data-business-picker]'),input=picker.querySelector('input[type=search]'),identity=picker.querySelector('input[name=client_id]'),help=picker.querySelector('[data-business-help]');
 const options=Array.from(document.getElementById(input.getAttribute('list')).options);
 function syncBusiness(){
  const match=options.find(option=>option.value===input.value);
  identity.value=match?match.dataset.clientId:'';
  input.setCustomValidity(match?'':'Choose a registered business from the suggestions.');
  const term=input.value.trim().toLowerCase(),count=options.filter(option=>option.value.toLowerCase().includes(term)).length;
  help.textContent=match?'Business selected.':count?'Choose a matching business from the suggestions.':'No matching business. Use Add Business on Home first.';
 }
 input.addEventListener('input',syncBusiness);input.addEventListener('change',syncBusiness);
 const educator=form.elements.educator_id,other=form.querySelector('[data-other-educator]'),name=form.elements.educator_name;
 function syncEducator(){const custom=educator.value==='0';other.hidden=!custom;name.disabled=!custom;name.required=custom;if(!custom)name.value='';}
 educator.addEventListener('change',syncEducator);
 form.addEventListener('submit',event=>{syncBusiness();syncEducator();if(!form.reportValidity())event.preventDefault();});
 syncBusiness();syncEducator();
})();
