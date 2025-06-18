# Datei: netlify/functions/hood_sync.py
import os
import hashlib
import requests
import xml.etree.ElementTree as ET
import csv
import io
import time
from typing import Optional, Dict, Any, Union, cast

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Union[int, str]]:
    """
    Netlify Scheduled Function: Sync von Shopware CSV-Feed zu Hood API.
    Synchronisiert Produkte von TaschenParadies zu Hood.de
    """
    # Umgebungsvariablen prüfen
    required_vars = ['FEED_URL', 'HOOD_PASSWORD', 'ACCOUNT_NAME']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        return {
            'statusCode': 500,
            'body': f'Fehlende Umgebungsvariablen: {", ".join(missing_vars)}'
        }

    # Hood-API-Client initialisieren
    hood_client = HoodAPI(
        account_name=os.getenv('ACCOUNT_NAME', ''),
        password=os.getenv('HOOD_PASSWORD', ''),
        feed_url=os.getenv('FEED_URL', ''),
        endpoint=os.getenv('HOOD_ENDPOINT', 'https://www.hood.de/api.htm')
    )

    try:
        # CSV verarbeiten und Artikel synchronisieren
        hood_client.process_csv()
        return {
            'statusCode': 200,
            'body': f'Hood-Sync erfolgreich ausgeführt. Statistik: {hood_client.stats}'
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Fehler beim Hood-Sync: {str(e)}'
        }

