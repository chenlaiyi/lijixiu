const fs=require('fs'),vm=require('vm'),assert=require('assert');
const areas=[{id:123,city:'厦门市',district:'海沧区',name:'未来海岸社区',estates:['未来海岸-蓝月湾一期'],region_id:6,store_id:3},
 {id:124,city:'厦门市',district:'海沧区',name:'万科城社区',estates:[],region_id:5,store_id:4}];
const context={document:{addEventListener(){}}};
vm.runInNewContext(fs.readFileSync('admin-web/address-fields.js','utf8'),context);
const value=context.AddressFields.resolve(areas,{city_region:'厦门市/海沧区',estate:'未来海岸-蓝月湾一期',door_number:'嵩屿北五里23号2101室'});
assert.strictEqual(value.service_area_id,123);
assert.throws(()=>context.AddressFields.resolve(areas,{city_region:'厦门市/思明区',estate:'未来海岸',door_number:'1号'}));
let definition;
vm.runInNewContext(fs.readFileSync('miniprogram/components/address-fields/address-fields.js','utf8'),{
 Component:d=>{definition=d;},require:()=>({get:async()=>areas})
});
const component={...definition.methods,data:{...definition.data},properties:{value:{}},
 setData(v){Object.assign(this.data,v);},triggerEvent(name,v){this.value=v;}};
(async()=>{
 await component.load();
 component.selectRegion({detail:{value:0}});
 component.inputEstate({detail:{value:'未来海岸-蓝月湾一期'}});
 component.inputDoor({detail:{value:'嵩屿北五里23号2101室'}});
 assert.strictEqual(component.value.store_id,3);
 assert.strictEqual(component.value.service_area_id,123);
 component.inputEstate({detail:{value:'万科城二期'}});
 assert.strictEqual(component.value.store_id,4);
 component.inputEstate({detail:{value:'没有开通的小区'}});
 assert.strictEqual(component.value.service_area_id,null);
 console.log('PASS: web and mini-program address matching; unmatched neighborhoods cannot keep a stale store');
})().catch(e=>{console.error(e);process.exitCode=1;});
