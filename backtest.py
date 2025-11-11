"""
Backtesting engine for breakout + ATR SL/TP with confirmation candles.
Diubah menjadi aplikasi Streamlit untuk menampilkan chart secara live di satu halaman.

Usage:
    1. Pastikan Anda punya file SYMBOL.csv di folder yang sama.
    2. Jalankan dari terminal: streamlit run bt_multi_backtest.py
    3. Buka browser yang muncul, lalu klik tombol "Start Backtest".
"""

import os
import glob
import pandas as pd
import numpy as np
import math
import time
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime

# Impor library untuk web app dan plotting
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# -------------------------
# CONFIG (tweak these)
# -------------------------
DATA_FOLDER = "."
OUTPUT_TRADES = "backtest_trades.csv"
LOOKBACK = 100
CONFIRMATION = 2
ATR_PERIOD = 14
SL_ATR_MULT = 1.5
TP_ATR_MULT = 3.0
FALLBACK_SL_PCT = 0.05
FALLBACK_TP_PCT = 0.10
CONTRACT_SIZE = 1.0
VOLUME = 0.1
DIGITS = 2
MARK_TO_MARKET_CLOSE = True
# --- PENGATURAN BARU ---
PAUSE_AFTER_TRADE_S = 3  # Jeda (detik) setelah menampilkan chart sebelum lanjut ke trade berikutnya

# -------------------------
# Data structures (Tidak ada perubahan)
# -------------------------
@dataclass
class TradeRecord:
    symbol: str
    ticket: int
    side: str
    entry_index: int
    entry_time: pd.Timestamp
    entry_price: float
    sl: float
    tp: float
    exit_index: int
    exit_time: pd.Timestamp
    exit_price: float
    reason: str
    profit_usd: float

# -------------------------
# Utils (Tidak ada perubahan signifikan)
# -------------------------
def read_csv_symbol(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, sep=",")
        if df.shape[1] < 2:
            df = pd.read_csv(path, sep="\t")
    except Exception:
        df = pd.read_csv(path, sep="\t")
    
    if 'time' not in df.columns:
        raise ValueError("Kolom 'time' tidak ditemukan di file CSV")
    df['time'] = pd.to_datetime(df['time'], format="%Y.%m.%d %H:%M:%S", errors='coerce')
    df = df.dropna(subset=['time'])
    df = df.sort_values(by="time").reset_index(drop=True)
    df = df.replace([1.7976931348623157e+308, np.inf, -np.inf], np.nan)
    df = df.fillna(method="ffill").fillna(method="bfill")
    return df

def calculate_atr(df: pd.DataFrame, period: int=14) -> pd.Series:
    high = df['high']; low = df['low']; close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

def round_price(p: float, digits: int = DIGITS) -> float:
    factor = 10 ** digits
    return math.floor(p * factor + 0.5) / factor

def is_breakout_confirmed(df: pd.DataFrame, idx: int, lookback: int, confirmation: int, direction: str) -> bool:
    if idx < lookback + confirmation:
        return False
    lookback_slice = df.iloc[idx - confirmation - lookback : idx - confirmation]
    max_high = lookback_slice['high'].max()
    min_low  = lookback_slice['low'].min()
    confirm_slice = df.iloc[idx - confirmation : idx]
    if confirm_slice.shape[0] < confirmation:
        return False
    if direction == 'long':
        return (confirm_slice['close'] > max_high).all()
    else:
        return (confirm_slice['close'] < min_low).all()

