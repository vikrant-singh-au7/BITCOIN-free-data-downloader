"""Double-clickable status and refresh window (Python standard library only)."""
import json
import ctypes
import datetime as dt
from tkinter import ttk
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox,filedialog
import shutil
import runtime

from runtime import ROOT,command as process_command
PYTHON = str(Path(sys.executable).with_name('python.exe'))
window = tk.Tk()
window.title('BITCOIN free data downloader')
window.geometry('980x840')
window.configure(padx=22, pady=18)


def choose_folder(first=False):
    global ROOT
    while True:
        selected = filedialog.askdirectory(parent=window,title='Choose where to save BTC options data',
                    initialdir=str(ROOT if ROOT.exists() else Path.home()),mustexist=False)
        if not selected:
            return False
        try:
            folder,free = runtime.validate_folder(selected)
            note = ('Space is below the suggested 60 GiB planning allowance. The final size varies; '
                    'you may need to free space later.\n\n') if free<60*1024**3 else ''
            if not messagebox.askyesno('Confirm download location',
                    f'Data folder:\n{folder}\n\nFree space on this drive: {free/1024**3:.1f} GiB\n\n'
                    +note+'All data, exports and download logs will be saved here.\n'
                    'Choose the original archive folder to resume existing data.\n'
                    'Existing data is not moved automatically.\n\nUse this folder?',parent=window):
                continue
            ROOT,_ = runtime.select_folder(folder)
            return True
        except (OSError,ValueError) as exc:
            messagebox.showerror('Cannot use this folder',str(exc),parent=window)


if runtime.needs_folder_selection():
    window.withdraw()
    if not choose_folder(first=True):
        window.destroy()
        raise SystemExit(0)
    window.deiconify()
tk.Label(window, text='BITCOIN free data downloader', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
tk.Label(window, text='Delta Exchange India • Calls and puts only • One-minute history', font=('Segoe UI', 11)).pack(anchor='w', pady=(4,18))
storage = tk.StringVar()
tk.Label(window,textvariable=storage,justify='left',anchor='w',wraplength=920,font=('Segoe UI',10)).pack(fill='x',pady=(0,10))
details = tk.StringVar(value='Loading status…')
tk.Label(window, textvariable=details, justify='left', anchor='nw', font=('Consolas', 10), wraplength=665).pack(fill='both', expand=True)


def launch(*args):
    log = open(ROOT/'launcher.log', 'a', encoding='utf-8')
    subprocess.Popen([*process_command('worker'), *args], cwd=ROOT,
                     creationflags=subprocess.CREATE_NO_WINDOW, stdout=log, stderr=log)
    log.close()


def update():
    try:
        _,free = runtime.validate_folder(ROOT)
    except (OSError,ValueError) as exc:
        messagebox.showerror('Download cannot start',str(exc),parent=window)
        return
    if free < 60*1024**3 and not messagebox.askyesno('Check available storage',
            f'Selected folder:\n{ROOT}\n\nFree space: {free/1024**3:.1f} GiB\n'
            'Suggested allowance for a full archive: about 60 GiB (size varies).\n'
            'The downloader pauses below 2 GiB free.\n\nContinue with this folder?',parent=window):
        return
    with open(ROOT/'launcher.log','a',encoding='utf-8') as output:
        subprocess.Popen([*process_command('supervisor'),'--enable'],cwd=ROOT,
                         creationflags=subprocess.CREATE_NO_WINDOW,stdout=output,stderr=output)


def stop():
    (ROOT/'auto_resume.enabled').write_text('no')
    (ROOT/'stop.request').write_text('stop')


def alive(pid):
    if not pid:
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    code = ctypes.c_ulong()
    ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    return bool(ok and code.value == 259)


def local(value):
    if value is None:
        return 'not yet recorded'
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value).timestamp()
    zone = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return dt.datetime.fromtimestamp(value,zone).strftime('%d %b %Y %I:%M:%S %p IST')


def duration(value):
    if value is None:
        return 'measuring...'
    hours = value / 3600
    return f'{hours:.1f} hours' if hours < 48 else f'{hours/24:.1f} days'


