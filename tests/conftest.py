"""Suite-wide offline brake: no test in any module may open a network socket.

The quality bar says tests run with NO network access. A per-module fixture only keeps
that promise for the modules that remember to copy it (and the copies drift), so the
brake lives here, where pytest applies it to every test without an opt-in.
"""

from __future__ import annotations

import socket

import pytest


class NetworkAttempted(AssertionError):
    """Raised when a test reaches for the network.

    An `AssertionError` subclass so a breach reads as a test failure, never as an
    environment error a broad `except OSError` in product code could swallow.
    """


@pytest.fixture(autouse=True)
def _offline_brake(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every socket entry point with a tripwire for the duration of each test.

    `monkeypatch` restores the originals afterwards, so pytest and xdist's own transport
    (which uses sockets/pipes between tests, never inside one) are untouched.
    """

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise NetworkAttempted("network access attempted during test")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)
