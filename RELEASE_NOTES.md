# BITCOIN free data downloader v1.1.1

Created by **Vikrant Singh** for the trading and research community.

## Large-archive performance fixes

- Uses compact covering indexes for progress totals instead of repeatedly scanning
  candle payload storage as the archive grows.
- Releases contract-list read cursors before downloading, allowing SQLite journal
  checkpoints to run normally rather than accumulating an oversized journal.
- Shows overall archive completion across restarts, separately from this-run work.
- Calculates throughput and remaining-time estimates from the recent two minutes.
- Adds a regression test proving that a suspended job iterator does not pin the journal.
- Requests compressed API responses to reduce network transfer while retaining
  the same one-minute candles and all saved data fields.

All saved checkpoints and candle data are retained on upgrade.

## New: choose your download drive

- First launch asks where to place your data before any download starts.
- Displays the complete selected path and the drive's free space for confirmation.
- Remembers your choice for future launches, updates, retries and Windows recovery.
- Shows the destination and available drive space in the main window.
- Adds **Change data folder**, available while stopped.
- Blocks downloads below 2 GiB free and asks before continuing below the suggested
  60 GiB planning allowance. The final data size can vary.
- Fixes the GUI's process-launch callback so Update and Export dispatch correctly.
- Adds a Windows update ZIP with documentation and existing-archive upgrade steps.

Select your **existing archive folder** on upgrade to keep your downloaded data
and resume without starting a separate archive. See UPDATE.md in the ZIP.

## Windows download

Download `Bitcoin-Free-Data-Downloader.exe` below, save it in a permanent folder,
and double-click it. Python and API credentials are not required.
Click **Update / Resume** to begin downloading BTC option history.

## Included

- Delta Exchange India BTC calls and puts only; futures are excluded.
- One-minute traded-price OHLCV, mark-price OHLC and open-interest OHLC where available.
- Incremental downloads, transactional checkpoints and timestamp deduplication.
- Automatic retries with backoff and recovery after unexpected process exits.
- Automatic recovery at Windows sign-in while a download is enabled.
- Live saved totals, data ranges, current request, speed and estimated completion times.
- Compressed local SQLite storage and compressed CSV exports.
- Traded-price history is prioritised; mark prices and OI follow automatically.
- Shared request pacing and server-directed rate-limit cooldowns.

The executable is unsigned. `SHA256SUMS.txt` provides its checksum.
Data and logs are stored in **the folder you select**. Only the small folder
preference is stored under `%LOCALAPPDATA%\BitcoinFreeDataDownloader\settings.json`.
Use **Stop safely** to pause automatic recovery; **Update / Resume** enables it again.
Internet and an awake computer are required; shutdowns resume after the next sign-in.

## Coverage

The program queries public historical endpoints. Availability depends on the
exchange and contract. It does not guarantee a complete archive, reconstruct
historical bid/ask or Greeks, or fabricate missing candles. Market data is not
bundled with this release. This independent project is not affiliated with Delta Exchange.

MIT-licensed source code is available in the repository.
