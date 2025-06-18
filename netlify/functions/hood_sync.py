import os, hashlib, requests
import xml.etree.ElementTree as ET
import csv, io

def handler(event, context):
    """
    Netlify Scheduled Function: Sync von Shopware CSV-Feed zu Hood API.
    """
    # --- 1. Umgebungsvariablen einlesen ---
    account = os.getenv('ACCOUNT_NAME')
    feed_url = os.getenv('FEED_URL')
    endpoint = os.getenv('HOOD_ENDPOINT', 'https://www.hood.de/api.htm')
    pwd = os.getenv('HOOD_PASSWORD', '')
    # Hash
    pwd = hashlib.md5(pwd.encode()).hexdigest()
    
    # --- 2. CSV-Feed abrufen ---
    data = requests.get(feed_url).text
    reader = csv.DictReader(io.StringIO(data), delimiter=';')
    
    # --- 3. API-Client Hilfsfunktionen ---
    def xml_req(method, payload=None):
        root = ET.Element('api')
        ET.SubElement(root, 'accountName').text = account
        ET.SubElement(root, 'accountPass').text = pwd
        ET.SubElement(root, 'method').text = method
        if payload:
            for k,v in payload.items(): ET.SubElement(root, k).text = v
        return ET.tostring(root, encoding='utf-8')

    def call(method, payload=None):
        xml = xml_req(method, payload)
        r = requests.post(endpoint, data=xml, headers={'Content-Type':'application/xml'})
        r.raise_for_status()
        return ET.fromstring(r.content)

    # --- 4. CSV parsen und an Hood senden ---
    for row in reader:
        aid = row.get('mpnr') or row.get('aid')
        item = ET.Element('item')
        ET.SubElement(item, 'articleID').text = aid
        # Mapping
        for col,tag in [('name','name'),('desc','description'),('price','startPrice'),('shop_cat','category'),('stock','stock')]:
            val = row.get(col)
            if val: ET.SubElement(item, tag).text = val
        call('itemInsert', {'xml': ET.tostring(item, encoding='utf-8').decode()})

    # --- 5. Abschluss ---
    return {
        "statusCode": 200,
        "body": "Hood-Sync erfolgreich ausgeführt."
    } 