
import logging
import select
import threading
import time
import traceback
from typing import Callable, TypeVar

from minecraft.serverwrapper.serverloop.objects import RepeatedCallback, WaitingObject, WaitingOnetimeCallback

logger = logging.getLogger(__name__)


class ServerLoop:

    _idle_timeout: float = 5.0
    _running: bool = False
    _current_tick: float = None
    _last_tick: float = None
    _waiting_objects: list[WaitingObject] = []
    _callbacks: dict[str, list[Callable]] = {
        'on_idle_timeout': [],
        'on_keyboard_interrupt': [],
        'on_shutdown': []
    }

    def __init__(self):
        pass

    def run(self) -> None:
        self.main_loop()

    def stop(self) -> None:
        self._running = False

    def add_waiting_object(self, waiting_object) -> WaitingObject:
        self._waiting_objects.append(waiting_object)
        return waiting_object

    def remove_waiting_object(self, waiting_object) -> None:
        self._waiting_objects.remove(waiting_object)

    def remove_maybe_waiting_object(self, waiting_object) -> None:
        try:
            self._waiting_objects.remove(waiting_object)
        except ValueError:
            # Ignore if not in list
            pass

    def call_after(self, seconds, callback, name=None) -> WaitingObject:
        return self.add_waiting_object(WaitingOnetimeCallback(callback, seconds=seconds, name=name))

    def call_when_ready_to_receive(self, fileno, callback, name=None) -> WaitingObject:
        return self.add_waiting_object(WaitingOnetimeCallback(callback, fileno=fileno, is_waiting_to_receive=True, name=name))

    def call_when_ready_to_send(self, fileno, callback, name=None) -> WaitingObject:
        return self.add_waiting_object(WaitingOnetimeCallback(callback, fileno=fileno, is_waiting_to_send=True, name=name))

    def call_when_exception(self, fileno, callback, name=None) -> WaitingObject:
        return self.add_waiting_object(WaitingOnetimeCallback(callback, fileno=fileno, is_waiting_for_exception=True, name=name))

    def call_repeatedly(self, interval, callback, name=None) -> WaitingObject:
        return self.add_waiting_object(RepeatedCallback(callback, interval, name=name))

    def call_on_idle_timeout(self, callback, name=None):
        # FIXME: Add name to callback
        self._callbacks['on_idle_timeout'].append(callback)

    def call_on_keyboard_interrupt(self, callback, name=None):
        # FIXME: Add name to callback
        self._callbacks['on_keyboard_interrupt'].append(callback)

    def call_on_shutdown(self, callback, name=None):
        # FIXME: Add name to callback
        self._callbacks['on_shutdown'].append(callback)

    def build_waiting_lists(self) -> tuple[int, list, list, list, float]:
        total = 0
        waiting_r = []
        waiting_w = []
        waiting_x = []
        min_timestamp = None

        # Sort waiting objects into lists, depending on what they are waiting for
        to_process = self._waiting_objects[:]
        for waiting_object in to_process:
            if waiting_object.is_done():
                logger.debug(f'build_waiting_lists: Removing {waiting_object} from waiting list.')
                self._waiting_objects.remove(waiting_object)
                continue
            waiting = False
            if waiting_object.is_waiting_to_receive():
                waiting_r.append(waiting_object)
                waiting = True
            if waiting_object.is_waiting_to_send():
                waiting_w.append(waiting_object)
                waiting = True
            if waiting_object.is_waiting_for_exception():
                waiting_x.append(waiting_object)
                waiting = True
            timeout = waiting_object.is_waiting_for_timeout()
            if not (timeout is None or timeout is False):
                if min_timestamp is None or timeout < min_timestamp:
                    min_timestamp = timeout
                waiting = True

            if not waiting_object.ignore_when_idle():
                if waiting:
                    total += 1
                else:
                    logger.warning(f'build_waiting_lists: {waiting_object} is not waiting for anything.')

        return total, waiting_r, waiting_w, waiting_x, min_timestamp

    def prune_waiting_list(self) -> None:
        # Remove all waiting objects that are done
        to_process = self._waiting_objects[:]
        for waiting_object in to_process:
            if waiting_object.is_done():
                logger.debug(f'prune_waiting_list: Removing {waiting_object} from waiting list.')
                self._waiting_objects.remove(waiting_object)

    def handle_timeouts(self) -> int:
        # Call do_timeout() on objects that are waiting for a timeout and have timed out
        count_timeouts = 0
        for waiting_object in self._waiting_objects:
            timeout = waiting_object.is_waiting_for_timeout()
            if timeout is not None and timeout is not False:
                if timeout <= self._current_tick:
                    count_timeouts += 1
                    self._run_callbacks(waiting_object.do_timeout, owner=waiting_object, name='do_timeout')
        return count_timeouts

    def main_loop(self) -> None:
        self._last_tick = time.time()
        self._current_tick = None
        self._running = True

        # Main loop
        while self._running:
            try:
                # Build lists & calculate timeout
                count, waiting_r, waiting_w, waiting_x, min_timestamp = self.build_waiting_lists()
                if count == 0:
                    logger.debug('No waiting objects in main_loop() - exitting.')
                    self.stop()
                    continue

                if min_timestamp is None:
                    rel_timeout = self._idle_timeout
                else:
                    rel_timeout = min(max(0.1, min_timestamp - time.time()), self._idle_timeout)

                # Run select
                r, w, x = select.select(waiting_r, waiting_w, waiting_x, rel_timeout)
                self._current_tick = time.time()

                # Handle timeouts
                count_timeouts = self.handle_timeouts()

                # Handle I/O
                for waiting_object in r:
                    try:
                        waiting_object.do_receive()
                    except Exception as e:
                        logger.error(f'Exception in do_receive() of {waiting_object}: {e}')
                for waiting_object in w:
                    try:
                        waiting_object.do_send()
                    except Exception as e:
                        logger.error(f'Exception in do_send() of {waiting_object}: {e}')
                for waiting_object in x:
                    try:
                        waiting_object.do_exception()
                    except Exception as e:
                        logger.error(f'Exception in do_exception() of {waiting_object}: {e}')

                # Handle idle timeout, if nothing happened
                if len(r) == 0 and len(w) == 0 and len(x) == 0 and count_timeouts == 0:
                    self.on_idle_timeout()

                # Prune waiting list
                self.prune_waiting_list()

                self._last_tick = self._current_tick
                self._current_tick = None

            except KeyboardInterrupt:
                self.on_keyboard_interrupt()

        # FIXME: Remaining waiting objects should be finalized somehow

        self.on_shutdown()

    def _run_callbacks(self, callback_name_or_callbacks, owner=None, name=None) -> None:
        if isinstance(callback_name_or_callbacks, str):
            self._run_callbacks(self._callbacks[callback_name_or_callbacks], name=callback_name_or_callbacks)
        elif isinstance(callback_name_or_callbacks, list):
            for callback in callback_name_or_callbacks:
                self._run_callbacks(callback, name=callback_name_or_callbacks)
        else:
            callback = callback_name_or_callbacks
            try:
                callback()
            except Exception as e:
                if name is None:
                    name = 'unknown'
                st = traceback.format_exc()
                ownerstr = ''
                if owner is not None:
                    ownerstr = f' of {owner}'
                logger.error(f'Exception in {name} callback {callback}{ownerstr}: {e}\n{st}')

    def on_idle_timeout(self) -> None:
        self._run_callbacks('on_idle_timeout')

    def on_keyboard_interrupt(self) -> None:
        self._run_callbacks('on_keyboard_interrupt')

    def on_shutdown(self) -> None:
        self._run_callbacks('on_shutdown')


_thread_local = threading.local()


def get_server_loop():
    if not hasattr(_thread_local, 'ServerLoop_instance'):
        _thread_local.ServerLoop_instance = ServerLoop()
    return _thread_local.ServerLoop_instance


T = TypeVar('T')


def run_server_loop(inner: Callable[[], T]) -> T:
    result = None

    def do_inner():
        nonlocal result
        result = inner()

    sl = get_server_loop()
    sl.call_after(0.0, do_inner, name='run_server_loop-inner')
    sl.run()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.warning('Running this script directly is JUST FOR DEBUGGING')
    print('This just quickly tests the ServerLoop class.')
    run_server_loop(lambda: print('Hello, world!'))
