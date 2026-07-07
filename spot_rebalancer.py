"""
spot_rebalancer.py — Automatic Spot Portfolio Rebalancer

Automates weekly rebalancing of Spot assets on Binance according to config targets.
Executes Sell trades first to free up capital, then executes Buy trades with fallbacks.
"""
import os
import sys
import ccxt
import dotenv
import pandas as pd

sys.path.append(r"c:\Users\Asus\Desktop\Project crypto")
import config
from security import logger, send_push_notification

dotenv.load_dotenv(r"c:\Users\Asus\Desktop\Project crypto\.env")

def run_spot_rebalancer():
    logger.info("Starting Spot Portfolio Rebalancing Engine...")
    
    api_key = os.getenv("EXCHANGE_API_KEY", "")
    secret_key = os.getenv("EXCHANGE_SECRET_KEY", "")
    
    if not api_key or not secret_key:
        logger.error("API keys missing from environment. Rebalancing halted.")
        return
        
    if not getattr(config, 'ENABLE_SPOT_REBALANCING', False):
        logger.info("Spot rebalancing is disabled in config.py.")
        return
        
    try:
        # Initialize Spot exchange client
        spot_exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        spot_exchange.load_markets()
        
        # 1. Fetch current balances
        balances = spot_exchange.fetch_balance()
        usdt_balance = float(balances['free'].get('USDT', 0.0))
        
        # Target configurations
        allocations = config.SPOT_REBALANCE_ALLOCATION
        total_assets_val_usdt = 0.0
        
        holdings = {}
        prices = {}
        
        # 2. Get current values for target assets
        for yf_ticker, target_ratio in allocations.items():
            base = yf_ticker.split("-")[0]
            if base == "SUI20947": base = "SUI"
            if base == "TON11419": base = "TON"
            spot_symbol = f"{base}/USDT"
            
            # Fetch current free balance of base asset
            asset_balance = float(balances['free'].get(base, 0.0))
            
            # Fetch latest price
            ticker_info = spot_exchange.fetch_ticker(spot_symbol)
            price = float(ticker_info['close'])
            
            val_usdt = asset_balance * price
            total_assets_val_usdt += val_usdt
            
            holdings[spot_symbol] = {
                'base': base,
                'balance': asset_balance,
                'current_value': val_usdt,
                'target_ratio': target_ratio
            }
            prices[spot_symbol] = price
            
        # Total portfolio value under management (Target assets + USDT cash)
        total_portfolio_value = total_assets_val_usdt + usdt_balance
        logger.info(f"Total Spot Portfolio Value: ${total_portfolio_value:,.2f} USDT (Cash: ${usdt_balance:,.2f} USDT)")
        
        if total_portfolio_value < 10.0:
            logger.warning("Total Spot Portfolio value too small to rebalance (< $10.00). Halted.")
            return
            
        trades_to_execute = []
        
        # 3. Calculate target values and deviations
        for symbol, info in holdings.items():
            target_value = total_portfolio_value * info['target_ratio']
            difference = target_value - info['current_value']
            
            # Percent deviation from target
            deviation = abs(difference) / target_value if target_value > 0 else 0.0
            
            logger.info(f"{info['base']}: Current Value: ${info['current_value']:.2f} | Target: ${target_value:.2f} | Deviation: {deviation:.2%}")
            
            if deviation > getattr(config, 'SPOT_REBALANCE_THRESHOLD', 0.03):
                trades_to_execute.append({
                    'symbol': symbol,
                    'base': info['base'],
                    'diff_usdt': difference,
                    'price': prices[symbol]
                })
                
        if not trades_to_execute:
            logger.info("All spot holdings are within allocation thresholds. No rebalancing needed.")
            return
            
        # Sort trades: SELLS FIRST (diff_usdt < 0) to free up USDT cash, then BUYS second
        trades_to_execute = sorted(trades_to_execute, key=lambda x: x['diff_usdt'])
        
        executed_trades_log = []
        
        # 4. Execute trades
        for trade in trades_to_execute:
            symbol = trade['symbol']
            diff = trade['diff_usdt']
            price = trade['price']
            
            if diff < 0:
                # Over-allocated: SELL to reduce size
                sell_val = abs(diff)
                qty = sell_val / price
                qty_str = spot_exchange.amount_to_precision(symbol, qty)
                qty_float = float(qty_str)
                
                # Check minimum trade requirements (Binance generally requires min $5-$10 value)
                if (qty_float * price) >= 5.0:
                    logger.info(f"Rebalance: Placing MARKET SELL order for {symbol} of {qty_float:.6f} quantity...")
                    order = spot_exchange.create_market_sell_order(symbol, qty_float)
                    filled_qty = float(order.get('amount', qty_float))
                    logger.info(f"Rebalance: Sold {filled_qty:.6f} {trade['base']} successfully.")
                    executed_trades_log.append(f"• **SELL** {trade['base']} | Value: `${sell_val:.2f} USDT`")
                else:
                    logger.warning(f"Rebalance: Sell order value for {symbol} is too small (${qty_float * price:.2f}). Skipped.")
                    
            elif diff > 0:
                # Under-allocated: BUY to increase size
                buy_val = diff
                # Check available cash
                balances = spot_exchange.fetch_balance()
                current_usdt = float(balances['free'].get('USDT', 0.0))
                
                # Cap the buy cost at the actual available USDT balance
                actual_cost = min(buy_val, current_usdt)
                
                if actual_cost >= 5.0:
                    logger.info(f"Rebalance: Placing MARKET BUY order for {symbol} with cost {actual_cost:.2f} USDT...")
                    try:
                        order = spot_exchange.create_market_buy_order_with_cost(symbol, actual_cost)
                    except Exception as e:
                        logger.info(f"create_market_buy_order_with_cost failed: {e}. Falling back to standard buy...")
                        # 0.5% safety buffer for price slippage
                        safe_cost = actual_cost * 0.995
                        qty = safe_cost / price
                        qty_str = spot_exchange.amount_to_precision(symbol, qty)
                        order = spot_exchange.create_market_buy_order(symbol, float(qty_str))
                        
                    filled_qty = float(order.get('amount', 0.0))
                    logger.info(f"Rebalance: Bought {filled_qty:.6f} {trade['base']} successfully.")
                    executed_trades_log.append(f"• **BUY** {trade['base']} | Value: `${actual_cost:.2f} USDT`")
                else:
                    logger.warning(f"Rebalance: Buy order value for {symbol} is too small (${actual_cost:.2f}) or insufficient USDT cash.")
                    
        # 5. Send report
        if executed_trades_log:
            summary_lines = "\n".join(executed_trades_log)
            send_push_notification(
                f"🔄 **[SPOT REBALANCED]** Portfolio rebalancing complete!\n\n"
                f"**Executed Trades**:\n{summary_lines}\n\n"
                f"• Total Spot Portfolio Value: **${total_portfolio_value:,.2f} USDT**"
            )
        else:
            logger.info("Spot rebalancer finished with no trades executed.")
            
    except Exception as e:
        logger.error(f"Spot Rebalancer failed: {e}")
        send_push_notification(f"⚠️ **[WARNING]** Spot Rebalancer error: {e}")

if __name__ == '__main__':
    run_spot_rebalancer()
