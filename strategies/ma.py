import logging
from helpers import get_env_var
from strategies.strategy_base import Strategy
import pandas as pd
import MetaTrader5 as mt

class Ma_Crossover(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.fast_period = get_env_var('MA_CROSSOVER_FAST_PERIOD', 9, int)
        self.slow_period = get_env_var('MA_CROSSOVER_SLOW_PERIOD', 21, int)
        self.sl_mult = get_env_var('MA_CROSSOVER_SL_ATR_MULT', 2.0, float)
        self.tp_mult = get_env_var('MA_CROSSOVER_TP_ATR_MULT', 4.0, float)
        self.atr_period = 14 # Menggunakan ATR untuk SL/TP
        logging.info(f"{self.symbol} [Ma_Crossover]: Strategi aktif (fast={self.fast_period}, slow={self.slow_period})")

    def check_signal(self, ohlc, tick):
        # 1. Hitung Moving Averages
        fast_ma = ohlc['close'].rolling(window=self.fast_period).mean()
        slow_ma = ohlc['close'].rolling(window=self.slow_period).mean()

        # 2. Identifikasi sinyal crossover pada candle terakhir yang sudah close
        # Kita butuh 3 candle terakhir untuk mendeteksi cross: [-3] dan [-2]
        # [-1] adalah candle yang sedang berjalan
        prev_fast = fast_ma.iloc[-3]
        prev_slow = slow_ma.iloc[-3]
        last_fast = fast_ma.iloc[-2]
        last_slow = slow_ma.iloc[-2]
        
        atr_val = self._calculate_atr(ohlc).iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = (tick.ask * 0.005)

        # 3. Cek Sinyal BUY (Golden Cross)
        if prev_fast < prev_slow and last_fast > last_slow:
            logging.info(f"{self.symbol}: Sinyal Golden Cross terdeteksi.")
            sl_ideal = tick.ask - (atr_val * self.sl_mult)
            tp_ideal = tick.ask + (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
            return

        # 4. Cek Sinyal SELL (Death Cross)
        if prev_fast > prev_slow and last_fast < last_slow:
            logging.info(f"{self.symbol}: Sinyal Death Cross terdeteksi.")
            sl_ideal = tick.bid + (atr_val * self.sl_mult)
            tp_ideal = tick.bid - (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)

    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()