# --------------------------------
# FUNGSI PLOTTING (DIMODIFIKASI UNTUK STREAMLIT)
# --------------------------------
def plot_trade_chart(df: pd.DataFrame, trade_info: dict, chart_placeholder, info_placeholder, chart_before: int = 40, chart_after: int = 60):
    entry_index = trade_info['entry_index']
    start_index = max(0, entry_index - chart_before)
    end_index = min(len(df), entry_index + chart_after)
    chart_df = df.iloc[start_index:end_index]
    
    fig = go.Figure(data=[go.Candlestick(x=chart_df['time'],
                                       open=chart_df['open'],
                                       high=chart_df['high'],
                                       low=chart_df['low'],
                                       close=chart_df['close'],
                                       name='Candles')])

    # Garis Entry, SL, dan TP
    fig.add_hline(y=trade_info['entry_price'], line_dash="dash", line_color="blue", annotation_text=f"Entry: {trade_info['entry_price']}", annotation_position="bottom right")
    fig.add_hline(y=trade_info['sl'], line_dash="dash", line_color="red", annotation_text=f"SL: {trade_info['sl']}", annotation_position="bottom right")
    fig.add_hline(y=trade_info['tp'], line_dash="dash", line_color="green", annotation_text=f"TP: {trade_info['tp']}", annotation_position="bottom right")
    
    # Tanda panah pada saat entry
    arrow_symbol = 'triangle-up' if trade_info['side'] == 'BUY' else 'triangle-down'
    arrow_color = 'green' if trade_info['side'] == 'BUY' else 'red'
    fig.add_trace(go.Scatter(x=[trade_info['entry_time']],
                             y=[trade_info['entry_price']],
                             mode='markers',
                             marker=dict(symbol=arrow_symbol, color=arrow_color, size=15),
                             name='Entry Point'))
    
    fig.update_layout(
        title=f"Trade on {trade_info['symbol']} - {trade_info['side']} @ {trade_info['entry_time']}",
        xaxis_rangeslider_visible=False,
        showlegend=False
    )
    
    # --- PERUBAHAN UTAMA: TAMPILKAN DI PLACEHOLDER STREAMLIT ---
    info_placeholder.info(f"Menampilkan Chart untuk: {trade_info['side']} Trade #{trade_info['ticket']} pada {trade_info['symbol']}")
    chart_placeholder.plotly_chart(fig, use_container_width=True)


