import logging
import pandas as pd
import MetaTrader5 as mt
from helpers import get_env_var
from strategies.strategy_base import Strategy


class Fakeout(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.lookback = get_env_var('FAKEOUT_CANDLE_LOOKBACK', 50, int); self.sl_mult = get_env_var('FAKEOUT_SL_ATR_MULT', 1.2, float)
        self.tp_mult = get_env_var('FAKEOUT_TP_ATR_MULT', 2.5, float); self.atr_period = 14
    def check_signal(self, ohlc, tick):
        if ohlc.shape[0] < self.lookback + 2: return
        lookback_data = ohlc.iloc[-(self.lookback + 2):-2]
        max_high = lookback_data['high'].max(); min_low = lookback_data['low'].min()
        signal_candle = ohlc.iloc[-2]
        atr_series = self._calculate_atr(ohlc); atr_val = atr_series.iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = (tick.ask * 0.005)
        if signal_candle['high'] > max_high and signal_candle['close'] < max_high:
            logging.info(f"{self.symbol}: Sinyal Bullish FAKEOUT terdeteksi di {max_high:.{self.digits}f}")
            sl_ideal = signal_candle['high'] + (atr_val * self.sl_mult); tp_ideal = tick.bid - (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)
            return
        if signal_candle['low'] < min_low and signal_candle['close'] > min_low:
            logging.info(f"{self.symbol}: Sinyal Bearish FAKEOUT terdeteksi di {min_low:.{self.digits}f}")
            sl_ideal = signal_candle['low'] - (atr_val * self.sl_mult); tp_ideal = tick.ask + (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']; tr1 = high - low; tr2 = (high - close.shift(1)).abs(); tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1); return tr.rolling(self.atr_period).mean()
