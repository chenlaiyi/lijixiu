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
      <div class="field"><label>小区</label><input name="estate" list="${id}" maxlength="160" required value="${escape(value.estate)}" placeholder="例如：未来海岸-蓝月湾一期" /><datalist id="${id}"></datalist></div>
      <div class="field"><label>门牌号</label><input name="door_number" maxlength="240" required value="${escape(value.door_number)}" placeholder="例如：嵩屿北五里23号2101室" /></div>`;
  }
  function resolve(areas, data) {
    const estate = String(data.estate || '').trim();
    const candidates = areas.filter(area => region(area) === data.city_region)
      .map(area => ({ area, score: Math.max(0, ...names(area).map(name => estate.includes(name) ? name.length : 0)) }))
      .filter(item => item.score > 0).sort((a,b) => b.score - a.score);
    if (!candidates.length || candidates[1] && candidates[1].score === candidates[0].score) {
      throw new Error('请选择城市/区域，并从候选小区中选择后补充名称');
    }
    if (!String(data.door_number || '').trim()) throw new Error('请填写门牌号');
    return { service_area_id: candidates[0].area.id, estate, door_number: data.door_number.trim() };
  }
  document.addEventListener('change', e => {
    const id = e.target.dataset && e.target.dataset.addressCity;
    if (!id) return;
    const areas = registry.get(id) || [];
    const datalist = document.getElementById(id);
    datalist.innerHTML = [...new Set(areas.filter(area => region(area) === e.target.value).flatMap(names))]
      .map(name => `<option value="${escape(name)}"></option>`).join('');
  });
  globalThis.AddressFields = { render, resolve };
})();
