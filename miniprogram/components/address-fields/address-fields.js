const api = require('../../utils/api');

function regionLabel(area) { return `${area.city || ''}/${area.district || ''}`; }
function choices(areas) {
  return areas.flatMap(area => {
    const names = [...new Set([...(area.estates || []), area.name.replace(/社区$|居委会$/, '')])];
    return names.map(name => ({ label: name, area })).concat((area.addresses || []).flatMap(row =>
      (row.aliases || '').split(/\n|；|;/).filter(Boolean).map(alias => ({ label: alias, area, address: row }))));
  });
}

Component({
  properties: { value: { type: Object, value: {}, observer() { this.syncValue(); } } },
  data: { regions: [], regionIndex: -1, neighborhoods: [], areaIndex: -1,
    buildings: [], units: [], rooms: [], building: '', unit: '', room: '', aliases: '',
    regionText: '', estate: '', doorNumber: '', loading: true, error: '' },
  lifetimes: { attached() { this.load(); } },
  methods: {
    async load() {
      try {
        this.areas = await api.get('/api/v1/service-areas/address-catalog');
        this.setData({ regions: [...new Set(this.areas.map(regionLabel))], loading: false, error: '' });
        this.syncValue();
      } catch (e) { this.setData({ loading: false, error: '地址加载失败，请重试' }); }
    },
    syncValue() {
      if (!this.areas) return;
      const v = this.properties.value || {};
      this.selectedAddress = null;
      const area = this.areas.find(item => Number(item.id) === Number(v.service_area_id));
      if (!area) return;
      const text = regionLabel(area);
      this.selectedArea = area;
      const neighborhoods = choices(this.areas.filter(item => regionLabel(item) === text));
      const rows = area.addresses || [];
      const selected = rows.find(row => row.id === (v.address_book_id || v.service_address_id)) || rows.find(row => row.estate === v.estate && row.door_number === v.door_number);
      this.selectedAddress = selected || null;
      this.setData({ building: selected ? selected.building : (v.building || ''), unit: selected ? selected.unit : (v.unit || ''), room: selected ? selected.room : (v.room || ''), aliases: selected ? selected.aliases : '', regionText: text, regionIndex: this.data.regions.indexOf(text), neighborhoods,
        estate: v.estate || '', doorNumber: v.door_number || '',
        areaIndex: neighborhoods.findIndex(item => item.area.id === area.id && item.label === v.estate) });
      this.refreshHierarchy();
    },
    selectRegion(e) {
      const i = Number(e.detail.value), text = this.data.regions[i];
      this.selectedArea = null;
      this.clearHierarchy();
      this.setData({ regionIndex: i, regionText: text, estate: '', areaIndex: -1,
        neighborhoods: choices(this.areas.filter(item => regionLabel(item) === text)) });
      this.emit();
    },
    selectNeighborhood(e) {
      const i = Number(e.detail.value), item = this.data.neighborhoods[i];
      if (!item) return;
      this.selectedArea = item.area;
      this.setData({ areaIndex: i, estate: item.label });
      this.emit();
    },
    inputEstate(e) {
      const estate = e.detail.value;
      const matches = this.data.neighborhoods.filter(item => estate.includes(item.label)).sort((a,b) => b.label.length-a.label.length);
      const top = matches.length ? matches.filter(item => item.label.length === matches[0].label.length) : [];
      const ids = [...new Set(top.map(item => item.area.id))];
      if (ids.length === 1) this.selectedArea = matches[0].area;
      else this.selectedArea = null;
      this.clearHierarchy();
      this.setData({ estate }); this.refreshHierarchy(); this.emit();
    },
    clearHierarchy() {
      this.selectedAddress = null;
      this.setData({ building: '', unit: '', room: '', doorNumber: '', aliases: '', buildings: [], units: [], rooms: [] });
    },
    refreshHierarchy() {
      const rows = ((this.selectedArea || {}).addresses || []).filter(row => row.estate === this.data.estate);
      const unique = key => [...new Set(rows.filter(row => key === 'building' || row.building === this.data.building)
        .filter(row => key !== 'room' || row.unit === this.data.unit).map(row => row[key]))];
      this.setData({ buildings: unique('building'), units: unique('unit'), rooms: unique('room') });
    },
    selectBuilding(e) {
      this.selectedAddress = null;
      this.setData({ building: this.data.buildings[Number(e.detail.value)], unit: '', room: '', doorNumber: '', aliases: '' });
      this.refreshHierarchy(); this.emit();
    },
    selectUnit(e) {
      this.selectedAddress = null;
      this.setData({ unit: this.data.units[Number(e.detail.value)], room: '', doorNumber: '', aliases: '' });
      this.refreshHierarchy(); this.emit();
    },
    selectRoom(e) {
      const room = this.data.rooms[Number(e.detail.value)];
      const row = ((this.selectedArea || {}).addresses || []).find(item => item.estate === this.data.estate && item.building === this.data.building && item.unit === this.data.unit && item.room === room);
      this.selectedAddress = row || null;
      this.setData({ room, doorNumber: row ? row.door_number : '', aliases: row ? row.aliases : '' });
      this.emit();
    },
    inputDoor(e) { this.selectedAddress = null; this.setData({ doorNumber: e.detail.value, aliases: '' }); this.emit(); },
    emit() {
      const area = this.selectedArea;
      this.triggerEvent('change', {
        address_book_id: this.selectedAddress ? this.selectedAddress.id : null,
        building: this.data.building, unit: this.data.unit, room: this.data.room,
        service_area_id: area ? area.id : null, estate: this.data.estate.trim(),
        door_number: this.data.doorNumber.trim(), region_id: area ? area.region_id : null,
        store_id: area ? area.store_id : null, store_name: area ? area.store_name : '',
        city: area ? area.city : '', district: area ? area.district : '',
        address: area ? [area.city, area.district, this.data.estate.trim(), this.data.doorNumber.trim()].join(' ') : '',
      });
    },
  },
});
