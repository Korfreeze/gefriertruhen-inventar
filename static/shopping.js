let shoppingEntries = [];
let shoppingChannel = null;

async function loadShopping() {
  if (!session) return;
  try {
    shoppingEntries = await api('/shopping-list');
    renderShopping();
    const openCount = shoppingEntries.filter(entry => !entry.checked).length;
    $('shopping-count').textContent = openCount ? `(${openCount})` : '';
  } catch (error) { msg(error.message); }
}

function subscribeShopping() {
  if (shoppingChannel) return;
  shoppingChannel = sb.channel('shopping-list-live')
    .on('postgres_changes', {event: '*', schema: 'public', table: 'shopping_list'}, loadShopping)
    .subscribe();
}

function renderShopping() {
  $('shopping-items').innerHTML = '';
  if (!shoppingEntries.length) {
    $('shopping-items').innerHTML = '<div class="empty-state">Die Einkaufsliste ist noch leer.</div>';
    return;
  }
  for (const entry of shoppingEntries) {
    const node = $('shopping-template').content.cloneNode(true);
    const article = node.querySelector('.shopping-item');
    article.classList.toggle('checked', entry.checked);
    node.querySelector('h3').textContent = entry.name;
    node.querySelector('small').textContent = entry.unit;
    const check = node.querySelector('.shopping-check');
    check.checked = entry.checked;
    check.onchange = () => updateShopping(entry.id, {checked: check.checked});
    const amount = node.querySelector('.shopping-amount');
    amount.value = Number(entry.quantity);
    amount.onchange = () => updateShopping(entry.id, {quantity: Math.max(0, Number(amount.value))});
    node.querySelector('.shopping-delete').onclick = () => deleteShopping(entry);
    $('shopping-items').append(node);
  }
}

async function updateShopping(id, changes) {
  try {
    await api(`/shopping-list/${id}`, {method: 'PATCH', body: JSON.stringify(changes)});
    await loadShopping();
  } catch (error) { msg(error.message); }
}

async function deleteShopping(entry) {
  if (!confirm(`„${entry.name}“ von der Einkaufsliste löschen?`)) return;
  try {
    await api(`/shopping-list/${entry.id}`, {method: 'DELETE'});
    await loadShopping();
  } catch (error) { msg(error.message); }
}

async function addShoppingEntry(data) {
  try {
    shoppingEntries = await api('/shopping-list');
    const existing = shoppingEntries.find(entry => !entry.checked && (
      (data.source_item_id && entry.source_item_id === data.source_item_id) ||
      (entry.name.toLowerCase() === data.name.toLowerCase() && entry.unit === data.unit)
    ));
    if (existing) {
      await api(`/shopping-list/${existing.id}`, {
        method: 'PATCH',
        body: JSON.stringify({quantity: Number(existing.quantity) + Number(data.quantity)})
      });
    } else {
      await api('/shopping-list', {method: 'POST', body: JSON.stringify(data)});
    }
    await loadShopping();
    msg(`${data.name} wurde zur Einkaufsliste hinzugefügt.`);
  } catch (error) { msg(error.message); }
}

function addItemToShopping(item) {
  return addShoppingEntry({name: item.name, quantity: 1, unit: item.unit, source_item_id: item.id});
}

function showShoppingView() {
  show('inventory-view', false);
  show('shopping-view');
  $('inventory-tab').classList.add('secondary');
  $('shopping-tab').classList.remove('secondary');
  loadShopping();
  subscribeShopping();
}

function showInventoryView() {
  show('shopping-view', false);
  show('inventory-view');
  $('shopping-tab').classList.add('secondary');
  $('inventory-tab').classList.remove('secondary');
}

$('shopping-tab').onclick = showShoppingView;
$('inventory-tab').onclick = showInventoryView;
$('shopping-form').onsubmit = async event => {
  event.preventDefault();
  await addShoppingEntry({
    name: $('shopping-name').value.trim(),
    quantity: Number($('shopping-quantity').value),
    unit: $('shopping-unit').value
  });
  event.target.reset();
  $('shopping-quantity').value = 1;
};

setTimeout(() => { if (session) loadShopping(); }, 0);

