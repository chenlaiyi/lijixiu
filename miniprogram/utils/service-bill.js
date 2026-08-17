function asNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatQuantity(value) {
  const number = asNumber(value, 1);
  return Number.isInteger(number) ? String(number) : number.toFixed(2);
}

function parseItems(bill) {
  if (!bill || !bill.items_json) return [];
  try {
    const items = JSON.parse(bill.items_json);
    if (!Array.isArray(items)) return [];
    return items.map((item) => {
      const quantity = asNumber(item.quantity ?? item.qty, 1);
      const unitPrice = asNumber(item.unit_price ?? item.price, 0);
      const subtotal = asNumber(
        item.subtotal ?? item.amount,
        quantity * unitPrice,
      );
      return {
        ...item,
        quantity,
        unitPrice,
        subtotal,
        qtyText: formatQuantity(quantity),
        priceText: unitPrice.toFixed(2),
        amountText: subtotal.toFixed(2),
        remarkText: item.remark || '',
      };
    });
  } catch (e) {
    return [];
  }
}

module.exports = {
  parseItems,
};
