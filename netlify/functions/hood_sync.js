const axios = require('axios');
const csv = require('csv-parse/sync');
const crypto = require('crypto');
const fs = require('fs');

// Hilfsfunktion zum Loggen in Datei
function logToFile(message) {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] ${message}\n`;
  fs.appendFileSync('/tmp/hood_sync_debug.log', logMessage);
  console.log(message);
}

class HoodAPI {
  constructor() {
    // Konfiguration aus Umgebungsvariablen
    this.feedUrl = process.env.FEED_URL || 'https://taschenparadies.de/store-api/product-export/SWPEDTVIYVJKCZK2WFO4YJZKOQ/hood';
    this.password = process.env.HOOD_PASSWORD || 'SWPEDTVIYVJKCZK2WFO4YJZKOQ';
    this.accountName = process.env.ACCOUNT_NAME || 'TaschenParadies';
    this.endpoint = process.env.HOOD_ENDPOINT || 'https://www.hood.de/api.htm';
    
    console.log('HoodAPI initialisiert mit:', {
      accountName: this.accountName,
      feedUrl: this.feedUrl,
      endpoint: this.endpoint
    });
  }

  // Hash das Passwort für Hood API
  hashPassword(password) {
    return crypto.createHash('md5').update(password).digest('hex');
  }

  escapeXml(text) {
    if (!text) return '';
    return text.toString()
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\\\"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  // Kategorie-Mapping von Shopware zu Hood.de
  mapCategory(category) {
    const categoryLower = category.toLowerCase();
    
    // Hood.de Kategorie-IDs für Taschen
    if (categoryLower.includes('rucksack') || categoryLower.includes('backpack')) {
      return '23029'; // Rucksäcke
    } else if (categoryLower.includes('sport') || categoryLower.includes('fitness')) {
      return '23030'; // Sporttaschen
    } else if (categoryLower.includes('umhängetasche') || categoryLower.includes('messenger')) {
      return '23026'; // Messenger-Bags & Umhängetaschen
    } else if (categoryLower.includes('schultertasche')) {
      return '23033'; // Schultertaschen
    } else if (categoryLower.includes('henkeltasche')) {
      return '23034'; // Henkeltaschen
    } else if (categoryLower.includes('abendtasche') || categoryLower.includes('clutch')) {
      return '23035'; // Abendtaschen
    } else if (categoryLower.includes('gürteltasche')) {
      return '23025'; // Gürteltaschen
    } else if (categoryLower.includes('handytasche')) {
      return '23032'; // Handytaschen
    } else if (categoryLower.includes('kosmetik') || categoryLower.includes('beutel')) {
      return '23031'; // Kosmetikbeutel
    } else if (categoryLower.includes('akten') || categoryLower.includes('notebook')) {
      return '23027'; // Akten- & Notebooktaschen
    } else if (categoryLower.includes('tragetasche')) {
      return '23028'; // Tragetaschen
    } else {
      return '23036'; // Sonstige Taschen
    }
  }

  async getExistingItems() {
    try {
      const hashedPassword = this.hashPassword(this.password);
      console.log('🔐 Verwende gehashtes Passwort für Hood API');
      
      const xml = `<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0.1" user="${this.accountName}" password="${hashedPassword}">
    <function>itemList</function>
    <accountName>${this.accountName}</accountName>
    <accountPass>${hashedPassword}</accountPass>
