import base64, contextlib, hashlib, importlib.util, io, json, sys, tempfile, threading, unittest, urllib.request, uuid
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
sys.dont_write_bytecode = True
EVENTS = [{'type':'transcript.text.delta','delta':'合成测试','timestamp':[0,1000],'custom':{'keep':True}},
          {'type':'transcript.text.done','text':'合成测试'}]
spec=importlib.util.spec_from_file_location('asr_security_source',Path(__file__).resolve().parents[1]/'scripts/transcribe_stepfun.py')
asr=importlib.util.module_from_spec(spec);spec.loader.exec_module(asr)

class ASRRedirectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rc6-asr-security-')
        self.root = Path(self.temp.name)
        self.audio = self.root / 'synthetic.mp3'; self.audio.write_bytes(b'chunk-001')
        self.token = 'synthetic-' + uuid.uuid4().hex
        self.calls = []; self.cross_calls = []; self.status_code = 302; self.second_ready = False
        owner = self
        class Sink(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                owner.cross_calls.append(self.headers.get('Authorization') is not None)
                self.send_response(200); self.end_headers(); self.wfile.write(b'data: [DONE]\n')
            do_POST = do_GET
        self.sink = ThreadingHTTPServer(('127.0.0.1', 0), Sink)
        class Source(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                owner.calls.append({'path': self.path, 'method': self.command,
                                    'auth_ok': self.headers.get('Authorization') == 'Bearer ' + owner.token})
                if self.path == '/chunks':
                    payload = json.loads(raw); chunk = base64.b64decode(payload['audio']['data'])
                    if chunk == b'chunk-002' and not owner.second_ready:
                        return self.redirect(f'http://127.0.0.1:{owner.sink.server_port}/sink')
                    return self.events()
                if self.path == '/ok': return self.events()
                if self.path == '/same': return self.redirect(f'http://127.0.0.1:{self.server.server_port}/ok')
                if self.path == '/loop': return self.redirect(f'http://127.0.0.1:{self.server.server_port}/loop')
                if self.path == '/sensitive': return self.redirect(f'http://127.0.0.1:{owner.sink.server_port}/?secret={owner.token}')
                return self.redirect(f'http://127.0.0.1:{owner.sink.server_port}/sink')
            def do_GET(self):
                owner.calls.append({'path': self.path, 'method': self.command,
                                    'auth_ok': self.headers.get('Authorization') == 'Bearer ' + owner.token})
                self.events()
            def redirect(self, target):
                self.send_response(owner.status_code); self.send_header('Location', target); self.end_headers()
            def events(self):
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                for event in EVENTS:
                    self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Source)
        for server in (self.server, self.sink):
            threading.Thread(target=server.serve_forever, daemon=True).start()
    def tearDown(self):
        for server in (self.server, self.sink): server.shutdown(); server.server_close()
        self.temp.cleanup()
    def args(self, path):
        return Namespace(url=f'http://127.0.0.1:{self.server.server_port}{path}', timeout=3,
                         language='zh', hotword=[], model='synthetic', format='mp3', channels=1)
    def normal(self):
        self.assertEqual(asr.transcribe(self.audio, self.token, self.args('/ok')), EVENTS)
        self.assertTrue(self.calls[-1]['auth_ok']); self.assertEqual(self.calls[-1]['method'], 'POST')
        self.calls.clear(); self.cross_calls.clear()
    def test_normal_sse_response_is_unchanged(self):
        self.normal()
    def test_all_redirect_statuses_stop_without_contacting_target(self):
        self.normal()
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.status_code = status
                with self.assertRaisesRegex(asr.ASRRedirectError, str(status)):
                    asr.transcribe(self.audio, self.token, self.args('/cross'))
                self.assertFalse(self.cross_calls)
    def test_same_origin_redirect_requires_endpoint_confirmation(self):
        self.normal()
        with self.assertRaises(asr.ASRRedirectError):
            asr.transcribe(self.audio, self.token, self.args('/same'))
        self.assertEqual([x['path'] for x in self.calls], ['/same'])
    def test_cross_origin_redirect_does_not_send_credentials_or_request(self):
        self.normal()
        with self.assertRaises(asr.ASRRedirectError):
            asr.transcribe(self.audio, self.token, self.args('/cross'))
        self.assertEqual(len(self.calls), 1); self.assertFalse(self.cross_calls)
    def test_https_downgrade_policy_rejects_before_next_request(self):
        self.normal()
        request = urllib.request.Request('https://example.invalid/asr', data=b'synthetic')
        with self.assertRaises(asr.ASRRedirectError):
            asr.RejectASRRedirects().redirect_request(request, None, 302, 'Found', {}, 'http://example.invalid/asr')
        self.assertFalse(self.calls); self.assertFalse(self.cross_calls)
    def test_redirect_loop_is_not_retried(self):
        self.normal()
        with self.assertRaises(asr.ASRRedirectError):
            asr.transcribe(self.audio, self.token, self.args('/loop'))
        self.assertEqual(len(self.calls), 1); self.assertFalse(self.cross_calls)
    def test_rejection_never_prints_credentials_or_location(self):
        self.normal()
        with self.assertRaises(asr.ASRRedirectError) as result:
            asr.transcribe(self.audio, self.token, self.args('/sensitive'))
        self.assertNotIn(self.token, str(result.exception)); self.assertNotIn('http://', str(result.exception))
        self.assertFalse(self.cross_calls)
    def test_redirect_failure_preserves_cache_then_resumes_missing_chunk(self):
        self.normal()
        chunks = self.root/'chunks'; chunks.mkdir(); out = self.root/'out'
        for n in (1,2): (chunks/f'chunk-{n:03}.mp3').write_bytes(f'chunk-{n:03}'.encode())
        def invoke():
            with mock.patch.object(sys,'argv',['asr',str(chunks),str(out),'--api-base-url',f'http://127.0.0.1:{self.server.server_port}/chunks']), \
                 mock.patch.object(asr,'api_url',return_value=self.args('/chunks').url), \
                 mock.patch.object(asr,'duration_ms',return_value=1000), \
                 mock.patch.object(asr,'credential',return_value=self.token), contextlib.redirect_stdout(io.StringIO()):
                asr.main()
        with self.assertRaises(asr.ASRRedirectError): invoke()
        first = out/'chunk-001.json'; checksum=hashlib.sha256(first.read_bytes()).hexdigest()
        self.assertFalse((out/'chunk-002.json').exists()); self.assertFalse(self.cross_calls)
        self.calls.clear(); self.second_ready=True; invoke()
        self.assertEqual(len(self.calls),1); self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),checksum)
        self.assertEqual(json.loads((out/'chunk-002.json').read_text()),EVENTS)
        self.assertFalse(self.cross_calls)

if __name__ == '__main__': unittest.main()
