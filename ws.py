"""Hand-rolled WebSocket client (RFC 6455). Stdlib only. Client-side masking."""

import base64
import hashlib
import os
import socket
import struct

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WSError(Exception):
    pass


class WS:
    """Minimal WebSocket client. Text and binary frames. No fragmentation."""

    def __init__(self, sock):
        self.sock = sock
        self._buf = b""

    @classmethod
    def connect(cls, host, port, path, timeout=30):
        sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(4096)
            if not chunk:
                raise WSError("handshake: closed before headers")
            resp += chunk
        head, _, rest = resp.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise WSError(f"handshake failed: {head[:200]!r}")
        accept_expected = base64.b64encode(
            hashlib.sha1((key + _WS_GUID).encode()).digest()
        ).decode()
        accept_got = None
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"sec-websocket-accept:"):
                accept_got = line.split(b":", 1)[1].strip().decode()
                break
        if accept_got is None:
            raise WSError("handshake: no Sec-WebSocket-Accept")
        if accept_got != accept_expected:
            raise WSError("handshake: bad Sec-WebSocket-Accept")
        ws = cls(sock)
        ws._buf = rest
        return ws

    def send_text(self, text):
        self._send_frame(0x1, text.encode("utf-8"))

    def _send_frame(self, opcode, payload):
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
        else:
            header = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
        self.sock.sendall(header + mask + masked)

    def recv(self):
        opcode, payload = self._recv_frame()
        if opcode == 0x8:
            raise WSError("closed by peer")
        if opcode == 0x9:
            self._send_frame(0xA, payload)
            return self.recv()
        if opcode == 0x1:
            return payload.decode("utf-8")
        if opcode == 0x2:
            return payload
        raise WSError(f"unexpected opcode: {opcode}")

    def _recv_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WSError("recv: closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _recv_frame(self):
        b1, b2 = self._recv_exact(2)
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack("!H", self._recv_exact(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = bytearray(self._recv_exact(n))
        if mask:
            for i in range(n):
                payload[i] ^= mask[i & 3]
        return opcode, bytes(payload)

    def close(self):
        try:
            self._send_frame(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
