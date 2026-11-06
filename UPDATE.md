# Updating to v1.1.0

Created by Vikrant Singh.

1. In the old application, click **Stop safely** and wait for the downloader to stop.
2. Close the old progress window. Keep your existing data folder and database.
3. Download the new EXE or extract the Windows update ZIP to a permanent program folder.
4. Launch the new EXE. On first launch it asks where to store data.
5. **Select your existing archive folder** to resume it. This is the folder containing
   the `data` directory and `status.json`, not the `data` directory itself.
6. Confirm the destination and free-space information, then click **Update / Resume**.

Previous standalone EXEs defaulted to
`%LOCALAPPDATA%\BitcoinFreeDataDownloader`. If you used that default, choose that
folder. Source runs normally kept data beside the Python scripts. Users who
previously supplied a custom directory should select that same directory.

Your chosen folder is remembered in a small settings file. The archive stays
there across application updates, retries, worker restarts and Windows sign-in.
Updating the EXE does not require downloading saved data again. No data migration
or deletion is performed automatically. A new empty folder starts a separate archive.

Stop before changing or moving a data folder. Keep the new EXE in a permanent
location; starting an update refreshes its Windows recovery startup command.

The ZIP contains the EXE, README, license, release notes and these update instructions.
Downloaded market data is not bundled. SHA256SUMS.txt verifies both release assets.
