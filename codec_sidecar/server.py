"""Network-isolated Ford white-box codec over a private Unix socket.

The owner supplies the official APK-derived native library and key file at
runtime. This image does not contain or redistribute either one.
"""

from __future__ import annotations

import base64
import ctypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import os
from pathlib import Path
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile


VENDOR = Path("/vendor")
SOCKET = Path("/socket/codec.sock")
LIBRARY_SHA256 = "19ed0892eafaa38d18060654b07117839f9124a3b1c804a7e94da29da48c65f2"
MAX_BODY = 1_500_000


def disable_android_host_initializers(library: Path) -> None:
    """Use the tested codec without its Android package/MD5 constructors."""
    data = bytearray(library.read_bytes())
    if data[:5] != b"\x7fELF\x02":
        raise ValueError("not an ELF64 library")
    phoff = struct.unpack_from("<Q", data, 0x20)[0]
    phentsize = struct.unpack_from("<H", data, 0x36)[0]
    phnum = struct.unpack_from("<H", data, 0x38)[0]
    found = set()
    for index in range(phnum):
        offset = phoff + index * phentsize
        if struct.unpack_from("<I", data, offset)[0] != 2:  # PT_DYNAMIC
            continue
        dynamic_offset = struct.unpack_from("<Q", data, offset + 8)[0]
        dynamic_size = struct.unpack_from("<Q", data, offset + 32)[0]
        for entry in range(dynamic_offset, dynamic_offset + dynamic_size, 16):
            tag = struct.unpack_from("<Q", data, entry)[0]
            if tag in (27, 28):  # DT_INIT_ARRAYSZ, DT_FINI_ARRAYSZ
                struct.pack_into("<Q", data, entry + 8, 0)
                found.add(tag)
    if found != {27, 28}:
        raise ValueError("Android initializer layout changed")
    library.write_bytes(data)


def mapped_base(library: Path) -> int:
    for mapping in Path("/proc/self/maps").read_text().splitlines():
        columns = mapping.split()
        if str(library) in mapping and columns[2] == "00000000":
            return int(columns[0].split("-")[0], 16)
    raise RuntimeError("native library mapping not found")


class Codec:
    def __init__(self) -> None:
        from hashlib import sha256

        vendor_library = VENDOR / "libwbsk_crypto_tool.so"
        if sha256(vendor_library.read_bytes()).hexdigest() != LIBRARY_SHA256:
            raise ValueError("untested Ford native codec library")
        self.keys = json.loads((VENDOR / "whitebox_keys_for_prod.json").read_text())
        runtime = Path(tempfile.mkdtemp(prefix="ford-codec-"))
        library = runtime / "libwbsk_crypto_tool.so"
        shutil.copyfile(vendor_library, library)
        subprocess.run(["patchelf", "--replace-needed", "libc.so", "libc.so.6", str(library)], check=True)
        subprocess.run(["patchelf", "--replace-needed", "libdl.so", "libdl.so.2", str(library)], check=True)
        disable_android_host_initializers(library)
        self.lib = ctypes.CDLL(str(library))
        base = mapped_base(library)
        ctypes.c_int.from_address(base + 0x7B088).value = 1
        ctypes.c_int.from_address(base + 0x7B08C).value = 1
        signature = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int), ctypes.c_void_p, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ]
        self.encrypt = self.lib.wbsk_AES_cbc_encrypt
        self.decrypt = self.lib.wbsk_AES_cbc_decrypt
        for function in (self.encrypt, self.decrypt):
            function.argtypes = signature
            function.restype = ctypes.c_int

    def transform(self, service: str, operation: str, data: bytes, iv: bytes) -> bytes:
        if len(iv) != 16:
            raise ValueError("IV must be exactly 16 bytes")
        if service not in self.keys or operation not in ("encrypt", "decrypt"):
            raise ValueError("unsupported service or operation")
        key = bytes.fromhex(self.keys[service][operation])
        output = ctypes.create_string_buffer(len(data) + 16)
        size = ctypes.c_int(len(output))
        function = self.encrypt if operation == "encrypt" else self.decrypt
        code = function(data, len(data), output, ctypes.byref(size),
                        iv, len(iv), key, len(key), 1)
        if code != 0 or not 0 <= size.value <= len(output):
            raise ValueError(f"native codec failed with status {code}")
        return output.raw[:size.value]


class UnixHTTPServer(socketserver.UnixStreamServer):
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def address_string(self) -> str:
        return "local"

    def log_message(self, format: str, *args: object) -> None:
        # Requests may carry credentials. Never write them to container logs.
        return

    def do_POST(self) -> None:
        if self.path != "/codec":
            self.send_error(404)
            return
        expected = self.server.bearer
        if expected and not hmac.compare_digest(
            self.headers.get("Authorization", ""), f"Bearer {expected}"
        ):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(length))
            payload = base64.b64decode(request["data_base64"], validate=True)
            iv = bytes.fromhex(request["iv_hex"])
            result = self.server.codec.transform(request["service"], request["operation"], payload, iv)
            body = json.dumps({"data_base64": base64.b64encode(result).decode("ascii")}).encode()
            status = 200
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            body = b'{"error":"invalid codec request"}'
            status = 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    os.umask(0o077)
    port = os.environ.get("FORD_CODEC_TCP_PORT")
    bearer = os.environ.get("FORD_CODEC_BEARER", "")
    if port:
        if not bearer:
            raise ValueError("TCP mode requires FORD_CODEC_BEARER")
        server = HTTPServer(("0.0.0.0", int(port)), Handler)
    else:
        if SOCKET.exists():
            with socket.socket(socket.AF_UNIX) as probe:
                try:
                    probe.connect(str(SOCKET))
                except ConnectionRefusedError:
                    SOCKET.unlink()
                else:
                    raise RuntimeError("codec socket belongs to another server")
        SOCKET.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        server = UnixHTTPServer(str(SOCKET), Handler)
    with server:
        server.codec = Codec()
        server.bearer = bearer
        server.serve_forever()


if __name__ == "__main__":
    main()
