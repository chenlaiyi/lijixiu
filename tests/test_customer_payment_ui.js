const vm=require('vm'),fs=require('fs'),assert=require('assert');let page,created=false,requested=false;
const api={get:async()=>{throw Error('staff only');},post:async url=>{if(url==='/api/v1/payment/create'){created=true;return {pay_order_id:1,payment_params:{package:'mock'}};}return {};}};
const wx={getStorageSync:()=>({id:8}),login:o=>o.success({code:'fresh-test-code'}),requestPayment:o=>{requested=true;o.success({});},showToast:()=>{},redirectTo:()=>{}};
vm.runInNewContext(fs.readFileSync('miniprogram/pages/customer/pay/pay.js','utf8'),{Page:p=>page=p,require:n=>n.endsWith('/api')?api:n.endsWith('/share')?{create:()=>({})}:{},wx,setTimeout:()=>{}});
page.data={...page.data,order:{id:1},orderId:1,amount:'1.00'};page.setData=v=>Object.assign(page.data,v);page.loadOrder=async()=>{};
(async()=>{await page.doPay();assert(created);assert(requested);assert(!page.data.payErrorText);console.log('PASS customer reaches payment creation and WeChat dialog without staff-only diagnostics');})().catch(e=>{console.error(e);process.exitCode=1;});
