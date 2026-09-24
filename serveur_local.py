#!/usr/bin/env python3
"""Sert les rapports de veille sur ce poste (portail local)."""

from __future__ import annotations

import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

from publication import _archives_html, _index_html

HOTE = "127.0.0.1"
PORT = 8766


def _fichier_rapport(nom: str) -> Path | None:
    if not nom.startswith("Veille_"):
        return None
    if not nom.endswith((".html", ".pdf")):
        return None
    chemin = (ROOT / nom).resolve()
    if chemin.parent != ROOT or not chemin.is_file():
        return None
    return chemin


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        chemin = unquote(urlparse(self.path).path)
        if chemin in ("/", "/index.html"):
            self._send(200, _index_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if chemin == "/archives.html":
            self._send(200, _archives_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        fichier = _fichier_rapport(chemin.lstrip("/"))
        if fichier is None:
            self._send(404, "Introuvable.".encode("utf-8"), "text/plain; charset=utf-8")
            return
        ctype = "application/pdf" if fichier.suffix == ".pdf" else "text/html; charset=utf-8"
        self._send(200, fichier.read_bytes(), ctype)


def main() -> None:
    bindings = (
        (socket.AF_INET, HOTE),
        (socket.AF_INET6, "::1"),
    )
    servers = []
    for family, address in bindings:

        class BoundServer(ThreadingHTTPServer):
            address_family = family

        try:
            servers.append(BoundServer((address, PORT), Handler))
        except OSError as exc:
            print(f"Pas d'écoute sur {address}:{PORT} ({exc})", flush=True)
    if not servers:
        raise SystemExit(1)
    for server in servers:
        shown = f"[{server.server_address[0]}]" if ":" in server.server_address[0] else server.server_address[0]
        print(f"Veille sur http://{shown}:{PORT}/", flush=True)
    for extra in servers[1:]:
        threading.Thread(target=extra.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
