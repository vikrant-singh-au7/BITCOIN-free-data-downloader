"""Restart this specific archive job after failure, network loss or next login."""
import argparse
import ctypes
import json
import logging
import msvcrt
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

from runtime import ROOT,command,install_autostart
FLAG = ROOT/'auto_resume.enabled'


def enabled():
    return FLAG.exists() and FLAG.read_text().strip() == 'yes'


def alive(pid):
    if not pid:
        return False
    k = ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.GetExitCodeProcess.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k.OpenProcess(0x1000,False,int(pid))
    if not h:
        return False
    value = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h,ctypes.byref(value))
    k.CloseHandle(h)
    return bool(ok and value.value == 259)


def read_status():
    try:
        return json.loads((ROOT/'status.json').read_text())
    except (OSError,ValueError):
        return {}


def wait(seconds):
    deadline = time.monotonic()+seconds
    while enabled() and time.monotonic()<deadline:
        time.sleep(1)


def main(enable=False):
    if enable:
        FLAG.write_text('yes')
        install_autostart()
        (ROOT/'stop.request').unlink(missing_ok=True)
    lock = open(ROOT/'supervisor.lock','a+b')
    lock.write(b'0');lock.flush();lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        return
    logging.basicConfig(filename=ROOT/'supervisor.log',level=logging.INFO,
                        format='%(asctime)s %(message)s')
    python = str(Path(sys.executable).with_name('python.exe'))
    delay = 15
    while enabled():
        state = read_status()
        if state.get('running') and alive(state.get('pid')):
            wait(2)
            continue
        if shutil.disk_usage(ROOT).free < 2*1024**3:
            logging.warning('Waiting for at least 2 GB free space')
            wait(60)
            continue
        try:
            req = urllib.request.Request('https://api.india.delta.exchange/v2/time',
                                         headers={'User-Agent':'BTCOptionsArchiveWatchdog/1.0'})
            # A 404 still proves network connectivity; other errors are retried.
            try:
                with urllib.request.urlopen(req,timeout=15) as response:
                    response.read()
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
        except Exception as exc:
            logging.warning('Waiting for Delta connectivity: %s',exc)
            wait(delay)
            delay = min(delay*2,300)
            continue
        delay = 15
        (ROOT/'stop.request').unlink(missing_ok=True)
        with open(ROOT/'launcher.log','a',encoding='utf-8') as output:
            worker = subprocess.Popen(command('worker'),cwd=ROOT,
                       creationflags=subprocess.CREATE_NO_WINDOW,stdout=output,stderr=output)
        logging.info('Started/resumed downloader PID %s',worker.pid)
        while worker.poll() is None:
            if not enabled():
                (ROOT/'stop.request').write_text('stop')
            time.sleep(1)
        if not enabled():
            break
        if worker.returncode == 0 and read_status().get('phase') == 'Up to date':
            logging.info('Archive completed. Automatic recovery disabled until next Update.')
            FLAG.write_text('no')
            break
        logging.warning('Worker exited %s. Retrying in %ss',worker.returncode,delay)
        wait(delay)
        delay = min(delay*2,300)
    lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--enable',action='store_true')
    args = parser.parse_args()
    main(args.enable)
