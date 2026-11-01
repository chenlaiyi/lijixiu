"""Preview and atomic, repeatable imports into the sole address catalog."""
import hashlib
import json
import re
from collections import Counter,defaultdict
from sqlalchemy import select,update
from ..models.region import Region
from ..models.service_area import ServiceArea
from ..models.store import StoreAddress,CatalogImportBatch
from .address_format import clean,door_number
from .store import _address_identity
from .catalog_files import read_file


def normalize(rows):
    result=[]
    for index,raw in enumerate(rows,2):
        def text(key):
            value=raw.get(key,'')
            if value is None:return ''
            if not isinstance(value,(str,int)):raise ValueError(f'第{index}行：{key}必须是文本')
            return str(value).strip()
        city,county,code,estate=(text(k) for k in ['城市','区县','立即修小区编号','小区名称'])
        external=text('贝壳小区ID')
        if not all([city,county,code,estate]) or any('示例' in x for x in [code,estate]):
            raise ValueError(f'第{index}行：城市、区县、小区编号和名称必填，请替换模板示例')
        if external and code!=external:raise ValueError(f'第{index}行：立即修小区编号应与贝壳小区ID一致')
        for key in ['立即修小区编号','贝壳小区ID','贝壳楼栋ID','贝壳单元ID','房号']:
            if re.search(r'\d[eE][+-]?\d',text(key)):raise ValueError(f'第{index}行：{key}不能使用科学计数法')
        building,room=text('楼栋名称'),text('房号')
        if not building or not room:raise ValueError(f'第{index}行：楼栋和房号不能为空')
        kind=text('房屋类型') or '住宅'
        if kind not in ['住宅','商业']:raise ValueError(f'第{index}行：只导入住宅和商业，车位请另表留存')
        etype=text('入口类型') or '普通单元'
        if etype not in ['普通单元','道路门牌','待确认']:raise ValueError(f'第{index}行：入口类型不正确')
        road=text('道路门牌标准写法') or text('道路门牌原文')
        unit=text('单元名称') or (text('原始单元名称') if etype!='道路门牌' else '')
        if etype=='道路门牌':
            if not road:raise ValueError(f'第{index}行：道路门牌不能为空')
            if re.search(r'\d$',road):road+='号'
            entrance=clean(road);unit=''
            door=entrance+room+('' if room.endswith(('室','号','铺','房')) else '室')
            full=clean(city)+clean(county)+door
        else:
            entrance=clean(unit);road=''
            door=door_number(None,building,unit,room)
            full=clean(city)+clean(county)+clean(estate)+door
        if external and not all(text(k) for k in ['贝壳楼栋ID','贝壳单元ID','贝壳房屋ID']):
            raise ValueError(f'第{index}行：贝壳数据必须保留楼栋、单元和房屋来源ID；人工数据请留空贝壳小区ID')
        house=text('贝壳房屋ID')
        sourcekey=hashlib.sha256(f'beike|{external}|{house}'.encode()).hexdigest() if external else None
        _,canonical,addresscode=_address_identity([city,county,estate,door])
        row=dict(city=clean(city),district=clean(county),community_code=code,source_community_id=external,
            estate=clean(estate),estate_aliases=text('小区别名'),business_circle=text('商圈'),building=clean(building),
            unit=clean(unit),entrance_type=etype,entrance_name=entrance,road_number=clean(road),raw_unit=text('原始单元名称'),
            room=clean(room),door_number=door,full_address=full,aliases=text('同址别名'),search_aliases='',
            source_building_id=text('贝壳楼栋ID'),source_unit_id=text('贝壳单元ID'),source_house_id=house,
            source_key=sourcekey,canonical_key=canonical,address_code=addresscode,property_type=kind,
            verification_status=text('核验状态') or '来源采集，未实地核验',review_required=etype=='待确认',
            detail_hint=text('内部备注'),source_name=text('来源名称') or ('贝壳找房' if external else '人工导入'),
            source_ref=text('来源链接'),collected_at=text('采集时间'),source_record_json=json.dumps(raw,ensure_ascii=False),line=index)
        limits={'community_code':64,'estate':120,'estate_aliases':4000,'business_circle':160,'building':80,'unit':80,
            'room':80,'door_number':240,'full_address':500,'aliases':4000,'detail_hint':300,'source_name':80,
            'source_ref':240,'entrance_name':160,'road_number':160,'raw_unit':160,'source_building_id':100,
            'source_unit_id':100,'source_house_id':160,'verification_status':100,'collected_at':40}
        for key,limit in limits.items():
            if len(row[key])>limit:raise ValueError(f'第{index}行：{key}超过{limit}字')
        result.append(row)
    groups=defaultdict(set)
    for r in result:groups[(r['community_code'],r['building'])].add(r['entrance_name'])
    for r in result:
        if r['entrance_type']=='道路门牌' and len(groups[(r['community_code'],r['building'])])>1:
            # A short building/room label can match several homes. Keep it only for search.
            r['search_aliases']=r['aliases']
            r['aliases']=f"{r['city']}{r['district']}{r['estate']}{r['building']}（{r['road_number']}入口）{r['room']}"+('' if r['room'].endswith(('室','号','铺','房')) else '室')
    return result


