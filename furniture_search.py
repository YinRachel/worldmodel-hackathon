"""Server-side UK shopping search. Persist only normalized public product data."""
import hashlib
import json
import os
from pathlib import Path
import time
from threading import Lock
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'outputs/shopping-cache.json'
LOCK = Lock()

def safe_url(value):
    return value if isinstance(value, str) and urlparse(value).scheme == 'https' else None

def normalize(row):
    identity = str(row.get('product_id') or row.get('product_link') or row.get('title')) + str(row.get('source',''))
    return {'id': 'shopping-' + hashlib.sha256(identity.encode()).hexdigest()[:24],
            'name': row.get('title', 'Unnamed product'), 'retailer': row.get('source'),
            'price': row.get('price'), 'price_value': row.get('extracted_price'),
            'currency': 'GBP' if str(row.get('price','')).startswith('£') else None,
            'product_url': safe_url(row.get('product_link') or row.get('link')),
            'image_url': safe_url(row.get('thumbnail')),
            'dimensions_cm': {'width': None, 'depth': None, 'height': None},
            'dimensions_note': 'Dimensions not verified. Check the retailer listing.',
            'is_demo': False, 'source': 'SerpApi Google Shopping',
            'retrieved_at': time.time()}

def read_cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}

def get_product(product_id):
    with LOCK:
        for entry in read_cache().values():
            for p in entry['products']:
                if p['id'] == product_id:
                    return p
    return None

def search_catalog(query=''):
    query=query.strip()[:200]
    if not query:
        return []
    with LOCK:
        cache=read_cache()
        entry=cache.get(query.lower())
        if entry and time.time()-entry['time'] < 3600:
            return entry['products']
    key=os.environ.get('SERPAPI_API_KEY','').strip()
    if not key:
        key=(ROOT/'serpapi_key.txt').read_text().strip()
    params={'engine':'google_shopping','q':query,'gl':'uk','hl':'en','google_domain':'google.co.uk','api_key':key}
    try:
        with urlopen('https://serpapi.com/search.json?'+urlencode(params),timeout=120) as response:
            result=json.load(response)
    except HTTPError as exc:
        raise ValueError(f'Shopping search returned HTTP {exc.code}. Check SerpApi key and search credits.') from None
    except TimeoutError:
        raise ValueError('Shopping search timed out. Please try again later.') from None
    except URLError:
        raise ValueError('Cannot reach shopping search. Please check network access.') from None
    if result.get('error'):
        raise ValueError(str(result['error']).replace(key,'[REDACTED]')[:500])
    products=[normalize(row) for row in result.get('shopping_results',[])[:12]]
    with LOCK:
        cache=read_cache()
        cache[query.lower()]={'time':time.time(),'products':products}
        CACHE.parent.mkdir(exist_ok=True)
        temp=CACHE.with_suffix('.tmp')
        temp.write_text(json.dumps(cache))
        temp.replace(CACHE)
    return products
