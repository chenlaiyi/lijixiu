const api = require('../../utils/api');

function regionLabel(area) { return `${area.city || ''}/${area.district || ''}`; }
function choices(areas) {
  return areas.flatMap(area => {
    const names = [...new Set([...(area.estates || []), area.name.replace(/社区$|居委会$/, '')])];
    return names.map(name => ({ label: name, area }));
  });
}

Component({
  properties: { value: { type: Object, value: {}, observer() { this.syncValue(); } } },
  data: { regions: [], regionIndex: -1, neighborhoods: [], areaIndex: -1,
    regionText: '', estate: '', doorNumber: '', loading: true, error: '' },
  lifetimes: { attached() { this.load(); } },
  methods: {
    async load() {
      try {
        this.areas = await api.get('/api/v1/service-areas/public-options');
        this.setData({ regions: [...new Set(this.areas.map(regionLabel))], loading: false, error: '' });
        this.syncValue();
      } catch (e) { this.setData({ loading: false, error: '地址加载失败，请重试' }); }
    },
    syncValue() {
      if (!this.areas) return;
      const v = this.properties.value || {};
      const area = this.areas.find(item => Number(item.id) === Number(v.service_area_id));
      if (!area) return;
      const text = regionLabel(area);
      this.selectedArea = area;
      const neighborhoods = choices(this.areas.filter(item => regionLabel(item) === text));
      this.setData({ regionText: text, regionIndex: this.data.regions.indexOf(text), neighborhoods,
        estate: v.estate || '', doorNumber: v.door_number || '',
        areaIndex: neighborhoods.findIndex(item => item.area.id === area.id && item.label === v.estate) });
    },
    selectRegion(e) {
      const i = Number(e.detail.value), text = this.data.regions[i];
      this.selectedArea = null;
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
      this.setData({ estate }); this.emit();
    },
    inputDoor(e) { this.setData({ doorNumber: e.detail.value }); this.emit(); },
    emit() {
      const area = this.selectedArea;
      this.triggerEvent('change', {
        service_area_id: area ? area.id : null, estate: this.data.estate.trim(),
        door_number: this.data.doorNumber.trim(), region_id: area ? area.region_id : null,
        store_id: area ? area.store_id : null, store_name: area ? area.store_name : '',
        city: area ? area.city : '', district: area ? area.district : '',
        address: area ? [area.city, area.district, this.data.estate.trim(), this.data.doorNumber.trim()].join(' ') : '',
      });
    },
  },
});
