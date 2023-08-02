import logging
import subprocess
from typing import Callable

from minecraft.serverwrapper.serverloop.buffers import LineInputBuffer, OutputBuffer
from minecraft.serverwrapper.serverloop.objects import (
    RepeatedCallback,
    neutral_callback,
)
from minecraft.serverwrapper.serverloop.serverloop import ServerLoop, get_server_loop, run_server_loop

logger = logging.getLogger(__name__)


class Process:
    _serverloop: ServerLoop = None
    _name: str = None
    _working_dir: str = None
    _commandline: list[str] = None
    _subprocess: subprocess = None
    _wo_stdin: OutputBuffer = None
    _wo_stdout: LineInputBuffer = None
    _wo_stderr: LineInputBuffer = None
    _wo_check_alive: RepeatedCallback = None

    stdout_callback: Callable[[str], None] = neutral_callback
    stderr_callback: Callable[[str], None] = neutral_callback
    exit_callback: Callable[[int], None] = neutral_callback

    def __init__(
        self,
        commandline: list[str],
        working_dir: str = None,
        serverloop: ServerLoop = None,
        name: str = None,
        stdout_callback: Callable[[str], None] = None,
        stderr_callback: Callable[[str], None] = None,
        exit_callback: Callable[[int], None] = None,
    ):
        self._serverloop = serverloop or get_server_loop()
        self._name = name or commandline[0]
        self._working_dir = working_dir or "."
        self._commandline = commandline
        self.stdout_callback = stdout_callback or self.stdout_callback
        self.stderr_callback = stderr_callback or self.stderr_callback
        self.exit_callback = exit_callback or self.exit_callback
        self._async_enter()

    def _async_enter(self):
        sl = self._serverloop
        self._subprocess = subprocess.Popen(
            self._commandline,
            cwd=self._working_dir,
            bufsize=1,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self._wo_stdin = sl.add_waiting_object(
            OutputBuffer(self._subprocess.stdin, name=self._name + "-stdin")
        )
        self._wo_stdout = sl.add_waiting_object(
            LineInputBuffer(
                self._subprocess.stdout,
                lambda line: self._stdout_callback(line),
                name=self._name + "-stdout",
            )
        )
        self._wo_stderr = sl.add_waiting_object(
            LineInputBuffer(
                self._subprocess.stderr,
                lambda line: self._stderr_callback(line),
                name=self._name + "-stderr",
            )
        )
        self._wo_check_alive = sl.call_repeatedly(
            1.0, self._check_alive, name=self._name + "-check-alive"
        )
        return self

    def _async_exit(self):
        if self._wo_check_alive is not None:
            logger.error("Server subprocess seems still alive because _wo_check_alive is not None")
            self._wo_check_alive = None
        # if self._wo_stderr is not None:
        #     self._serverloop.remove_waiting_object(self._wo_stderr)
        #     self._wo_stderr = None
        # if self._wo_stdout is not None:
        #     self._serverloop.remove_waiting_object(self._wo_stdout)
        #     self._wo_stdout = None
        if self._wo_stdin is not None:
            self._serverloop.remove_maybe_waiting_object(self._wo_stdin)
            self._wo_stdin = None
        if self._subprocess.poll() is None:
            self._subprocess.kill()
            self._subprocess.wait()

    def _check_alive(self):
        if self._subprocess is None:
            logger.warning("Server subprocess is None")
            return False
        rc = self._subprocess.poll()
        if rc is not None:
            logger.debug(f'Subprocess {self._name} exitted with rc={rc}, removing check_alive callback')
            # Note: We remove the WaitingObject here, because we don't have to check again,
            #       just in case _check_alive is called from anywhere else.
            self._serverloop.remove_waiting_object(self._wo_check_alive)
            self._wo_check_alive = None
            self._exit_callback(rc)
            return False
        # Process is alive, call again next time
        return True

    def _stdout_callback(self, line):
        self.stdout_callback(line)

    def _stderr_callback(self, line):
        self.stderr_callback(line)

    def _exit_callback(self, rc):
        self.exit_callback(rc)
        self._async_exit()

    def send(self, data: str) -> None:
        self._wo_stdin.send(data)

    def send_line(self, line: str) -> None:
        self._wo_stdin.send_line(line)

    def close_stdin(self) -> None:
        self._wo_stdin.close()

    def terminate(self) -> None:
        self._subprocess.terminate()
        # _check_alive and _async_exit will handle the rest

    def kill(self) -> None:
        self._subprocess.kill()
        self._subprocess.wait()
        # _check_alive and _async_exit will handle the rest

    def returncode(self) -> int:
        return self._subprocess.returncode

    def __str__(self) -> str:
        return f'sl_Process({self._name})'

    def __repr__(self) -> str:
        return f'sl_Process({self._name})'


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logger.warning("Running this script directly is JUST FOR DEBUGGING")
    print("This just quickly tests the Process class.")

    def show_output(pipename, line):
        print(f'[{pipename}] {line}')

    def example_main():
        p = Process(["cat"],
            stdout_callback=lambda line: show_output("stdout", line),
            stderr_callback=lambda line: show_output("stderr", line),
        )
        # At this point, all the waiting objects should be registered
        p.send_line("Hello")
        p.send_line("World")
        p.send_line("!")
        p.close_stdin()

    run_server_loop(example_main)
