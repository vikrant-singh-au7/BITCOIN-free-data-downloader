import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import downloader as d


class ArchiveTests(unittest.TestCase):
    def test_child_process_command_preserves_archive_folder(self):
        import runtime
        for mode in ('worker','supervisor'):
            args = runtime.command(mode)
            self.assertIn('--'+mode,args)
            self.assertEqual(args[args.index('--data-dir')+1],str(runtime.ROOT))

    def test_https_connection_reused(self):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = b'{"success":true,"result":[]}'
        with patch.object(d,'HTTP_LOCAL',d.threading.local()),patch.object(d,'pace'), \
             patch.object(d.http.client,'HTTPSConnection',return_value=connection) as create:
            for _ in range(2):
                self.assertTrue(d.http_json(d.BASE+'/history/candles?symbol=test')['success'])
            self.assertEqual(create.call_count,1)
            self.assertEqual(connection.request.call_count,2)

    def test_status_file_collision_does_not_stop_download(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(d,'ROOT',Path(folder)), patch.object(d,'STATUS_CACHE',{}), \
                 patch.object(Path,'replace',side_effect=PermissionError('busy')),patch.object(d.time,'sleep'):
                d.status(phase='Downloading')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = d.DATA
        d.DATA = Path(self.tmp.name)
        self.db = d.database()
        self.db.execute('INSERT INTO products VALUES(?,?,?,?)', ('C-BTC-1-010126', 0, 300000, '{}'))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        d.DATA = self.old
        self.tmp.cleanup()

    def test_options_only(self):
        for kind, symbol, asset, expected in [
            ('call_options','C-BTC-1-010126','BTC',True),
            ('put_options','P-BTC-1-010126','BTC',True),
            ('perpetual_futures','BTCUSD','BTC',False),
            ('call_options','C-ETH-1-010126','ETH',False)]:
            self.assertEqual(d.btc(dict(contract_type=kind,symbol=symbol,underlying_asset={'symbol':asset})),expected)

    def test_resume_keeps_holes_and_extends_partial(self):
        now = 1000000
        # First and third windows saved; middle one must still be requested.
        for start, end in [(0,d.STEP),(2*d.STEP,250000)]:
            self.db.execute('INSERT INTO windows VALUES(?,?,?,?,?,?,?)',
                            ('C-BTC-1-010126','trades',start,end,now,10,b''))
        self.db.commit()
        jobs = list(d.jobs(self.db, now, ['trades']))
        self.assertEqual([j[2] for j in jobs], [d.STEP,2*d.STEP])

    def test_failed_window_not_skipped(self):
        self.db.execute('INSERT INTO failures VALUES(?,?,?,?,?,?)', ('C-BTC-1-010126','trades',0,d.STEP,'network',1))
        self.assertEqual(next(d.jobs(self.db,1000000,['trades']))[2],0)

    def test_all_trades_prioritized_before_other_series(self):
        self.db.execute('INSERT INTO products VALUES(?,?,?,?)', ('P-BTC-1-020126',0,120,'{}'))
        kinds = [job[1] for job in d.jobs(self.db,1000000,['trades','mark','oi'])]
        self.assertEqual(kinds, sorted(kinds,key=['trades','mark','oi'].index))

    def test_completed_empty_windows_not_downloaded_again(self):
        self.db.execute('INSERT INTO windows VALUES(?,?,?,?,?,?,?)', ('C-BTC-1-010126','trades',0,d.STEP,1,0,b''))
        self.assertNotIn(0,[j[2] for j in d.jobs(self.db,1000000,['trades'])])

    def test_fetch_deduplicates_and_excludes_boundary(self):
        candles = [dict(time=t,open=1,high=2,low=1,close=2) for t in (0,0,60,120)]
        with patch.object(d,'api',return_value={'result':candles}):
            rows,payload = d.fetch(('C-BTC-1-010126','trades',0,120))
        self.assertEqual([r['time'] for r in rows],[0,60])
        self.assertEqual(json.loads(d.zlib.decompress(payload)), rows)

    def test_partial_extension_requests_only_missing_tail(self):
        job=('C-BTC-1-010126','trades',0,180)
        with patch.object(d,'api',return_value={'result':[]}) as call:
            d.fetch(job,120)
        self.assertEqual(call.call_args.kwargs['start'],120)
        self.assertEqual(call.call_args.kwargs['end'],179)

    def test_recent_completed_window_not_downloaded_again(self):
        now=1000000
        self.db.execute('INSERT INTO windows VALUES(?,?,?,?,?,?,?)',
                        ('C-BTC-1-010126','trades',0,d.STEP,now-2000,100,b''))
        self.assertNotIn(0,[j[2] for j in d.jobs(self.db,now,['trades'])])

    def test_refresh_preserves_archived_candles(self):
        job = ('C-BTC-1-010126','trades',0,120)
        candles = [dict(time=0,open=1,high=2,low=1,close=2)]
        d.save_window(self.db, job, candles, d.zlib.compress(json.dumps(candles).encode()))
        d.save_window(self.db, job, [], d.zlib.compress(b'[]'))
        row = self.db.execute('SELECT rows,payload FROM windows').fetchone()
        self.assertEqual(row[0],1)
        self.assertEqual(json.loads(d.zlib.decompress(row[1])),candles)
        stats = d.archive_stats(self.db)
        self.assertEqual(stats['candles'],1)
        self.assertEqual(stats['first'],0)
        self.assertEqual(stats['last'],0)
        self.assertEqual(stats['contracts_with_data'],1)


if __name__ == '__main__':
    unittest.main()
