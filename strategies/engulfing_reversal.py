import logging
import pandas as pd
import MetaTrader5 as mt
from helpers import get_env_var
from strategies.strategy_base import Strategy


class Engulfing_Reversal(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.trend_lookback = get_env_var('ENGULFING_REVERSAL_TREND_LOOKBACK', 5, int)
        self.sl_mult = get_env_var('ENGULFING_REVERSAL_SL_ATR_MULT', 1.5, float)
        self.tp_mult = get_env_var('ENGULFING_REVERSAL_TP_ATR_MULT', 3.0, float)
        self.atr_period = 14
        logging.info(f"{self.symbol} [Engulfing_Reversal]: Strategi aktif (lookback={self.trend_lookback})")

    def check_signal(self, ohlc, tick):
        # Kita butuh setidaknya 3 candle untuk mengevaluasi pola
        if len(ohlc) < self.trend_lookback + 3: return

        # Identifikasi candle
        prev_candle = ohlc.iloc[-3]
        signal_candle = ohlc.iloc[-2]
        
        atr_val = self._calculate_atr(ohlc).iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = (tick.ask * 0.005)

        # Cek Sinyal Bullish Engulfing (untuk BUY)
        # 1. Candle sebelumnya harus bearish.
        # 2. Candle sinyal harus bullish.
        # 3. Badan candle sinyal harus "memakan" badan candle sebelumnya.
        # 4. (Filter) Pola ini harus terjadi di dekat level terendah baru-baru ini.
        is_bullish_engulfing = (prev_candle['close'] < prev_candle['open'] and
                                signal_candle['close'] > signal_candle['open'] and
                                signal_candle['open'] < prev_candle['close'] and
                                signal_candle['close'] > prev_candle['open'] and
                                signal_candle['low'] <= ohlc['low'].iloc[-self.trend_lookback-2:-2].min())
                                
        if is_bullish_engulfing:
            logging.info(f"{self.symbol}: Sinyal Bullish Engulfing terdeteksi.")
            sl_ideal = signal_candle['low'] - (atr_val * self.sl_mult)
            tp_ideal = tick.ask + (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
            return

        # Cek Sinyal Bearish Engulfing (untuk SELL)
        is_bearish_engulfing = (prev_candle['close'] > prev_candle['open'] and
                                signal_candle['close'] < signal_candle['open'] and
                                signal_candle['open'] > prev_candle['close'] and
                                signal_candle['close'] < prev_candle['open'] and
                                signal_candle['high'] >= ohlc['high'].iloc[-self.trend_lookback-2:-2].max())

        if is_bearish_engulfing:
            logging.info(f"{self.symbol}: Sinyal Bearish Engulfing terdeteksi.")
            sl_ideal = signal_candle['high'] + (atr_val * self.sl_mult)
            tp_ideal = tick.bid - (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)

    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()
