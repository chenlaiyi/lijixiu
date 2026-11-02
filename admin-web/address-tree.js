/* Catalog navigation and allocation share the same estate/type/entrance hierarchy. */
(() => {
 const types=['住宅','商业','车位'];
 const entrance=r=>r.entrance_name || r.unit || '';
 const order=(a,b)=>String(a).localeCompare(String(b),'zh-CN',{numeric:true});
 const key=r=>`${r.service_area_id}|${r.city}|${r.district}|${r.estate}`;
 function group(rows){
  const estates=new Map();
  for(const row of rows){
   const id=key(row);if(!estates.has(id))estates.set(id,{key:id,id:row.service_area_id,name:row.estate,code:row.community_code,city:row.city,district:row.district,rows:[],categories:types.map(type=>({type,groups:[],rows:[]}))});
   const estate=estates.get(id),type=row.property_type || '住宅',category=estate.categories.find(c=>c.type===type);if(!category)continue;
   estate.rows.push(row);category.rows.push(row);
   const entry=entrance(row),road=row.entrance_type==='道路门牌' || Boolean(row.road_number) || (/号$/.test(entry) && !/单元$/.test(entry));
   const scopeEntrance=road?entry:null;
   let node=category.groups.find(g=>g.building===row.building && g.entrance===scopeEntrance);
   if(!node){node={key:`${id}|${type}|${row.building}|${scopeEntrance || ''}`,estateId:estate.id,type,building:row.building,entrance:scopeEntrance,rows:[]};category.groups.push(node);}
   node.rows.push(row);
  }
  const result=[...estates.values()].sort((a,b)=>order(a.city+a.district+a.name,b.city+b.district+b.name));
  for(const estate of result)for(const c of estate.categories){c.groups.sort((a,b)=>order(a.building+a.entrance,b.building+b.entrance));for(const g of c.groups)g.rows.sort((a,b)=>order(a.room,b.room));}
  return result;
 }
 function matches(rule,row){return rule.service_area_id===row.service_area_id && (!rule.property_type || rule.property_type===(row.property_type || '住宅')) &&
  (rule.address_id?rule.address_id===row.id:(rule.building==null || rule.building===row.building) && (rule.entrance_name==null || rule.entrance_name===entrance(row)));}
 function covers(rule,node){return !rule.address_id && rule.service_area_id===node.estateId && (!rule.property_type || rule.property_type===node.type) &&
  (rule.building==null || rule.building===node.building) && (rule.entrance_name==null || rule.entrance_name===node.entrance);}
 function editor(rows,rules,others=[]){
  const tree=group(rows.filter(r=>r.enabled));let id=0;const nodes=new Map();
  for(const estate of tree){
   estate.dirty=false;estate.original=rules.filter(r=>r.service_area_id===estate.id);
   for(const category of estate.categories){
    category.wide=estate.original.some(r=>!r.address_id && r.building==null && r.entrance_name==null && (!r.property_type || r.property_type===category.type));
    for(const node of category.groups){
     node.id=String(++id);node.blocked=others.some(r=>covers(r,node) || node.rows.some(row=>matches(r,row)));
     node.ownerNames=[...new Set(others.filter(r=>covers(r,node) || node.rows.some(row=>matches(r,row))).map(r=>r.store_name || '其他门店'))].join('、');
     node.selected=estate.original.some(r=>covers(r,node));
     node.partial=!node.selected && estate.original.some(r=>node.rows.some(row=>matches(r,row)));
     node.original=estate.original.filter(r=>node.rows.some(row=>matches(r,row)));
     node.touched=false;node.category=category;node.estate=estate;nodes.set(node.id,node);
    }
    // Defaults apply to a new unassigned estate draft only; persisted scopes always win.
    if(!estate.original.length){category.wide=category.type!=='车位';for(const node of category.groups)node.selected=category.wide && !node.blocked;estate.dirty=true;}
   }
  }
  function toggle(nodeIds,checked,level){
   for(const nodeId of nodeIds){const node=nodes.get(String(nodeId));if(!node || (node.blocked && checked))continue;node.selected=checked;node.partial=false;node.touched=true;node.estate.dirty=true;node.category.wide=level!=='group' && checked;}
  }
  function items(){
   const result=[];
   for(const estate of tree){
    if(!estate.dirty){result.push(...estate.original);continue;}
    for(const category of estate.categories){
     const leaves=category.groups;
     if(leaves.length && category.wide && leaves.every(n=>n.selected && !n.blocked)){
      result.push({service_area_id:estate.id,property_type:category.type,building:null,entrance_name:null,address_id:null});continue;
     }
     for(const node of leaves){
      if(node.selected && !node.blocked)result.push({service_area_id:estate.id,property_type:category.type,building:node.building,entrance_name:node.entrance,address_id:null});
      else if(node.partial && !node.touched)result.push(...node.original);
     }
    }
    // Retain legacy references not represented by active catalog rows until explicitly removed.
    for(const rule of estate.original.filter(r=>r.address_id))if(!estate.rows.some(r=>r.id===rule.address_id))result.push(rule);
   }
   result.push(...rules.filter(r=>!tree.some(e=>e.id===r.service_area_id)));
   return [...new Map(result.map(r=>[JSON.stringify([r.service_area_id,r.property_type || null,r.building,r.entrance_name,r.address_id]),r])).values()];
  }
  return {tree,nodes,toggle,items};
 }
 globalThis.AddressTree={types,group,editor,matches,entrance};
})();
