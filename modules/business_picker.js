// One visible search control; retain the source select for existing submit/change handlers.
(() => {
 document.querySelectorAll('[data-unified-business]').forEach((picker,index)=>{
  const select=picker.querySelector('select'),input=picker.querySelector('input[type=search]');
  if(!select||!input)return;
  const required=select.required;select.required=false;select.hidden=true;
  const list=document.createElement('div'),help=document.createElement('small');
  list.className='business-suggestions';list.id='business-options-'+index;list.hidden=true;list.setAttribute('role','listbox');
  help.setAttribute('aria-live','polite');picker.appendChild(list);picker.appendChild(help);
  input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls',list.id);input.setAttribute('aria-expanded','false');input.required=required;
  let matches=[],active=-1,chosen='';
  const options=()=>Array.from(select.options).filter(o=>o.value&&!o.disabled&&!o.parentElement?.disabled);
  const label=o=>o.textContent.trim();
  function close(){list.hidden=true;active=-1;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');}
  function validity(){input.setCustomValidity(required&&(!select.value||input.value!==chosen)?'Choose a registered business from the suggestions.':'');}
  function refresh(){const item=options().find(o=>o.value===select.value);chosen=item?label(item):'';input.value=chosen;validity();close();}
  function choose(item){select.value=item.value;chosen=label(item);input.value=chosen;validity();help.textContent='Business selected.';close();select.dispatchEvent(new Event('change',{bubbles:true}));}
  function render(){
   const term=input.value.trim().toLowerCase();matches=options().filter(o=>label(o).toLowerCase().includes(term));active=-1;list.replaceChildren();input.removeAttribute('aria-activedescendant');
   if(!term){close();help.textContent='Type a business name, mobile or area.';return;}
   for(const [i,item] of matches.entries()){
    const row=document.createElement('button');row.type='button';row.tabIndex=-1;row.id=list.id+'-'+i;row.setAttribute('role','option');row.setAttribute('aria-selected','false');row.textContent=label(item);
    row.addEventListener('click',()=>choose(item));list.appendChild(row);
   }
   list.hidden=!matches.length;input.setAttribute('aria-expanded',String(matches.length>0));
   help.textContent=matches.length?'Tap a matching business.':'No matching business. Use Add Business on Home first.';
  }
  input.addEventListener('input',()=>{if(input.value!==chosen){select.value='';chosen='';select.dispatchEvent(new Event('businessclear',{bubbles:true}));}validity();render();});
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
  select.addEventListener('businessoptionschange',refresh);
  document.addEventListener('pointerdown',event=>{if(!picker.contains(event.target))close();});
  if(select.form)select.form.addEventListener('submit',event=>{validity();if(!input.reportValidity())event.preventDefault();});
  refresh();
 });
})();
