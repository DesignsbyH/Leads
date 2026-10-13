"""Requests from the browser extension, served two ways:

* native_host.py — Edge/Chrome start it on demand, so leads save even when the desktop app is closed.
* the HTTP bridge below — on 127.0.0.1 while the desktop app is open; every request except /health must carry
  the pairing key in X-LeadDock-Key.

Actions (HTTP: POST /<action> with a JSON body):
  capture  {business: {...}, crm: {status, priority, next_followup, note, note_type}}  -> save/refresh a lead
  lookup   {business: {...}}                    -> is this business already a lead? (with recent activity)
  update   {id, status?, priority?, next_followup?, note?, note_type?}
  focus    {id}                                 -> show the lead in the desktop app
"""
import json, secrets, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import store

PORT = 18765
MAX_BODY = 262_144
API = 4  # 4 = native helper + offline queue aware


def health():
    return {'ok': True, 'app': 'LeadDock', 'version': store.VERSION, 'api': API,
            'stages': store.STAGES, 'priorities': store.PRIORITIES, 'activity_types': store.ACTIVITY_TYPES, 'industries': store.INDUSTRIES}


def business_of(body):
    # The 2.0 extension posted the business fields at the top level.
    biz = body.get('business', body)
    if not isinstance(biz, dict):
        raise ValueError('business must be an object')
    return biz


def handle(action, body):
    """Run one extension request. Returns (response, event) where event is (kind, lead_id, outcome) or None."""
    if action == 'health':
        return health(), None
    if action == 'capture':
        crm = body.get('crm') if isinstance(body.get('crm'), dict) else None
        lead_id, outcome, changes = store.store_lead(business_of(body), crm)
        return ({'ok': True, 'id': lead_id, 'result': outcome, 'name': store.get_lead(lead_id)['name'],
                 'changes': [{'field': store.LABELS[k], 'old': o, 'new': n} for k, o, n in changes],
                 'lead': store.lead_summary(lead_id)}, ('capture', lead_id, outcome))
    if action == 'lookup':
        biz = business_of(body)
        row = store.lookup(biz)
        return {'ok': True, 'found': bool(row), 'lead': store.lead_summary(row['id']) if row else None,
                'suggested_industry': store.industry_for(biz.get('category', ''), biz.get('name', ''))}, None
    if action == 'update':
        lead_id = int(body['id'])
        if not store.get_lead(lead_id):
            raise ValueError('That lead was deleted in LeadDock.')
        store.apply_crm(lead_id, body)
        return {'ok': True, 'lead': store.lead_summary(lead_id)}, ('update', lead_id, 'updated')
    if action == 'focus':
        return {'ok': True}, ('focus', int(body['id']), '')
    raise ValueError(f'Unknown request: {action}')


def make_handler(key, on_event=lambda kind, lead_id, outcome: None):
    """on_event(kind, lead_id, outcome) is called from the server thread after captures/updates."""

    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-LeadDock-Key')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.end_headers()

        def respond(self, code, body):
            blob = json.dumps(body).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(blob)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(blob)

        def do_GET(self):
            if self.path == '/health':
                self.respond(200, health())
            else:
                self.respond(404, {'error': 'Not found'})

        def read_json(self):
            length = int(self.headers.get('Content-Length', '0') or 0)
            if length < 2 or length > MAX_BODY:
                raise ValueError('Payload size invalid')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object')
            return body

        def do_POST(self):
            action = self.path.strip('/')
            if action not in ('capture', 'lookup', 'update', 'focus'):
                return self.respond(404, {'error': 'Not found'})
            if not secrets.compare_digest(self.headers.get('X-LeadDock-Key', ''), key):
                return self.respond(403, {'error': 'Invalid pairing key — copy it again from LeadDock → Connect browser'})
            try:
                response, event = handle(action, self.read_json())
            except (ValueError, KeyError, TypeError) as e:
                return self.respond(400, {'error': str(e)})
            except Exception as e:
                return self.respond(500, {'error': 'LeadDock error: ' + str(e)})
            self.respond(200, response)
            if event:
                on_event(*event)

        def log_message(self, *args):
            pass

    return Handler


def start_server(key, on_event, port=PORT):
    """Raises OSError if the port is taken (another LeadDock is already running)."""
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(key, on_event))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name='leaddock-bridge').start()
    return server
