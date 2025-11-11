import MetaTrader5 as mt
import pandas as pd
import numpy as np
import logging
from .strategy_base import Strategy
from helpers import get_env_var

class Stochastic_Divergence(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.k_period = get_env_var('STOCHASTIC_DIVERGENCE_K_PERIOD', 14, int)
        self.d_period = get_env_var('STOCHASTIC_DIVERGENCE_D_PERIOD', 3, int)
        self.smoothing = get_env_var('STOCHASTIC_DIVERGENCE_SMOOTHING', 3, int)
        self.lookback = get_env_var('STOCHASTIC_DIVERGENCE_LOOKBACK', 30, int)
        self.sl_mult = get_env_var('STOCHASTIC_DIVERGENCE_SL_ATR_MULT', 1.5, float)
        self.tp_mult = get_env_var('STOCHASTIC_DIVERGENCE_TP_ATR_MULT', 3.0, float)
        self.atr_period = 14
        logging.info(f"{self.symbol} [Stochastic_Divergence]: Strategi aktif (k={self.k_period}, lookback={self.lookback})")

    def check_signal(self, ohlc, tick):
        # 1. Hitung Stochastic Oscillator (%K dan %D)
        low_k = ohlc['low'].rolling(window=self.k_period).min()
        high_k = ohlc['high'].rolling(window=self.k_period).max()
        percent_k = 100 * ((ohlc['close'] - low_k) / (high_k - low_k))
        percent_d = percent_k.rolling(window=self.d_period).mean()

        # Kita perlu data yang cukup
        if len(ohlc) < self.lookback + 5: return

        # Ambil data harga dan stochastic untuk periode lookback
        prices = ohlc['close'].iloc[-self.lookback:]
        stoch = percent_d.iloc[-self.lookback:]

        atr_val = self._calculate_atr(ohlc).iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = (tick.ask * 0.005)

        # 2. Cek Sinyal Bearish Divergence (untuk SELL)
        # Cari puncak signifikan (swing high) pada harga
        price_pivots_high_idx = (prices.shift(1) < prices) & (prices.shift(-1) < prices)
        price_swing_highs = prices[price_pivots_high_idx]

        if len(price_swing_highs) >= 2:
            # Ambil dua puncak harga terakhir
            last_price_peak = price_swing_highs.iloc[-1]
            prev_price_peak = price_swing_highs.iloc[-2]
            
            # Kondisi: Puncak harga naik (Higher High)
            if last_price_peak > prev_price_peak:
                # Cari puncak stochastic yang sesuai
                stoch_at_last_peak = stoch.loc[price_swing_highs.index[-1]]
                stoch_at_prev_peak = stoch.loc[price_swing_highs.index[-2]]
                
                # Kondisi: Puncak stochastic turun (Lower High)
                if stoch_at_last_peak < stoch_at_prev_peak:
                    logging.info(f"{self.symbol}: Sinyal Bearish Divergence Stochastic terdeteksi.")
                    sl_ideal = tick.bid + (atr_val * self.sl_mult)
                    tp_ideal = tick.bid - (atr_val * self.tp_mult)
                    sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
                    self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)
                    return # Hentikan jika sinyal ditemukan

        # 3. Cek Sinyal Bullish Divergence (untuk BUY)
        # Cari lembah signifikan (swing low) pada harga
        price_pivots_low_idx = (prices.shift(1) > prices) & (prices.shift(-1) > prices)
        price_swing_lows = prices[price_pivots_low_idx]

        if len(price_swing_lows) >= 2:
            # Ambil dua lembah harga terakhir
            last_price_valley = price_swing_lows.iloc[-1]
            prev_price_valley = price_swing_lows.iloc[-2]

            # Kondisi: Lembah harga turun (Lower Low)
            if last_price_valley < prev_price_valley:
                # Cari lembah stochastic yang sesuai
                stoch_at_last_valley = stoch.loc[price_swing_lows.index[-1]]
                stoch_at_prev_valley = stoch.loc[price_swing_lows.index[-2]]

                # Kondisi: Lembah stochastic naik (Higher Low)
                if stoch_at_last_valley > stoch_at_prev_valley:
                    logging.info(f"{self.symbol}: Sinyal Bullish Divergence Stochastic terdeteksi.")
                    sl_ideal = tick.ask - (atr_val * self.sl_mult)
                    tp_ideal = tick.ask + (atr_val * self.tp_mult)
                    sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
                    self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
                    
    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()