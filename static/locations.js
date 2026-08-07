function renderLocationManager() {
  const manager = $('location-manager');
  manager.innerHTML = '';
  const ordered = [...locations].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  if (!ordered.length) {
    manager.innerHTML = '<div class="empty-state">Noch keine Fächer angelegt.</div>';
    return;
  }
  ordered.forEach((location, index) => {
    const node = $('location-template').content.cloneNode(true);
    const input = node.querySelector('.location-edit');
    input.value = location.name;
    const count = items.filter(item => item.location_id === location.id).length;
    node.querySelector('small').textContent = `${count} ${count === 1 ? 'Lebensmittel' : 'Lebensmittel'}`;
    const up = node.querySelector('.location-up');
    const down = node.querySelector('.location-down');
    up.disabled = index === 0;
    down.disabled = index === ordered.length - 1;
    up.onclick = () => moveLocation(ordered, index, -1);
    down.onclick = () => moveLocation(ordered, index, 1);
    node.querySelector('.location-save').onclick = () => renameLocation(location, input.value);
    node.querySelector('.location-delete').onclick = () => removeLocation(location, count);
    manager.append(node);
  });
}

async function renameLocation(location, name) {
  name = name.trim();
  if (!name) return msg('Der Fachname darf nicht leer sein.');
  try {
    await api(`/locations/${location.id}`, {method: 'PATCH', body: JSON.stringify({name})});
    await selectFreezer();
    renderLocationManager();
    msg('Fach wurde umbenannt.');
  } catch (error) { msg(error.message); }
}

async function moveLocation(ordered, index, direction) {
  const target = index + direction;
  if (target < 0 || target >= ordered.length) return;
  [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
  try {
    await Promise.all(ordered.map((location, position) => api(`/locations/${location.id}`, {
      method: 'PATCH', body: JSON.stringify({sort_order: position})
    })));
    await selectFreezer();
    renderLocationManager();
  } catch (error) { msg(error.message); }
}

async function removeLocation(location, count) {
  const detail = count ? ` ${count} enthaltene Lebensmittel werden auf „Ohne Fach“ gesetzt.` : '';
  if (!confirm(`Fach „${location.name}“ wirklich löschen?${detail}`)) return;
  try {
    await api(`/locations/${location.id}`, {method: 'DELETE'});
    await selectFreezer();
    renderLocationManager();
    msg('Fach wurde gelöscht. Die Lebensmittel bleiben erhalten.');
  } catch (error) { msg(error.message); }
}

$('show-location').onclick = () => { show('location-form'); renderLocationManager(); };
$('location-form').addEventListener('submit', () => {
  setTimeout(async () => { await selectFreezer(); renderLocationManager(); }, 600);
});

