"""Local-only, fail-closed OpenAI gateway for this budget-limited experiment.

Clients receive a dummy token, never the upstream key. Prices checked 2026-11-22:
https://developers.openai.com/api/docs/models/gpt-4.1-mini
https://developers.openai.com/api/docs/models/text-embedding-3-large
Reservations assume uncached input; settlement uses provider-reported cached
tokens at the published cached rate. Unresolved calls retain full reservations.
"""
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
import urllib.request
import urllib.error

D = Decimal


def reservation(path, payload):
    model = payload.get('model')
    # Serialized UTF-8 bytes conservatively bound text/token-array input tokens.
    count = len(json.dumps(payload, ensure_ascii=True).encode()) + 4096
    if path == '/v1/embeddings' and model == 'text-embedding-3-large':
        return D(count) * D('0.13') / 1000000
    if path not in ('/v1/chat/completions','/v1/responses') or model not in ('gpt-4.1-mini', 'gpt-4.1-mini-2025-04-14'):
        raise ValueError('Endpoint/model outside the approved priced scope')
    if payload.get('tools') or payload.get('modalities') or payload.get('prediction') or payload.get('service_tier', 'auto') not in ('auto', 'default'):
        raise ValueError('Only standard text completions are approved')
    if payload.get('previous_response_id') or payload.get('conversation') or payload.get('background'):
        raise ValueError('Hidden history and background calls are not approved')
    if path == '/v1/responses' and payload.get('stream'):
        raise ValueError('Streaming Responses are outside this evaluator scope')
    messages = payload.get('input', []) if path == '/v1/responses' else payload.get('messages', [])
    if not isinstance(messages, list):
        raise ValueError('Expected explicit plain-text message list')
    for message in messages:
        if not isinstance(message.get('content'), (str, type(None))):
            raise ValueError('Only plain-text messages are approved')
    output = payload.get('max_output_tokens') or payload.get('max_completion_tokens') or payload.get('max_tokens') or 32768
    if type(output) is not int or not 1 <= output <= 32768 or payload.get('n', 1) != 1:
        raise ValueError('Unexpected completion bounds')
    return (D(count) * D('0.40') + D(output) * D('1.60')) / 1000000


