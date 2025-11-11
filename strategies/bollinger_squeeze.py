import logging
import pandas as pd
import MetaTrader5 as mt
from helpers import get_env_var
from strategies.strategy_base import Strategy

class Bollinger_Squeeze(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.period = get_env_var('BOLLINGER_SQUEEZE_PERIOD', 20, int)
        self.std_dev = get_env_var('BOLLINGER_SQUEEZE_STD_DEV', 2.0, float)
        self.lookback = get_env_var('BOLLINGER_SQUEEZE_LOOKBACK', 100, int)
        self.sl_mult = get_env_var('BOLLINGER_SQUEEZE_SL_ATR_MULT', 2.0, float)
        self.tp_mult = get_env_var('BOLLINGER_SQUEEZE_TP_ATR_MULT', 4.0, float)
        self.atr_period = 14
        logging.info(f"{self.symbol} [Bollinger_Squeeze]: Strategi aktif (period={self.period}, lookback={self.lookback})")

    def check_signal(self, ohlc, tick):
        if len(ohlc) < self.lookback: return

        # 1. Hitung Bollinger Bands dan Bandwidth
        middle_band = ohlc['close'].rolling(window=self.period).mean()
        std = ohlc['close'].rolling(window=self.period).std()
        upper_band = middle_band + (std * self.std_dev)
        lower_band = middle_band - (std * self.std_dev)
        bandwidth = (upper_band - lower_band) / middle_band

        # 2. Cek Kondisi Squeeze
        # Squeeze terjadi jika bandwidth candle sebelumnya adalah yang terendah dalam periode lookback
        is_in_squeeze = bandwidth.iloc[-3] <= bandwidth.iloc[-self.lookback:-3].min()
        
        if not is_in_squeeze:
            return

        # 3. Jika sedang dalam squeeze, cek sinyal breakout pada candle terakhir
        signal_candle = ohlc.iloc[-2]
        
        atr_val = self._calculate_atr(ohlc).iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = (tick.ask * 0.005)

        # 4. Sinyal BUY: Tutup di atas Upper Band
        if signal_candle['close'] > upper_band.iloc[-2]:
            logging.info(f"{self.symbol}: Sinyal Bollinger Squeeze BUY terdeteksi.")
            sl_ideal = tick.ask - (atr_val * self.sl_mult)
            tp_ideal = tick.ask + (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
            return

        # 5. Sinyal SELL: Tutup di bawah Lower Band
        if signal_candle['close'] < lower_band.iloc[-2]:
            logging.info(f"{self.symbol}: Sinyal Bollinger Squeeze SELL terdeteksi.")
            sl_ideal = tick.bid + (atr_val * self.sl_mult)
            tp_ideal = tick.bid - (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)

    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()
 