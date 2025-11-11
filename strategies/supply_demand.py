import MetaTrader5 as mt
import pandas as pd
import logging
from .strategy_base import Strategy
from helpers import get_env_var

class Supply_Demand(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.lookback = get_env_var('SUPPLY_DEMAND_LOOKBACK', 150, int)
        self.explosive_mult = get_env_var('SUPPLY_DEMAND_EXPLOSIVE_MULT', 2.0, float)
        self.sl_buffer_atr = get_env_var('SUPPLY_DEMAND_SL_BUFFER_ATR', 0.5, float)
        self.tp_mult = get_env_var('SUPPLY_DEMAND_TP_ATR_MULT', 3.0, float)
        self.atr_period = 14
        self.last_tested_zones = {} # Untuk melacak zona yang sudah diuji
        logging.info(f"{self.symbol} [Supply_Demand]: Strategi aktif (lookback={self.lookback})")

    def check_signal(self, ohlc, tick):
        if len(ohlc) < self.lookback: return

        atr_val = self._calculate_atr(ohlc).iloc[-1]
        if pd.isna(atr_val) or atr_val == 0: return

        # 1. Cari zona Supply dan Demand yang paling baru dan belum diuji
        last_supply = None
        last_demand = None

        # Iterasi dari candle terbaru ke belakang untuk menemukan zona
        for i in range(2, len(ohlc) - 1):
            base_candle = ohlc.iloc[-i]
            explosive_candle = ohlc.iloc[-i-1] # Candle sebelum base_candle
            
            base_range = abs(base_candle['close'] - base_candle['open'])
            explosive_range = abs(explosive_candle['close'] - explosive_candle['open'])

            if base_range > 0 and explosive_range > (base_range * self.explosive_mult):
                # Ditemukan pola base + explosive candle
                
                # Cek Supply Zone (Drop-Base-Drop atau Rally-Base-Drop)
                if explosive_candle['close'] < explosive_candle['open']: # Candle eksplosif bearish
                    zone_high = base_candle['high']
                    zone_low = base_candle['low']
                    
                    # Jika belum ada supply zone atau zona ini lebih baru
                    if last_supply is None and not self._was_zone_tested(zone_high, zone_low, ohlc.iloc[-i:]):
                        last_supply = {'high': zone_high, 'low': zone_low}
                        
                # Cek Demand Zone (Rally-Base-Rally atau Drop-Base-Rally)
                if explosive_candle['close'] > explosive_candle['open']: # Candle eksplosif bullish
                    zone_high = base_candle['high']
                    zone_low = base_candle['low']

                    if last_demand is None and not self._was_zone_tested(zone_high, zone_low, ohlc.iloc[-i:]):
                        last_demand = {'high': zone_high, 'low': zone_low}
            
            # Hentikan pencarian jika kedua zona sudah ditemukan
            if last_supply and last_demand:
                break

        # 2. Cek sinyal entry
        last_close = ohlc['close'].iloc[-2]

        # Sinyal SELL: Harga masuk ke Supply Zone dari bawah
        if last_supply and (last_close <= last_supply['high']) and (last_close >= last_supply['low']):
            logging.info(f"{self.symbol}: Sinyal Supply Zone terdeteksi. Zona: {last_supply['low']:.{self.digits}f}-{last_supply['high']:.{self.digits}f}")
            sl_ideal = last_supply['high'] + (atr_val * self.sl_buffer_atr)
            tp_ideal = tick.bid - (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_SELL, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_SELL, tick.bid, sl, tp)
            self._mark_zone_as_tested(last_supply['high'], last_supply['low'])
            return

        # Sinyal BUY: Harga masuk ke Demand Zone dari atas
        if last_demand and (last_close <= last_demand['high']) and (last_close >= last_demand['low']):
            logging.info(f"{self.symbol}: Sinyal Demand Zone terdeteksi. Zona: {last_demand['low']:.{self.digits}f}-{last_demand['high']:.{self.digits}f}")
            sl_ideal = last_demand['low'] - (atr_val * self.sl_buffer_atr)
            tp_ideal = tick.ask + (atr_val * self.tp_mult)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
            self._mark_zone_as_tested(last_demand['high'], last_demand['low'])
            
    def _was_zone_tested(self, zone_high, zone_low, future_candles):
        """Cek apakah harga sudah kembali dan menyentuh zona ini."""
        # Cek history internal
        if (zone_high, zone_low) in self.last_tested_zones:
            return True
        # Cek candle setelah zona terbentuk
        for index, candle in future_candles.iterrows():
            if candle['low'] <= zone_high and candle['high'] >= zone_low:
                return True
        return False
        
    def _mark_zone_as_tested(self, zone_high, zone_low):
        """Tandai zona agar tidak ditradingkan lagi."""
        self.last_tested_zones[(zone_high, zone_low)] = True
        # Batasi ukuran dictionary agar tidak terlalu besar
        if len(self.last_tested_zones) > 50:
            self.last_tested_zones.pop(next(iter(self.last_tested_zones)))

    def _calculate_atr(self, ohlc_df):
        high, low, close = ohlc_df['high'], ohlc_df['low'], ohlc_df['close']
        tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()