def usage_cost(path, usage):
    prompt = usage.get('prompt_tokens', usage.get('input_tokens'))
    completion = usage.get('completion_tokens', usage.get('output_tokens', 0))
    if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
        raise ValueError('Invalid usage')
    cached = (usage.get('prompt_tokens_details') or usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
    if type(cached) is not int or not 0 <= cached <= prompt:
        raise ValueError('Invalid cached-token usage')
    if path.endswith('embeddings'):
        return D(prompt) * D('0.13') / 1000000
    return (D(prompt-cached) * D('0.40') + D(cached) * D('0.10')
            + D(completion) * D('1.60')) / 1000000


class Ledger:
    def __init__(self, path, limit='14.40', prior=None, authorized='14.66'):
        self.path = Path(path)
        self.limit = D(limit)
        self.authorized = D(authorized)
        if not 0 < self.limit <= self.authorized:
            raise ValueError('Operating ceiling must be within authorization')
        self.lock = threading.Lock()
        self.exhausted = threading.Event()
        self.stage = 'preflight'
        self.records = []
        if self.path.exists():
            raise FileExistsError('Preserve existing budget ledger; do not reset spending')
        if prior is not None:
            old = json.loads(Path(prior).read_text(encoding='utf-8'))
            if D(old['operating_limit_usd']) > self.limit or D(old.get('authorized_usd','14.66')) > self.authorized:
                raise ValueError('Cannot discard an earlier budget authorization')
            self.records = old['requests']
            for row in self.records:
                row.setdefault('origin_ledger', str(prior))
                if row['state'] == 'reserved':
                    row['state'] = 'prior_attempt_maximum_retained'
                if row['state'] == 'usage_received':
                    row.setdefault('previous_accounted_usd', row['accounted_usd'])
                    row['accounted_usd'] = str(usage_cost(row['endpoint'], row['usage']))
            if sum(D(r['accounted_usd']) for r in self.records) > self.limit:
                self.exhausted.set()
        self.write()

    def write(self):
        data = {'authorized_usd': str(self.authorized), 'operating_limit_usd': str(self.limit),
                'accounted_usd': str(sum(D(r['accounted_usd']) for r in self.records)),
                'note': 'Published token rates including provider-reported cached tokens; unresolved requests retain maximum reservation. Provider billing is authoritative.',
                'usd_per_million_tokens': {'gpt-4.1-mini': {'input': '0.40', 'cached_input': '0.10', 'output': '1.60'}, 'text-embedding-3-large': {'input': '0.13'}},
                'requests': self.records}
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        # Windows readers, OneDrive and antivirus can briefly deny rename.
        # Never forward a request until its reservation has persisted.
        for attempt in range(300):
            try:
                temp.replace(self.path)
                break
            except PermissionError:
                if attempt == 299:
                    raise
                time.sleep(0.1)

    def reserve(self, amount, model, endpoint):
        with self.lock:
            if self.exhausted.is_set() or sum(D(r['accounted_usd']) for r in self.records) + amount > self.limit:
                self.exhausted.set()
                raise ValueError('Budget limit reached; no request was forwarded')
            row = {'sequence': len(self.records)+1, 'stage': self.stage, 'model': model,
                   'endpoint': endpoint, 'started_at': datetime.now(timezone.utc).isoformat(),
                   'state': 'reserved', 'reserved_usd': str(amount), 'accounted_usd': str(amount)}
            self.records.append(row)
            self.write()
            return row

    def settle(self, row, status, usage=None, request_id=None):
        with self.lock:
            row.update(status=status, finished_at=datetime.now(timezone.utc).isoformat(), request_id=request_id)
            if usage is not None:
                cost = usage_cost(row['endpoint'], usage)
                row.update(usage=usage, accounted_usd=str(cost), state='usage_received')
                if cost > D(row['reserved_usd']):
                    self.exhausted.set()
                    row['state'] = 'bound_violation_stop'
            elif 400 <= status < 500 and status != 408:
                row.update(accounted_usd='0', state='rejected_by_provider')
            else:
                row['state'] = 'maximum_retained_no_usage'
            self.write()


def start(ledger, key, port=0):
    token = 'local-budget-' + secrets.token_hex(24)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body, content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.headers.get('Authorization') != 'Bearer ' + token:
                return self.reply(401, b'{"error":{"message":"Invalid local token"}}')
            row = None
            try:
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if data.get('stream'):
                    data['stream_options'] = {'include_usage': True}
                estimate = reservation(self.path, data)
                row = ledger.reserve(estimate, data['model'], self.path)
            except Exception as exc:
                return self.reply(400, json.dumps({'error': {'message': str(exc), 'type': 'budget_gateway'}}).encode())
            try:
                request = urllib.request.Request('https://api.openai.com' + self.path,
                    data=json.dumps(data).encode(), headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
                try:
                    response = urllib.request.urlopen(request, timeout=600)
                except urllib.error.HTTPError as exc:
                    response = exc
                with response:
                    status, body = response.status, response.read()
                    content_type = response.headers.get('Content-Type', 'application/json')
                    request_id = response.headers.get('x-request-id')
                usage = None
                if status == 200:
                    if 'text/event-stream' in content_type:
                        for line in body.splitlines():
                            if line.startswith(b'data: ') and line != b'data: [DONE]':
                                chunk = json.loads(line[6:])
                                usage = chunk.get('usage') or usage
                    else:
                        usage = json.loads(body).get('usage')
                ledger.settle(row, status, usage, request_id)
                self.reply(status, body, content_type)
            except Exception:
                ledger.settle(row, 599)
                self.reply(502, b'{"error":{"message":"Upstream transport failed; maximum reservation retained"}}')

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}/v1', token
