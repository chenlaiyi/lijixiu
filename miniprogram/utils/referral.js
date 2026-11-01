const api=require('./api');
let binding=false;
async function bindPending(){
 const code=wx.getStorageSync('pendingReferralCode');
 if(!code || binding || !wx.getStorageSync('token'))return;
 binding=true;
 try{await api.post('/api/v1/referrals/bind',{code});wx.removeStorageSync('pendingReferralCode');}catch(e){}finally{binding=false;}
}
module.exports={bindPending};
