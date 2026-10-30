/* Shared vocabulary and service-area resolution for web address forms. */
(() => {
  const escape = value => String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const region = area => `${area.city}/${area.district}`;
  const names = area => [...new Set([...(area.estates || []), area.name.replace(/社区$|居委会$/, '')])];
  let nextId = 0;
  const registry = new Map();
  function render(areas, value = {}) {
    const id = `address-options-${++nextId}`;
    registry.set(id, areas);
    const regions = [...new Set(areas.map(region))];
    return `<div class="field"><label>城市/区域</label><select name="city_region" data-address-city="${id}" required><option value="">请选择城市/区域</option>${regions.map(text => `<option value="${escape(text)}" ${text === value.city_region ? 'selected' : ''}>${escape(text)}</option>`).join('')}</select></div>
      <div class="field"><label>搜索标准地址 / 同址别名</label><input name="address_lookup" list="${id}-addresses" placeholder="先选城市区域，再搜索小区、楼栋或其他写法"/><datalist id="${id}-addresses"></datalist></div>
      <div class="field"><label>小区</label><input name="estate" list="${id}" maxlength="160" required value="${escape(value.estate)}" placeholder="例如：未来海岸-蓝月湾一期" /><datalist id="${id}"></datalist></div>
      <div class="field"><label>楼栋</label><input name="building" data-address-part="building" list="${id}-building" value="${escape(value.building)}" placeholder="例如：S5栋"/><datalist id="${id}-building"></datalist></div>
      <div class="field"><label>单元（无则留空）</label><input name="unit" data-address-part="unit" list="${id}-unit" value="${escape(value.unit)}"/><datalist id="${id}-unit"></datalist></div>
      <div class="field"><label>房号</label><input name="room" data-address-part="room" list="${id}-room" value="${escape(value.room)}" placeholder="例如：2605"/><datalist id="${id}-room"></datalist></div>
      <div class="field"><label>门牌号 / 标准写法</label><input name="door_number" maxlength="240" required value="${escape(value.door_number)}" placeholder="例如：嵩屿北五里23号2101室" /></div>`;
  }
  function resolve(areas, data) {
    const estate = String(data.estate || '').trim();
    const candidates = areas.filter(area => region(area) === data.city_region)
      .map(area => ({ area, score: Math.max(0, ...names(area).map(name => estate.includes(name) ? name.length : 0)) }))
      .filter(item => item.score > 0).sort((a,b) => b.score - a.score);
    if (!candidates.length || candidates[1] && candidates[1].score === candidates[0].score) {
      throw new Error('请选择城市/区域，并从候选小区中选择后补充名称');
    }
    const area = candidates[0].area;
    const row = (area.addresses || []).find(item => item.estate === estate && item.building === (data.building || '') && item.unit === (data.unit || '') && item.room === (data.room || '') && (!data.door_number || item.door_number === data.door_number));
    const door = String(data.door_number || (row && row.door_number) || [data.building, data.unit, data.room && `${data.room}室`].filter(Boolean).join('')).trim();
    if (!door) throw new Error('请填写门牌号或选择楼栋、单元、房号');
    return { service_area_id: area.id, estate, door_number: door, building: data.building || '', unit: data.unit || '', room: data.room || '', address_book_id: row ? row.id : null, service_address_id: row ? row.id : null };

  }
  document.addEventListener('change', e => {
    const form = e.target.closest('form');
    if (!form) return;
    const city = form.querySelector('[data-address-city]');
    if (!city) return;
    const id = city.dataset.addressCity, areas = registry.get(id) || [];
    const input = name => form.querySelector(`[name="${name}"]`);
    const field = e.target.name;
    if (!['city_region','address_lookup','estate','building','unit','room'].includes(field)) return;
    const clear = names => names.forEach(name => { if (input(name)) input(name).value = ''; });
    if (field === 'city_region') clear(['estate','building','unit','room','door_number']);
    if (field === 'estate') clear(['building','unit','room','door_number']);
    if (field === 'building') clear(['unit','room','door_number']);
    if (field === 'unit') clear(['room','door_number']);
    const selected = areas.filter(area => region(area) === city.value);
    const addressRows = selected.flatMap(area => area.addresses || []);
    const labels = row => [[row.estate,row.building,row.unit,row.room].filter(Boolean).join(' '), ...(row.aliases || '').split(/\n|；|;/).filter(Boolean)];
    document.getElementById(`${id}-addresses`).innerHTML = [...new Set(addressRows.flatMap(labels))].map(value => `<option value="${escape(value)}"></option>`).join('');
    if (field === 'address_lookup') {
      const matches = addressRows.filter(row => labels(row).includes(e.target.value.trim()));
      if (matches.length === 1) for (const key of ['estate','building','unit','room','door_number']) input(key).value = matches[0][key] || '';
    }
    document.getElementById(id).innerHTML = [...new Set(selected.flatMap(names))].map(name => `<option value="${escape(name)}"></option>`).join('');
    const rows = selected.flatMap(area => area.addresses || []).filter(row => row.estate === input('estate').value);
    for (const key of ['building','unit','room']) {
      const options = rows.filter(row => key === 'building' || row.building === input('building').value).filter(row => key !== 'room' || row.unit === input('unit').value);
      document.getElementById(`${id}-${key}`).innerHTML = [...new Set(options.map(row => row[key]))].map(value => `<option value="${escape(value)}"></option>`).join('');
    }
    const row = rows.find(row => row.building === input('building').value && row.unit === input('unit').value && row.room === input('room').value);
    if (row && field === 'room') input('door_number').value = row.door_number;
  });
  globalThis.AddressFields = { render, resolve };
})();
