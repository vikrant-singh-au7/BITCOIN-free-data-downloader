# BITCOIN free data downloader

**Created by [Vikrant Singh](https://github.com/vikrant-singh-au7)** for the trading and research community.

A free, open-source Windows application for downloading BTC option data from
**Delta Exchange India** and maintaining a resumable local archive. Calls and
puts only. No futures, trading orders, paid account or API credentials required.

## Download and start

1. Open [Releases](https://github.com/vikrant-singh-au7/BITCOIN-free-data-downloader/releases/latest).
2. Download **Bitcoin-Free-Data-Downloader.exe** to a permanent folder.
3. Double-click it. On first launch, **choose the folder/drive where you want your data**.
4. Review the full destination path and available drive space, then confirm.
5. Click **Update / Resume** to start downloading.
6. Keep the computer awake and online. Closing the window leaves it downloading.

Python is not required for the executable. The release includes a SHA-256
checksum. The Windows executable is unsigned.

## Data included

| Dataset | Details |
|---|---|
| BTC contracts | Discoverable live, expired and upcoming BTC calls and puts |
| Traded prices | One-minute open, high, low, close and volume |
| Mark prices | One-minute OHLC where available |
| Open interest | One-minute OHLC where available |
| Metadata | Strike, expiry, contract specifications and settlement fields |
| Current chain | BTC ticker snapshot at the beginning of each update |

Traded-price history across all contracts is prioritised. Mark prices and OI
follow automatically. Prices, volume and OI use native exchange units.

## Resume, retries and duplicate prevention

- Data and completed-window checkpoints are saved in one transaction.
- Completed windows are **not downloaded again**, including successful empty responses.
- Partial windows fetch only their missing tail. Candles merge by timestamp.
- Failed requests use exponential backoff. Failed batches persist across restarts
  and are queued for automatic retry during the same download.
- A watchdog restarts the downloader after unexpected process exits.
- Starting an update registers recovery at the current Windows user's next sign-in.
  Enabled jobs resume from checkpoints after a computer restart.
- **Stop safely** deliberately pauses downloading and automatic recovery.
  **Update / Resume** re-enables it. Recovery is disabled once the run completes.
- Network loss and low disk space are retried automatically. At least 2 GB of
  free space is required. Downloading cannot continue while the computer is asleep
  or shut down; it resumes after Windows sign-in.

Sign-in recovery can also be disabled in **Windows Settings > Apps > Startup >
BitcoinFreeDataDownloader**. Keep the executable in the same folder so its startup
command remains valid. No administrator access is required.

## Progress and speed

The window shows saved totals per dataset, archive size, contracts with data,
actual date extremes, current request, queued retries, speed and estimated time
remaining. Date extremes do **not** certify uninterrupted coverage.

The downloader uses 96 workers, persistent HTTPS connections and a shared cap of
22 requests/second. Delta documents a 20,000-unit quota per five minutes and a
cost of three units per candle request. HTTP 429 responses pause all workers
using the server's reset header. Estimates depend on network and API performance.

## Local storage and CSV export

The executable asks where to store the archive on first launch. All data, exports
and download logs go in **your selected folder**, which is remembered for updates
and recovery after Windows sign-in. No archive is silently placed on C:.

The small folder-preference file is stored at
`%LOCALAPPDATA%/BitcoinFreeDataDownloader/settings.json` (it contains only the chosen
path). The window always shows the archive path and the drive's available space.
Under 2 GiB free, downloads are blocked/paused. Under the suggested 60 GiB planning
allowance, the app asks whether to continue; final archive size is not guaranteed.

Use **Change data folder** while stopped to pick another location. Choose the
original archive folder to resume existing data. Changing the selection does not
move files: move an archive yourself only while stopped, then select its new folder.

Your selected folder contains:

```text
data/btc_options.sqlite       Compressed data and transactional checkpoints
data/contracts.jsonl.gz       Contract metadata
exports/                     Compressed CSV exports
status.json                  Live progress
download.log                 Download and retry events
supervisor.log               Recovery events
coverage.json                Last generated coverage report
failed_windows.csv           Last generated failure report
```

Click **Open data folder** to locate it. **Export CSV** writes separate compressed
CSVs for traded prices, mark prices and OI with symbol, Unix/UTC timestamps, OHLC
and volume where available. A complete export takes time and extra disk space.
The app does not upload data.

SQLite tables: `products` stores metadata; `windows` stores zlib-compressed JSON
arrays keyed by symbol, series and window start; `window_bounds` stores actual
timestamps; `snapshots` stores compressed tickers; `failures` stores pending errors.

## Run from source

Windows, Python 3.10+ and Tkinter are required. No third-party runtime dependencies.
Source runs store data beside the scripts. The optional `BTC_OPTIONS_HOME`
environment variable selects another data directory.

```powershell
pythonw app.pyw
python supervisor.py --enable
python downloader.py --report
python downloader.py --export
python downloader.py --export --symbol C-BTC-82200-051126
python -m unittest -v
```

Running `downloader.py` directly performs a pass without the watchdog. The GUI
uses the watchdog automatically. Only one worker and watchdog run per data folder.

## Build the Windows executable

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Bitcoin-Free-Data-Downloader --hidden-import downloader --hidden-import supervisor --hidden-import gui main.py
```

The executable appears in `dist/`. The release workflow runs tests, builds on
Windows and publishes the executable and checksum for version tags.

## Coverage and limitations

The exchange controls retention and contract discovery. The app does not guarantee
a complete archive or every minute. Successful empty responses are recorded as
queried-empty. Historical corrections inside already queried windows require an
explicit repair; normal Update skips completed checkpoints. Historical bid/ask
and Greeks are not reconstructed. Current snapshots are collected per update.

Initial downloads can take many hours and substantial disk space. Market data
is **not** bundled in the repository or releases. MIT covers the software and
does not grant redistribution rights to exchange data. This independent project
is not affiliated with Delta Exchange.

[Official API documentation](https://docs.delta.exchange/)

## Credits and license

Created and maintained by **Vikrant Singh**. Contributions and reproducible bug
reports are welcome through GitHub issues and pull requests.

Released under the [MIT License](LICENSE).