# -------------------------
# Backtest per-symbol (DIMODIFIKASI UNTUK STREAMLIT)
# -------------------------
def backtest_symbol(symbol: str, df: pd.DataFrame, chart_placeholder, info_placeholder, start_ticket=1) -> List[TradeRecord]:
    # ... (logika internal fungsi ini sebagian besar sama) ...
    df = df.reset_index(drop=True).copy()
    atr = calculate_atr(df, ATR_PERIOD)
    trades: List[TradeRecord] = []
    open_positions = []
    ticket = start_ticket

    for i in range(len(df)):
        if i < max(LOOKBACK + CONFIRMATION, ATR_PERIOD):
            continue

        long_conf = is_breakout_confirmed(df, i, LOOKBACK, CONFIRMATION, 'long')
        short_conf = is_breakout_confirmed(df, i, LOOKBACK, CONFIRMATION, 'short')

        bar_high = df.loc[i, 'high']
        bar_low  = df.loc[i, 'low']
        bar_time = df.loc[i, 'time']

        for pos in open_positions[:]:
            if pos['side'] == 'BUY':
                if bar_high >= pos['tp']:
                    exit_price = pos['tp']
                    profit = (exit_price - pos['entry_price']) * CONTRACT_SIZE * pos['volume']
                    trades.append(TradeRecord(symbol, pos['ticket'], 'BUY', pos['entry_index'], pos['entry_time'], pos['entry_price'], pos['sl'], pos['tp'], i, bar_time, exit_price, 'TP', profit))
                    open_positions.remove(pos)
                    continue
                if bar_low <= pos['sl']:
                    exit_price = pos['sl']
                    profit = (exit_price - pos['entry_price']) * CONTRACT_SIZE * pos['volume']
                    trades.append(TradeRecord(symbol, pos['ticket'], 'BUY', pos['entry_index'], pos['entry_time'], pos['entry_price'], pos['sl'], pos['tp'], i, bar_time, exit_price, 'SL', profit))
                    open_positions.remove(pos)
                    continue
            else:  # SELL
                if bar_low <= pos['tp']:
                    exit_price = pos['tp']
                    profit = (pos['entry_price'] - exit_price) * CONTRACT_SIZE * pos['volume']
                    trades.append(TradeRecord(symbol, pos['ticket'], 'SELL', pos['entry_index'], pos['entry_time'], pos['entry_price'], pos['sl'], pos['tp'], i, bar_time, exit_price, 'TP', profit))
                    open_positions.remove(pos)
                    continue
                if bar_high >= pos['sl']:
                    exit_price = pos['sl']
                    profit = (pos['entry_price'] - exit_price) * CONTRACT_SIZE * pos['volume']
                    trades.append(TradeRecord(symbol, pos['ticket'], 'SELL', pos['entry_index'], pos['entry_time'], pos['entry_price'], pos['sl'], pos['tp'], i, bar_time, exit_price, 'SL', profit))
                    open_positions.remove(pos)
                    continue

        next_idx = i + 1
        if next_idx >= len(df):
            continue

        if len(open_positions) == 0:
            entry_time = df.loc[next_idx, 'time']
            entry_price = df.loc[next_idx, 'open']
            current_atr = atr.iloc[i] if not np.isnan(atr.iloc[i]) else None
            
            new_pos = None
            if long_conf:
                if current_atr and not np.isnan(current_atr):
                    sl = entry_price - current_atr * SL_ATR_MULT
                    tp = entry_price + current_atr * TP_ATR_MULT
                else:
                    sl = entry_price * (1 - FALLBACK_SL_PCT)
                    tp = entry_price * (1 + FALLBACK_TP_PCT)
                
                new_pos = {'ticket': ticket, 'side': 'BUY', 'entry_price': round_price(entry_price), 'sl': round_price(sl), 'tp': round_price(tp), 'entry_index': next_idx, 'entry_time': entry_time, 'volume': VOLUME, 'symbol': symbol}
                open_positions.append(new_pos)
                ticket += 1

            elif short_conf:
                if current_atr and not np.isnan(current_atr):
                    sl = entry_price + current_atr * SL_ATR_MULT
                    tp = entry_price - current_atr * TP_ATR_MULT
                else:
                    sl = entry_price * (1 + FALLBACK_SL_PCT)
                    tp = entry_price * (1 - FALLBACK_TP_PCT)
                
                new_pos = {'ticket': ticket, 'side': 'SELL', 'entry_price': round_price(entry_price), 'sl': round_price(sl), 'tp': round_price(tp), 'entry_index': next_idx, 'entry_time': entry_time, 'volume': VOLUME, 'symbol': symbol}
                open_positions.append(new_pos)
                ticket += 1

            # --- JIKA ADA POSISI BARU, PLOT KE STREAMLIT ---
            if new_pos:
                plot_trade_chart(df, new_pos, chart_placeholder, info_placeholder)
                time.sleep(PAUSE_AFTER_TRADE_S) # Beri jeda agar user bisa lihat

    # ... sisa fungsi sama ...
    if MARK_TO_MARKET_CLOSE and len(open_positions) > 0:
        last_idx = len(df)-1
        last_time = df.loc[last_idx, 'time']
        last_close = df.loc[last_idx, 'close']
        for pos in open_positions:
            if pos['side'] == 'BUY':
                profit = (last_close - pos['entry_price']) * CONTRACT_SIZE * pos['volume']
                trades.append(TradeRecord(symbol, pos['ticket'], 'BUY', pos['entry_index'], pos['entry_time'], pos['entry_price'], pos['sl'], pos['tp'], last_idx, last_time, last_close, 'EXIT', profit))
            else:
                profit = (pos['entry_price'] - last_close) * CONTRACT_SIZE * pos['volume']
                trades.append(TradeRecord(symbol, pos['ticket'], 'SELL', pos['entry_index'], pos['entry_time'], pos['entry_price'], pos['sl'], pos['tp'], last_idx, last_time, last_close, 'EXIT', profit))
        open_positions.clear()
    return trades

