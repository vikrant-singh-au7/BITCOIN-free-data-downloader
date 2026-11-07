"""Delta India BTC options archive. Public, read-only APIs only."""
import argparse
import concurrent.futures as futures
from collections import Counter,deque
import csv
import datetime as dt
import gzip
import heapq
import http.client
import io
import json
import logging
import os
import shutil
from pathlib import Path
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from runtime import ROOT
DATA = ROOT / 'data'
BASE = 'https://api.india.delta.exchange/v2'
STEP = 1800 * 60  # Below the API's 2,000 candle limit, even with inclusive endpoints.
PREFIXES = {'trades': '', 'mark': 'MARK:', 'oi': 'OI:'}
STOP = threading.Event()
STATUS_CACHE = {}
HTTP_LOCAL = threading.local()
RATE_LOCK = threading.Lock()
NEXT_REQUEST = 0.0
COOLDOWN_UNTIL = 0.0
REQUESTS_PER_SECOND = 22.0  # 19,800 weighted units / 5min; published quota 20,000.


def pace():
    global NEXT_REQUEST
    while True:
        if STOP.is_set() or (ROOT/'stop.request').exists():
            raise InterruptedError('Stopped')
        with RATE_LOCK:
            now = time.monotonic()
            wait = max(NEXT_REQUEST, COOLDOWN_UNTIL) - now
            if wait <= 0:
                NEXT_REQUEST = now + 1 / REQUESTS_PER_SECOND
                return
        if STOP.wait(min(max(wait, 0.001), 0.25)):
            raise InterruptedError('Stopped')


def http_json(url):
    # One reusable HTTPS connection per worker avoids a new TLS handshake
    # for every historical window. All calls still share the global rate cap.
    pace()
    parsed = urllib.parse.urlsplit(url)
    connection = getattr(HTTP_LOCAL, 'connection', None)
    if connection is None:
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=30)
        HTTP_LOCAL.connection = connection
    try:
        connection.request('GET', parsed.path + '?' + parsed.query,
                           headers={'User-Agent':'BTCOptionsArchive/2.0','Accept':'application/json',
                                    'Accept-Encoding':'gzip'})
        response = connection.getresponse()
        body = response.read()
        if response.getheader('Content-Encoding') == 'gzip':
            body = gzip.decompress(body)
        if response.status >= 400:
            raise urllib.error.HTTPError(url,response.status,response.reason,response.headers,io.BytesIO(body))
        return json.loads(body)
    except Exception:
        connection.close()
        HTTP_LOCAL.connection = None
        raise


def stamp(value):
    return int(dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())


