const assert=require('assert'),vm=require('vm'),fs=require('fs'),ctx={};vm.runInNewContext(fs.readFileSync('admin-web/address-tree.js','utf8'),ctx);const T=ctx.AddressTree;
const rows=[{id:1,service_area_id:10,estate:'蓝月湾一期',city:'厦门市',district:'海沧区',building:'S6号楼',entrance_name:'28号',room:'101',enabled:true,property_type:'住宅'},
 {id:2,service_area_id:10,estate:'蓝月湾一期',city:'厦门市',district:'海沧区',building:'S6号楼',entrance_name:'30号',room:'101',enabled:true,property_type:'住宅'},
 {id:3,service_area_id:10,estate:'蓝月湾一期',city:'厦门市',district:'海沧区',building:'商业',entrance_name:'0单元',room:'19-101',enabled:true,property_type:'商业',review_required:true},
 {id:4,service_area_id:10,estate:'蓝月湾一期',city:'厦门市',district:'海沧区',building:'车库',entrance_name:'B1',room:'01',enabled:true,property_type:'车位'}];
let editor=T.editor(rows,[]);assert.strictEqual(editor.tree.length,1);assert.strictEqual(editor.nodes.size,4);
assert.strictEqual(editor.items().length,2);assert(editor.items().every(r=>r.property_type!=='车位' && r.address_id===null));
const nodes=[...editor.nodes.values()];const n28=nodes.find(n=>n.entrance==='28号'),n30=nodes.find(n=>n.entrance==='30号');
editor.toggle([n30.id],false,'group');assert(editor.items().some(r=>r.entrance_name==='28号'));assert(!editor.items().some(r=>r.entrance_name==='30号'));
editor.toggle(nodes.map(n=>n.id),true,'estate');assert.strictEqual(editor.items().length,3);assert(editor.items().some(r=>r.property_type==='车位'));
editor.toggle(nodes.map(n=>n.id),false,'estate');assert.strictEqual(editor.items().length,0);
const old=[{service_area_id:10,building:null,entrance_name:null,address_id:null}];editor=T.editor(rows,old);assert.strictEqual(JSON.stringify(editor.items()),JSON.stringify(old));
const partial=[{service_area_id:10,building:null,entrance_name:null,address_id:1},{service_area_id:99,address_id:999}];editor=T.editor(rows,partial);assert.strictEqual(editor.items().length,1);assert.strictEqual(editor.items()[0].address_id,1);
const group=editor.tree[0].categories[0].groups.find(n=>n.entrance==='28号');assert(group.partial);editor.toggle([group.id],true,'group');assert(editor.items().some(r=>r.entrance_name==='28号' && r.address_id===null));assert(!editor.items().some(r=>r.address_id===999));
editor=T.editor(rows,[],[{service_area_id:10,property_type:'住宅',building:'S6号楼',entrance_name:'28号',address_id:null,store_name:'其他店'}]);
assert([...editor.nodes.values()].find(n=>n.entrance==='28号').blocked);assert(!editor.items().some(r=>r.entrance_name==='28号'));
assert(!T.matches({service_area_id:10,property_type:'住宅'},rows[2]));
const ordinary=[1,2].map((n,i)=>({...rows[0],id:100+i,building:'N1号楼',entrance_name:n+'单元',unit:n+'单元',entrance_type:'普通单元'}));
const ordinaryTree=T.editor(ordinary,[]);assert.strictEqual(ordinaryTree.nodes.size,1);assert.strictEqual([...ordinaryTree.nodes.values()][0].entrance,null);assert.strictEqual([...ordinaryTree.nodes.values()][0].rows.length,2);
console.log('PASS hierarchical type defaults, parent selection, entrance scopes, parking opt-in, legacy partial and hidden scope preservation, competitor guards');

// Regression: hidden disabled, missing, pending and wrong-estate precise rules
// must not poison a replacement request; valid partial allocations still survive.
const archived={...rows[0],id:119,service_area_id:552,enabled:false};
const stale=[{service_area_id:552,address_id:119},{service_area_id:99,address_id:999},{service_area_id:10,address_id:3},{service_area_id:99,address_id:1}];
editor=T.editor([...rows,archived],stale);
assert(editor.items().every(r=>!r.address_id));
editor.toggle([...editor.nodes.keys()],false,'estate');assert.strictEqual(editor.items().length,0);
editor.toggle([...editor.nodes.keys()],true,'estate');assert.strictEqual(editor.items().length,3);
const saved=JSON.parse(JSON.stringify(editor.items()));
editor=T.editor([...rows,archived],saved);assert.strictEqual(JSON.stringify(editor.items()),JSON.stringify(saved));
editor.toggle([...editor.nodes.keys()],false,'estate');assert.strictEqual(editor.items().length,0);
console.log('PASS cancel and reassign drops invalid hidden legacy addresses and round-trips saved scopes');