def poll():
    try:
        free = shutil.disk_usage(ROOT).free
        storage.set(f'Download folder: {ROOT}\nDrive free space: {free/1024**3:.1f} GiB | Pauses below 2 GiB free')
    except OSError:
        storage.set(f'Download folder unavailable: {ROOT}')
    try:
        s = json.loads((ROOT/'status.json').read_text(encoding='utf-8'))
        active = alive(s.get('pid'))
        phase = s.get('phase','Ready')
        if s.get('running') and not active:
            phase = 'NOT RUNNING - click Update / Resume'
        a = s.get('archive',{})
        total = a.get('candles',0)
        planned = s.get('planned_windows',0)
        saved = s.get('run_windows',0)
        overall = s.get('overall_windows',0)
        target = s.get('target_windows',0)
        pct = min(100,overall/target*100) if target else 0
        progress['value'] = pct
        update_button['state'] = 'disabled' if active else 'normal'
        stop_button['state'] = 'normal' if active else 'disabled'
        recovery_enabled = (ROOT/'auto_resume.enabled').exists() and (ROOT/'auto_resume.enabled').read_text().strip()=='yes'
        stop_button['state'] = 'normal' if active or recovery_enabled else 'disabled'
        folder_button['state'] = 'disabled' if active or recovery_enabled else 'normal'
        lines = [f'Status: {phase}', f'Background downloader: {"RUNNING" if active else "STOPPED"}',
                 '', f'TOTAL SAVED: {total:,} candle records',
                 f'Contracts with candle data: {a.get("contracts_with_data",0):,} / {s.get("contracts",0):,} discovered',
                 f'Database size: {a.get("bytes",0)/1024**2:,.1f} MB',
                 f'Earliest saved candle: {local(a.get("first"))}',
                 f'Latest saved candle:   {local(a.get("last"))}',
                 'Date extremes do not mean every intervening contract is downloaded.', '']
        for kind in ('trades','mark','oi'):
            info=a.get('series',{}).get(kind,{})
            lines.append(f'  {kind:7s}: {info.get("candles",0):>12,} candles | {info.get("windows",0):,} saved batches')
        lines += ['',f'Overall archive: {overall:,} / {target:,} batches ({pct:.2f}%)',
                  f'This run: {saved:,} / {planned:,} remaining batches',
                  f'This run: {s.get("run_rows",0):,} candle records received',
                  f'Speed: {s.get("batches_per_second",0):.1f} batches/sec | {s.get("workers",8)} workers',
                  f'Est. remaining: trades {duration(s.get("trades_eta_seconds"))} | all data {duration(s.get("eta_seconds"))}',
                  f'Priority: {s.get("mode","All series")}',
                  f'Automatic recovery: {"ON" if (ROOT/"auto_resume.enabled").exists() and (ROOT/"auto_resume.enabled").read_text().strip()=="yes" else "OFF"} | queued retries: {s.get("queued_retries",0)}',
                  f'Unresolved failed batches: {a.get("failures",0):,}',
                  f'Current contract / series: {s.get("current_contract") or "--"} / {s.get("current_series") or "--"}',
                  f'Requested from: {local(s.get("current_start"))}',
                  f'Requested to:   {local(s.get("current_end"))}',
                  f'Last activity:  {local(s.get("heartbeat"))}']
        if phase == 'Discovering contracts':
            lines.append(f'Catalog scan: {s.get("catalog_state")} page {s.get("catalog_page")}')
        if s.get('error'):
            lines.append('Error: '+s['error'])
        details.set('\n'.join(lines))
    except (OSError, ValueError):
        details.set('Loading archive status. Click Update / Resume if the downloader is stopped.')
        folder_button['state'] = 'normal'
    window.after(1500, poll)


buttons = tk.Frame(window)
buttons.pack(fill='x', pady=12)
update_button = tk.Button(buttons,text='Update / Resume',command=update,padx=9,pady=7)
update_button.pack(side='left',padx=(0,7))
stop_button = tk.Button(buttons,text='Stop safely',command=stop,padx=9,pady=7)
stop_button.pack(side='left',padx=(0,7))
folder_button = tk.Button(buttons,text='Change data folder',command=choose_folder,padx=9,pady=7)
folder_button.pack(side='left',padx=(0,7))
for label,action in [('Open data folder',lambda: os.startfile(ROOT)),('Export CSV',lambda: launch('--export'))]:
    tk.Button(buttons,text=label,command=action,padx=9,pady=7).pack(side='left',padx=(0,7))
progress = ttk.Progressbar(window,maximum=100)
progress.pack(fill='x',pady=(0,8))
tk.Label(window, text='Created by Vikrant Singh | Local storage | No API key required', font=('Segoe UI', 9)).pack(anchor='w')
poll()
window.mainloop()
