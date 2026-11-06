"""Windows executable entry point."""
import runpy
import sys

if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.argv.remove('--worker')
        runpy.run_module('downloader',run_name='__main__')
    elif '--supervisor' in sys.argv:
        import supervisor
        supervisor.main('--enable' in sys.argv)
    else:
        import gui