async def make_plan(db,filename,content):
    source,file_hash=read_file(filename,content);rows=normalize(source)
    regions=(await db.execute(select(Region))).scalars().all()
    areas=(await db.execute(select(ServiceArea).where(ServiceArea.area_type=='estate'))).scalars().all()
    old=(await db.execute(select(StoreAddress))).scalars().all()
    bysource={r.source_key:r for r in old if r.source_key}
    bycanonical={r.canonical_key:r for r in old if r.canonical_key}
    seen_source=set();seen_location=set();seen_canonical=set();errors=[];operations=[]
    for r in rows:
        cities=[c for c in regions if c.level==1 and clean(c.name)==r['city']]
        counties=[c for c in regions if c.level==2 and clean(c.name)==r['district'] and any(city.id==c.parent_id for city in cities)]
        if len(counties)!=1:
            errors.append(f"第{r['line']}行：城市/区县未创建或存在重名，请先在城市区域列表核实");continue
        r['region_id']=counties[0].id
        area=next((a for a in areas if a.community_code==r['community_code']),None)
        if not area:area=next((a for a in areas if (a.city,a.district,a.name)==(r['city'],r['district'],r['estate'])),None)
        if area and ((area.city,area.district,area.name)!=(r['city'],r['district'],r['estate']) or (area.community_code and area.community_code!=r['community_code'])):
            errors.append(f"第{r['line']}行：小区编号与已有小区信息冲突");continue
        r['area_id']=area.id if area else None
        loc=(r['community_code'],r['building'],r['entrance_name'],r['room'])
        if loc in seen_location or r['canonical_key'] in seen_canonical or (r['source_key'] and r['source_key'] in seen_source):
            errors.append(f"第{r['line']}行：文件内重复的来源房屋ID或完整地址层级");continue
        seen_location.add(loc);seen_source.add(r['source_key']);seen_canonical.add(r['canonical_key'])
        existing=bysource.get(r['source_key']) if r['source_key'] else None
        if existing:
            if (existing.city,existing.district,existing.estate,existing.building,existing.entrance_name or existing.unit,existing.room)!=(r['city'],r['district'],r['estate'],r['building'],r['entrance_name'],r['room']):
                errors.append(f"第{r['line']}行：来源ID对应的地址已变化，需人工核对，不自动覆盖")
            else:operations.append(('skip',existing,r))
            continue
        existing=bycanonical.get(r['canonical_key'])
        if not existing:
            same=[a for a in old if (a.city,a.district,a.estate,a.building,a.entrance_name or a.unit,a.room)==
                (r['city'],r['district'],r['estate'],r['building'],r['entrance_name'],r['room'])]
            if same:
                errors.append(f"第{r['line']}行：已有相同房屋层级但门牌写法不同，请先核对同址关系");continue
        if existing:
            if existing.source_key and existing.source_key!=r['source_key']:
                errors.append(f"第{r['line']}行：同一地址对应不同来源房屋ID")
            elif (existing.building,existing.unit,existing.room)!=(r['building'],r['unit'],r['room']):
                errors.append(f"第{r['line']}行：已有门牌结构不一致，需人工核对")
            else:operations.append(('link',existing,r))
        else:operations.append(('create',None,r))
    # Inconsistent metadata within a file must not create duplicate estates on apply.
    metadata=defaultdict(set)
    for r in rows:metadata[r['community_code']].add((r['city'],r['district'],r['estate']))
    for code,values in metadata.items():
        if len(values)>1:errors.append(f'小区编号{code}在文件内对应多个小区名称或区域')
    reverse=defaultdict(set)
    for r in rows:reverse[(r['city'],r['district'],r['estate'])].add(r['community_code'])
    if any(len(values)>1 for values in reverse.values()):errors.append('同一小区在文件内使用了多个小区编号，请先核对')
    counts=Counter(op for op,_,_ in operations)
    report=dict(file_hash=file_hash,total=len(rows),created=counts['create'],skipped=counts['skip'],linked=counts['link'],
        pending_review=sum(r['review_required'] for r in rows),residential=sum(r['property_type']=='住宅' for r in rows),
        commercial=sum(r['property_type']=='商业' for r in rows),alias_qualified=sum(bool(r['search_aliases']) for r in rows),
        errors=errors[:30],error_count=len(errors),can_apply=not errors,
        samples=[{k:r[k] for k in ['community_code','estate','building','entrance_name','room','full_address','review_required']} for r in rows[:3]],
        message='仅导入总库，不分配门店；重复导入跳过已有记录，不覆盖人工修改或恢复停用地址。待确认记录暂不可下单。')
    return report,operations


