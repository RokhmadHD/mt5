# strategies/strategy_base.py
import MetaTrader5 as mt
from decimal import Decimal, ROUND_HALF_UP
import logging

# Variabel global mt_lock dan order_send_request perlu di-pass atau di-import
# Cara termudah adalah membuatnya bisa diakses secara global (meski bukan praktik terbaik, tapi paling simpel untuk kasus ini)
from main import mt_lock, order_send_request

class Strategy:
    # ... (Tempelkan seluruh isi class Strategy di sini) ...
    def __init__(self, symbol, volume):
        self.symbol = symbol
        self.volume = volume
        self.order_sent = False
        
        # Coba dapatkan info dari MT5 jika terhubung, jika tidak gunakan fallback
        try:
            from main import get_symbol_info # Coba impor
            self.info = get_symbol_info(self.symbol)
        except ImportError:
            self.info = None # Akan diisi oleh backtester nanti

        if self.info:
            self.digits = self.info.digits
            self.point = self.info.point
        else:
            # Nilai fallback default jika tidak terhubung ke MT5 (untuk backtest)
            self.digits = 5 if "JPY" not in symbol.upper() else 3
            self.point = 0.00001 if "JPY" not in symbol.upper() else 0.001
    
    def check_signal(self, ohlc_df, tick): raise NotImplementedError
    
    def _create_order(self, order_type, price, sl, tp):
        if sl is None or tp is None or sl == 0 or tp == 0: logging.error(f"[{self.symbol}|{self.__class__.__name__}] Kalkulasi SL/TP gagal, order dibatalkan."); return
        order_type_str = "BUY" if order_type == mt.ORDER_TYPE_BUY else "SELL"
        log_message = f"-> MENGIRIM ORDER [{self.__class__.__name__}]: {order_type_str} {self.symbol} {self.volume} @ {price:.{self.digits}f} (SL: {sl:.{self.digits}f}, TP: {tp:.{self.digits}f})"
        logging.info(log_message)
        request = {"action": mt.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": float(self.volume), "type": order_type, "price": price, "sl": sl, "tp": tp, "comment": f"BotV2.7 {self.__class__.__name__}", "type_time": mt.TRADE_ACTION_DEAL, "type_filling": mt.ORDER_FILLING_IOC}
        res = order_send_request(request)
        if getattr(res, "retcode", None) == mt.TRADE_RETCODE_DONE:
            self.order_sent = True
            logging.info(f"   -- BERHASIL: Order untuk {self.symbol} diterima (Ticket: {res.order}).")
        else:
            logging.error(f"   -- GAGAL: Order untuk {self.symbol} ditolak. Kode: {getattr(res, 'retcode', 'N/A')}, Komentar: '{getattr(res, 'comment', 'N/A')}'")

    def _get_final_sl_tp(self, order_type, tick, sl_price_ideal, tp_price_ideal):
        if not all([self.info, self.info.trade_tick_size > 0]): return None, None
        tick_size = Decimal(str(self.info.trade_tick_size)); ask = Decimal(str(tick.ask)); bid = Decimal(str(tick.bid))
        sl = Decimal(str(sl_price_ideal)); tp = Decimal(str(tp_price_ideal))
        if order_type == mt.ORDER_TYPE_BUY:
            if sl >= bid: sl = bid - tick_size
            if tp <= ask: tp = ask + tick_size
        else:
            if sl <= ask: sl = ask + tick_size
            if tp >= bid: tp = bid - tick_size
        stops_level = self.info.trade_stops_level
        if stops_level > 0:
            min_stop_distance = Decimal(str(stops_level)) * Decimal(str(self.info.point))
            validation_price = bid if order_type == mt.ORDER_TYPE_BUY else ask
            if order_type == mt.ORDER_TYPE_BUY:
                if (validation_price - sl) < min_stop_distance: sl = validation_price - min_stop_distance
            else:
                if (sl - validation_price) < min_stop_distance: sl = validation_price - min_stop_distance
        sl = (sl / tick_size).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick_size
        tp = (tp / tick_size).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick_size
        return float(sl), float(tp)