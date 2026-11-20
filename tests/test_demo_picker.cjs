const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../modules/demo_picker.js'),'utf8');
function node(value=''){return {value,handlers:{},attrs:{},children:[],addEventListener(k,f){this.handlers[k]=f;},setCustomValidity(v){this.error=v;},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},replaceChildren(){this.children=[];},appendChild(row){this.children.push(row);},focus(){this.handlers.focus?.();},scrollIntoView(){}};}
const input=node(),id=node(),help=node(),list=node(),educator=node(''),name=node(),other={hidden:true},events={},outside={};
const picker={contains:target=>target!==outside,querySelector:s=>s.includes('type=search')?input:s.includes('client_id')?id:s==='[data-business-results]'?list:help};
const form={elements:{educator_id:educator,educator_name:name},querySelector:s=>s==='[data-business-picker]'?picker:other,addEventListener:(e,f)=>events[e]=f,reportValidity:()=>!input.error&&Boolean(educator.value)&&(educator.value!=='0'||Boolean(name.value))};
vm.runInNewContext(source,{document:{addEventListener:(e,f)=>events[e]=f,createElement:()=>node(),getElementById:id=>id==='demo-booking'?form:{options:[{value:'Karlek Hair & Beauty · 999',dataset:{clientId:'7'}},{value:'Salon Two · 888',dataset:{clientId:'8'}}]}}});
input.value='';input.handlers.keydown({key:'ArrowDown',preventDefault(){}});assert.equal(list.hidden,true);
input.value='Kar';input.handlers.input();assert.equal(list.hidden,false);assert.equal(list.children.length,1);assert.match(list.children[0].textContent,/Karlek/);assert.equal(input.attrs['aria-expanded'],'true');assert.equal(id.value,'');
list.children[0].handlers.click();assert.equal(id.value,'7');assert.equal(input.value,'Karlek Hair & Beauty · 999');assert.equal(list.hidden,true);
input.value='Changed name';input.handlers.input();assert.equal(id.value,'');assert.equal(list.hidden,true);assert.match(help.textContent,/No matching/);
input.value='888';input.handlers.input();assert.equal(list.hidden,false);input.handlers.keydown({key:'ArrowDown',preventDefault(){}});assert.equal(input.attrs['aria-activedescendant'],'business-result-0');input.handlers.keydown({key:'Enter',preventDefault(){}});assert.equal(id.value,'8');
input.value='Kar';input.handlers.input();events.pointerdown({target:outside});assert.equal(list.hidden,true);input.handlers.focus();assert.equal(list.hidden,false);input.handlers.keydown({key:'Escape'});assert.equal(list.hidden,true);
assert.equal(other.hidden,true);assert.equal(name.disabled,true);educator.value='0';educator.handlers.change();assert.equal(other.hidden,false);assert.equal(name.required,true);
name.value='Guest';educator.value='2';educator.handlers.change();assert.equal(name.value,'');assert.equal(name.disabled,true);
let prevented=false;events.submit({preventDefault(){prevented=true;}});assert(prevented);
console.log('PASS Kar auto-opens Karlek list, tap selection, stale-ID reset, mobile lookup, keyboard selection, outside dismissal, guest educator and required validation');