</api>`;

      console.log('📤 Sende Request an Hood API:', this.endpoint);
      console.log('🔑 Account:', this.accountName);
      
      const response = await axios.post(this.endpoint, xml, {
        headers: {
          'Content-Type': 'text/xml'
        }
      });
      
      console.log('📥 Hood API Antwort Status:', response.status);
      console.log('📄 Hood API Antwort Body:', response.data);
      
      if (response.data.includes('<status>error</status>') || response.data.includes('<error>')) {
        console.log('❌ Hood API Fehler:', response.data);
        return [];
      }
      
      // Parse XML response to extract items
      const items = [];
      const itemMatches = response.data.match(/<item>(.*?)<\/item>/gs);
      
      if (itemMatches) {
        for (const itemMatch of itemMatches) {
          const idMatch = itemMatch.match(/<id>(.*?)<\/id>/);
          const nameMatch = itemMatch.match(/<name>(.*?)<\/name>/);
          
          if (idMatch && nameMatch) {
            items.push({
              id: idMatch[1],
              name: nameMatch[1]
            });
          }
        }
      }
      
      console.log('📦 Bestehende Artikel gefunden:', items.length);
      return items;
    } catch (error) {
      console.error('Fehler beim Abrufen bestehender Artikel:', error.message);
      return [];
    }
  }

  async syncProduct(product, existingItems) {
    try {
      // AccountName IMMER als E-Mail (wie im Hood-Backend hinterlegt)
      const accountName = process.env.ACCOUNT_NAME || 'info@taschenparadies';
      const categoryId = this.mapCategory(product.shop_cat || 'Taschen');
      // Prüfe ob Artikel bereits existiert
      const exists = Array.isArray(existingItems) && existingItems.some(item => item.id === product.aid);
      const action = exists ? 'itemUpdate' : 'itemInsert';
      const hashedPassword = this.hashPassword(this.password);
      
      // Debug: Zeige alle verfügbaren Felder
      console.log(`🔍 Verarbeite Produkt: ${JSON.stringify(product)}`);
      
      // Verarbeite Bilder
      const pictureUrls = this.processImages(product);
      if (!pictureUrls.length) {
        throw new Error('Kein Bild gefunden!');
      }
      console.log(`🖼️ Gefundene Bilder für ${product.name}: ${pictureUrls.length} URLs`);
      const pictureUrlTags = this.createPictureUrlTags(pictureUrls);
      
      // Beschreibung AUSSCHLIESSLICH aus desc, NICHT aus name
      let description = (product.desc || '').trim();
      if (!description || description.length < 200) {
        // Wenn desc zu kurz ist, erweitern wir sie
        const baseDesc = description || product.name || 'Hochwertiges Produkt';
        description = `${baseDesc}. Dieses Produkt bietet beste Qualität und Funktionalität für Ihre Bedürfnisse. Perfekt für den täglichen Gebrauch und sorgfältig ausgewählt für höchste Ansprüche.`;
      }
      
      // startPrice als Integer in Cent - WICHTIG für Hood API
      let startPrice = 0;
      if (product.startPrice && !isNaN(product.startPrice)) {
        startPrice = parseInt(product.startPrice, 10);
      } else if (product.price && !isNaN(product.price)) {
        startPrice = Math.round(Number(product.price) * 100);
      }
      if (!startPrice || isNaN(startPrice) || startPrice <= 0) {
        startPrice = 100; // Mindestpreis 1€ in Cent
      }
      
      // Logging der kritischen Felder
      console.log(`📝 Beschreibung (${description.length} Zeichen): ${description.substring(0, 100)}...`);
      console.log(`💶 startPrice: ${startPrice} Cent`);
      console.log(`🖼️ Bilder: ${pictureUrls.length}`);
      console.log(`👤 AccountName: ${accountName}`);
      
      // Generiere das XML
      const xml = `<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0.1" user="${accountName}" password="${hashedPassword}">
    <function>${action}</function>
    <accountName>${accountName}</accountName>
    <accountPass>${hashedPassword}</accountPass>
    <items>
        <item>
            <itemMode>classic</itemMode>
            <categoryID>${categoryId}</categoryID>
            <itemName><![CDATA[${this.escapeXml(product.name)}]]></itemName>
            <quantity>${parseInt(product.stock, 10) || 1}</quantity>
            <condition>new</condition>
            <description><![CDATA[${this.escapeXml(description)}]]></description>
            <startPrice>${startPrice}</startPrice>
            ${pictureUrlTags}
            <payOptions><option>payPal</option></payOptions>
            <shipmethods><shipmethod name="DHLPacket_nat"><value>${product.dlv_cost || '4.95'}</value></shipmethod></shipmethods>
        </item>
    </items>
