# Datei: netlify/functions/hood_sync.py
import os
import json
import requests
from typing import Dict, Any

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Netlify Function Handler für Hood.de API Synchronisation
    """
    try:
        # Umgebungsvariablen prüfen
        required_vars = ['FEED_URL', 'HOOD_PASSWORD', 'ACCOUNT_NAME']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': f'Fehlende Umgebungsvariablen: {", ".join(missing_vars)}'
                })
            }

        # Basis-Konfiguration
        config = {
            'account_name': os.getenv('ACCOUNT_NAME'),
            'password': os.getenv('HOOD_PASSWORD'),
            'feed_url': os.getenv('FEED_URL'),
            'endpoint': os.getenv('HOOD_ENDPOINT', 'https://www.hood.de/api.htm')
        }

        # Test-Response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Hood-Sync Funktion erfolgreich aufgerufen',
                'config': {k: '***' if k == 'password' else v for k, v in config.items()}
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
