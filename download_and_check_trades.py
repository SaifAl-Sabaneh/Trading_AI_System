import urllib.request
import zipfile
import os
import io
import pandas as pd

def download_and_audit_trades(symbol="SOLUSDT", date_str="2026-07-15"):
    # Binance Vision daily futures (USD-margined) trades URL template:
    # Example: https://data.binance.vision/data/futures/um/daily/trades/SOLUSDT/SOLUSDT-trades-2026-07-15.zip
    url = f"https://data.binance.vision/data/futures/um/daily/trades/{symbol}/{symbol}-trades-{date_str}.zip"
    
    print(f"Downloading daily trade data for {symbol} on {date_str}...")
    print(f"URL: {url}")
    
    local_zip = f"{symbol}-trades-{date_str}.zip"
    local_csv = f"{symbol}-trades-{date_str}.csv"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            zip_data = response.read()
            
        with open(local_zip, "wb") as f:
            f.write(zip_data)
        print("  Download complete. Unzipping file...")
        
        with zipfile.ZipFile(local_zip, 'r') as zip_ref:
            zip_ref.extractall(".")
            
        print(f"  Extracted trade file: {local_csv}")
        
        # Audit schema
        # Binance Vision trade CSVs do not contain a header.
        # Column schema:
        # 0: id (Trade ID)
        # 1: price
        # 2: qty (Base asset quantity)
        # 3: quote_qty (Quote asset quantity)
        # 4: time (Epoch millisecond)
        # 5: is_buyer_maker (True/False - if True, taker was Seller. If False, taker was Buyer)
        
        df = pd.read_csv(local_csv)
        
        print("\n" + "=" * 60)
        print("  DAILY TRADE DATA AUDIT RESULTS")
        print("=" * 60)
        print(f"Total Trades Logged:  {len(df):,}")
        print(f"First Trade Time:     {pd.to_datetime(df['time'].iloc[0], unit='ms')} UTC")
        print(f"Last Trade Time:      {pd.to_datetime(df['time'].iloc[-1], unit='ms')} UTC")
        print(f"Unique Price Ticks:   {df['price'].nunique():,}")
        print(f"Total Base Volume:    {df['qty'].sum():,.2f} {symbol[:-4]}")
        print(f"Total Quote Volume:   {df['quote_qty'].sum():,.2f} USDT")
        print("-" * 60)
        print("First 5 Raw Trade Records:")
        print(df.head(5).to_string())
        print("=" * 60)
        
        # Clean up zip
        if os.path.exists(local_zip):
            os.remove(local_zip)
            
        return local_csv
    except Exception as e:
        print(f"\n[ERROR] Failed to download or audit data: {e}")
        return None

if __name__ == '__main__':
    download_and_audit_trades()
