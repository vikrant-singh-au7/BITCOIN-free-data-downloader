"""Shared writable storage and source/frozen process commands."""
import os
from pathlib import Path
import sys
import json
import shutil
import tempfile

SOURCE = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys,'frozen',False))
CONFIG = Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'BitcoinFreeDataDownloader'/'settings.json'


def saved_folder():
    try:
        value = json.loads(CONFIG.read_text(encoding='utf-8')).get('data_dir')
        return Path(value) if value and Path(value).is_absolute() else None
    except (OSError,ValueError,TypeError):
        return None


ROOT = Path(os.environ['BTC_OPTIONS_HOME']) if os.environ.get('BTC_OPTIONS_HOME') else (
    saved_folder() or (CONFIG.parent if FROZEN else SOURCE))


def needs_folder_selection():
    return not os.environ.get('BTC_OPTIONS_HOME') and saved_folder() is None


def validate_folder(path):
    folder = Path(path).expanduser().resolve()
    folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryFile(dir=folder) as probe:
        probe.write(b'write test')
    free = shutil.disk_usage(folder).free
    if free < 2*1024**3:
        raise ValueError('This drive has less than 2 GiB free. Choose another drive or free space first.')
    return folder,free


def select_folder(path):
    global ROOT
    folder,free = validate_folder(path)
    CONFIG.parent.mkdir(parents=True,exist_ok=True)
    tmp = CONFIG.with_suffix('.tmp')
    tmp.write_text(json.dumps({'data_dir':str(folder)},indent=2),encoding='utf-8')
    tmp.replace(CONFIG)
    ROOT = folder
    os.environ['BTC_OPTIONS_HOME'] = str(folder)
    return folder,free


def command(mode='worker'):
    if FROZEN:
        return [sys.executable,'--'+mode,'--data-dir',str(ROOT)]
    python = str(Path(sys.executable).with_name('python.exe'))
    return [python,str(SOURCE/'main.py'),'--'+mode,'--data-dir',str(ROOT)]


def install_autostart():
    import subprocess
    import winreg
    args = command('supervisor')
    if not FROZEN:
        args[0] = str(Path(args[0]).with_name('pythonw.exe'))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        winreg.SetValueEx(key,'BitcoinFreeDataDownloader',0,winreg.REG_SZ,subprocess.list2cmdline(args))
