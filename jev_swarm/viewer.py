"""Self-contained trace explorer and read-only loopback watch server."""
from __future__ import annotations
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .models import RunResult

TEMPLATE=Path(__file__).parent/'assets'/'viewer.html'

def viewer_html(result: RunResult | None = None) -> str:
    data=json.dumps(result.to_dict(),ensure_ascii=False,allow_nan=False) if result else 'null'
    # Prevent an observation from ending the JSON script element.
    data=data.replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    return TEMPLATE.read_text().replace('__TRACE_JSON__',data)

def serve_trace(trace: str | Path, port: int = 8765) -> None:
    path=Path(trace).resolve()
    if path.is_dir() or path.suffix != '.json':path=path/'run.json'
    if not 1 <= port <= 65535:raise ValueError('Port must be 1–65535')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                self.send_error(403, 'Local requests only')
                return
            if self.path=='/':
                payload=viewer_html().encode();ctype='text/html; charset=utf-8';status=200
            elif self.path=='/trace':
                try:
                    if path.stat().st_size>15000000:raise ValueError('Trace too large')
                    payload=path.read_bytes();RunResult.from_dict(json.loads(payload))
                    ctype='application/json';status=200
                except FileNotFoundError:
                    payload=b'{"error":"Waiting for checkpoint"}';ctype='application/json';status=404
                except (ValueError,TypeError,KeyError):
                    payload=b'{"error":"Invalid trace"}';ctype='application/json';status=422
            else:
                payload=b'Not found';ctype='text/plain';status=404
            self.send_response(status)
            self.send_header('Content-Type',ctype);self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(payload)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Swarm trace viewer: http://127.0.0.1:{port}',flush=True)
    print(f'Watching {path}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
