function orderStatusTone(status) {
  if (['completed', 'store_reviewed'].includes(status)) return 'tone-success';
  if (['cancelled', 'bill_returned'].includes(status)) return 'tone-danger';
  if (['wait_payment', 'bill_submitted'].includes(status)) return 'tone-warning';
  if (['paid', 'paid_pending_review'].includes(status)) return 'tone-action';
  if (['servicing', 'repairer_accepted', 'accepted'].includes(status)) return 'tone-progress';
  if (['created', 'store_pending', 'store_accepted', 'assigned', 'dispatched'].includes(status)) return 'tone-waiting';
  return 'tone-neutral';
}

function financeStatusTone(status) {
  const value = String(status || '').toLowerCase();
  if (['paid', 'settled', 'completed', 'success', 'approved'].includes(value)) return 'tone-success';
  if (['rejected', 'failed', 'cancelled', 'canceled'].includes(value)) return 'tone-danger';
  if (['pending', 'waiting', 'wait', 'reviewing', 'processing'].includes(value)) return 'tone-warning';
  return 'tone-action';
}

function resourceStatusTone(status) {
  const value = String(status || '').toLowerCase();
  if (['active', 'online', 'open', 'enabled', 'normal', '营业中'].includes(value)) return 'tone-success';
  if (['pending', 'reviewing', '待审核'].includes(value)) return 'tone-warning';
  if (['inactive', 'offline', 'closed', 'disabled', '停用', '关闭'].includes(value)) return 'tone-neutral';
  return 'tone-action';
}

module.exports = {
  orderStatusTone,
  financeStatusTone,
  resourceStatusTone,
};
