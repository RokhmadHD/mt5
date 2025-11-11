# Multi-Pair, Multi-Strategy MT5 Trading Bot (V2.7+)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)
![MetaTrader5](https://img.shields.io/badge/API-MetaTrader5-orange.svg)
![Status](https://img.shields.io/badge/status-development-yellow.svg)

Ini adalah sebuah bot trading algoritmik canggih yang ditulis dalam Python, dirancang untuk berjalan di platform MetaTrader 5. Bot ini menggunakan arsitektur *multithreaded* untuk memonitor beberapa pasangan mata uang secara bersamaan, di mana setiap pair dianalisis oleh serangkaian strategi trading yang beragam secara paralel.

## Fitur Utama

-   **Multi-Pair & Multi-Threaded**: Setiap simbol yang ditradingkan berjalan di *thread*-nya sendiri, memungkinkan pemantauan pasar secara paralel dan efisien tanpa penundaan.
-   **Arsitektur Multi-Strategi**: Setiap pair secara otomatis dianalisis oleh **semua strategi yang tersedia**, meningkatkan peluang untuk menemukan sinyal trading di berbagai kondisi pasar.
-   **Konfigurasi Terpusat**: Semua pengaturan, mulai dari kredensial akun, daftar pair, hingga parameter detail setiap strategi, dikelola sepenuhnya melalui satu file `.env`.
-   **Manajemen Risiko Dinamis**: Ukuran volume (lot) dapat diatur secara spesifik untuk setiap pair, memungkinkan manajemen risiko yang lebih baik antara aset volatil (seperti Crypto) dan yang lebih stabil (seperti Forex).
-   **Pelaporan Kinerja**: Sebuah *thread* khusus berjalan untuk secara periodik menghasilkan dan menampilkan laporan kinerja bot, termasuk metrik kunci seperti Win Rate, Profit Factor, dan P/L total.
-   **Strategi Bawaan yang Beragam**: Dilengkapi dengan kumpulan strategi yang kuat untuk berbagai kondisi pasar:
    -   **Trend-Following**: `Breakout`, `Ma_Crossover`, `Ichimoku_Crossover`
    -   **Mean-Reversion**: `Rsi_Oversold`, `Bollinger_Reversal`
    -   **Counter-Trend**: `Fakeout`
    -   **Price Action**: `Engulfing_Reversal`
    -   **Volatility-Based**: `Bollinger_Squeeze`
-   **Kode yang Terstruktur**: Proyek diorganisir dengan baik, dengan setiap strategi dipisahkan ke dalam file-nya sendiri di dalam folder `strategies`, membuatnya sangat mudah untuk diperluas dan dirawat.

## Prasyarat

-   Python 3.8 atau lebih baru.
-   Terminal MetaTrader 5 yang sudah terinstal dan berjalan.
-   Akun trading (Demo atau Live) di broker yang mendukung MT5.

## Instalasi

1.  **Clone repository ini:**
    ```bash
    git clone [URL_REPOSITORY_GITHUB_ANDA]
    cd [NAMA_FOLDER_PROYEK]
    ```

2.  **Instal dependensi Python:**
    Disarankan untuk menggunakan *virtual environment*.
    ```bash
    python -m venv venv
    source venv/bin/activate  # Di Windows, gunakan `venv\Scripts\activate`
    pip install -r requirements.txt
    ```
    *Catatan: Pastikan Anda membuat file `requirements.txt` dengan menjalankan `pip freeze > requirements.txt`.*

3.  **Konfigurasi Bot:**
    -   Salin file `.env.example` menjadi file baru bernama `.env`.
        ```bash
        cp .env.example .env
        ```
    -   Buka file `.env` dan isi semua detail yang diperlukan, terutama:
        -   `MT5_LOGIN`
        -   `MT5_PASSWORD`
        -   `MT5_SERVER`
        -   `PAIRS_TO_TRADE`
        -   `VOLUMES`

4.  **Konfigurasi MetaTrader 5:**
    -   Buka terminal MT5 Anda.
    -   Pergi ke `Tools -> Options -> Expert Advisors`.
    -   Centang **"Allow algorithmic trading"**.

## Cara Menjalankan Bot

Pastikan terminal MT5 Anda sedang berjalan dan sudah login ke akun. Kemudian, jalankan skrip utama dari terminal Anda:

```bash
python main.py
```

Bot akan mulai berjalan, menampilkan log aktivitasnya langsung di konsol. Laporan kinerja akan dicetak secara periodik sesuai dengan interval yang diatur di `.env`.

Untuk menghentikan bot dengan aman, tekan **`Ctrl+C`**. Bot akan menangkap sinyal ini, menghentikan semua *thread* pekerja, mencetak laporan kinerja final, dan menutup koneksi ke MT5.

## Struktur Proyek

```
/
|-- main.py             # Skrip utama untuk menjalankan bot
|-- .env                # File konfigurasi (diabaikan oleh Git)
|-- .env.example        # Template untuk file .env
|-- .gitignore          # Daftar file yang diabaikan oleh Git
|-- README.md           # Anda sedang membaca ini
|-- requirements.txt    # Daftar dependensi Python
|-- helpers.py          # Fungsi-fungsi bantuan
+-- /strategies/
    |-- __init__.py     # Membuat folder ini menjadi package & memuat strategi secara dinamis
    |-- strategy_base.py# Class dasar untuk semua strategi
    |-- breakout.py
    |-- fakeout.py
    |-- rsi_oversold.py
    |-- ... (dan file strategi lainnya)
```

## Menambahkan Strategi Baru

Berkat arsitektur dinamis, menambahkan strategi baru sangatlah mudah:

1.  Buat file Python baru di dalam folder `strategies/` (misalnya, `my_strategy.py`).
2.  Di dalam file tersebut, buat sebuah *class* baru yang mewarisi (`inherit`) dari `Strategy` (yang diimpor dari `strategy_base`).
3.  Implementasikan metode `__init__` dan `check_signal` sesuai dengan logika strategi Anda.
4.  Daftarkan parameter baru untuk strategi Anda di file `.env` (jika diperlukan).

Bot akan secara otomatis mendeteksi dan menjalankan strategi baru Anda pada start berikutnya, tanpa perlu mengubah `main.py`.

## Disclaimer

Trading algoritmik memiliki risiko yang signifikan. Kode ini disediakan untuk tujuan edukasi dan eksperimental. Selalu uji bot secara ekstensif di **akun demo** sebelum mempertimbangkan untuk menggunakannya di akun live. Penulis tidak bertanggung jawab atas kerugian finansial apa pun.