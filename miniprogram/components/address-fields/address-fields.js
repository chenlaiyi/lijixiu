const api = require('../../utils/api');
const regionLabel = area => `${area.city || ''}/${area.district || ''}`;
const entrance = row => row.entrance_name || row.unit || '';
const sorted = values => [...new Set(values)].sort((a,b)=>String(a).localeCompare(String(b),'zh-CN',{numeric:true}));
function choices(areas,query='') {
  const q=query.trim().toLowerCase(), result=[];
  for(const area of areas){
    const names=[area.name,...(area.estates || []),...(area.estate_aliases || '').split(/\n|；|;/)];
    if(!q || names.some(name=>name.toLowerCase().includes(q)))result.push({label:`${area.name} · ${area.city}/${area.district}`,areaId:area.id});
    if(q)for(const row of area.addresses || []){
      if([row.estate,row.building,entrance(row),row.room,row.door_number,row.aliases,row.search_aliases].join(' ').toLowerCase().includes(q))
        result.push({label:[area.name,row.building,entrance(row),row.room].filter(Boolean).join(' / '),areaId:area.id,addressId:row.id});
      if(result.length>=20)break;
    }
    if(result.length>=20)break;
  }
  return result.slice(0,20);
}
Component({
 properties:{value:{type:Object,value:{},observer(){this.syncValue();}}},
 data:{regions:[],regionIndex:-1,regionText:'',keyword:'',neighborhoods:[],areaIndex:-1,estate:'',
   buildings:[],units:[],unitLabels:[],rooms:[],building:'',unit:'',room:'',doorNumber:'',aliases:'',
   addressOptions:[],loading:true,error:''},
 lifetimes:{attached(){this.load();}},
 methods:{
  async load(){try{this.areas=await api.get('/api/v1/service-areas/address-catalog');this.setData({regions:sorted(this.areas.map(regionLabel)),loading:false,error:''});this.syncValue();}catch(e){this.setData({loading:false,error:'地址加载失败，请重试'});}},
  syncValue(){
   if(!this.areas)return;
   const v=this.properties.value || {},area=this.areas.find(a=>Number(a.id)===Number(v.service_area_id));
   if(!area)return;
   this.selectedArea=area;
   const rows=area.addresses || [],matches=rows.filter(r=>r.estate===v.estate && r.door_number===v.door_number);
   const row=rows.find(r=>r.id===(v.address_book_id || v.service_address_id)) || (matches.length===1?matches[0]:null);
   this.selectedAddress=row || null;
   const text=regionLabel(area);
   this.setData({regionText:text,regionIndex:this.data.regions.indexOf(text),estate:area.name,keyword:area.name,
     neighborhoods:choices(this.areas.filter(a=>regionLabel(a)===text)),building:row?row.building:(v.building || ''),
     unit:row?entrance(row):(v.entrance_name || v.unit || ''),room:row?row.room:(v.room || ''),
     doorNumber:row?row.door_number:(v.door_number || ''),aliases:row?row.aliases:''});
   this.refreshHierarchy();
   if(row && (v.address_book_id!==row.id || v.store_id!==row.store_id || v.region_id!==row.region_id))this.emit();
  },
  clearHierarchy(){this.selectedAddress=null;this.setData({building:'',unit:'',room:'',doorNumber:'',aliases:'',buildings:[],units:[],unitLabels:[],rooms:[],addressOptions:[]});},
  selectRegion(e){const i=Number(e.detail.value),text=this.data.regions[i];this.selectedArea=null;this.clearHierarchy();this.setData({regionIndex:i,regionText:text,estate:'',keyword:'',neighborhoods:choices(this.areas.filter(a=>regionLabel(a)===text))});this.emit();},
  inputEstate(e){this.selectedArea=null;this.clearHierarchy();const keyword=e.detail.value;this.setData({keyword,estate:'',neighborhoods:choices(this.areas.filter(a=>regionLabel(a)===this.data.regionText),keyword)});this.emit();},
  selectCandidate(e){this.selectNeighborhood({detail:{value:e.currentTarget.dataset.index}});},
  selectNeighborhood(e){
   const item=this.data.neighborhoods[Number(e.detail.value)];if(!item)return;
   const area=this.areas.find(a=>a.id===item.areaId);if(!area)return;
   this.clearHierarchy();this.selectedArea=area;
   const row=(area.addresses || []).find(r=>r.id===item.addressId);this.selectedAddress=row || null;
   this.setData({estate:area.name,keyword:area.name,areaIndex:Number(e.detail.value),building:row?row.building:'',unit:row?entrance(row):'',room:row?row.room:'',doorNumber:row?row.door_number:'',aliases:row?row.aliases:''});
   this.refreshHierarchy();this.emit();
  },
  refreshHierarchy(){
   const rows=(this.selectedArea || {}).addresses || [],buildings=sorted(rows.map(r=>r.building));
   const buildingRows=rows.filter(r=>r.building===this.data.building),units=sorted(buildingRows.map(entrance));
   const selectedRows=buildingRows.filter(r=>entrance(r)===this.data.unit);
   this.setData({buildings,units,unitLabels:units.map(v=>v || '无单元编号'),rooms:sorted(selectedRows.map(r=>r.room)),
      addressOptions:rows.filter(r=>(!this.data.building || r.building===this.data.building) && (!this.data.unit || entrance(r)===this.data.unit)).slice(0,100).map(r=>({id:r.id,label:[r.building,entrance(r),r.room || r.door_number].filter(Boolean).join(' / ')}))});
  },
  selectBuilding(e){this.selectedAddress=null;this.setData({building:this.data.buildings[Number(e.detail.value)],unit:'',room:'',doorNumber:'',aliases:''});this.refreshHierarchy();this.emit();},
  selectUnit(e){this.selectedAddress=null;this.setData({unit:this.data.units[Number(e.detail.value)],room:'',doorNumber:'',aliases:''});this.refreshHierarchy();this.emit();},
  selectRoom(e){const room=this.data.rooms[Number(e.detail.value)],rows=((this.selectedArea || {}).addresses || []).filter(r=>r.building===this.data.building && entrance(r)===this.data.unit && r.room===room);this.setAddress(rows.length===1?rows[0]:null);},
  selectAddress(e){const item=this.data.addressOptions[Number(e.detail.value)];this.setAddress(item?((this.selectedArea || {}).addresses || []).find(r=>r.id===item.id):null);},
  setAddress(row){this.selectedAddress=row || null;if(row)this.setData({building:row.building,unit:entrance(row),room:row.room,doorNumber:row.door_number,aliases:row.aliases});else this.setData({room:'',doorNumber:'',aliases:''});this.refreshHierarchy();this.emit();},
  inputDoor(){this.selectedAddress=null;this.setData({doorNumber:'',aliases:''});this.emit();},
  emit(){const area=this.selectedArea,row=this.selectedAddress;this.triggerEvent('change',{
    address_book_id:row?row.id:null,service_address_id:row?row.id:null,building:this.data.building,unit:this.data.unit,entrance_name:this.data.unit,room:this.data.room,
    service_area_id:area?area.id:null,estate:this.data.estate,door_number:this.data.doorNumber,region_id:row?row.region_id:null,
    store_id:row?row.store_id:null,store_name:row?row.store_name:'',city:area?area.city:'',district:area?area.district:'',
    address:row?(row.full_address || [area.city,area.district,area.name,row.door_number].join(' ')):''});}
 }
});
