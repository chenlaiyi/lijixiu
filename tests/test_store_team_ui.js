const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync('admin-web/app.js','utf8');
const start=source.indexOf('} else if (action === "store-default-repairer") {');
const end=source.indexOf('} else if (action === "region-name")',start);
const body=source.slice(start+source.slice(start).indexOf('{')+1,end);
let shown=false;const run=new (Object.getPrototypeOf(async function(){}).constructor)('id','state','api','showModal','escapeHtml',body);
(async()=>{await run('14',{cache:{storeForm:{stores:[{id:14}],regions:[],users:[],repairers:[]}}},async()=>[{id:5,display_name:'Worker',skills:'repair'}],(title,html)=>{shown=true;assert(html.includes('value="5"'));assert(html.includes('checked'));},x=>x);assert(shown);console.log('PASS string dataset store ID opens populated technician modal');})().catch(e=>{console.error(e);process.exitCode=1});
