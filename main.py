"""
Multi-pair, All-Strategies MT5 trading bot (multithreaded) - V2.6

Fitur:
- Laporan Kinerja Otomatis: Menampilkan statistik trading (Win Rate, P/L, dll.)
  secara periodik dan saat bot dimatikan.
- Arsitektur Multi-Strategi: Setiap pair dimonitor oleh SEMUA strategi yang tersedia.
- Konfigurasi Terpusat: Semua pengaturan dikelola melalui file .env.
- Logika Cerdas: Termasuk validasi breakout, penanganan stop level, dll.
"""
import MetaTrader5 as mt
import pandas as pd
import numpy as np
import threading
import time
import logging
import math
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from decimal import Decimal, ROUND_HALF_UP

from helpers import get_env_var, AGGRESSION_LEVEL
from strategies import STRATEGY_FACTORY

# ---------------------------
# 1. SETUP KONFIGURASI DAN LOGGING
# ---------------------------
load_dotenv()

def get_env_var(name, default, type_func=str):
    value = os.getenv(name, default)
    try:
        if type_func == bool:
            return value.lower() in ['true', '1', 't', 'y', 'yes']
        return type_func(value)
    except (ValueError, TypeError):
        logging.warning(f"Variabel .env '{name}' tidak valid. Menggunakan default: {default}")
        return default

# Kredensial
LOGIN = get_env_var('MT5_LOGIN', None, int)
PASSWORD = get_env_var('MT5_PASSWORD', None)
SERVER = get_env_var('MT5_SERVER', None)

# Pengaturan Global
TIMEFRAME_STR = get_env_var('TIMEFRAME', 'M1')
TIMEFRAME_MAP = {"M1": mt.TIMEFRAME_M1, "M5": mt.TIMEFRAME_M5, "M15": mt.TIMEFRAME_M15, "H1": mt.TIMEFRAME_H1}
INTERVAL = TIMEFRAME_MAP.get(TIMEFRAME_STR.upper(), mt.TIMEFRAME_M1)
LOOP_DELAY_SEC = get_env_var('LOOP_DELAY_SEC', 60, int)
MAX_ALLOWED_SPREAD = get_env_var('MAX_ALLOWED_SPREAD', 50.0, float)
AGGRESSION_LEVEL = get_env_var('AGGRESSION_LEVEL', 'medium').lower()
REPORT_INTERVAL_MINUTES = get_env_var('REPORT_INTERVAL_MINUTES', 60, int)
LOGFILE = "mt5_bot_v2.6.log"

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s", handlers=[logging.FileHandler(LOGFILE), logging.StreamHandler()])

# Kunci global dan event
mt_lock = threading.Lock()
stop_event = threading.Event()

# ---------------------------
# 2. FUNGSI WRAPPER MT5
# ---------------------------
def mt_initialize_and_login():
    with mt_lock:
        if not mt.initialize(login=LOGIN, password=PASSWORD, server=SERVER): logging.error(f"MT5 init/login gagal: {mt.last_error()}"); return False
        logging.info(f"Login berhasil ke MT5 {LOGIN}@{SERVER}"); return True
def mt_shutdown_safe():
    with mt_lock: mt.shutdown(); logging.info("Koneksi MT5 ditutup.")
def get_symbol_tick(symbol):
    with mt_lock: return mt.symbol_info_tick(symbol)
def copy_ohlc(symbol, timeframe, rows):
    with mt_lock: rates = mt.copy_rates_from_pos(symbol, timeframe, 0, rows)
    if rates is None: return pd.DataFrame()
    df = pd.DataFrame(rates); df['time'] = pd.to_datetime(df['time'], unit='s'); return df
def positions_get_symbol(symbol):
    with mt_lock: pos = mt.positions_get(symbol=symbol)
    return pos if pos else []
def order_send_request(request):
    with mt_lock: return mt.order_send(request)
def get_symbol_info(symbol):
    with mt_lock: return mt.symbol_info(symbol)
def get_history_deals(start_date, end_date):
    with mt_lock: return mt.history_deals_get(start_date, end_date)

