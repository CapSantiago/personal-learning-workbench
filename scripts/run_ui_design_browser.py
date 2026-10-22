"""Start/stop an isolated real Streamlit app and run the browser acceptance."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

repo = Path(__file__).resolve().parents[1]
phase = sys.argv[1] if len(sys.argv) > 1 else 'after'
browser_script = sys.argv[2] if len(sys.argv) > 2 else 'scripts/verify_ui_design_browser.cjs'
folder = repo / '.sandbox' / ('ui-design-' + phase + '-' + str(uuid4()))
folder.mkdir()
env = os.environ.copy()
env['PLW_DESIGN_FOLDER'] = str(folder)
env['NODE_PATH'] = r'C:\Users\张梓灏\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
with (folder / 'server.log').open('wb') as log:
    server = subprocess.Popen([sys.executable, '-B', str(repo / 'scripts/ui_design_fixture.py')],
        cwd=repo, env=env, stdout=log, stderr=log,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        for _ in range(300):
            if (folder / 'config.json').exists():
                break
            if server.poll() is not None:
                raise RuntimeError((folder / 'server.log').read_text(errors='replace'))
            time.sleep(.1)
        for _ in range(100):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8506/_stcore/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Disposable Streamlit app did not become healthy')
        result = subprocess.run([r'D:\node.exe', str(repo / browser_script), str(folder), phase],
                                cwd=repo, env=env, timeout=240)
        print('UI_DESIGN_REPORT', folder, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=5)
