import urllib.request
import zipfile
import os
import io
import pandas as pd
from datetime import datetime, timedelta

def download_and_extract_range(symbol="SOLUSDT", start_date_str="2026-07-10", end_date_str="2026-07-16"):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    current_date = start_date
    dates = []
    while current_date <= end_date:
        dates.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)
        
    print("=" * 80)
    print(f"  DOWNLOADING BATCH DATA FOR {symbol} ({start_date_str} to {end_date_str})")
    print("=" * 80)
    
    extracted_files = []
    
    for date_str in dates:
        url = f"https://data.binance.vision/data/futures/um/daily/trades/{symbol}/{symbol}-trades-{date_str}.zip"
        local_zip = f"{symbol}-trades-{date_str}.zip"
        local_csv = f"{symbol}-trades-{date_str}.csv"
        
        # Check if CSV already exists to avoid redundant download
        if os.path.exists(local_csv):
            print(f"  {local_csv} already exists. Skipping download.")
            extracted_files.append(local_csv)
            continue
            
        print(f"Downloading {date_str}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                zip_data = response.read()
                
            with open(local_zip, "wb") as f:
                f.write(zip_data)
                
            with zipfile.ZipFile(local_zip, 'r') as zip_ref:
                zip_ref.extractall(".")
                
            print(f"    Extracted: {local_csv}")
            extracted_files.append(local_csv)
            
            if os.path.exists(local_zip):
                os.remove(local_zip)
        except Exception as e:
            print(f"    [ERROR] Failed to download {date_str}: {e}")
            
    print(f"\nBatch download completed. Total successfully retrieved files: {len(extracted_files)}/{len(dates)}")
    return extracted_files

if __name__ == '__main__':
    download_and_extract_range()
