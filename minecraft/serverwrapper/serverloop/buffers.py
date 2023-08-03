
import logging
import os
from typing import Any, TextIO
from minecraft.serverwrapper.serverloop.serverloop import WaitingObject

logger = logging.getLogger(__name__)


class LineInputBuffer(WaitingObject):
    _handle: TextIO = None
    _buffer: str = ""
    _callback: callable = None

    def __init__(self, handle: TextIO, callback: callable, name=None):
        super().__init__(name=name)
        self._handle = handle
        self._callback = callback
        os.set_blocking(self._handle.fileno(), False)

    def fileno(self) -> int:
        return self._handle.fileno()

    def is_waiting_to_receive(self) -> bool:
        return True

    def do_receive(self) -> None:
        read_bytes = self._handle.read()
        if len(read_bytes) == 0:
            logger.debug(f'LineInputBuffer: EOF on {self._name}')
            self._handle.close()
            self._is_done = True
            return
        self._buffer += read_bytes
        while True:
            pos = self._buffer.find('\n')
            if pos == -1:
                break
            line = self._buffer[:pos]
            self._buffer = self._buffer[pos+1:]
            self._callback(line)


class OutputBuffer(WaitingObject):
    _handle: TextIO = None
    _buffer: str = ""
    _callback: callable = None
    _error_callback: callable = None
    _close_after_send: bool = False
    _ignore_when_idle: bool = True

    def __init__(self, handle: TextIO, callback: callable = None, name=None):
        super().__init__(name=name)
        self._handle = handle
        self._callback = callback
        os.set_blocking(self._handle.fileno(), False)

    def set_error_callback(self, callback: callable) -> None:
        self._error_callback = callback

    def fileno(self) -> int:
        return self._handle.fileno()

    def is_waiting_to_send(self) -> bool:
        return len(self._buffer) > 0

    def ignore_when_idle(self) -> bool:
        return self._ignore_when_idle

    def do_send(self) -> None:
        try:
            written_bytes = self._handle.write(self._buffer)
        except BrokenPipeError as e:
            if self._error_callback is not None:
                self._error_callback(e)
            return

        self._buffer = self._buffer[written_bytes:]
        if self._callback is not None:
            self._callback()
        if len(self._buffer) == 0 and self._close_after_send:
            self._handle.close()
            self._is_done = True

    def send(self, data: str) -> None:
        if self._close_after_send:
            raise RuntimeError('OutputBuffer: cannot send data after close')
        self._buffer += data

    def send_line(self, data: str) -> None:
        if self._close_after_send:
            raise RuntimeError('OutputBuffer: cannot send data after close')
        self._buffer += data + '\n'

    def buffer_size(self) -> int:
        return len(self._buffer)

    def buffer_empty(self) -> bool:
        return len(self._buffer) == 0

    def close(self) -> None:
        self._close_after_send = True
