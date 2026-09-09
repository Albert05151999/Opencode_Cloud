#!/usr/bin/env python3
"""Start the localhost chat and administration UI."""
import argparse
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import threading
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    import uvicorn
    from local_web.server import create_local_app
    from local_web.runtime import LocalServer
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}/chat')).start()
    LocalServer(uvicorn.Config(create_local_app(), host='127.0.0.1', port=args.port,
        access_log=False, timeout_graceful_shutdown=5)).run()


if __name__ == '__main__':
    main()
