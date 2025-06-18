const axios = require('axios');
const csv = require('csv-parse/sync');

class HoodAPI {
  constructor(accountName, password, feedUrl, endpoint = 'https://www.hood.de/api.htm') {
    this.accountName = accountName;
    this.password = password;
    this.feedUrl = feedUrl;
    this.endpoint = endpoint;
    this.stats = { updated: 0, inserted: 0, errors: 0, skipped: 0 };
  }

  escapeXml(text) {
    if (!text) return '';
    return text.toString()
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }

  async getCsvData() {
    if (process.env.TEST_CSV) {
      return process.env.TEST_CSV;
    }
    
    const response = await axios.get(this.feedUrl);
    if (response.status !== 200) {
      throw new Error(`Fehler beim Abrufen der CSV-Daten: ${response.status}`);
    }
    return response.data;
  }

  async checkItemExists(articleId) {
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="${this.escapeXml(this.accountName)}" password="${this.escapeXml(this.password)}">
\t<function>itemDetail</function>
\t<accountName>${this.escapeXml(this.accountName)}</accountName>
\t<accountPass>${this.escapeXml(this.password)}</accountPass>
\t<articleID>${this.escapeXml(articleId)}</articleID>
</api>`;

    const response = await axios.post(this.endpoint, xml, {
      headers: { 'Content-Type': 'application/xml' }
    });

    return response.status === 200 && response.data.includes('<status>ok</status>');
  }

  createItemXml(articleId, name, price, stock, description, row, method) {
    // Bilder sammeln
    const images = Object.entries(row)
      .filter(([key, value]) => key.startsWith('image') && value)
      .map(([_, value]) => value.trim().replace(/^"|"$/g, ''))
      .filter((url, index, self) => url && self.indexOf(url) === index)
      .slice(0, 10);

    // XML erstellen
    let xml = `<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="${this.escapeXml(this.accountName)}" password="${this.escapeXml(this.password)}">
\t<function>${method}</function>
\t<accountName>${this.escapeXml(this.accountName)}</accountName>
\t<accountPass>${this.escapeXml(this.password)}</accountPass>
\t<items>
\t\t<item>
\t\t\t<itemMode>classic</itemMode>
\t\t\t<categoryID>1000</categoryID>
\t\t\t<itemName><![CDATA[${name}]]></itemName>
\t\t\t<quantity>${stock}</quantity>
\t\t\t<condition>new</condition>
\t\t\t<description><![CDATA[${description || name}]]></description>
\t\t\t<price>${price.toFixed(2)}</price>
\t\t\t<ean>${this.escapeXml(row.ean?.replace(/^"|"$/g, '') || '')}</ean>
\t\t\t<manufacturer>${this.escapeXml(row.brand?.replace(/^"|"$/g, '') || '')}</manufacturer>
\t\t\t<productURL>${this.escapeXml(row.link?.replace(/^"|"$/g, '') || '')}</productURL>
\t\t\t<shippingTime>${this.escapeXml(row.dlv_time?.replace(/^"|"$/g, '') || 'Sofort verfügbar, Lieferzeit: 1-3 Tage')}</shippingTime>
\t\t\t<articleID>${this.escapeXml(articleId)}</articleID>
\t\t\t
\t\t\t<payOptions>
\t\t\t\t<option>wireTransfer</option>
\t\t\t\t<option>payPal</option>
\t\t\t\t<option>invoice</option>
\t\t\t\t<option>sofort</option>
\t\t\t</payOptions>

\t\t\t<shipmethods>
\t\t\t\t<shipmethod name="DHLPacket_nat">
\t\t\t\t\t<value>${this.escapeXml(row.dlv_cost?.replace(/^"|"$/g, '') || '4.95')}</value>
\t\t\t\t</shipmethod>
\t\t\t\t<shipmethod name="DHLPacket_eu">
\t\t\t\t\t<value>9.95</value>
\t\t\t\t</shipmethod>
\t\t\t\t<shipmethod name="DHLPacket_at">
\t\t\t\t\t<value>9.95</value>
\t\t\t\t</shipmethod>
\t\t\t\t<shipmethod name="DHLPacket_ch">
\t\t\t\t\t<value>14.95</value>
\t\t\t\t</shipmethod>
\t\t\t</shipmethods>`;

    if (images.length > 0) {
      xml += '\n\t\t\t<pictures>';
      images.forEach((image, idx) => {
        xml += `\n\t\t\t\t<picture${idx + 1}>${this.escapeXml(image)}</picture${idx + 1}>`;
      });
      xml += '\n\t\t\t</pictures>';
    }

    xml += '\n\t\t</item>\n\t</items>\n</api>';
    return xml;
  }

  async apiRequest(xml) {
    console.log('Request XML:', xml);
    
    const response = await axios.post(this.endpoint, xml, {
      headers: { 'Content-Type': 'application/xml' }
    });

    console.log('Response Status:', response.status);
    console.log('Response Content:', response.data);

    if (response.status !== 200) {
      throw new Error(`HTTP Error ${response.status}: ${response.data}`);
    }

    // Parse response XML for errors
    if (response.data.includes('<status>error</status>')) {
      const errorMatch = response.data.match(/<error>(.*?)<\/error>/);
      const errorText = errorMatch ? errorMatch[1] : 'Unknown error';
      throw new Error(`Hood API Error: ${errorText}`);
    }

    return response;
  }

  async updateItem(articleId, name, price, stock, description, row) {
    const xml = this.createItemXml(articleId, name, price, stock, description, row, 'itemUpdate');
    await this.apiRequest(xml);
  }

  async insertItem(articleId, name, price, stock, description, row) {
    const xml = this.createItemXml(articleId, name, price, stock, description, row, 'itemInsert');
    await this.apiRequest(xml);
  }

  async processCsv() {
    const csvData = await this.getCsvData();
    const records = csv.parse(csvData, {
      columns: true,
      skip_empty_lines: true,
      delimiter: ',',
      trim: true
    });

    for (const row of records) {
      try {
        const articleId = row.mpnr || row.aid;
        const name = row.name?.replace(/^"|"$/g, '');
        const price = parseFloat(row.price?.replace(/^"|"$/g, '').replace(',', '.'));
        const stock = parseInt(row.stock?.replace(/^"|"$/g, ''));
        const description = row.description?.replace(/^"|"$/g, '');

        if (!articleId) {
          console.log('Überspringe Zeile: Keine Artikel-ID gefunden');
          this.stats.skipped++;
          continue;
        }

        if (!name || !price) {
          console.log(`Artikel ${articleId}: Pflichtfelder fehlen (Name: ${Boolean(name)}, Preis: ${Boolean(price)})`);
          this.stats.skipped++;
          continue;
        }

        console.log(`Verarbeite Artikel ${articleId} - Name: ${name}, Preis: ${price}`);

        const exists = await this.checkItemExists(articleId);
        
        if (exists) {
          await this.updateItem(articleId, name, price, stock, description, row);
          this.stats.updated++;
        } else {
          await this.insertItem(articleId, name, price, stock, description, row);
          this.stats.inserted++;
        }

      } catch (error) {
        console.error(`Fehler bei der Verarbeitung von Artikel: ${error.message}`);
        this.stats.errors++;
      }
    }
  }
}

exports.handler = async function(event, context) {
  try {
    // Einfacher Test-Response
    return {
      statusCode: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: "Hood-Sync Test",
        timestamp: new Date().toISOString(),
        event: {
          path: event.path,
          httpMethod: event.httpMethod,
          headers: event.headers
        }
      })
    };
  } catch (error) {
    return {
      statusCode: 500,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: error.message })
    };
  }
}; 