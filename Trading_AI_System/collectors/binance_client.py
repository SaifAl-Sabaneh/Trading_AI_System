import urllib.request
import urllib.error
import json
import time
import sys
import os
from typing import Any, Dict, List, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import HTTP_TIMEOUT_SECS, MAX_RETRIES, BINANCE_SPOT_BASE_URL, BINANCE_FUTURES_BASE_URL

class BinanceClient:
    def __init__(self, is_futures: bool = True):
        self.base_url = BINANCE_FUTURES_BASE_URL if is_futures else BINANCE_SPOT_BASE_URL

    def get(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Any]:
        url = f"{self.base_url}{endpoint}"
        if params:
            query_str = "&".join([f"{k}={v}" for k, v in params.items() if v is not None])
            url += f"?{query_str}"
            
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECS) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    return data
            except urllib.error.HTTPError as e:
                if e.code == 429: # Rate limit
                    print(f"Rate limited (429). Backing off {attempt*2}s...", flush=True)
                    time.sleep(attempt * 2)
                elif e.code == 404:
                    return None
                else:
                    print(f"HTTP Error {e.code} for {url}: {e.reason}", flush=True)
                    time.sleep(1)
            except Exception as e:
                print(f"Request error (attempt {attempt}/{MAX_RETRIES}) for {url}: {e}", flush=True)
                time.sleep(1)
                
        return None

if __name__ == "__main__":
    client = BinanceClient(is_futures=True)
    ping = client.get("/fapi/v1/ping")
    print("Ping Binance Futures API:", ping)