class TradeReporter:
    def __init__(self):
        self.lock = threading.Lock()
        self.processed_tickets = set()
        self.trade_log = []
    def update_history(self):
        with self.lock:
            from_date = datetime.now() - timedelta(days=1); to_date = datetime.now()
            deals = get_history_deals(from_date, to_date)
            if deals is None: return
            for deal in deals:
                if deal.entry == mt.DEAL_ENTRY_OUT and deal.ticket not in self.processed_tickets:
                    strategy_name = "Unknown"
                    parts = deal.comment.split(' ')
                    if len(parts) > 1: strategy_name = parts[1]
                    self.trade_log.append({'ticket': deal.ticket, 'symbol': deal.symbol, 'strategy': strategy_name, 'profit': deal.profit})
                    self.processed_tickets.add(deal.ticket)
    def generate_summary(self):
        with self.lock:
            if not self.trade_log: return {"total_trades": 0}
            df = pd.DataFrame(self.trade_log)
            total_trades = len(df); wins = df[df['profit'] > 0]; losses = df[df['profit'] <= 0]
            total_pnl = df['profit'].sum(); win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
            total_profit = wins['profit'].sum(); total_loss = abs(losses['profit'].sum())
            profit_factor = total_profit / total_loss if total_loss > 0 else 999
            return {"total_trades": total_trades, "wins": len(wins), "losses": len(losses), "win_rate_pct": win_rate, "total_pnl": total_pnl, "profit_factor": profit_factor, "avg_win": wins['profit'].mean() if len(wins) > 0 else 0, "avg_loss": losses['profit'].mean() if len(losses) > 0 else 0}
    def display_report(self):
        summary = self.generate_summary()
        if summary["total_trades"] == 0: logging.info("Laporan Kinerja: Belum ada trade yang ditutup."); return
        report_str = "\n" + "="*45 + "\n" + " " * 10 + "LAPORAN KINERJA BOT" + " " * 10 + "\n" + "="*45 + "\n"
        report_str += f"| Total Trade     : {summary['total_trades']}\n| Profit      : {summary['wins']}\n| Lose       : {summary['losses']}\n| Win Rate        : {summary['win_rate_pct']:.2f} %\n"
        report_str += "-"*45 + "\n"
        report_str += f"| Total P/L       : {summary['total_pnl']:.2f}\n| Rata2 Profit: {summary['avg_win']:.2f}\n| Rata2 Lose : {summary['avg_loss']:.2f}\n| Profit Factor   : {summary['profit_factor']:.2f}\n"
        report_str += "="*45 + "\n"; print(report_str)

# ---------------------------
# 4. WORKER THREAD DAN MAIN LAUNCHER
# ---------------------------


def pair_worker(symbol, volume):
    strategies = [StrategyClass(symbol, volume) for StrategyClass in STRATEGY_FACTORY.values()]
    logging.info(f"[{symbol}] Worker dimulai dengan {len(strategies)} strategi, volume {volume}")
    while not stop_event.is_set():
        try:
            if positions_get_symbol(symbol): time.sleep(LOOP_DELAY_SEC); continue
            tick = get_symbol_tick(symbol)
            if tick is None or (tick.ask - tick.bid) > MAX_ALLOWED_SPREAD * strategies[0].info.point:
                time.sleep(LOOP_DELAY_SEC); continue
            ohlc = copy_ohlc(symbol, INTERVAL, 200)
            if ohlc.empty or ohlc.shape[0] < 50: time.sleep(LOOP_DELAY_SEC); continue
            for strategy in strategies:
                strategy.check_signal(ohlc, tick)
                if strategy.order_sent:
                    logging.info(f"[{symbol}] Order dikirim oleh {strategy.__class__.__name__}. Menghentikan pengecekan untuk siklus ini.")
                    break
            for strategy in strategies: strategy.order_sent = False
        except Exception as e:
            logging.exception(f"[{symbol}] Error di worker loop: {e}")
        time.sleep(LOOP_DELAY_SEC)
    logging.info(f"[{symbol}] Worker berhenti.")

def reporting_worker(reporter, interval_seconds):
    logging.info("Reporter worker dimulai.")
    while not stop_event.is_set():
        for _ in range(interval_seconds):
            if stop_event.is_set(): break
            time.sleep(1)
        if not stop_event.is_set():
            reporter.update_history(); reporter.display_report()
    logging.info("Reporter worker berhenti.")

def main():
    if not mt_initialize_and_login(): return
    logging.info(f"===== Bot Dimulai dengan Tingkat Agresivitas: {AGGRESSION_LEVEL.upper()} =====")
    reporter = TradeReporter()
    reporter.update_history()
    
    pairs_str = get_env_var('PAIRS_TO_TRADE', ''); volumes_str = get_env_var('VOLUMES', '')
    default_volume = get_env_var('DEFAULT_VOLUME', 0.01, float)
    pairs_list = [p.strip().upper() for p in pairs_str.split(',') if p.strip()]
    volume_map = {v.split(':')[0].strip().upper(): float(v.split(':')[1]) for v in volumes_str.split(',') if ':' in v}

    if not pairs_list: logging.error("Tidak ada pair di PAIRS_TO_TRADE .env. Bot berhenti."); return
        
    threads = []
    for symbol in pairs_list:
        volume = volume_map.get(symbol, default_volume)
        info = get_symbol_info(symbol)
        if not (info and info.visible):
            with mt_lock: mt.symbol_select(symbol, True)
        t = threading.Thread(target=pair_worker, name=f"Worker-{symbol}", args=(symbol, volume), daemon=True)
        threads.append(t); t.start()

    report_interval_sec = REPORT_INTERVAL_MINUTES * 60
    report_thread = threading.Thread(target=reporting_worker, name="Reporter", args=(reporter, report_interval_sec), daemon=True)
    threads.append(report_thread); report_thread.start()

    logging.info(f"================ {len(pairs_list)} WORKER TRADING + 1 REPORTER DIMULAI ================")
    try:
        while all(t.is_alive() for t in threads): time.sleep(1)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt diterima, menghentikan workers..."); stop_event.set()
        for t in threads: t.join(timeout=10)
    finally:
        logging.info("Menampilkan Laporan Kinerja Final...")
        reporter.update_history(); reporter.display_report()
        mt_shutdown_safe()

if __name__ == "__main__":
    main()