"""LeadDock browser helper (an Edge/Chrome "native messaging" host).

Edge starts this script on demand whenever the extension saves or looks up a lead, so leads go straight into the
LeadDock database even when the desktop app is closed. The desktop app registers it on every start
(or run:  python native_host.py --install).

Messages are JSON with a 4-byte length prefix on stdin/stdout, as the browser's native messaging protocol requires.
"""
import json, os, struct, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bridge, store  # noqa: E402

HOST_NAME = 'com.designsbyh.leaddock'
EXTENSION_ID = 'gpeejmphkdjmjbdkkfalmpohbnmdpapg'  # fixed by the "key" in extension/manifest.json
REGISTRY_KEYS = [r'Software\Microsoft\Edge\NativeMessagingHosts', r'Software\Google\Chrome\NativeMessagingHosts',
                 r'Software\BraveSoftware\Brave-Browser\NativeMessagingHosts']


def read_message(stream):
    header = stream.read(4)
    if len(header) < 4:
        return None  # the browser closed the connection
    (length,) = struct.unpack('=I', header)
    return json.loads(stream.read(length).decode('utf-8'))


def write_message(stream, obj):
    data = json.dumps(obj).encode('utf-8')
    stream.write(struct.pack('=I', len(data)))
    stream.write(data)
    stream.flush()


def focus_running_app(lead_id):
    """Ask an open desktop app to show the lead. Returns False when the app isn't running."""
    req = urllib.request.Request(f'http://127.0.0.1:{bridge.PORT}/focus', data=json.dumps({'id': lead_id}).encode(),
                                 headers={'Content-Type': 'application/json', 'X-LeadDock-Key': store.get_key()})
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=2).read()
        return True
    except Exception:
        return False


def launch_app(lead_id=None):
    python = Path(sys.executable)
    if os.name == 'nt' and python.with_name('pythonw.exe').exists():
        python = python.with_name('pythonw.exe')  # no console window
    args = [str(python), str(HERE / 'app.py')] + (['--select', str(lead_id)] if lead_id else [])
    options = dict(cwd=str(HERE.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == 'nt':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:  # the browser runs helpers inside a job object; break away so the app outlives this helper
            subprocess.Popen(args, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options)
        except OSError:
            subprocess.Popen(args, creationflags=flags, **options)
    else:
        subprocess.Popen(args, start_new_session=True, **options)


def respond(message):
    action = message.get('action')
    if action == 'ping':
        return dict(bridge.health(), helper=True)
    if action == 'open':
        lead_id = int(message['id']) if message.get('id') else None
        if lead_id and focus_running_app(lead_id):
            return {'ok': True, 'opened': 'focused'}
        launch_app(lead_id)
        return {'ok': True, 'opened': 'launched'}
    if action not in ('capture', 'lookup', 'update'):
        raise ValueError(f'Unknown request: {action}')
    response, _ = bridge.handle(action, message)
    return response


def serve(inp=None, out=None):
    inp, out = inp or sys.stdin.buffer, out or sys.stdout.buffer
    store.init_db()
    while True:
        message = read_message(inp)
        if message is None:
            return
        try:
            reply = respond(message)
        except (ValueError, KeyError, TypeError) as e:
            reply = {'ok': False, 'error': str(e)}
        except Exception as e:
            reply = {'ok': False, 'error': 'LeadDock error: ' + str(e)}
        write_message(out, reply)


def host_manifest(launcher):
    return {'name': HOST_NAME, 'description': 'LeadDock browser helper — saves captured leads to your LeadDock database',
            'path': str(launcher), 'type': 'stdio', 'allowed_origins': [f'chrome-extension://{EXTENSION_ID}/']}


def install():
    """Register the helper with Edge, Chrome and Brave for the current Windows user. Safe to run on every start."""
    if os.name != 'nt':
        return 'Browser helper registration is only needed on Windows.'
    import winreg
    folder = store.APP_DIR / 'native'
    folder.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable)
    if python.name.lower() == 'pythonw.exe':
        python = python.with_name('python.exe')  # the helper talks over stdin/stdout, which pythonw doesn't have
    launcher = folder / 'leaddock_host.bat'
    launcher.write_text(f'@echo off\r\n"{python}" "{HERE / "native_host.py"}" %*\r\n', encoding='utf-8')
    manifest = folder / f'{HOST_NAME}.json'
    manifest.write_text(json.dumps(host_manifest(launcher), indent=2), encoding='utf-8')
    for base in REGISTRY_KEYS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + '\\' + HOST_NAME) as key:
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(manifest))
    return 'Browser helper installed — the extension can save leads even when LeadDock is closed.'


if __name__ == '__main__':
    if '--install' in sys.argv:
        print(install())
    else:
        serve()
