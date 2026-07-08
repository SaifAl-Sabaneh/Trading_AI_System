# apply_emergency_stop_losses.py
import os
import ccxt
import sys
import pandas as pd
import time
from dotenv import load_dotenv

sys.path.append("c:/Users/Asus/Desktop/Project crypto")
import config

load_dotenv("c:/Users/Asus/Desktop/Project crypto/.env")

def run():
    print("Starting DYNAMIC Emergency Stop-Loss Placement Script...")
    
    api_key = os.getenv("EXCHANGE_API_KEY", "")
    secret_key = os.getenv("EXCHANGE_SECRET_KEY", "")
    
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret_key,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    try:
        # 1. Fetch active positions
        positions = exchange.fetch_positions()
        active_positions = []
        for p in positions:
            contracts = float(p.get('contracts', 0.0))
            if contracts > 0:
                active_positions.append(p)
        print(f"Detected {len(active_positions)} active positions on Binance Futures.")
        
        # 2. Iterate positions and check open orders symbol-by-symbol
        for pos in active_positions:
            symbol = pos['symbol']
            side = pos['side'].lower() # 'long' or 'short'
            size = float(pos['contracts'])
            entry_price = float(pos['entryPrice'])
            
            # Fetch open orders for this specific symbol
            try:
                open_orders = exchange.fetch_open_orders(symbol)
            except Exception as oe_err:
                print(f"  Failed to fetch open orders for {symbol}: {oe_err}")
                open_orders = []
                
            # Check if this symbol has an open stop order
            has_sl = False
            for order in open_orders:
                if order.get('stopPrice') is not None:
                    has_sl = True
                    break
            
            if has_sl:
                print(f"  [OK] Stop-Loss already configured for {symbol}.")
                continue
                
            print(f"  [MISSING] Emergency SL needed for {symbol} ({side.upper()} position of size {size})...")
            
            # Fetch OHLCV to calculate ATR
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=50)
                df_pd = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                
                # Calculate True Range and ATR
                df_pd['TR'] = pd.concat([
                    df_pd['High'] - df_pd['Low'],
                    (df_pd['High'] - df_pd['Close'].shift(1)).abs(),
                    (df_pd['Low'] - df_pd['Close'].shift(1)).abs()
                ], axis=1).max(axis=1)
                df_pd['ATR'] = df_pd['TR'].rolling(14).mean()
                
                atr_val = float(df_pd['ATR'].iloc[-1])
                mark_price = float(df_pd['Close'].iloc[-1])
            except Exception as fe:
                print(f"    Failed to fetch ATR for {symbol}: {fe}. Using fallback values.")
                # Fallback ATR = 2.5% of entry price
                atr_val = entry_price * 0.025
                mark_price = entry_price
                
            # Calculate SL price
            sl_mult = config.SL_ATR_MULT_SHORT if side == 'short' else config.SL_ATR_MULT_LONG
            if side == 'long':
                sl_price = entry_price - (sl_mult * atr_val)
                if mark_price <= sl_price:
                    sl_price = mark_price * 0.995 # Protect position if already below target
                sl_side = 'sell'
            else:
                sl_price = entry_price + (sl_mult * atr_val)
                if mark_price >= sl_price:
                    sl_price = mark_price * 1.005 # Protect position if already above target
                sl_side = 'buy'
                
            # Format to exchange's precision
            sl_price_prec = float(exchange.price_to_precision(symbol, sl_price))
            amount_prec = float(exchange.amount_to_precision(symbol, size))
            
            print(f"    Calculated SL: {sl_price_prec:.6f} (Mark: {mark_price:.6f}, Size: {amount_prec})")
            
            # Place the order
            try:
                order = exchange.create_order(
                    symbol=symbol,
                    type='STOP_MARKET',
                    side=sl_side,
                    amount=amount_prec,
                    price=None,
                    params={
                        'stopPrice': sl_price_prec,
                        'reduceOnly': True
                    }
                )
                print(f"    [SUCCESS] Placed SL order ID: {order.get('id')} for {symbol} at {sl_price_prec}")
            except Exception as oe:
                print(f"    [ERROR] Failed to place order for {symbol}: {oe}")
                
            # Sleep briefly to avoid rate limits
            time.sleep(0.5)
            
    except Exception as e:
        print(f"General Error: {e}")

if __name__ == '__main__':
    run()
