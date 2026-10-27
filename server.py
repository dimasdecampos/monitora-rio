"""Servidor local para testar o site (no ar, quem publica é o GitHub Pages).

Serve a pasta public/ e, no lugar do painel e do modo TV de cada bacia, os modelos da
pasta modelos/ — assim uma mudança no painel aparece só de recarregar a página, sem
precisar rodar scripts/montar_site.py.

Uso:  python server.py        (abre http://localhost:8000)
"""

import json
import re
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORTA = 8000
RAIZ = Path(__file__).parent
BACIAS = {b["id"] for b in json.loads((RAIZ / "public" / "bacias.json").read_text(encoding="utf-8"))["bacias"]}
MODELO = {"": "painel.html", "index.html": "painel.html", "tv.html": "tv.html", "manifest.webmanifest": "manifest.webmanifest"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ / "public"), **kwargs)

    def translate_path(self, path):
        m = re.fullmatch(r"/([\w-]+)/([\w.]*)", path.split("?")[0])
        if m and m[1] in BACIAS and m[2] in MODELO:
            return str(RAIZ / "modelos" / MODELO[m[2]])
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # sempre a versão mais nova durante os testes
        super().end_headers()

    def log_message(self, formato, *args):
        pass


if __name__ == "__main__":
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    endereco = f"http://localhost:{PORTA}"
    print(f"Monitor dos rios rodando em {endereco}  (Ctrl+C para parar)")
    threading.Timer(1.0, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
