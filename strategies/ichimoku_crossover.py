import MetaTrader5 as mt
import pandas as pd
import logging
from .strategy_base import Strategy
from helpers import get_env_var

class Ichimoku_Crossover(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.tenkan_p = get_env_var('ICHIMOKU_TENKAN_PERIOD', 9, int)
        self.kijun_p = get_env_var('ICHIMOKU_KIJUN_PERIOD', 26, int)
        self.senkou_b_p = get_env_var('ICHIMOKU_SENKOU_B_PERIOD', 52, int)
        self.sl_mult = get_env_var('ICHIMOKU_SL_ATR_MULT', 2.5, float)
        self.tp_mult = get_env_var('ICHIMOKU_TP_ATR_MULT', 5.0, float)
        self.atr_period = 14
        logging.info(f"{self.symbol} [Ichimoku_Crossover]: Strategi aktif (p={self.tenkan_p},{self.kijun_p},{self.senkou_b_p})")

    def check_signal(self, ohlc, tick):
        # 1. Hitung semua komponen Ichimoku
        # Tenkan-sen (Conversion Line)
        tenkan_high = ohlc['high'].rolling(window=self.tenkan_p).max()
        tenkan_low = ohlc['low'].rolling(window=self.tenkan_p).min()
        tenkan_sen = (tenkan_high + tenkan_low) / 2

        # Kijun-sen (Base Line)
        kijun_high = ohlc['high'].rolling(window=self.kijun_p).max()
        kijun_low = ohlc['low'].rolling(window=self.kijun_p).min()
        kijun_sen = (kijun_high + kijun_low) / 2

        # Senkou Span A (Leading Span A)
        senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(self.kijun_p)

        # Senkou Span B (Leading Span B)
        senkou_b_high = ohlc['high'].rolling(window=self.senkou_b_p).max()
        senkou_b_low = ohlc['low'].rolling(window=self.senkou_b_p).min()
        senkou_b = ((senkou_b_high + senkou_b_low) / 2).shift(self.kijun_p)
        
        # Chikou Span (Lagging Span)
        chikou_span = ohlc['close'].shift(-self.kijun_p)

        # 2. Ambil nilai-nilai terbaru untuk pengecekan sinyal
        # Kita butuh 3 candle terakhir untuk mendeteksi cross: [-3] (sebelum cross) dan [-2] (setelah cross)
        # [-1] adalah candle yang sedang berjalan
        if len(ohlc) < self.senkou_b_p + self.kijun_p: return

        prev_tenkan = tenkan_sen.iloc[-3]
        prev_kijun = kijun_sen.iloc[-3]
        last_tenkan = tenkan_sen.iloc[-2]
        last_kijun = kijun_sen.iloc[-2]
        
        last_close = ohlc['close'].iloc[-2]
        
        # Nilai Kumo (Awan) pada saat candle sinyal terjadi
        # Ingat, Kumo diproyeksikan ke depan, jadi kita lihat nilai Kumo di masa lalu
        kumo_a_at_signal = senkou_a.iloc[-2]
        kumo_b_at_signal = senkou_b.iloc[-2]
        
        # Nilai Chikou Span
        chikou_at_signal = chikou_span.iloc[-2-self.kijun_p] # Chikou saat ini
        price_for_chikou = ohlc['close'].iloc[-2-self.kijun_p] # Harga yang dibandingkan dengan Chikou

        atr_val = self._calculate_atr(ohlc).iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: atr_val = (tick.ask * 0.005)

        # 3. Cek Sinyal BUY (Golden Cross di atas Kumo)
        is_bullish_cross = prev_tenkan < prev_kijun and last_tenkan > last_kijun
        is_above_kumo = last_close > kumo_a_at_signal and last_close > kumo_b_at_signal
        is_chikou_free_bullish = chikou_at_signal > price_for_chikou
        
        if is_bullish_cross and is_above_kumo and is_chikou_free_bullish:
            logging.info(f"{self.symbol}: Sinyal Ichimoku Golden Cross (STRONG) terdeteksi.")
            sl_ideal = tick.ask - (atr_val * self.sl_mult)
            tp_ideal = tick.ask + (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
            return

        # 4. Cek Sinyal SELL (Death Cross di bawah Kumo)
        is_bearish_cross = prev_tenkan > prev_kijun and last_tenkan < last_kijun
        is_below_kumo = last_close < kumo_a_at_signal and last_close < kumo_b_at_signal
        is_chikou_free_bearish = chikou_at_signal < price_for_chikou

        if is_bearish_cross and is_below_kumo and is_chikou_free_bearish:
            logging.info(f"{self.symbol}: Sinyal Ichimoku Death Cross (STRONG) terdeteksi.")
            sl_ideal = tick.bid + (atr_val * self.sl_mult)
            tp_ideal = tick.bid - (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)
            
    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()