
import logging
import time
import traceback

logger = logging.getLogger(__name__)


def neutral_callback(*args, **kwargs) -> None:
    pass


class WaitingObject:
    _name = None
    _is_done = False

    def __init__(self, name=None):
        if name is None:
            logger.debug('WaitingObject: created unnamed object at:\n    ' + '\n    '.join(traceback.format_stack()))
        self._name = name

    def is_done(self):
        return self._is_done

    def is_waiting_to_receive(self) -> bool:
        return False

    def is_waiting_to_send(self) -> bool:
        return False

    def is_waiting_for_exception(self) -> bool:
        return False

    def is_waiting_for_timeout(self) -> bool:
        return False

    def do_receive(self) -> None:
        pass

    def do_send(self) -> None:
        pass

    def do_exception(self) -> None:
        pass

    def do_timeout(self) -> None:
        pass

    def ignore_when_idle(self) -> bool:
        return False

    def __str__(self) -> str:
        return f'{type(self).__name__}({self._name})'

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self._name})'


class WaitingOnetimeCallback(WaitingObject):
    _target = None
    _fileno = None
    _callback = None
    _is_waiting_to_receive = False
    _is_waiting_to_send = False
    _is_waiting_for_exception = False

    def __init__(self, callback, seconds=None, fileno=None, is_waiting_to_receive=False, is_waiting_to_send=False, is_waiting_for_exception=False, name=None):
        super().__init__(name=name)
        self._callback = callback
        if seconds is not None:
            self._target = time.time() + seconds
        if fileno is not None:
            # If fileno is an integer, it is a file descriptor, otherwise it is a file-like object
            if isinstance(fileno, int):
                self._fileno = fileno
            else:
                self._fileno = fileno.fileno()
        self._is_waiting_to_receive = is_waiting_to_receive
        self._is_waiting_to_send = is_waiting_to_send
        self._is_waiting_for_exception = is_waiting_for_exception

    def is_waiting_to_receive(self):
        return self._is_waiting_to_receive

    def is_waiting_to_send(self):
        return self._is_waiting_to_send

    def is_waiting_for_exception(self):
        return self._is_waiting_for_exception

    def is_waiting_for_timeout(self):
        return self._target

    def fileno(self):
        return self._fileno

    def do_receive(self):
        self._callback()
        self._is_done = True

    def do_send(self):
        self._callback()
        self._is_done = True

    def do_exception(self):
        self._callback()
        self._is_done = True

    def do_timeout(self):
        self._target = None
        self._callback()
        self._is_done = True


class RepeatedCallback(WaitingObject):
    _target = None
    _callback = None
    _interval = None

    def __init__(self, callback, interval, name=None):
        super().__init__(name=name)
        self._callback = callback
        self._interval = interval
        self._target = time.time() + interval

    def is_waiting_for_timeout(self):
        return self._target

    def do_timeout(self):
        self._target = time.time() + self._interval
        r = self._callback()
        if r is False:
            self._target = None
            self._is_done = True
