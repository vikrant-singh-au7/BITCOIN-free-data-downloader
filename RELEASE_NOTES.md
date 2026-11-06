# BITCOIN free data downloader v1.0.1

Created by **Vikrant Singh** for the trading and research community.

Version 1.0.1 preserves custom data-folder paths when the watchdog or Windows
sign-in recovery launches a new process, keeping resumes attached to the same archive.

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
Data is stored under `%LOCALAPPDATA%\BitcoinFreeDataDownloader`.
Use **Stop safely** to pause automatic recovery; **Update / Resume** enables it again.
Internet and an awake computer are required; shutdowns resume after the next sign-in.

## Coverage

The program queries public historical endpoints. Availability depends on the
exchange and contract. It does not guarantee a complete archive, reconstruct
historical bid/ask or Greeks, or fabricate missing candles. Market data is not
bundled with this release. This independent project is not affiliated with Delta Exchange.

MIT-licensed source code is available in the repository.
