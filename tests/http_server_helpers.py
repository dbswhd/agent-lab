"""Local HTTPServer helpers — avoid xdist race (connection reset before bind)."""

from __future__ import annotations

import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Type


def wait_for_tcp_server(host: str, port: int, *, timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.05):
                return
        except OSError as exc:
            last_err = exc
            time.sleep(0.01)
    raise TimeoutError(f"server not accepting on {host}:{port}: {last_err}")


def start_local_http_server(
    handler: Type[BaseHTTPRequestHandler],
    *,
    host: str = "127.0.0.1",
) -> tuple[HTTPServer, int, Thread]:
    server = HTTPServer((host, 0), handler)
    port = int(server.server_address[1])
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    wait_for_tcp_server(host, port)
    return server, port, thread


def stop_local_http_server(server: HTTPServer, thread: Thread) -> None:
    server.shutdown()
    thread.join(timeout=3.0)
    server.server_close()


def read_post_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return b""
    return handler.rfile.read(length)
