"""Servidor local para testar o site (no ar, quem faz isso é a Vercel).

Uso:  python server.py        (abre http://localhost:8000)
"""

import json
import threading
import time
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from api.dados import responder

PORTA = 8000
PASTA = Path(__file__).parent
_cache = {}
_trava = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PASTA / "public"), **kwargs)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/api/dados":
            return super().do_GET()
        with _trava:
            guardado = _cache.get(url.query)
        if guardado and time.time() < guardado[0]:
            status, corpo = guardado[1]
        else:
            status, corpo, cache = responder(parse_qs(url.query))
            if cache:
                with _trava:
                    _cache[url.query] = (time.time() + cache, (status, corpo))
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, formato, *args):
        if args and "/api/" in str(args[0]):
            print(f"[{datetime.now():%H:%M:%S}] {args[0]}")


if __name__ == "__main__":
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    endereco = f"http://localhost:{PORTA}"
    print(f"Monitor dos rios Paraitinga e Paraibuna rodando em {endereco}  (Ctrl+C para parar)")
    threading.Timer(1.0, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