</api>`;
      
      console.log('📤 Sende itemInsert Request für:', product.name);
      console.log('📄 Generiertes XML:');
      console.log('──────────────────────────────────────────────────');
      console.log(xml);
      console.log('──────────────────────────────────────────────────');
      
      const response = await axios.post(this.endpoint, xml, {
        headers: {
          'Content-Type': 'text/xml'
        }
      });
      
      console.log('📥 Hood API Antwort Status:', response.status);
      console.log('📄 Hood API Antwort Body:', response.data);
      
      if (response.data.includes('<status>error</status>') || response.data.includes('<error>')) {
        console.log('❌ Hood API Fehler:', response.data);
        throw new Error('Hood API Fehler');
      }
      
      if (action === 'itemInsert') {
        this.stats.inserted++;
        console.log(`✅ Artikel eingefügt: ${product.name}`);
      } else {
        this.stats.updated++;
        console.log(`🔄 Artikel aktualisiert: ${product.name}`);
      }
      
      return true;
    } catch (error) {
      console.log(`❌ Fehler bei ${product.name}:`, error.message);
      this.stats.errors++;
      return false;
    }
  }

  async syncAll() {
    try {
      console.log('📥 Lade CSV-Daten von:', this.feedUrl);
      
      const response = await axios.get(this.feedUrl);
      const csvData = response.data;
      
      console.log('📊 CSV-Daten geladen, Größe:', csvData.length, 'Zeichen');
      
      // Debug: Zeige die ersten 1000 Zeichen der CSV-Daten
      console.log('🔍 Erste 1000 Zeichen der CSV-Daten:');
      console.log(csvData.substring(0, 1000));
      
      const records = csv.parse(csvData, {
        columns: true,
        skip_empty_lines: true,
        trim: true
      });
      
      console.log('📋 CSV geparst,', records.length, 'Datensätze gefunden');
      
      // Debug: Zeige die ersten 3 Artikel-Namen
      console.log('🔍 Erste 3 Artikel im Feed:');
      records.slice(0, 3).forEach((record, index) => {
        console.log(`  ${index + 1}. ${record.name} (aid: ${record.aid})`);
      });
      
      // TEST-Modus: Nur die ersten 5 Produkte verarbeiten
      const testRecords = records.slice(0, 5);
      console.log('🧪 TEST-Modus: Verarbeite nur die ersten 5 Produkte');
      
      // Hole bestehende Artikel von Hood.de
      console.log('🔄 Hole bestehende Artikel von Hood.de...');
      const existingItems = await this.getExistingItems();
      
      console.log(`📦 Verarbeite ${testRecords.length} Produkte...`);
      
      for (const record of testRecords) {
        try {
          const result = await this.syncProduct(record, existingItems);
          
          if (!result) {
            this.stats.errors++;
            console.log(`❌ Fehler bei ${record.name}: Fehler beim Synchronisieren`);
          }
        } catch (error) {
          this.stats.errors++;
          console.error(`Fehler beim Synchronisieren des Produkts: ${error.message}`);
        }
      }
      
      console.log('✅ Synchronisation abgeschlossen!');
      console.log('📊 Statistiken:', this.stats);
      
      return this.stats;
      
    } catch (error) {
      console.error('❌ Fehler beim Laden der CSV-Daten:', error.message);
      throw error;
    }
  }

  async insertItem(product) {
    const categoryId = this.mapCategory(product.shop_cat || 'Taschen');
    const hashedPassword = this.hashPassword(this.password);
    
    // Verarbeite Bilder
    const pictureUrls = this.processImages(product);
    const pictureUrlTags = this.createPictureUrlTags(pictureUrls);
    
    // Verwende die vollständige Beschreibung aus dem CSV-Feld 'desc'
    let description = product.desc || product.name || '';
    // Hood verlangt mindestens 200 Zeichen für die Beschreibung
    if (description.length < 200) {
      description = `${description} - Hochwertiges Produkt von ${product.brand || 'unserem Shop'}. Perfekt für den täglichen Gebrauch. Diese Artikel bietet beste Qualität und Funktionalität für Ihre Bedürfnisse.`;
    }
    
    // Verwende startPrice direkt aus der CSV (bereits in Cent)
    const startPriceInCents = Number(product.startPrice || product.price || 0);
    const shippingCost = Number(product.dlv_cost || 4.95).toFixed(2);
    
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0.1" user="${this.accountName}" password="${hashedPassword}">
    <function>itemInsert</function>
    <accountName>${this.accountName}</accountName>
    <accountPass>${hashedPassword}</accountPass>
    <items>
        <item>
            <itemMode>classic</itemMode>
            <categoryID>${categoryId}</categoryID>
            <itemName><![CDATA[${this.escapeXml(product.name)}]]></itemName>
            <quantity>${product.stock || 1}</quantity>
            <condition>new</condition>
            <description><![CDATA[${this.escapeXml(description)}]]></description>
            <startPrice>${startPriceInCents}</startPrice>
${pictureUrlTags}
            <payOptions>
                <option>payPal</option>
            </payOptions>
            <shipmethods>
                <shipmethod name="DHLPacket_nat">
                    <value>${shippingCost}</value>
                </shipmethod>
            </shipmethods>
        </item>
    </items>
</api>`;

    console.log('📤 Sende itemInsert Request für:', product.name);

    try {
      const response = await axios.post(this.endpoint, xml, {
        headers: {
          'Content-Type': 'text/xml'
        }
      });
      
      if (response.status === 200 && !response.data.includes('<status>error</status>')) {
        console.log('✅ Artikel eingefügt:', product.name);
        this.stats.inserted++;
        return true;
      } else {
        console.log('❌ Fehler beim Einfügen:', response.data);
        this.stats.errors++;
        return false;
      }
    } catch (error) {
      console.error('❌ Fehler beim API-Request:', error.message);
      this.stats.errors++;
      return false;
    }
  }

  // Verarbeite Bilder aus CSV-Feldern und erstelle pictureURL-Tags
  processImages(product) {
    const pictureUrls = [];
    
    // Prüfe das 'image' Feld
    if (product.image && product.image.trim()) {
      const imageUrl = product.image.trim();
      if (imageUrl && imageUrl !== '') {
        pictureUrls.push(imageUrl);
      }
    }
    
    // Prüfe das 'images' Feld (Komma-getrennte URLs)
    if (product.images && product.images.trim()) {
      const imageUrls = product.images.split(',').map(url => url.trim()).filter(url => url && url !== '');
      pictureUrls.push(...imageUrls);
    }
    
    // Entferne Duplikate
    const uniqueUrls = [...new Set(pictureUrls)];
    
    console.log(`🖼️ Gefundene Bilder für ${product.name}: ${uniqueUrls.length} URLs`);
    
    return uniqueUrls;
  }

  // Erstelle pictureURL-Tags für XML
  createPictureUrlTags(pictureUrls) {
    if (!pictureUrls || pictureUrls.length === 0) {
      return '';
    }
    
    return pictureUrls.map(url => `            <pictureURL>${this.escapeXml(url)}</pictureURL>`).join('\n');
  }
}

exports.handler = async (event, context) => {
  try {
    console.log('🚀 Starte Sync-Prozess...');
    
    // Prüfe Umgebungsvariablen
    const requiredEnvVars = ['FEED_URL', 'HOOD_PASSWORD', 'ACCOUNT_NAME'];
    const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);
    
    if (missingVars.length > 0) {
      throw new Error(`Fehlende Umgebungsvariablen: ${missingVars.join(', ')}`);
    }
    
    console.log('🔧 Konfiguration:', {
      accountName: process.env.ACCOUNT_NAME,
      feedUrl: process.env.FEED_URL,
      endpoint: process.env.HOOD_ENDPOINT || 'https://www.hood.de/api.htm'
    });
    
    // Initialisiere HoodAPI mit Umgebungsvariablen
    const hoodAPI = new HoodAPI();
    
    // Starte Synchronisation
    const result = await hoodAPI.syncAll();
    
    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify({
        success: true,
        message: 'Synchronisation abgeschlossen!',
        stats: result,
        timestamp: new Date().toISOString()
      })
    };
    
  } catch (error) {
    console.error('Fehler:', error);
    
    return {
      statusCode: 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify({
        success: false,
        error: error.message,
        timestamp: new Date().toISOString()
      })
    };
  }
}; 