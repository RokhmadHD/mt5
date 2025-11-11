import MetaTrader5 as mt
import logging
from helpers import AGGRESSION_LEVEL, get_env_var
from strategies.strategy_base import Strategy


class Rsi_Oversold(Strategy):
    def __init__(self, symbol, volume):
        super().__init__(symbol, volume)
        self.period = get_env_var('RSI_OVERSOLD_PERIOD', 14, int); self.level = get_env_var('RSI_OVERSOLD_LEVEL', 30, int)
        self.sl_pips = get_env_var('RSI_OVERSOLD_SL_PIPS', 100, int); self.tp_pips = get_env_var('RSI_OVERSOLD_TP_PIPS', 200, int)
        if AGGRESSION_LEVEL == 'high': self.level = 35
        elif AGGRESSION_LEVEL == 'low': self.level = 25
    def check_signal(self, ohlc, tick):
        delta = ohlc['close'].diff(); gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        if loss.iloc[-1] == 0: return
        rs = gain / loss; rsi = 100 - (100 / (1 + rs)); last_rsi = rsi.iloc[-2]
        if last_rsi < self.level:
            logging.info(f"{self.symbol}: Sinyal RSI Oversold terdeteksi! RSI={last_rsi:.2f} (Level={self.level})")
            sl_ideal = tick.ask - (self.sl_pips * self.point); tp_ideal = tick.ask + (self.tp_pips * self.point)
            sl, tp = self._get_final_sl_tp(mt.ORDER_TYPE_BUY, tick, sl_ideal, tp_ideal)
            self._create_order(mt.ORDER_TYPE_BUY, tick.ask, sl, tp)
