const api=require('../../../utils/api');
Page({data:{rows:[],selected:[],storeId:null,saving:false,error:''},
async onLoad(options){this.setData({storeId:Number(options.storeId)});await this.load();},
async load(){try{const [rows,team]=await Promise.all([api.get(`/api/v1/stores/${this.data.storeId}/technician-candidates`),api.get(`/api/v1/stores/${this.data.storeId}/technicians`)]);const selected=team.map(r=>String(r.id));this.setData({rows:rows.map(r=>({...r,checked:selected.includes(String(r.id))})),selected,error:''});}catch(e){this.setData({error:e.message});}},
change(e){this.setData({selected:e.detail.value});},
async save(){if(this.data.saving)return;this.setData({saving:true});try{await api.put(`/api/v1/stores/${this.data.storeId}/technicians`,{repairer_ids:this.data.selected.map(Number)});wx.showToast({title:'已保存'});}catch(e){this.setData({error:e.message});}finally{this.setData({saving:false});}}
});
