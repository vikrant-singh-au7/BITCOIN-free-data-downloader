"""Windows executable entry point."""
import runpy
import sys
import os

if __name__ == '__main__':
    if '--data-dir' in sys.argv:
        index = sys.argv.index('--data-dir')
        os.environ['BTC_OPTIONS_HOME'] = sys.argv[index+1]
        del sys.argv[index:index+2]
    if '--worker' in sys.argv:
        sys.argv.remove('--worker')
        runpy.run_module('downloader',run_name='__main__')
    elif '--supervisor' in sys.argv:
        import supervisor
        supervisor.main('--enable' in sys.argv)
    else:
        import gui