async def apply_plan(db,filename,content,operator_id,expected_hash):
    # Serialize imports before checking source IDs, including imports by other admins.
    await db.execute(update(Region).values(name=Region.name))
    report,operations=await make_plan(db,filename,content)
    if report['file_hash']!=expected_hash:raise ValueError('文件已变化，请重新预览后导入')
    if not report['can_apply']:raise ValueError('导入校验失败：'+'；'.join(report['errors'][:3]))
    from .address_catalog import estate_area
    areas={}
    for op,existing,r in operations:
        if op=='skip':continue
        code=r['community_code']
        if code not in areas:
            area=await db.get(ServiceArea,r['area_id']) if r['area_id'] else await estate_area(db,r['region_id'],r['estate'])
            area.community_code=code;area.source_community_id=r['source_community_id']
            area.estate_aliases=r['estate_aliases'];area.business_circle=r['business_circle'];areas[code]=area
        area=areas[code]
        if op=='link':
            # Enrich provenance only. Keep manual notes, status, aliases and historical identity.
            for key in ['source_key','source_building_id','source_unit_id','source_house_id','raw_unit','collected_at','source_record_json']:
                setattr(existing,key,r[key])
            continue
        fields={k:v for k,v in r.items() if k not in ['community_code','source_community_id','estate_aliases','business_circle','area_id','line']}
        db.add(StoreAddress(**fields,service_area_id=area.id,province=area.province,street='',community=area.name,
            created_by_user_id=operator_id,store_id=None,catalog_published=True,enabled=True))
    batch=CatalogImportBatch(operator_id=operator_id,filename=filename[:240],file_hash=report['file_hash'],report_json=json.dumps(report,ensure_ascii=False))
    db.add(batch);await db.flush();report['batch_id']=batch.id
    await db.commit()
    return report
