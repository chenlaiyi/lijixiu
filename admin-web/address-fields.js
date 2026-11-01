/* All web order/address forms select the same catalog entity and entrance. */
(() => {
 const escape=v=>String(v || '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const region=a=>`${a.city}/${a.district}`,entrance=r=>r.entrance_name || r.unit || '';
 const names=a=>[a.name,...(a.estates || []),...(a.estate_aliases || '').split(/\n|；|;/).filter(Boolean)];
 const sorted=v=>[...new Set(v)].sort((a,b)=>String(a).localeCompare(String(b),'zh-CN',{numeric:true}));
 let nextId=0;const registry=new Map();
 function render(areas,value={}){
  const id=`address-options-${++nextId}`;registry.set(id,areas);
  const field=(name,label)=>`<div class="field"><label>${label}</label><input name="${name}" list="${id}-${name}" value="${escape(value[name])}" autocomplete="off"><datalist id="${id}-${name}"></datalist></div>`;
  return `<div class="field"><label>城市/区县</label><select name="city_region" data-address-city="${id}" required><option value="">请选择城市/区县</option>${sorted(areas.map(region)).map(text=>`<option ${text===value.city_region?'selected':''}>${escape(text)}</option>`).join('')}</select></div>`+
   `<div class="field"><label>搜索并选定小区</label><input name="estate" list="${id}-estate" required autocomplete="off" placeholder="输入未来海岸、蓝月湾，从候选选定"><datalist id="${id}-estate"></datalist></div>`+
   field('building','楼栋')+field('unit','单元／道路门牌')+field('room','房号')+
   `<div class="field"><label>完整地址候选／同址别名搜索</label><input name="address_lookup" list="${id}-lookup" placeholder="含糊简称须进一步选择入口"><datalist id="${id}-lookup"></datalist></div><div class="field"><label>选择完整门牌（兼容未拆分旧地址）</label><select name="address_choice"><option value="">请先选小区，可再选楼栋缩小范围</option></select></div><input type="hidden" name="address_book_id"><div class="field"><label>确认门牌号</label><input name="door_number" readonly required value="${escape(value.door_number)}"></div>`;
 }
 function resolve(areas,data){
  const candidates=areas.filter(a=>region(a)===data.city_region && names(a).includes(String(data.estate || '').trim()));
  if(candidates.length!==1)throw new Error('请输入关键词并从候选中选定小区');
  const area=candidates[0],rows=area.addresses || [];
  let found=rows.filter(r=>r.building===(data.building || '') && entrance(r)===(data.unit || '') && r.room===(data.room || ''));
  if(data.address_book_id)found=rows.filter(r=>r.id===Number(data.address_book_id) && r.building===(data.building || '') && entrance(r)===(data.unit || '') && r.room===(data.room || ''));
  if(found.length!==1)throw new Error('请选择楼栋、单元／道路门牌和房号，确定唯一地址');
  const row=found[0];
  if(data.door_number && data.door_number!==row.door_number)throw new Error('门牌与所选地址不一致，请重新选择');
  return {service_area_id:area.id,estate:area.name,building:row.building,unit:row.unit,entrance_name:entrance(row),room:row.room,door_number:row.door_number,address_book_id:row.id,service_address_id:row.id};
 }
 document.addEventListener('change',e=>{
  const form=e.target.closest('form');if(!form)return;const city=form.querySelector('[data-address-city]');if(!city)return;
  const id=city.dataset.addressCity,areas=registry.get(id) || [],input=name=>form.querySelector(`[name="${name}"]`),field=e.target.name;
  if(!['city_region','estate','building','unit','room','address_lookup','address_choice'].includes(field))return;
  const clear=keys=>keys.forEach(k=>{if(input(k))input(k).value='';});
  if(field==='city_region')clear(['estate','building','unit','room','door_number','address_book_id','address_lookup']);
  if(field==='estate')clear(['building','unit','room','door_number','address_book_id','address_lookup']);
  if(field==='building')clear(['unit','room','door_number','address_book_id']);
  if(field==='unit')clear(['room','door_number','address_book_id']);
  const selected=areas.filter(a=>region(a)===city.value);
  document.getElementById(`${id}-estate`).innerHTML=selected.flatMap(a=>names(a).map(name=>`<option value="${escape(name)}" label="${escape(a.name)}"></option>`)).join('');
  const area=selected.filter(a=>names(a).includes(input('estate').value));
  const rows=area.length===1?(area[0].addresses || []):[];
  if(area.length===1)input('estate').value=area[0].name;
  const labels=r=>[[r.estate,r.building,entrance(r),r.room].filter(Boolean).join(' / '),...(r.aliases || '').split(/\n|；|;/).filter(Boolean),...(r.search_aliases || '').split(/\n|；|;/).filter(Boolean)];
  const setRow=r=>{input('building').value=r.building;input('unit').value=entrance(r);input('room').value=r.room;input('door_number').value=r.door_number;input('address_book_id').value=r.id;};
  if(field==='address_lookup'){
   clear(['door_number','address_book_id']);const found=rows.filter(r=>labels(r).includes(input('address_lookup').value.trim()));
   if(found.length===1)setRow(found[0]);else clear(['room']);
  }
  if(field==='address_choice'){const row=rows.find(r=>r.id===Number(e.target.value));if(row)setRow(row);else clear(['door_number','address_book_id']);}
  for(const key of ['building','unit','room']){
   const candidates=rows.filter(r=>key==='building' || r.building===input('building').value).filter(r=>key!=='room' || entrance(r)===input('unit').value);
   document.getElementById(`${id}-${key}`).innerHTML=sorted(candidates.map(r=>key==='unit'?entrance(r):r[key])).map(v=>`<option value="${escape(v)}"></option>`).join('');
  }
  const shown=rows.filter(r=>!input('building').value || r.building===input('building').value).filter(r=>!input('unit').value || entrance(r)===input('unit').value);
  input('address_choice').innerHTML='<option value="">请选择完整地址</option>'+shown.map(r=>`<option value="${r.id}">${escape(labels(r)[0])}</option>`).join('');
  document.getElementById(`${id}-lookup`).innerHTML=sorted(rows.flatMap(labels)).map(v=>`<option value="${escape(v)}"></option>`).join('');
  if(field==='room'){
   clear(['door_number','address_book_id']);const found=rows.filter(r=>r.building===input('building').value && entrance(r)===input('unit').value && r.room===input('room').value);
   if(found.length===1)setRow(found[0]);
  }
  if(input('address_book_id').value)input('address_choice').value=input('address_book_id').value;
 });
 globalThis.AddressFields={render,resolve};
})();