def utc(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()


def btc(p):
    return (p.get('contract_type') in ('call_options', 'put_options')
            and p.get('underlying_asset', {}).get('symbol') == 'BTC'
            and p.get('symbol', '').startswith(('C-BTC-', 'P-BTC-')))


def api(path, **params):
    global COOLDOWN_UNTIL
    url = BASE + path + '?' + urllib.parse.urlencode(params)
    for attempt in range(7):
        if STOP.is_set() or (ROOT/'stop.request').exists():
            STOP.set()
            raise InterruptedError('Stopped')
        try:
            body = http_json(url)
            if body.get('success') is not True:
                raise ValueError(str(body)[:500])
            return body
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
            if attempt == 6:
                raise
            delay = min(60, 2 ** attempt)
            if isinstance(exc, urllib.error.HTTPError):
                if 400 <= exc.code < 500 and exc.code not in (408, 429):
                    raise
                delay = max(delay, float(exc.headers.get('Retry-After', '0')))
                if exc.code == 429:
                    delay = max(delay, float(exc.headers.get('X-RATE-LIMIT-RESET', '0'))/1000, 2)
                    with RATE_LOCK:
                        COOLDOWN_UNTIL = max(COOLDOWN_UNTIL,time.monotonic()+delay)
            logging.warning('API retry %s: %s', attempt + 1, exc)
            if STOP.wait(delay):
                raise InterruptedError('Stopped')


def database():
    DATA.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(DATA / 'btc_options.sqlite', timeout=60)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS products(symbol TEXT PRIMARY KEY, launch INTEGER,
      expiry INTEGER, metadata TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS windows(symbol TEXT, series TEXT, start INTEGER,
      end INTEGER, checked INTEGER, rows INTEGER, payload BLOB,
      PRIMARY KEY(symbol,series,start));
    CREATE TABLE IF NOT EXISTS failures(symbol TEXT, series TEXT, start INTEGER,
      end INTEGER, error TEXT, checked INTEGER, PRIMARY KEY(symbol,series,start));
    CREATE TABLE IF NOT EXISTS snapshots(time INTEGER PRIMARY KEY, payload BLOB);
    CREATE TABLE IF NOT EXISTS window_bounds(symbol TEXT,series TEXT,start INTEGER,
      first INTEGER,last INTEGER,PRIMARY KEY(symbol,series,start));
    CREATE INDEX IF NOT EXISTS windows_metadata
      ON windows(symbol,series,start,end,checked,rows);
    CREATE INDEX IF NOT EXISTS bounds_first ON window_bounds(first);
    CREATE INDEX IF NOT EXISTS bounds_last ON window_bounds(last);
    ''')
    return db


def status(**values):
    current = STATUS_CACHE
    target = ROOT / 'status.json'
    if not current and target.exists():
        try:
            current.update(json.loads(target.read_text()))
        except (ValueError, OSError):
            pass
    current.update(values, heartbeat=utc(time.time()))
    tmp = target.with_suffix('.tmp')
    # Windows readers/antivirus can briefly prevent replacement. A progress-file
    # collision must never terminate the actual data download.
    for attempt in range(12):
        try:
            tmp.write_text(json.dumps(current, indent=2), encoding='utf-8')
            tmp.replace(target)
            return
        except PermissionError:
            time.sleep(0.05)
        except OSError as exc:
            logging.warning('Could not publish progress (data download continues): %s', exc)
            return
    logging.warning('Progress file busy; will retry on next progress update')


def discover(db):
    # Filters are not trusted: validate every returned product locally.
    marker = ROOT/'catalog_full_scan.json'
    archive = DATA/'contracts.jsonl.gz'
    if not marker.exists() and archive.exists():
        marker.write_text(json.dumps({'time': archive.stat().st_mtime}))
    full_time = json.loads(marker.read_text()).get('time', 0) if marker.exists() else 0
    cached = time.time() - full_time < 86400
    for state in ('live', 'expired', 'upcoming'):
        cursor = None
        seen = set()
        page = 0
        while True:
            params = dict(contract_types='call_options,put_options', states=state, page_size=3000)
            if cursor:
                params['after'] = cursor
            body = api('/products', **params)
            page += 1
            batch = body['result']
            known = {r[0] for r in db.execute('SELECT symbol FROM products')}
            all_known = all(p['symbol'] in known for p in batch if btc(p))
            with db:
                for p in batch:
                    if not btc(p):
                        continue
                    launch = p.get('launch_time') or p.get('auction_start_time')
                    expiry = p.get('settlement_time')
                    if not launch or not expiry:
                        raise ValueError('Missing contract lifecycle: ' + p['symbol'])
                    db.execute('INSERT OR REPLACE INTO products VALUES(?,?,?,?)',
                               (p['symbol'], stamp(launch)//60*60, stamp(expiry), json.dumps(p)))
            count = db.execute('SELECT COUNT(*) FROM products').fetchone()[0]
            logging.info('Catalog %s page %s: %s BTC options discovered', state, page, count)
            status(phase='Discovering contracts', contracts=count, catalog_state=state, catalog_page=page)
            if state == 'expired' and cached and all_known:
                logging.info('Recent full catalog reused; older contracts already indexed')
                break
            cursor = body.get('meta', {}).get('after')
            if not batch or not cursor:
                break
            if cursor in seen:
                raise RuntimeError('Repeated pagination cursor; refusing to silently truncate catalog')
            seen.add(cursor)
    out = DATA / 'contracts.jsonl.gz'
    with gzip.open(out.with_suffix('.tmp'), 'wt', encoding='utf-8') as f:
        for row in db.execute('SELECT metadata FROM products ORDER BY expiry,symbol'):
            f.write(row[0] + '\n')
    out.with_suffix('.tmp').replace(out)
    if not cached:
        marker.write_text(json.dumps({'time': time.time()}))


def jobs_for_series(db, now, series):
    # Window start is anchored to listing time, independent of the run date.
    # Windows are atomic: failed/absent/partly downloaded windows stay eligible.
    # Materialise the small contract list. Holding this cursor while yielding
    # hundreds of thousands of jobs pins the WAL and prevents checkpointing.
    products = db.execute('SELECT symbol,launch,expiry FROM products '
                          'ORDER BY (expiry>?) ASC,expiry DESC,symbol', (now,)).fetchall()
    for symbol, launch, expiry in products:
        end = min(now, expiry + 60)
        for kind in series:
            done = {r[0]: r[1:] for r in db.execute(
                'SELECT start,end,checked,rows FROM windows WHERE symbol=? AND series=?', (symbol, kind))}
            for start in range(launch, end, STEP):
                finish = min(start + STEP, end)
                old = done.get(start)
                if old and old[0] >= finish:
                    # Successful windows are immutable checkpoints, including
                    # explicit empty API responses. Never re-download them.
                    continue
                yield symbol, kind, start, finish


def jobs(db, now, series):
    # Finish traded-price history across ALL contracts before mark and OI.
    for kind in series:
        yield from jobs_for_series(db,now,[kind])


def fetch(job, request_start=None):
    symbol, kind, start, end = job
    requested = start if request_start is None else max(start,request_start)
    result = api('/history/candles', symbol=PREFIXES[kind]+symbol,
                 resolution='1m', start=requested, end=end-1)['result']
    if not isinstance(result, list):
        raise ValueError('Unexpected candles response')
    records = {}
    for c in result:
        t = int(c['time'])
        if t % 60 or not all(k in c for k in ('open','high','low','close')):
            raise ValueError('Invalid candle: ' + str(c))
        if start <= t < end:
            records[t] = c
    rows = [records[t] for t in sorted(records)]
    if len(result) >= 2000:
        raise ValueError('Possible response truncation; window not marked complete')
    return rows, zlib.compress(json.dumps(rows, separators=(',', ':')).encode(), 6)


def save_window(db, job, candles, payload):
    # A transient sparse response must not erase candles already archived.
    old = db.execute('SELECT payload FROM windows WHERE symbol=? AND series=? AND start=?', job[:3]).fetchone()
    if old:
        merged = {c['time']: c for c in json.loads(zlib.decompress(old[0]))}
        merged.update({c['time']: c for c in candles})
        candles = [merged[t] for t in sorted(merged)]
        payload = zlib.compress(json.dumps(candles, separators=(',', ':')).encode(), 6)
    with db:
        db.execute('INSERT OR REPLACE INTO windows VALUES(?,?,?,?,?,?,?)',
                   (*job, int(time.time()), len(candles), payload))
        db.execute('DELETE FROM failures WHERE symbol=? AND series=? AND start=?', job[:3])
        times = [int(c['time']) for c in candles]
        db.execute('INSERT OR REPLACE INTO window_bounds VALUES(?,?,?,?,?)',
                   (*job[:3], min(times) if times else None, max(times) if times else None))


def archive_stats(db):
    result = {'series': {}}
    for kind,n,rows in db.execute('SELECT series,COUNT(*),SUM(rows) FROM windows INDEXED BY windows_metadata GROUP BY series'):
        result['series'][kind] = {'windows': n, 'candles': rows or 0}
    result['candles'] = sum(s['candles'] for s in result['series'].values())
    result['windows'] = sum(s['windows'] for s in result['series'].values())
    result['contracts_with_data'] = db.execute('SELECT COUNT(DISTINCT symbol) FROM windows INDEXED BY windows_metadata WHERE rows>0').fetchone()[0]
    result['failures'] = db.execute('SELECT COUNT(*) FROM failures').fetchone()[0]
    result['first'],result['last'] = db.execute('SELECT (SELECT MIN(first) FROM window_bounds),'
                                              '(SELECT MAX(last) FROM window_bounds)').fetchone()
    result['bytes'] = sum(p.stat().st_size for p in DATA.glob('btc_options.sqlite*'))
    return result


def index_bounds(db):
    pending = db.execute('SELECT w.symbol,w.series,w.start FROM windows w LEFT JOIN window_bounds b '
                         'ON w.symbol=b.symbol AND w.series=b.series AND w.start=b.start WHERE b.symbol IS NULL').fetchall()
    for symbol,kind,start in pending:
        payload = db.execute('SELECT payload FROM windows WHERE symbol=? AND series=? AND start=?',
                             (symbol,kind,start)).fetchone()[0]
        times = [int(c['time']) for c in json.loads(zlib.decompress(payload))]
        db.execute('INSERT OR REPLACE INTO window_bounds VALUES(?,?,?,?,?)',
                   (symbol,kind,start,min(times) if times else None,max(times) if times else None))
    db.commit()


def run(workers=96, series=('trades','mark','oi')):
    import msvcrt
    ROOT.mkdir(parents=True,exist_ok=True)
    lock = open(ROOT / 'download.lock', 'a+b')
    lock.seek(0)
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print('Another downloader is already running.')
        return 2
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(ROOT/'download.log', encoding='utf-8')]+([logging.StreamHandler()] if __import__('sys').stderr else []))
    (ROOT / 'stop.request').unlink(missing_ok=True)
    status(phase='Preparing archive indexes',pid=os.getpid(),running=True,error=None)
    db = database()
    status(phase='Starting', pid=os.getpid(), running=True, error=None, run_windows=0, run_rows=0,
           planned_windows=0,run_failures=0,current_contract=None,current_series=None,current_start=None,
           current_end=None,cutoff_utc=None,started=time.time(),batches_per_second=0,
           eta_seconds=None,trades_eta_seconds=None)
    status(mode='One-minute trades first, then mark and OI',workers=workers,rate_limit=REQUESTS_PER_SECOND)
    try:
        status(phase='Reading saved archive totals')
        index_bounds(db)
        status(archive=archive_stats(db))
        discover(db)
        now = int(time.time())//60*60  # Only closed candles.
        chain = api('/tickers', contract_types='call_options,put_options', underlying_asset_symbols='BTC')['result']
        chain = [p for p in chain if p.get('symbol', '').startswith(('C-BTC-', 'P-BTC-'))]
        with db:
            db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?)', (int(time.time()), zlib.compress(json.dumps(chain).encode())))
        queue = iter(jobs(db, now, series))
        by_series = Counter(job[1] for job in jobs(db, now, series))
        planned = sum(by_series.values())
        target_windows = sum(max(0,(min(now,expiry+60)-launch+STEP-1)//STEP)*len(series)
                             for launch,expiry in db.execute('SELECT launch,expiry FROM products').fetchall())
        baseline_complete = target_windows-planned
        status(planned_windows=planned,planned_by_series=dict(by_series),target_windows=target_windows,
               overall_windows=baseline_complete)
        logging.info('%s history windows to download', planned)
        completed = rows = failed = 0
        completed_by_series = Counter()
        work_started = time.monotonic()
        speed_samples = deque([(work_started,0)])
        last_progress = 0
        last_totals = 0
        last_status = 0
        totals = archive_stats(db)
        retry_heap = []
        retry_attempts = Counter()
        retry_serial = 0
        with futures.ThreadPoolExecutor(max_workers=workers) as pool:
            pending = {}
            exhausted = False
            while pending or not exhausted or retry_heap:
                if (ROOT/'stop.request').exists():
                    STOP.set()
                while not STOP.is_set() and len(pending) < workers*2:
                    if retry_heap and retry_heap[0][0] <= time.monotonic():
                        _,_,job = heapq.heappop(retry_heap)
                    elif not exhausted:
                        job = next(queue,None)
                        if job is None:
                            exhausted = True
                            continue
                    else:
                        break
                    old = db.execute('SELECT end FROM windows WHERE symbol=? AND series=? AND start=?',job[:3]).fetchone()
                    request_start = max(job[2],old[0]) if old else job[2]
                    pending[pool.submit(fetch,job,request_start)] = job
                if time.time() - last_progress >= 5:
                    active = next(iter(pending.values()), None)
                    if time.time()-last_totals >= 30:
                        totals = archive_stats(db)
                        last_totals = time.time()
                    sample_time = time.monotonic()
                    speed_samples.append((sample_time,completed))
                    while len(speed_samples)>2 and speed_samples[1][0]<sample_time-120:
                        speed_samples.popleft()
                    speed = (completed-speed_samples[0][1])/max(sample_time-speed_samples[0][0],1)
                    status(phase='Downloading' if not STOP.is_set() else 'Stopping safely',
                           archive=totals, pending_requests=len(pending),batches_per_second=round(speed,2),
                           queued_retries=len(retry_heap),
                           overall_windows=baseline_complete+completed,
                           eta_seconds=round((planned-completed)/speed) if speed else None,
                           trades_eta_seconds=round(max(0,by_series['trades']-completed_by_series['trades'])/speed) if speed else None,
                           current_contract=active[0] if active else None,
                           current_series=active[1] if active else None,
                           current_start=active[2] if active else None,current_end=active[3] if active else None)
                    last_progress = time.time()
                if not pending:
                    if retry_heap and not STOP.is_set():
                        STOP.wait(1)
                        continue
                    break
                ready, _ = futures.wait(pending, timeout=1, return_when=futures.FIRST_COMPLETED)
                for future in ready:
                    job = pending.pop(future)
                    try:
                        candles, payload = future.result()
                        if shutil.disk_usage(DATA).free < 2 * 1024**3:
                            STOP.set()
                            raise OSError('Less than 2 GB free disk space; download stopped. Free space and resume.')
                        save_window(db, job, candles, payload)
                        completed += 1
                        completed_by_series[job[1]] += 1
                        retry_attempts.pop(job,None)
                        rows += len(candles)
                    except InterruptedError:
                        pass
                    except Exception as exc:
                        failed += 1
                        logging.error('%s: %s', job, exc)
                        with db:
                            db.execute('INSERT OR REPLACE INTO failures VALUES(?,?,?,?,?,?)', (*job, str(exc), int(time.time())))
                        if not STOP.is_set():
                            retry_attempts[job] += 1
                            delay = min(300,15*2**min(retry_attempts[job]-1,5))
                            retry_serial += 1
                            heapq.heappush(retry_heap,(time.monotonic()+delay,retry_serial,job))
                            logging.info('Automatic retry scheduled in %ss for %s',delay,job)
                    if completed % 50 == 0 or failed:
                        logging.info('%s windows saved; %s candles this run; %s failed', completed, rows, failed)
                    if time.time()-last_status >= 1:
                        status(phase='Downloading', run_windows=completed, run_rows=rows,
                               run_failures=failed, cutoff_utc=utc(now))
                        last_status = time.time()
        report(db)
        status(archive=archive_stats(db),overall_windows=baseline_complete+completed)
        failures = db.execute('SELECT COUNT(*) FROM failures').fetchone()[0]
        status(phase='Stopped; click Update to resume' if STOP.is_set() else
               ('Finished with failures; click Update to retry' if failures else 'Up to date'), running=False)
        return 1 if failures else 0
    except InterruptedError:
        status(phase='Stopped; click Update to resume', running=False)
        return 0
    except Exception as exc:
        logging.exception('Download interrupted by error')
        status(phase='Error; click Update to retry', running=False, error=str(exc))
        return 1
    finally:
        db.close()
        lock.close()


def report(db):
    summary = {'exchange': 'Delta Exchange India', 'resolution': '1m', 'generated_utc': utc(time.time()),
               'contracts': db.execute('SELECT COUNT(*) FROM products').fetchone()[0], 'series': {}}
    for kind in PREFIXES:
        r = db.execute('SELECT COUNT(*),COALESCE(SUM(rows),0),MIN(start),MAX(end),SUM(rows=0) FROM windows WHERE series=?', (kind,)).fetchone()
        summary['series'][kind] = dict(zip(('windows','candles','earliest_window','latest_window_end','empty_windows'), r))
    summary['failed_windows'] = db.execute('SELECT COUNT(*) FROM failures').fetchone()[0]
    (ROOT/'coverage.json').write_text(json.dumps(summary, indent=2))
    with open(ROOT/'failed_windows.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['symbol','series','start','end','error','checked'])
        writer.writerows(db.execute('SELECT * FROM failures'))
    return summary


def export(symbol=None):
    db = database()
    folder = ROOT/'exports'
    folder.mkdir(exist_ok=True)
    for kind in PREFIXES:
        path = folder / f'{symbol or "all_btc_options"}_{kind}_1m.csv.gz'
        sql = 'SELECT symbol,payload FROM windows WHERE series=?'
        args = [kind]
        if symbol:
            sql += ' AND symbol=?'
            args.append(symbol)
        sql += ' ORDER BY symbol,start'
        with gzip.open(path.with_suffix('.tmp'), 'wt', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol','time_unix','time_utc','open','high','low','close','volume'])
            for name, payload in db.execute(sql, args):
                for c in json.loads(zlib.decompress(payload)):
                    writer.writerow([name,c['time'],utc(c['time']),c['open'],c['high'],c['low'],c['close'],c.get('volume')])
        path.with_suffix('.tmp').replace(path)
        print(path)
    db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=96)
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--symbol')
    parser.add_argument('--report', action='store_true')
    args = parser.parse_args()
    if args.export:
        export(args.symbol)
    elif args.report:
        db = database()
        print(json.dumps(report(db), indent=2))
        db.close()
    else:
        raise SystemExit(run(max(1, min(args.workers, 96))))
