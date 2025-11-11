import MetaTrader5 as mt
from helpers import get_env_var, AGGRESSION_LEVEL # Kita akan buat file helpers
import pandas as pd
import logging

from strategies.strategy_base import Strategy

class Breakout(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.atr_period = get_env_var('BREAKOUT_ATR_PERIOD', 14, int); self.sl_mult = get_env_var('BREAKOUT_SL_ATR_MULT', 1.5, float)
        self.tp_mult = get_env_var('BREAKOUT_TP_ATR_MULT', 3.0, float); self.lookback = get_env_var('BREAKOUT_CANDLE_LOOKBACK', 100, int)
        self.validate_candle = get_env_var('BREAKOUT_VALIDATE_CANDLE', True, bool)
        self.min_body_ratio = get_env_var('BREAKOUT_MIN_BODY_RATIO', 0.4, float); self.vol_mult = get_env_var('BREAKOUT_VOLUME_MULT', 1.2, float)
        self.vol_period = get_env_var('BREAKOUT_VOLUME_PERIOD', 10, int)
        base_confirmation = get_env_var('BREAKOUT_MIN_CONFIRMATION_CANDLES', 2, int)
        if AGGRESSION_LEVEL == 'high': self.confirmation = 1
        elif AGGRESSION_LEVEL == 'low': self.confirmation = base_confirmation + 1
        else: self.confirmation = base_confirmation
    def check_signal(self, ohlc, tick):
        atr_series = self._calculate_atr(ohlc); atr_val = atr_series.iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = (tick.ask * 0.005)
        long_setup = self._is_confirmed(ohlc, 'long'); short_setup = self._is_confirmed(ohlc, 'short')
        if long_setup:
            if self.validate_candle and not self._is_breakout_candle_valid(ohlc, 'long'): return
            sl_ideal = tick.ask - (atr_val * self.sl_mult); tp_ideal = tick.ask + (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
        elif short_setup:
            if self.validate_candle and not self._is_breakout_candle_valid(ohlc, 'short'): return
            sl_ideal = tick.bid + (atr_val * self.sl_mult); tp_ideal = tick.bid - (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)
    def _is_confirmed(self, ohlc_df, direction='long'):
        if ohlc_df.shape[0] < self.lookback + self.confirmation + 1: return False
        lookback_data = ohlc_df.iloc[-(self.lookback + self.confirmation + 1):-(self.confirmation + 1)]
        confirm_data = ohlc_df.iloc[-(self.confirmation + 1):-1]
        if direction == 'long': return (confirm_data['close'] > lookback_data['high'].max()).all()
        else: return (confirm_data['close'] < lookback_data['low'].min()).all()
    def _is_breakout_candle_valid(self, ohlc_df, direction):
        breakout_candle = ohlc_df.iloc[-2]; total_range = breakout_candle['high'] - breakout_candle['low']
        body_size = abs(breakout_candle['close'] - breakout_candle['open'])
        if total_range > 0 and (body_size / total_range) < self.min_body_ratio: logging.info(f"{self.symbol}: Breakout DITOLAK. Badan candle terlalu kecil."); return False
        avg_volume = ohlc_df['tick_volume'].iloc[-self.vol_period-2:-2].mean()
        if breakout_candle['tick_volume'] < avg_volume * self.vol_mult: logging.info(f"{self.symbol}: Breakout DITOLAK. Volume terlalu rendah."); return False
        mid_point = (breakout_candle['high'] + breakout_candle['low']) / 2
        if (direction == 'long' and breakout_candle['close'] < mid_point) or (direction == 'short' and breakout_candle['close'] > mid_point):
            logging.info(f"{self.symbol}: Breakout DITOLAK. Penutupan candle lemah."); return False
        logging.info(f"{self.symbol}: Kualitas breakout TERVALIDASI."); return True
    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']; tr1 = high - low; tr2 = (high - close.shift(1)).abs(); tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1); return tr.rolling(self.atr_period).mean()
