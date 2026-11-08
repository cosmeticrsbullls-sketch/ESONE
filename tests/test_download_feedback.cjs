const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('modules/ui.py','utf8');
const script=source.match(/ACTION_FEEDBACK_SCRIPT = r'''<script>([\s\S]*?)<\/script>'''/)[1];
const handlers={},microtasks=[];
const context={document:{addEventListener:(name,fn)=>handlers[name]=fn},window:{addEventListener(){}},queueMicrotask:fn=>microtasks.push(fn),Map,Set};
vm.runInNewContext(script,context);
function form(download){return {attrs:{},hasAttribute:n=>download&&n==='data-download-form',setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}};}
function button(){return {tagName:'BUTTON',name:'output',value:'pdf',innerHTML:'Download Draft PDF',textContent:'Download Draft PDF',attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},classList:{add(){},remove(){}}};}
function submit(f,b){let e={target:f,submitter:b,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;}};handlers.submit(e);while(microtasks.length)microtasks.shift()();return e;}
const downloadForm=form(true),downloadButton=button();
assert.equal(submit(downloadForm,downloadButton).defaultPrevented,false);
assert.equal(downloadButton.textContent,'Download Draft PDF');
assert.equal(downloadForm.attrs['aria-busy'],undefined);
assert.equal(downloadButton.attrs['aria-disabled'],undefined);
assert.equal(submit(downloadForm,downloadButton).defaultPrevented,false);
assert.equal(downloadButton.name,'output');assert.equal(downloadButton.value,'pdf');
console.log('PASS PDF attachment downloads remain reusable without a permanent processing lock');
const normal=form(false),save=button();
submit(normal,save);assert.equal(save.textContent,'Processing…');
assert.equal(submit(normal,save).defaultPrevented,true);
assert.equal(save.value,'pdf');
console.log('PASS normal forms keep duplicate-submit protection and submitter values');
