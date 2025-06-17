import requests
import xml.etree.ElementTree as ET
import csv
import io
import schedule
import time

class HoodAPIClient:
    """
    Python-Client für die Hood API (V2), synchronisiert Shopware6 CSV-Feeds.
    """
    def __init__(self, account_name: str, account_pass_md5: str,
                 endpoint: str = "https://www.hood.de/api.htm"):
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
        resp.raise_for_status()
        return ET.fromstring(resp.content)

    def call(self, method: str, payload: dict = None) -> ET.Element:
        xml = self._build_request(method, payload)
        return self._post(xml)

    def item_exists(self, article_id: str) -> bool:
        """Prüft Existenz via itemDetail (kein Fehler = vorhanden)."""
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
        """
        Synchronisiert Artikel aus Shopware-CSV.
        Feld-Mapping, Insert/Update basierend auf SKU.
        """
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
            for tag,val in mapping.items():
                if val:
                    ET.SubElement(hood_item, tag).text = val
            for prop in extras:
                val = row.get(prop,'').strip()
                if val:
                    ET.SubElement(hood_item, prop).text = val
            for img_url in images:
                ET.SubElement(hood_item, 'images').text = img_url

            xml_str = ET.tostring(hood_item, encoding='utf-8').decode('utf-8')
            if self.item_exists(article_id):
                resp_xml = self.item_update(xml_str)
                print(f"Updated {article_id}: {ET.tostring(resp_xml,'utf-8').decode()}")
            else:
                resp_xml = self.item_insert(xml_str)
                print(f"Inserted {article_id}: {ET.tostring(resp_xml,'utf-8').decode()}")

# Automatischer Bestandsabgleich jede Stunde
def job():
    client.sync_from_shopware_csv(FEED_URL)

if __name__ == '__main__':
    FEED_URL = 'https://shop.taschenparadies.de/store-api/product-export/SWPEY1JJENCYZ0TJTEDUUZFWWQ/hoodcsv'
    MD5_HASH = '243dce8aace190ad275a2eff74f356ca'
    client = HoodAPIClient('TaschenParadies', MD5_HASH)
    # Einmaliger Lauf
    job()
    # Stunden-Intervall
    schedule.every(1).hours.do(job)
    while True:
        schedule.run_pending()
        time.sleep(60)
