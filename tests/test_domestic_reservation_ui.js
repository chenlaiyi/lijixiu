const assert=require('assert'),fs=require('fs'),vm=require('vm');
let definition;
const source=fs.readFileSync('miniprogram/pages/customer/domestic/demand/demand.js','utf8');
const markup=fs.readFileSync('miniprogram/pages/customer/domestic/demand/demand.wxml','utf8');
const config=JSON.parse(fs.readFileSync('miniprogram/pages/customer/domestic/demand/demand.json','utf8'));
assert.strictEqual(config.enableShareAppMessage,false);assert.strictEqual(config.enableShareTimeline,false);
assert(!/<textarea|chooseImages|toggleRecord|open-type="share"/.test(markup));
let hidden=0,requests=[],release;
const storage={token:'test',userInfo:{id:1,name:'测试客户',phone:'19900000001'}};
const api={get:async()=>[],post:async(url,body)=>{requests.push({url,body});if(release)await new Promise(r=>{release=r;});return {id:9};}};
vm.runInNewContext(source,{Page:d=>definition=d,require:()=>api,setTimeout:()=>{},wx:{getStorageSync:k=>storage[k],hideShareMenu:()=>hidden++,setNavigationBarTitle:()=>{},showToast:()=>{},showModal:()=>{}}});
function page(){const p={...definition,data:JSON.parse(JSON.stringify(definition.data))};p.setData=values=>{for(const [key,value] of Object.entries(values)){const parts=key.split('.');if(parts.length===1)p.data[key]=value;else p.data[parts[0]][parts[1]]=value;}};return p;}
(async()=>{
for(const type of ['maternity','nanny']){
 const p=page();p.onLoad({type});p.onShow();
 assert(!p.onShareAppMessage && !p.onShareTimeline);
 p.addressChange({detail:{address_book_id:7,region_id:2,store_id:3,address:'标准服务地址'}});
 p.setData({'form.startDate':'2026-11-15','form.description':'不应提交的自由文字'});
 p.tasksChange({detail:{value:['做饭','日常保洁']}});p.scheduleChange({detail:{value:2}});
 requests=[];await p.submit();
 assert.strictEqual(requests.length,1);
 assert.strictEqual(requests[0].body.description,type==='maternity'?'月嫂服务预约申请':'保姆服务预约申请');
 assert.strictEqual(requests[0].body.address_book_id,7);
 assert(!requests[0].body.media_json);
 if(type==='nanny'){const details=JSON.parse(requests[0].body.detail_json);assert.deepStrictEqual(details.tasks,['做饭','日常保洁']);assert.strictEqual(details.schedule,'上午');}
 await p.submit();assert.strictEqual(requests.length,1,'duplicate submit');
}
assert(hidden>=4);
const p=page();requests=[];await p.submit();assert.strictEqual(requests.length,0,'incomplete application accepted');
console.log('PASS maternity/nanny structured private reservations, fixed descriptions, no media/share, address selection and duplicate guard');
})().catch(e=>{console.error(e);process.exitCode=1;});
