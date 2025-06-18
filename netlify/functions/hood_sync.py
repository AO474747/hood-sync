# Datei: netlify/functions/hood_sync.py
import os
import hashlib
import requests
import xml.etree.ElementTree as ET
import csv
import io


def handler(event, context):
    """
    Netlify Scheduled Function: Sync von Shopware CSV-Feed zu Hood API.
    """
    # Umgebungsvariablen
    feed_url = os.getenv('FEED_URL')
    raw_pass = os.getenv('HOOD_PASSWORD')
    # Falls ein Klartext-Passwort übergeben wird, MD5-Hash erzeugen
    account_name = os.getenv('ACCOUNT_NAME')
    md5_hash = os.getenv('MD5_HASH') or hashlib.md5(raw_pass.encode('utf-8')).hexdigest()
    endpoint = os.getenv('HOOD_ENDPOINT', 'https://www.hood.de/api.htm')

    # Innerer API-Client
    class HoodAPIClient:
        def __init__(self, account_name: str, account_pass_md5: str, endpoint: str):
            self.account_name = account_name
            self.account_pass = account_pass_md5
            self.endpoint = endpoint
            self.session = requests.Session()

        def _build_request(self, method: str, payload: dict = None) -> bytes:
            root = ET.Element('api')
            ET.SubElement(root, 'accountName').text = self.account_name
            ET.SubElement(root, 'accountPass').text = self.account_pass
            ET.SubElement(root, 'method').text = method
            if payload:
                for tag, val in payload.items():
                    ET.SubElement(root, tag).text = str(val)
            return ET.tostring(root, encoding='utf-8', xml_declaration=True)

        def _post(self, xml_body: bytes) -> ET.Element:
            resp = self.session.post(
                self.endpoint,
                data=xml_body,
                headers={'Content-Type': 'application/xml'}
            )
            # Logging: Anfrage und Antwort ausgeben
            print("Request XML:
", xml_body.decode('utf-8'))
            print("Response Status:", resp.status_code)
            print("Response Content:
", resp.text)
            resp.raise_for_status()
            return ET.fromstring(resp.content)(
                self.endpoint,
                data=xml_body,
                headers={'Content-Type': 'application/xml'}
            )
            resp.raise_for_status()
            return ET.fromstring(resp.content)

        def call(self, method: str, payload: dict = None) -> ET.Element:
            return self._post(self._build_request(method, payload))

        def item_exists(self, article_id: str) -> bool:
            try:
                resp = self.call('itemDetail', {'articleID': article_id})
                return resp.find('error') is None
            except:
                return False

        def item_insert(self, xml_data: str) -> ET.Element:
            return self.call('itemInsert', {'xml': xml_data})

        def item_update(self, xml_data: str) -> ET.Element:
            return self.call('itemUpdate', {'xml': xml_data})

        def sync_from_shopware_csv(self, feed_url: str):
            resp = self.session.get(feed_url)
            resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(resp.text), delimiter=';')
            for row in reader:
                article_id = row.get('mpnr') or row.get('aid')
                hood_item = ET.Element('item')
                mapping = {
                    'name': row.get('name','').strip(),
                    'description': row.get('desc','').strip(),
                    'startPrice': row.get('price','').strip(),
                    'category': row.get('shop_cat','').strip(),
                    'stock': row.get('stock','').strip(),
                    'ean': row.get('ean','').strip(),
                    'brand': row.get('brand','').strip(),
                }
                extras = ['ppu','link','dlv_time','dlv_cost','pzn',
                          'unit_pricing_measure','unit_pricing_base_measure','target_url']
                images = []
                if row.get('image'):
                    images.append(row['image'].strip())
                if row.get('images'):
                    images.extend([u.strip() for u in row['images'].split(',') if u.strip()])
                ET.SubElement(hood_item, 'articleID').text = article_id
                for tag, val in mapping.items():
                    if val:
                        ET.SubElement(hood_item, tag).text = val
                for prop in extras:
                    val = row.get(prop,'').strip()
                    if val:
                        ET.SubElement(hood_item, prop).text = val
                for img_url in images:
                    ET.SubElement(hood_item, 'images').text = img_url
                xml_str = ET.tostring(hood_item, encoding='utf-8').decode('utf-8')
                if client.item_exists(article_id):
                    client.item_update(xml_str)
                else:
                    client.item_insert(xml_str)

    # Sync ausführen
    client = HoodAPIClient(account_name, md5_hash, endpoint)
    client.sync_from_shopware_csv(feed_url)

    return {
        'statusCode': 200,
        'body': 'Hood-Sync erfolgreich ausgeführt.'
    }

# Datei: netlify.toml (im Projekt-Root)
[build]
  functions = "netlify/functions"

[functions.hood_sync]
  schedule = "@hourly"

# Git-Workflow: Schritt für Schritt
# 1. Datei hood_sync.py aktualisieren (wie oben). 
# 2. In Git Bash:
#    cd "/c/Users/ao/Downloads/Hood Api/hood-sync"
#    git add netlify/functions/hood_sync.py netlify.toml
#    git commit -m "Update hood_sync.py to auto-hash password"
#    git push
# 3. In Netlify Dashboard auf Deploys → Trigger deploy → Deploy site.
# 4. Unter Logs → Functions → hood_sync Logs prüfen.
