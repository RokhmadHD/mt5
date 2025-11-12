import pandas as pd
import os
import glob
import logging
from datetime import datetime
from tqdm import tqdm
# Impor semua komponen yang dibutuhkan dari proyek Anda
from helpers import get_env_var
from strategies import STRATEGY_FACTORY # Pemuat strategi dinamis

# ---------------------------
# KONFIGURASI BACKTEST
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | BACKTEST | %(message)s")

DATA_FOLDER = "data"
OUTPUT_FILE = "backtest_results.csv"
INITIAL_BALANCE = 10000.0

# ---------------------------
# KELAS SIMULASI TICK & POSISI
# ---------------------------
class SimulatedTick:
    def __init__(self, row):
        self.time = row.time; self.ask = row.high; self.bid = row.low; self.last = row.close

class SimulatedPosition:
    def __init__(self, ticket, symbol, order_type, volume, price_open, sl, tp, comment):
        self.ticket = ticket; self.symbol = symbol; self.type = order_type
        self.volume = volume; self.price_open = price_open; self.sl = sl
        self.tp = tp; self.comment = comment

# ---------------------------
# KELAS UTAMA BACKTESTER
# ---------------------------
class Backtester:
    def __init__(self):
        self.balance = INITIAL_BALANCE
        self.open_positions = {}
        self.trade_history = []
        self.ticket_counter = 1
        self.account_blown = False # [BARU] Flag untuk menandai akun bangkrut

        volumes_str = get_env_var('VOLUMES', '')
        default_volume = get_env_var('DEFAULT_VOLUME', 0.01, float)
        self.volume_map = {v.split(':')[0].strip().upper(): float(v.split(':')[1]) for v in volumes_str.split(',') if ':' in v}
        self.default_volume = default_volume

        self.symbol_info_db = {
            'DEFAULT':  {'digits': 5, 'point': 0.00001, 'trade_tick_size': 0.00001, 'trade_stops_level': 0, 'contract_size': 100000},
            'XAUUSD':   {'digits': 2, 'point': 0.01,    'trade_tick_size': 0.01,    'trade_stops_level': 0, 'contract_size': 100}, # 100 troy ounces
            'BTCUSD':   {'digits': 2, 'point': 0.01,    'trade_tick_size': 0.01,    'trade_stops_level': 0, 'contract_size': 1},     # 1 Bitcoin
            'ETHUSD':   {'digits': 2, 'point': 0.01,    'trade_tick_size': 0.01,    'trade_stops_level': 0, 'contract_size': 1},     # 1 Ether
            'USDJPY':   {'digits': 3, 'point': 0.001,   'trade_tick_size': 0.001,   'trade_stops_level': 0, 'contract_size': 100000},
            'XAUJPY':   {'digits': 3, 'point': 0.001,   'trade_tick_size': 0.001,   'trade_stops_level': 0, 'contract_size': 100},
        }

    def run(self):
        csv_files = glob.glob(os.path.join(DATA_FOLDER, "*.csv"))
        if not csv_files:
            logging.error(f"Tidak ada file CSV yang ditemukan di folder '{DATA_FOLDER}'."); return

        for csv_file in csv_files:
            if self.account_blown:
                logging.critical("Akun bangkrut. Menghentikan semua backtest lebih lanjut.")
                break

            symbol = os.path.basename(csv_file).split('_')[0].upper()
            logging.info(f"===== Memulai Backtest untuk {symbol} =====")
            
            volume = self.volume_map.get(symbol, self.default_volume)
            strategies = [StrategyClass(symbol, volume) for StrategyClass in STRATEGY_FACTORY.values()]
            
            sim_info_raw = self.symbol_info_db.get(symbol, self.symbol_info_db['DEFAULT'])
            class SimulatedInfo:
                def __init__(self, data):
                    self.digits=data['digits']; self.point=data['point']; self.trade_tick_size=data['trade_tick_size']
                    self.trade_stops_level=data['trade_stops_level']; self.contract_size=data['contract_size']
            sim_info = SimulatedInfo(sim_info_raw)

            for s in strategies:
                s.info = sim_info; s.digits = sim_info.digits; s.point = sim_info.point
                original_create_order = s._create_order
                def sim_create_order_wrapper(order_type, price, sl, tp, original_method=original_create_order, strategy_instance=s):
                    self._sim_create_order(order_type, price, sl, tp, strategy_instance)
                s._create_order = sim_create_order_wrapper
            
            try:
                logging.info(f"Membaca file data {os.path.basename(csv_file)}...")
                df = pd.read_csv(csv_file, parse_dates=['timestamp'])
                df.rename(columns={'timestamp': 'time', 'volume': 'tick_volume'}, inplace=True)
                if not all(col in df.columns for col in ['time', 'open', 'high', 'low', 'close', 'tick_volume']):
                    raise ValueError("Kolom yang dibutuhkan hilang dari CSV.")
            except Exception as e:
                logging.error(f"Gagal memproses file {csv_file}: {e}"); continue
            
            start_index = 200
            total_bars = len(df)
            if total_bars <= start_index:
                logging.warning(f"Data untuk {symbol} tidak cukup ({total_bars} bar). Melewati..."); continue

            logging.info(f"Memulai simulasi untuk {total_bars - start_index} bar...")
            
            # [PERBAIKAN UTAMA] Gunakan tqdm untuk progress bar
            # Kita akan mengiterasi melalui objek tqdm yang membungkus range kita
            progress_bar = tqdm(range(start_index, total_bars), desc=f"Processing {symbol}", unit="bar")

            for i in progress_bar:
                if self.account_blown: break

                ohlc_slice = df.iloc[:i]; current_bar = df.iloc[i]; sim_tick = SimulatedTick(current_bar)
                
                if symbol in self.open_positions:
                    self._check_close_conditions(symbol, current_bar, sim_info)
                else:
                    for strategy in strategies:
                        strategy.check_signal(ohlc_slice, sim_tick)
                        if strategy.order_sent: break
                    for s in strategies: s.order_sent = False
            
            logging.info(f"Simulasi untuk {symbol} selesai.")

        self._generate_report()
    def _sim_create_order(self, order_type, price, sl, tp, strategy_instance):
        symbol = strategy_instance.symbol
        if self.open_positions.get(symbol): return
        position = SimulatedPosition(self.ticket_counter, symbol, order_type, strategy_instance.volume, price, sl, tp, f"Backtest {strategy_instance.__class__.__name__}")
        self.open_positions[symbol] = position; self.ticket_counter += 1
        logging.info(f"Posisi DIBUKA: {symbol} {('BUY' if order_type == 0 else 'SELL')} @ {price} | SL: {sl} TP: {tp}")

    def _check_close_conditions(self, symbol, current_bar, sim_info):
        pos = self.open_positions.get(symbol); close_price, reason = 0.0, ""
        if pos.type == 0: # BUY
            if current_bar.low <= pos.sl: close_price, reason = pos.sl, "SL"
            elif current_bar.high >= pos.tp: close_price, reason = pos.tp, "TP"
        else: # SELL
            if current_bar.high >= pos.sl: close_price, reason = pos.sl, "SL"
            elif current_bar.low <= pos.tp: close_price, reason = pos.tp, "TP"
        if close_price > 0: self._close_position(symbol, close_price, current_bar.time, reason, sim_info)

    def _close_position(self, symbol, close_price, close_time, reason, sim_info):
        pos = self.open_positions.pop(symbol)
        
        # [PERBAIKAN UTAMA] Kalkulasi Profit yang Lebih Akurat
        price_diff = close_price - pos.price_open
        if pos.type == 1: # SELL
            price_diff = pos.price_open - close_price
        
        # Hitung profit berdasarkan contract size
        profit = price_diff * sim_info.contract_size * pos.volume
        
        # Untuk pair Forex dengan quote currency non-USD (misal: XAUJPY), perlu konversi
        # Untuk saat ini kita asumsikan semua profit dalam USD untuk simplifikasi
        
        self.balance += profit
        
        self.trade_history.append({
            'ticket': pos.ticket, 'symbol': symbol, 'type': 'BUY' if pos.type == 0 else 'SELL', 'volume': pos.volume,
            'open_price': pos.price_open, 'close_price': close_price, 'sl': pos.sl, 'tp': pos.tp,
            'open_time': "N/A", 'close_time': close_time, 'profit': profit, 'reason': reason, 'comment': pos.comment
        })
        logging.info(f"Posisi DITUTUP: {symbol} @ {close_price} | Alasan: {reason} | Profit: {profit:.2f} | Balance: {self.balance:.2f}")

        # [BARU] Pengecekan Kondisi Bangkrut
        if self.balance <= 0:
            self.account_blown = True
            logging.critical(f"ACCOUNT BLOWN! Saldo saat ini: {self.balance:.2f}. Backtest dihentikan.")
            
    def _generate_report(self):
        if not self.trade_history: logging.info("Backtest selesai. Tidak ada trade."); return
        df = pd.DataFrame(self.trade_history); df.to_csv(OUTPUT_FILE, index=False)
        logging.info(f"Hasil backtest disimpan ke {OUTPUT_FILE}")

        total_trades = len(df); wins = df[df['profit'] > 0]
        pnl = df['profit'].sum(); win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        
        report_str = "\n" + "="*30 + "\n" + " " * 5 + "HASIL BACKTEST FINAL" + " " * 5 + "\n" + "="*30 + "\n"
        report_str += f"Total Trade : {total_trades}\n"
        report_str += f"Win Rate    : {win_rate:.2f} %\n"
        report_str += f"Total P/L   : {pnl:.2f}\n"
        report_str += f"Initial Balance: {INITIAL_BALANCE:.2f}\n"
        report_str += f"Final Balance: {self.balance:.2f}\n"
        if self.account_blown:
             report_str += "Status      : ACCOUNT BLOWN!\n"
        report_str += "="*30 + "\n"
        print(report_str)

# ---------------------------
# FUNGSI UNTUK MENJALANKAN
# ---------------------------
if __name__ == "__main__":
    backtester = Backtester()
    backtester.run()