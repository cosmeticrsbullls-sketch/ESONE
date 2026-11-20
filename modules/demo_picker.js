(() => {
 const form=document.getElementById('demo-booking');if(!form)return;
 const picker=form.querySelector('[data-business-picker]'),input=picker.querySelector('input[type=search]'),identity=picker.querySelector('input[name=client_id]'),help=picker.querySelector('[data-business-help]'),list=picker.querySelector('[data-business-results]');
 const options=Array.from(document.getElementById('demo-businesses').options);
 let matches=[],active=-1;
 function close(){list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');active=-1;}
 function syncBusiness(){
  const match=options.find(option=>option.value===input.value);
  identity.value=match?match.dataset.clientId:'';
  input.setCustomValidity(match?'':'Choose a registered business from the suggestions.');
  help.textContent=match?'Business selected.':'Type a name or mobile and tap a business below.';
 }
 function choose(option){input.value=option.value;syncBusiness();input.focus();close();}
 function render(){
  const term=input.value.trim().toLowerCase();matches=options.filter(option=>option.value.toLowerCase().includes(term));active=-1;input.removeAttribute('aria-activedescendant');list.replaceChildren();
  if(!term){matches=[];close();return;}
  for(const [index,option] of matches.entries()){
   const row=document.createElement('button');row.type='button';row.tabIndex=-1;row.id='business-result-'+index;row.setAttribute('role','option');row.setAttribute('aria-selected','false');row.textContent=option.value;
   row.addEventListener('click',()=>choose(option));list.appendChild(row);
  }
  list.hidden=!matches.length;input.setAttribute('aria-expanded',String(matches.length>0));
  help.textContent=matches.length?'Tap a matching business below.':'No matching business. Use Add Business on Home first.';
 }
 input.addEventListener('input',()=>{syncBusiness();render();});
 input.addEventListener('change',syncBusiness);
 input.addEventListener('focus',render);
 input.addEventListener('keydown',event=>{
  if(event.key==='Escape'||event.key==='Tab'){close();return;}
  if(event.key==='ArrowDown'||event.key==='ArrowUp'){
   event.preventDefault();if(list.hidden)render();if(!matches.length)return;
   active=active<0?(event.key==='ArrowDown'?0:matches.length-1):(active+(event.key==='ArrowDown'?1:-1)+matches.length)%matches.length;
   Array.from(list.children).forEach((row,i)=>row.setAttribute('aria-selected',String(i===active)));
   const row=list.children[active];input.setAttribute('aria-activedescendant',row.id);row.scrollIntoView({block:'nearest'});
  }
  if(event.key==='Enter'&&!list.hidden&&matches.length){event.preventDefault();choose(matches[active<0?0:active]);}
 });
 document.addEventListener('pointerdown',event=>{if(!picker.contains(event.target))close();});
 const educator=form.elements.educator_id,other=form.querySelector('[data-other-educator]'),name=form.elements.educator_name;
 function syncEducator(){const custom=educator.value==='0';other.hidden=!custom;name.disabled=!custom;name.required=custom;if(!custom)name.value='';}
 educator.addEventListener('change',syncEducator);
 form.addEventListener('submit',event=>{syncBusiness();syncEducator();if(!form.reportValidity())event.preventDefault();});
 syncBusiness();syncEducator();close();
})();
