let barcodeScanner = null;

async function lookupBarcode(code = $('barcode').value) {
  code = code.replace(/\D/g, '');
  $('barcode').value = code;
  if (!code) return msg('Bitte zuerst einen Barcode scannen oder eingeben.');
  try {
    const product = await api(`/products/${code}`);
    if (!product.found) return msg('Produkt nicht gefunden. Du kannst den Namen manuell eintragen.');
    if (product.name) $('name').value = product.name;
    if (product.category && !$('category').value) $('category').value = product.category;
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
      async decodedText => { await closeScanner(); await lookupBarcode(decodedText); }
    );
  } catch (error) {
    await closeScanner();
    msg('Kamera konnte nicht gestartet werden. Bitte Kamerazugriff erlauben oder den Barcode eingeben.');
  }
}

$('scan-barcode').onclick = openScanner;
$('lookup-barcode').onclick = () => lookupBarcode();
$('close-scanner').onclick = closeScanner;
