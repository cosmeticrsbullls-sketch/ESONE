const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../modules/business_picker.js'),'utf8');
function node(){return {value:'',textContent:'',handlers:{},attrs:{},children:[],addEventListener(k,f){this.handlers[k]=f},dispatchEvent(e){this.handlers[e.type]?.(e)},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},setCustomValidity(v){this.error=v},reportValidity(){return !this.error},replaceChildren(){this.children=[]},appendChild(c){this.children.push(c)},scrollIntoView(){}}}
function setup(required=true){
 const input=node(),select=node(),picker=node(),form=node(),docEvents={};
 const option=(id,text,dataset={})=>({value:id,textContent:text,dataset});
 select.options=[option('','Select'),option('7','Karlek · 999',{name:'Karlek',address:'Rajkot'}),option('8','Other · 888')];select.required=required;select.form=form;
 picker.querySelector=s=>s==='select'?select:input;picker.contains=t=>t===input||picker.children.includes(t);
 const doc={querySelectorAll:()=>[picker],createElement:node,addEventListener:(e,f)=>docEvents[e]=f};
 vm.runInNewContext(source,{document:doc,Event:class{constructor(type){this.type=type}}});
 return {input,select,form,list:picker.children[0],help:picker.children[1],option,outside:()=>docEvents.pointerdown({target:{}})};
}
const t=setup();assert.equal(t.select.hidden,true);assert.equal(t.select.required,false);assert.equal(t.input.required,true);
t.input.value='Kar';t.input.handlers.input();assert.equal(t.list.hidden,false);assert.equal(t.list.children.length,1);assert.match(t.list.children[0].textContent,/Karlek/);
let autofill,changes=0;t.select.addEventListener('change',()=>{changes++;autofill=t.select.options.find(o=>o.value===t.select.value).dataset.address});t.list.children[0].handlers.click();assert.equal(t.select.value,'7');assert.equal(autofill,'Rajkot');assert.equal(changes,1);assert.equal(t.list.hidden,true);assert.equal(t.input.error,'');
t.input.value='unregistered';t.input.handlers.input();assert.equal(t.select.value,'');assert(t.input.error);assert.equal(t.list.hidden,true);let prevented=false;t.form.handlers.submit({preventDefault(){prevented=true}});assert(prevented);
t.input.value='888';t.input.handlers.input();t.input.handlers.keydown({key:'ArrowDown',preventDefault(){}});assert.match(t.input.attrs['aria-activedescendant'],/business-options-0-0/);t.select.handlers.change=()=>{};t.input.handlers.keydown({key:'Enter',preventDefault(){}});assert.equal(t.select.value,'8');
t.input.value='Kar';t.input.handlers.input();t.outside();assert.equal(t.list.hidden,true);t.input.handlers.focus();assert.equal(t.list.hidden,false);t.input.handlers.keydown({key:'Escape'});assert.equal(t.list.hidden,true);
const field=setup(false);field.select.options=[field.option('','Select'),field.option('4','Nearby Salon (20m)')];field.select.value='';field.select.dispatchEvent({type:'businessoptionschange'});assert.equal(field.input.value,'');assert.equal(field.input.error,'');field.input.value='Nearby';field.input.handlers.input();let opened;field.select.addEventListener('change',()=>opened=field.select.value);field.list.children[0].handlers.click();assert.equal(opened,'4');field.select.value='';field.select.dispatchEvent({type:'businessoptionschange'});assert.equal(field.input.value,'');
console.log('PASS one visible business input, auto-open search, exact IDs, billing change callback, stale selection invalidation, submit validation, mobile text lookup, keyboard, dismissal, dynamic GPS options and return reset');
