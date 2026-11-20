const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../modules/demo_picker.js'),'utf8');
function field(value=''){return {value,handlers:{},addEventListener(k,f){this.handlers[k]=f;},setCustomValidity(v){this.error=v;},getAttribute(){return 'demo-businesses';}};}
const input=field(),id=field(),help={},educator=field(''),name=field(''),other={hidden:true},events={};
const picker={querySelector:s=>s.includes('type=search')?input:s.includes('client_id')?id:help};
const form={elements:{educator_id:educator,educator_name:name},querySelector:s=>s==='[data-business-picker]'?picker:other,addEventListener:(e,f)=>events[e]=f,reportValidity:()=>!input.error&&Boolean(educator.value)&&(educator.value!=='0'||Boolean(name.value))};
vm.runInNewContext(source,{document:{getElementById:id=>id==='demo-booking'?form:{options:[{value:'Earthshine Salon · 999',dataset:{clientId:'7'}},{value:'Salon Two · 888',dataset:{clientId:'8'}}]}}});
input.value='Earth';input.handlers.input();assert.equal(id.value,'');assert(input.error);
input.value='Earthshine Salon · 999';input.handlers.input();assert.equal(id.value,'7');assert.equal(input.error,'');
input.value='Changed name';input.handlers.input();assert.equal(id.value,'');
assert.equal(other.hidden,true);assert.equal(name.disabled,true);
educator.value='0';educator.handlers.change();assert.equal(other.hidden,false);assert.equal(name.disabled,false);assert.equal(name.required,true);
name.value='Guest';educator.value='2';educator.handlers.change();assert.equal(other.hidden,true);assert.equal(name.value,'');assert.equal(name.disabled,true);
let prevented=false;events.submit({preventDefault(){prevented=true;}});assert(prevented);
input.value='Salon Two · 888';input.handlers.change();prevented=false;events.submit({preventDefault(){prevented=true;}});assert.equal(prevented,false);assert.equal(id.value,'8');
console.log('PASS business suggestion selection, stale-ID reset, required selection, and Other educator visibility/validation');
