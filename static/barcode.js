let barcodeScanner = null;
let barcodeIsProcessing = false;

function existingBarcodeItem(code) {
  return items.find(item => String(item.barcode || '') === code);
}

async function addQuantityToExisting(item, amount) {
  const newQuantity = Number(item.quantity) + Number(amount);
  await api(`/items/${item.id}`, {
    method: 'PATCH',
    body: JSON.stringify({quantity: newQuantity})
  });
  await selectFreezer();
  resetItemForm();
  show('item-form', false);
  msg(`${item.name}: Menge wurde auf ${newQuantity.toLocaleString('de-DE')} ${item.unit} erhöht.`);
}

async function lookupBarcode(code = $('barcode').value, quickAdd = false) {
  code = code.replace(/\D/g, '');
  $('barcode').value = code;
  if (!code) return msg('Bitte zuerst einen Barcode scannen oder eingeben.');
  try {
    const existing = existingBarcodeItem(code);
    if (quickAdd && existing) {
      await addQuantityToExisting(existing, 1);
      return;
    }
    const product = await api(`/products/${code}`);
    if (!product.found) return msg('Produkt nicht gefunden. Du kannst den Namen manuell eintragen.');
    if (product.name) $('name').value = product.name;
    if (product.category && !$('category').value) $('category').value = product.category;
    if (product.image_url) currentImageUrl = product.image_url;
    show('notice', false);
  } catch (error) { msg(error.message); }
}

async function closeScanner() {
  if (barcodeScanner?.isScanning) await barcodeScanner.stop();
  barcodeScanner = null;
  $('reader').innerHTML = '';
  show('scanner', false);
}

async function openScanner() {
  show('scanner');
  $('scanner').scrollIntoView({behavior: 'smooth', block: 'start'});
  try {
    barcodeScanner = new Html5Qrcode('reader');
    await barcodeScanner.start(
      {facingMode: 'environment'},
      {fps: 10, qrbox: {width: 280, height: 140}, formatsToSupport: [Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.UPC_A, Html5QrcodeSupportedFormats.UPC_E]},
      async decodedText => {
        if (barcodeIsProcessing) return;
        barcodeIsProcessing = true;
        await closeScanner();
        await lookupBarcode(decodedText, true);
        barcodeIsProcessing = false;
      }
    );
  } catch (error) {
    await closeScanner();
    msg('Kamera konnte nicht gestartet werden. Bitte Kamerazugriff erlauben oder den Barcode eingeben.');
  }
}

$('scan-barcode').onclick = openScanner;
$('lookup-barcode').onclick = () => lookupBarcode();
$('close-scanner').onclick = closeScanner;

$('item-form').addEventListener('submit', async event => {
  if (editingId) return;
  const code = $('barcode').value.replace(/\D/g, '');
  const existing = existingBarcodeItem(code);
  if (!code || !existing) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  try {
    await addQuantityToExisting(existing, Number($('quantity').value));
  } catch (error) { msg(error.message); }
}, true);