# -------------------------
# Metrics & reporting (Tidak ada perubahan)
# -------------------------
def summarize_trades(trades: List[TradeRecord]) -> Dict:
    if not trades: return {}
    df = pd.DataFrame([t.__dict__ for t in trades])
    total_pnl = df['profit_usd'].sum()
    n = len(df)
    wins = df[df['profit_usd'] > 0]
    losses = df[df['profit_usd'] <= 0]
    winrate = len(wins) / n if n>0 else 0.0
    avg_win = wins['profit_usd'].mean() if not wins.empty else 0.0
    avg_loss = losses['profit_usd'].mean() if not losses.empty else 0.0
    df = df.sort_values(['symbol','exit_index']).reset_index(drop=True)
    df['cum_pnl'] = df['profit_usd'].cumsum()
    cum = df['cum_pnl'].values
    peak = np.maximum.accumulate(np.insert(cum,0,0))
    dd = peak[1:] - cum
    max_dd = dd.max() if len(dd)>0 else 0.0
    metrics = {'total_pnl': round(total_pnl,2), 'num_trades': n, 'winrate': round(winrate,4), 'avg_win': round(avg_win,2), 'avg_loss': round(avg_loss,2), 'max_drawdown': round(max_dd,2)}
    return metrics

# -------------------------
# Main: DIBUAT ULANG UNTUK STREAMLIT
# -------------------------
def main():
    st.set_page_config(layout="wide")
    st.title("📈 Live Backtest Chart Viewer")
    st.write("Skrip backtesting akan berjalan dan menampilkan chart untuk setiap trade secara otomatis di bawah ini.")

    # Siapkan placeholder di halaman web
    info_placeholder = st.empty()
    chart_placeholder = st.empty()
    
    info_placeholder.info("Klik tombol di bawah untuk memulai proses backtesting.")

    if st.button("🚀 Mulai Backtest"):
        csv_files = glob.glob(os.path.join(DATA_FOLDER, "*.csv"))
        if not csv_files:
            st.error("Tidak ada file .csv yang ditemukan di folder. Letakkan file CSV Anda dan coba lagi.")
            return

        all_trades: List[TradeRecord] = []
        next_ticket = 1
        
        progress_bar = st.progress(0)
        
        for i, path in enumerate(csv_files):
            symbol = os.path.splitext(os.path.basename(path))[0]
            st.write(f"--- Memproses {symbol} ---")
            try:
                df = read_csv_symbol(path)
            except (FileNotFoundError, ValueError) as e:
                st.warning(f"  -> Gagal membaca {symbol}: {e}")
                continue
            
            trades = backtest_symbol(symbol, df, chart_placeholder, info_placeholder, start_ticket=next_ticket)
            next_ticket += len(trades) + 5
            all_trades.extend(trades)
            st.write(f"  -> Ditemukan {len(trades)} trade.")
            progress_bar.progress((i + 1) / len(csv_files))

        info_placeholder.success("✅ Backtest Selesai!")
        chart_placeholder.empty() # Kosongkan chart setelah selesai

        # Tampilkan ringkasan hasil
        st.header("Ringkasan Hasil Keseluruhan")
        if all_trades:
            df_trades = pd.DataFrame([t.__dict__ for t in all_trades])
            df_trades.to_csv(OUTPUT_TRADES, index=False)
            st.success(f"Semua data trade disimpan ke {OUTPUT_TRADES}")

            overall_metrics = summarize_trades(all_trades)
            st.json(overall_metrics)

            st.subheader("Daftar Semua Trade")
            st.dataframe(df_trades)
        else:
            st.warning("Tidak ada trade yang dieksekusi selama periode backtest.")

if __name__ == "__main__":
    main()