import os
import pytest
from unittest.mock import patch, MagicMock
from netlify.functions.hood_sync import handler, HoodAPI
import requests
import io
import csv

# Test-Konfiguration
TEST_CONFIG = {
    'ACCOUNT_NAME': 'TaschenParadies',
    'HOOD_PASSWORD': 'Q4HX7j5pcbZkavtwGaZA',
    'FEED_URL': 'https://shop.taschenparadies.de/store-api/product-export/SWPEY1JJENCYZ0TJTEDUUZFWwQ/hoodcsv',
    'HOOD_ENDPOINT': 'https://www.hood.de/api.htm'
}

# Beispiel-CSV-Daten
SAMPLE_CSV = '''mpnr,name,price,stock,description,ean,brand,link,dlv_time,dlv_cost,image1
12345,"Test Tasche","29.99","10","Eine schöne Tasche","1234567890","TestBrand","http://example.com","1-3 Tage","4.95","http://example.com/image.jpg"
67890,"Zweite Tasche","39.99","5","Noch eine Tasche","0987654321","TestBrand","http://example.com","1-3 Tage","4.95","http://example.com/image2.jpg"'''

@pytest.fixture
def setup_environment():
    """Fixture zum Setzen der Umgebungsvariablen"""
    old_env = {}
    for key, value in TEST_CONFIG.items():
        old_env[key] = os.environ.get(key)
        os.environ[key] = value
    yield
    for key, value in old_env.items():
        if value is None:
            del os.environ[key]
        else:
            os.environ[key] = value

@pytest.fixture
def hood_api():
    """Fixture für HoodAPI-Instanz"""
    return HoodAPI(
        account_name=TEST_CONFIG['ACCOUNT_NAME'],
        password=TEST_CONFIG['HOOD_PASSWORD'],
        feed_url=TEST_CONFIG['FEED_URL'],
        endpoint=TEST_CONFIG['HOOD_ENDPOINT']
    )

@pytest.fixture
def mock_csv_response():
    """Fixture für Mock-CSV-Antwort"""
    return SAMPLE_CSV

def test_environment_variables(setup_environment):
    """Test: Prüft, ob alle erforderlichen Umgebungsvariablen gesetzt sind"""
    assert os.environ['ACCOUNT_NAME'] == TEST_CONFIG['ACCOUNT_NAME']
    assert os.environ['HOOD_PASSWORD'] == TEST_CONFIG['HOOD_PASSWORD']
    assert os.environ['FEED_URL'] == TEST_CONFIG['FEED_URL']
    assert os.environ['HOOD_ENDPOINT'] == TEST_CONFIG['HOOD_ENDPOINT']

def test_handler_missing_env():
    """Test: Handler mit fehlenden Umgebungsvariablen"""
    with patch.dict(os.environ, clear=True):
        result = handler({}, {})
        assert result['statusCode'] == 500
        assert 'Fehlende Umgebungsvariablen' in result['body']

@patch('requests.get')
def test_csv_processing(mock_get, hood_api, mock_csv_response):
    """Test: CSV-Verarbeitung"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = mock_csv_response.encode('utf-8')
    mock_get.return_value = mock_response

    # Setze TEST_CSV für direktes Testen
    os.environ['TEST_CSV'] = mock_csv_response
    
    csv_file = hood_api.get_csv_data()
    reader = csv.DictReader(csv_file)
    rows = list(reader)
    
    assert len(rows) == 2
    assert rows[0]['mpnr'] == '12345'
    assert rows[0]['name'].strip('"') == 'Test Tasche'
    assert float(rows[0]['price'].strip('"')) == 29.99

@patch('requests.post')
def test_check_item_exists(mock_post, hood_api):
    """Test: Artikel-Existenz-Prüfung"""
    # Mock für existierenden Artikel
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '<status>ok</status>'
    mock_post.return_value = mock_response

    exists = hood_api.check_item_exists('12345')
    assert exists == True

    # Überprüfe XML-Struktur im Request
    call_args = mock_post.call_args
    assert call_args is not None
    xml_data = call_args[1]['data']
    assert 'type="public"' in xml_data
    assert 'version="2.0"' in xml_data
    assert f'user="{TEST_CONFIG["ACCOUNT_NAME"]}"' in xml_data
    assert '<function>itemDetail</function>' in xml_data
    assert '<articleID>12345</articleID>' in xml_data

@patch('requests.post')
def test_item_insert(mock_post, hood_api):
    """Test: Artikel-Einfügung"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '<status>ok</status>'
    mock_post.return_value = mock_response

    test_item = {
        'mpnr': '12345',
        'name': '"Test Tasche"',
        'price': '"29.99"',
        'stock': '"10"',
        'description': '"Eine schöne Tasche"',
        'image1': '"http://example.com/image.jpg"'
    }

    hood_api.insert_item(
        article_id=test_item['mpnr'],
        name=test_item['name'].strip('"'),
        price=float(test_item['price'].strip('"')),
        stock=int(test_item['stock'].strip('"')),
        description=test_item['description'].strip('"'),
        row=test_item
    )

    # Überprüfe XML-Struktur im Request
    call_args = mock_post.call_args
    assert call_args is not None
    xml_data = call_args[1]['data']
    assert 'type="public"' in xml_data
    assert '<function>itemInsert</function>' in xml_data
    assert '<itemName><![CDATA[Test Tasche]]></itemName>' in xml_data
    assert '<price>29.99</price>' in xml_data
    assert '<quantity>10</quantity>' in xml_data

def test_create_item_xml(hood_api):
    """Test: XML-Generierung"""
    test_item = {
        'mpnr': '12345',
        'name': '"Test Tasche"',
        'price': '"29.99"',
        'stock': '"10"',
        'description': '"Eine schöne Tasche"',
        'image1': '"http://example.com/image.jpg"'
    }

    xml = hood_api.create_item_xml(
        article_id=test_item['mpnr'],
        name=test_item['name'].strip('"'),
        price=float(test_item['price'].strip('"')),
        stock=int(test_item['stock'].strip('"')),
        description=test_item['description'].strip('"'),
        row=test_item,
        method='itemInsert'
    )

    # Überprüfe XML-Struktur
    assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
    assert 'type="public" version="2.0"' in xml
    assert '<function>itemInsert</function>' in xml
    assert '<itemName><![CDATA[Test Tasche]]></itemName>' in xml
    assert '<price>29.99</price>' in xml
    assert '<quantity>10</quantity>' in xml
    assert '<pictures>' in xml
    assert '<picture1>http://example.com/image.jpg</picture1>' in xml

if __name__ == '__main__':
    pytest.main(['-v', __file__]) 