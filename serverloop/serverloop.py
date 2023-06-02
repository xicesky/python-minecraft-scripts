
import select
import time


class WaitingObject:
    _name = None
    _is_done = False
    
    def __init__(self, name=None):
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
    
    def __str__(self) -> str:
        return f'WaitingObject({self._name})'
    def __repr__(self) -> str:
        return f'WaitingObject({self._name})'    


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
        if not seconds is None:
            self._target = time.time() + seconds
        if not fileno is None:
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


class ServerLoop:
    
    _idle_timeout = 5.0
    _running = False
    _current_tick = None
    _last_tick = None
    _waiting_objects = []
    _callbacks = {
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
        
    def build_waiting_lists(self) -> tuple[list, list, list, float]:
        waiting_r = []
        waiting_w = []
        waiting_x = []
        min_timestamp = None
        
        # Sort waiting objects into lists, depending on what they are waiting for
        to_process = self._waiting_objects[:]
        for waiting_object in to_process:
            if waiting_object.is_done():
                print(f'build_waiting_lists: Removing {waiting_object} from waiting list.')
                self._waiting_objects.remove(waiting_object)
                continue
            if waiting_object.is_waiting_to_receive():
                waiting_r.append(waiting_object)
            if waiting_object.is_waiting_to_send():
                waiting_w.append(waiting_object)
            if waiting_object.is_waiting_for_exception():
                waiting_x.append(waiting_object)
            timeout = waiting_object.is_waiting_for_timeout()
            if not (timeout is None or timeout is False):
                if min_timestamp is None or timeout < min_timestamp:
                    min_timestamp = timeout
        
        return waiting_r, waiting_w, waiting_x, min_timestamp
    
    def prune_waiting_list(self) -> None:
        # Remove all waiting objects that are done
        to_process = self._waiting_objects[:]
        for waiting_object in to_process:
            if waiting_object.is_done():
                print(f'prune_waiting_list: Removing {waiting_object} from waiting list.')
                self._waiting_objects.remove(waiting_object)

    def handle_timeouts(self) -> int:
        # Call do_timeout() on objects that are waiting for a timeout and have timed out
        count_timeouts = 0
        for waiting_object in self._waiting_objects:
            timeout = waiting_object.is_waiting_for_timeout()
            if timeout is not None and timeout is not False:
                if timeout <= self._current_tick:
                    count_timeouts += 1
                    waiting_object.do_timeout()
        return count_timeouts

    def main_loop(self) -> None:
        self._last_tick = time.time()
        self._current_tick = None
        self._running = True
        
        # Main loop
        while self._running:
            try:
                # Build lists & calculate timeout
                waiting_r, waiting_w, waiting_x, min_timestamp = self.build_waiting_lists()
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
                    waiting_object.do_receive()
                for waiting_object in w:
                    waiting_object.do_send()
                for waiting_object in x:
                    waiting_object.do_exception()
                
                # Handle idle timeout, if nothing happened
                if len(r) == 0 and len(w) == 0 and len(x) == 0 and count_timeouts == 0:
                    self.on_idle_timeout()
                
                # Prune waiting list
                self.prune_waiting_list()

                self._last_tick = self._current_tick
                self._current_tick = None

            except KeyboardInterrupt:
                self.on_keyboard_interrupt()
        
        self.on_shutdown()

    def _run_callbacks(self, callback_name) -> None:
        for callback in self._callbacks[callback_name]:
            callback()
    
    def on_idle_timeout(self) -> None:
        self._run_callbacks('on_idle_timeout')
    
    def on_keyboard_interrupt(self) -> None:
        self._run_callbacks('on_keyboard_interrupt')
    
    def on_shutdown(self) -> None:
        self._run_callbacks('on_shutdown')


if __name__ == '__main__':
    serverLoop = ServerLoop()
    serverLoop.call_after(1.0, lambda: print('Hello, world!'))
    serverLoop.call_after(2.0, lambda: serverLoop.stop())
    serverLoop.run()
