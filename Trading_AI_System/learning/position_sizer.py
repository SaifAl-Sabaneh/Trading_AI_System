import numpy as np

class PositionSizer:
    @staticmethod
    def calculate_position_size(win_rate: float, avg_win_pct: float, avg_loss_pct: float, 
                                account_balance: float = 200.0, volatility_state: str = "NORMAL",
                                max_cap_pct: float = 0.10) -> float:
        """
        Calculates Fractional Kelly position size scaled by market volatility state.
        """
        if win_rate <= 0 or avg_loss_pct <= 0:
            return account_balance * 0.05  # Default conservative 5% allocation
            
        b = avg_win_pct / avg_loss_pct # Payoff ratio
        p = win_rate
        q = 1.0 - p
        
        kelly_f = (p * b - q) / b
        
        # Half-Kelly safety multiplier
        half_kelly = max(0.02, kelly_f * 0.5)
        
        # Volatility Scaling
        vol_multiplier = 1.0
        if volatility_state == "EXTREME":
            vol_multiplier = 0.50
        elif volatility_state == "HIGH":
            vol_multiplier = 0.75
        elif volatility_state == "LOW":
            vol_multiplier = 1.10
            
        final_fraction = min(max_cap_pct, half_kelly * vol_multiplier)
        position_usd = account_balance * final_fraction
        return round(position_usd, 2)

if __name__ == "__main__":
    pos_size = PositionSizer.calculate_position_size(0.55, 0.025, 0.012, 200.0, "NORMAL")
    print(f"Calculated Fractional Kelly Position Size: ${pos_size} USD")
