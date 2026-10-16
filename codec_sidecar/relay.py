"""Loopback-published TCP relay to the codec's network-isolated Unix socket.

This relay has no Ford library, key material, or bearer token. The codec checks
the bearer header itself. Publish its port on 127.0.0.1 only.
"""

from __future__ import annotations

import os
import select
import socket
import socketserver


SOCKET_PATH = "/socket/codec.sock"
PORT = int(os.environ.get("FORD_CODEC_RELAY_PORT", "8766"))


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        upstream = socket.socket(socket.AF_UNIX)
        try:
            upstream.connect(SOCKET_PATH)
            with upstream:
                peers = (self.request, upstream)
                while True:
                    readable, _, _ = select.select(peers, [], [], 30)
                    for source in readable:
                        payload = source.recv(65536)
                        if not payload:
                            return
                        destination = upstream if source is self.request else self.request
                        destination.sendall(payload)
        except OSError:
            return


class Relay(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Relay(("0.0.0.0", PORT), Handler) as server:
    server.serve_forever()
