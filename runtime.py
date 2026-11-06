"""Shared writable storage and source/frozen process commands."""
import os
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys,'frozen',False))
ROOT = Path(os.environ['BTC_OPTIONS_HOME']) if os.environ.get('BTC_OPTIONS_HOME') else (
    Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'BitcoinFreeDataDownloader' if FROZEN else SOURCE)
ROOT.mkdir(parents=True,exist_ok=True)


def command(mode='worker'):
    if FROZEN:
        return [sys.executable,'--'+mode]
    python = str(Path(sys.executable).with_name('python.exe'))
    return [python,str(SOURCE/('supervisor.py' if mode=='supervisor' else 'downloader.py'))]


def install_autostart():
    import subprocess
    import winreg
    args = command('supervisor')
    if not FROZEN:
        args[0] = str(Path(args[0]).with_name('pythonw.exe'))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        winreg.SetValueEx(key,'BitcoinFreeDataDownloader',0,winreg.REG_SZ,subprocess.list2cmdline(args))