class HoodAPI:
    """Hood.de API Client"""
    def __init__(self, account_name: str, password: str, feed_url: str, endpoint: str):
        self.account_name = account_name
        self.password = password  # Kein MD5-Hash mehr
        self.feed_url = feed_url
        self.endpoint = endpoint
        self.stats = {'updated': 0, 'inserted': 0, 'errors': 0, 'skipped': 0}

    def get_csv_data(self):
        """CSV-Daten vom Feed abrufen"""
        if 'TEST_CSV' in os.environ:
            return io.StringIO(os.environ['TEST_CSV'])
        
        response = requests.get(self.feed_url)
        if response.status_code != 200:
            raise Exception(f"Fehler beim Abrufen der CSV-Daten: {response.status_code}")
        return io.StringIO(response.content.decode('utf-8'))

    def process_csv(self):
        """CSV verarbeiten und Artikel synchronisieren"""
        csv_file = self.get_csv_data()
        reader = csv.DictReader(csv_file, delimiter=',')

        for row in reader:
            try:
                # Pflichtfelder extrahieren
                article_id = row.get('mpnr') or row.get('aid')
                name = row.get('name', '').strip('"')
                price = float(row.get('price', '0').strip('"').replace(',', '.'))
                stock = int(float(row.get('stock', '0').strip('"')))
                description = row.get('description', '').strip('"')

                if not article_id:
                    print(f"Überspringe Zeile: Keine Artikel-ID gefunden")
                    self.stats['skipped'] += 1
                    continue

                # Debug-Logging für Pflichtfelder
                if not name or not price:
                    print(f"Artikel {article_id}: Pflichtfelder fehlen (Name: {bool(name)}, Preis: {bool(price)})")
                    self.stats['skipped'] += 1
                    continue

                # Nur bei erfolgreicher Verarbeitung Debug-Info ausgeben
                print(f"Verarbeite Artikel {article_id} - Name: {name}, Preis: {price}")

                # Prüfe ob Artikel bereits existiert
                exists = self.check_item_exists(article_id)
                
                if exists:
                    self.update_item(article_id, name, price, stock, description, row)
                    self.stats['updated'] += 1
                else:
                    self.insert_item(article_id, name, price, stock, description, row)
                    self.stats['inserted'] += 1

            except Exception as e:
                print(f"Fehler bei der Verarbeitung von Artikel {article_id}: {str(e)}")
                self.stats['errors'] += 1

    def check_item_exists(self, article_id: str) -> bool:
        """Prüft ob ein Artikel bereits existiert"""
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="{self.escape_xml(self.account_name)}" password="{self.escape_xml(self.password)}">
\t<function>itemDetail</function>
\t<accountName>{self.escape_xml(self.account_name)}</accountName>
\t<accountPass>{self.escape_xml(self.password)}</accountPass>
\t<articleID>{self.escape_xml(article_id)}</articleID>
</api>'''
        
        headers = {'Content-Type': 'application/xml'}
        response = requests.post(self.endpoint, data=xml, headers=headers)
        return response.status_code == 200 and '<status>ok</status>' in response.text

    def update_item(self, article_id: str, name: str, price: float, stock: int, description: str, row: Dict[str, str]):
        """Aktualisiert einen bestehenden Artikel"""
        xml = self.create_item_xml(article_id, name, price, stock, description, row, 'itemUpdate')
        self.api_request(xml)

    def insert_item(self, article_id: str, name: str, price: float, stock: int, description: str, row: Dict[str, str]):
        """Fügt einen neuen Artikel ein"""
        xml = self.create_item_xml(article_id, name, price, stock, description, row, 'itemInsert')
        self.api_request(xml)

    def create_item_xml(self, article_id: str, name: str, price: float, stock: int, description: str, row: Dict[str, str], method: str) -> str:
        """Erstellt das XML für einen Artikel"""
        # Bilder sammeln
        images = []
        for key in row.keys():
            if key.startswith('image') and row[key]:
                # Bereinige die Bild-URLs
                urls = row[key].strip('"').split(',')
                for url in urls:
                    clean_url = url.strip()
                    if clean_url and clean_url not in images:  # Verhindere Duplikate
                        images.append(clean_url)

        # XML erstellen
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<api type="public" version="2.0" user="{self.escape_xml(self.account_name)}" password="{self.escape_xml(self.password)}">
\t<function>{method}</function>
\t<accountName>{self.escape_xml(self.account_name)}</accountName>
\t<accountPass>{self.escape_xml(self.password)}</accountPass>
\t<items>
\t\t<item>
\t\t\t<itemMode>classic</itemMode>
\t\t\t<categoryID>1000</categoryID>
\t\t\t<itemName><![CDATA[{name}]]></itemName>
\t\t\t<quantity>{stock}</quantity>
\t\t\t<condition>new</condition>
\t\t\t<description><![CDATA[{description or name}]]></description>
\t\t\t<price>{price:.2f}</price>
\t\t\t<ean>{self.escape_xml(row.get('ean', '').strip('"'))}</ean>
\t\t\t<manufacturer>{self.escape_xml(row.get('brand', '').strip('"'))}</manufacturer>
\t\t\t<productURL>{self.escape_xml(row.get('link', '').strip('"'))}</productURL>
\t\t\t<shippingTime>{self.escape_xml(row.get('dlv_time', 'Sofort verfügbar, Lieferzeit: 1-3 Tage').strip('"'))}</shippingTime>
\t\t\t<articleID>{self.escape_xml(article_id)}</articleID>
\t\t\t
\t\t\t<payOptions>
\t\t\t\t<option>wireTransfer</option>
\t\t\t\t<option>payPal</option>
\t\t\t\t<option>invoice</option>
\t\t\t\t<option>sofort</option>
\t\t\t</payOptions>

\t\t\t<shipmethods>
\t\t\t\t<shipmethod name="DHLPacket_nat">
\t\t\t\t\t<value>{self.escape_xml(row.get('dlv_cost', '4.95').strip('"'))}</value>
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
\t\t\t</shipmethods>'''

        # Bilder hinzufügen (maximal 10)
        if images:
            xml += '\n\t\t\t<pictures>'
            for idx, image in enumerate(images[:10], 1):
                if image:
                    xml += f'\n\t\t\t\t<picture{idx}>{self.escape_xml(image)}</picture{idx}>'
            xml += '\n\t\t\t</pictures>'

        xml += '''
\t\t</item>
\t</items>
</api>'''
        return xml

    def escape_xml(self, text: str) -> str:
        """Escaped XML-Sonderzeichen"""
        if not text:
            return ''
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')

    def api_request(self, xml: str):
        """Sendet eine Anfrage an die Hood-API"""
        print(f"Request XML:\n{xml}")
        headers = {'Content-Type': 'application/xml'}
        
        try:
            response = requests.post(self.endpoint, data=xml, headers=headers)
            print(f"Response Status: {response.status_code}")
            print(f"Response Content:\n{response.text}")

            if response.status_code != 200:
                raise Exception(f"HTTP Error {response.status_code}: {response.text}")

            # Parse the response XML to better handle errors
            try:
                root = ET.fromstring(response.text)
                status = root.find('status')
                if status is not None and status.text == 'error':
                    error = root.find('error')
                    error_text = error.text if error is not None else "Unknown error"
                    raise Exception(f"Hood API Error: {error_text}")
            except ET.ParseError as e:
                raise Exception(f"Failed to parse Hood API response: {str(e)}")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error while calling Hood API: {str(e)}")

        return response
