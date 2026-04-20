from __future__ import annotations

import ctypes
import sys
import threading
from pathlib import Path
from select import select
from typing import Final

from curl_cffi._wrapper import ffi
from curl_cffi.const import CurlECode, CurlInfo, CurlOpt
from curl_cffi.curl import Curl, CurlError

_CURLE_OK: Final[int] = 0
_CURLE_AGAIN: Final[int] = CurlECode.AGAIN
_SELECT_TIMEOUT: Final[float] = 0.5
_RECV_BUF_SIZE: Final[int] = 65536


def _load_curl_lib() -> ctypes.CDLL:
    import curl_cffi
    import curl_cffi._wrapper as _wrapper

    pkg_dir = Path(curl_cffi.__path__[0])

    if sys.platform == "win32":
        for dll in sorted(pkg_dir.glob("libcurl*.dll")):
            try:
                return ctypes.CDLL(str(dll))
            except OSError:
                continue
        return ctypes.CDLL(_wrapper.__file__)

    for candidate in (
        _wrapper.__file__,
        None,
    ):
        try:
            lib = ctypes.CDLL(candidate)
            _ = lib.curl_easy_send
            return lib
        except (OSError, AttributeError):
            continue

    for so in sorted(pkg_dir.glob("libcurl*")):
        try:
            lib = ctypes.CDLL(str(so))
            _ = lib.curl_easy_send
            return lib
        except (OSError, AttributeError):
            continue

    raise RuntimeError(
        "Cannot locate libcurl with curl_easy_send/recv. "
        "Ensure curl_cffi >= 0.7.0 is installed correctly."
    )


_curl_lib = _load_curl_lib()

_curl_easy_send = _curl_lib.curl_easy_send
_curl_easy_send.restype = ctypes.c_int
_curl_easy_send.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]

_curl_easy_recv = _curl_lib.curl_easy_recv
_curl_easy_recv.restype = ctypes.c_int
_curl_easy_recv.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]


class CurlTLSSocket:
    __slots__ = ("_curl", "_handle", "_sock_fd", "_closed", "_curl_lock")

    def __init__(self, curl: Curl, handle: ctypes.c_void_p, sock_fd: int) -> None:
        self._curl = curl
        self._handle = handle
        self._sock_fd = sock_fd
        self._closed = False
        self._curl_lock = threading.RLock()

    def _refresh_sock_fd(self) -> bool:
        with self._curl_lock:
            try:
                fd = int(self._curl.getinfo(CurlInfo.ACTIVESOCKET))
            except Exception:
                return False
            if fd < 0:
                return False
            self._sock_fd = fd
            return True

    @classmethod
    def connect(
        cls,
        host: str,
        port: int = 443,
        impersonate: str = "chrome131",
        proxy: str | None = None,
    ) -> CurlTLSSocket:
        curl = Curl()
        try:
            curl.setopt(CurlOpt.URL, f"https://{host}:{port}")
            curl.setopt(CurlOpt.CONNECT_ONLY, 1)
            curl.impersonate(impersonate)

            if proxy:
                curl.setopt(CurlOpt.PROXY, proxy.encode() if isinstance(proxy, str) else proxy)

            curl.perform()

            raw_handle = ctypes.c_void_p(int(ffi.cast("uintptr_t", curl._curl)))
            sock_fd = int(curl.getinfo(CurlInfo.ACTIVESOCKET))

            return cls(curl, raw_handle, sock_fd)
        except Exception:
            curl.close()
            raise

    def recv(self, bufsize: int = _RECV_BUF_SIZE) -> bytes:
        if self._closed:
            return b""

        buf = ctypes.create_string_buffer(bufsize)
        n_recv = ctypes.c_size_t(0)

        while True:
            with self._curl_lock:
                ret = _curl_easy_recv(
                    self._handle, buf, bufsize, ctypes.byref(n_recv),
                )
            if ret == _CURLE_OK:
                if n_recv.value == 0:
                    self.close()
                    return b""
                return buf.raw[: n_recv.value]
            if ret == _CURLE_AGAIN:
                if not self._refresh_sock_fd():
                    return b""
                try:
                    select([self._sock_fd], [], [], _SELECT_TIMEOUT)
                except (OSError, ValueError):
                    return b""
                continue
            raise CurlError(f"curl_easy_recv failed (code {ret})", ret)

    def sendall(self, data: bytes) -> None:
        if self._closed:
            raise OSError("Socket is closed")

        mv = memoryview(data)
        offset = 0
        total = len(data)
        n_sent = ctypes.c_size_t(0)

        while offset < total:
            chunk = bytes(mv[offset:])
            with self._curl_lock:
                ret = _curl_easy_send(
                    self._handle,
                    chunk,
                    len(chunk),
                    ctypes.byref(n_sent),
                )
            if ret == _CURLE_OK:
                offset += n_sent.value
                continue
            if ret == _CURLE_AGAIN:
                if not self._refresh_sock_fd():
                    raise OSError("Socket closed during send")
                try:
                    select([], [self._sock_fd], [], _SELECT_TIMEOUT)
                except (OSError, ValueError):
                    raise OSError("Socket closed during send")
                continue
            raise CurlError(f"curl_easy_send failed (code {ret})", ret)

    def close(self) -> None:
        with self._curl_lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._curl.close()
            except Exception:
                pass

    def setsockopt(self, *args, **kwargs) -> None:
        import socket as _socket

        try:
            s = _socket.fromfd(self._sock_fd, _socket.AF_INET, _socket.SOCK_STREAM)
            try:
                s.setsockopt(*args, **kwargs)
            finally:
                s.detach()
        except OSError:
            pass
