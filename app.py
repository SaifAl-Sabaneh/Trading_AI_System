"""
app.py — Gradio Dashboard & Background Scheduler for Hugging Face Spaces

This script:
1. Starts a background thread that runs the trade execution at 3:15 AM Jordan Time (00:15 UTC).
2. Serves a beautiful, responsive web UI dashboard to show stats and logs.
3. Performs a warm-up execution on startup.
"""

import os
import sys
import threading
import time
import pandas as pd
import gradio as gr
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config
from live_order_executor import execute_live_trading, get_exchange_connection, get_futures_balance

# Global status log for dashboard view
status_logs = []

def log_to_dashboard(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    status_logs.append(formatted_msg)
    print(formatted_msg)

def run_scheduler_loop():
    """Background thread running the daily trading script at 00:15 UTC (3:15 AM Jordan time)."""
    log_to_dashboard("Scheduler background thread started.")
    
    # Warm-up run: Execute immediately on startup to verify setup and take today's trade
    try:
        log_to_dashboard("Triggering startup check run...")
        execute_live_trading()
        log_to_dashboard("Startup check run completed successfully.")
    except Exception as e:
        log_to_dashboard(f"Startup run failed: {e}")
        
    while True:
        try:
            now = datetime.utcnow()
            # 00:15 UTC = 3:15 AM Jordan Time
            if now.hour == 0 and now.minute == 15:
                log_to_dashboard("Target time reached (00:15 UTC). Triggering daily trading run...")
                execute_live_trading()
                log_to_dashboard("Daily trading run completed.")
                time.sleep(60) # Prevent multiple triggers in same minute
        except Exception as e:
            log_to_dashboard(f"Error in scheduler loop: {e}")
            
        time.sleep(30) # Check every 30 seconds

# Start the background thread
threading.Thread(target=run_scheduler_loop, daemon=True).start()

# --- Gradio UI Dashboard ---

def get_stats():
    """Reads account state and returns summary metrics for the UI."""
    try:
        exchange = get_exchange_connection()
        balance = get_futures_balance(exchange)
    except Exception as e:
        balance = 0.0
        
    initial_cap = 32.33
    pnl_usd = balance - initial_cap
    pnl_pct = (pnl_usd / initial_cap) * 100 if initial_cap > 0 else 0.0
    
    # Load trade log
    trades_df = pd.DataFrame()
    csv_path = 'executed_trades.csv'
    if os.path.exists(csv_path):
        try:
            trades_df = pd.read_csv(csv_path)
        except Exception:
            pass
            
    total_trades = len(trades_df)
    
    # Calculate win rate
    win_rate = 0.0
    if total_trades > 0 and 'PnL_USD' in trades_df.columns:
        wins = sum(1 for x in trades_df['PnL_USD'] if float(x) > 0)
        win_rate = (wins / total_trades) * 100
        
    return f"${balance:,.2f}", f"${pnl_usd:+,.2f} ({pnl_pct:+.2f}%)", f"{total_trades}", f"{win_rate:.1f}%"

def get_trades_table():
    """Loads and formats the historical trades log."""
    csv_path = 'executed_trades.csv'
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            if not df.empty:
                # Order by exit time descending (most recent first)
                df = df.iloc[::-1]
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=["Ticker", "Direction", "EntryTime", "ExitTime", "EntryPrice", "ExitPrice", "PnL_Pct", "PnL_USD", "ExitReason"])

def get_logs_text():
    """Returns the background log list as a string."""
    return "\n".join(status_logs[-25:])

def force_manual_trigger():
    """Manually triggers a trade execution cycle from the UI button."""
    log_to_dashboard("Manual run triggered from dashboard.")
    try:
        execute_live_trading()
        log_to_dashboard("Manual run finished successfully.")
        return "Manual execution completed successfully. Check logs below."
    except Exception as e:
        log_to_dashboard(f"Manual run failed: {e}")
        return f"Manual execution failed: {e}"

# Build Gradio interface
with gr.Blocks(title="🤖 Quantitative Trading Bot Dashboard", theme=gr.themes.Default()) as demo:
    gr.Markdown("# 🤖 Quantitative Trading Bot Live Dashboard")
    gr.Markdown("Hosted 24/7 on European cloud servers (Ireland) to bypass geographic IP blocks.")
    
    with gr.Row():
        balance_box = gr.Textbox(label="Account Balance", value="$32.33", interactive=False)
        pnl_box = gr.Textbox(label="Total Return (PnL)", value="+$0.00 (0.0%)", interactive=False)
        trades_box = gr.Textbox(label="Total Trades", value="0", interactive=False)
        wr_box = gr.Textbox(label="Win Rate", value="0.0%", interactive=False)
        
    with gr.Row():
        refresh_btn = gr.Button("🔄 Refresh Stats", variant="secondary")
        trigger_btn = gr.Button("⚡ Trigger Manual Execution", variant="primary")
        
    manual_status = gr.Markdown()
    
    gr.Markdown("### 📜 Real-Time Execution Log")
    log_area = gr.TextArea(value="Initializing...", label="Console Logs", interactive=False, max_lines=10)
    
    gr.Markdown("### 📊 Live Trade History")
    trades_table = gr.Dataframe(value=pd.DataFrame(), interactive=False)
    
    # Event listeners
    def refresh_all():
        bal, pnl, trades, wr = get_stats()
        table = get_trades_table()
        logs = get_logs_text()
        return bal, pnl, trades, wr, table, logs
        
    refresh_btn.click(
        fn=refresh_all,
        outputs=[balance_box, pnl_box, trades_box, wr_box, trades_table, log_area]
    )
    
    trigger_btn.click(
        fn=force_manual_trigger,
        outputs=manual_status
    ).then(
        fn=refresh_all,
        outputs=[balance_box, pnl_box, trades_box, wr_box, trades_table, log_area]
    )
    
    # Auto-load on open
    demo.load(
        fn=refresh_all,
        outputs=[balance_box, pnl_box, trades_box, wr_box, trades_table, log_area]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
