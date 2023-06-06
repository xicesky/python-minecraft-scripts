
import logging
import sys
import os
import shlex
import libtmux
from time import sleep

logger = logging.getLogger(__name__)

def quote_command(command_raw):
    return ' '.join(shlex.quote(part) for part in command_raw)

def combine_commands_via_shell(commands_raw):
    return quote_command(['bash', '-c', ';'.join(quote_command(command_raw) for command_raw in commands_raw)])

class TmuxServerController:
    _working_dir = None
    _module_name = None
    _args = []
    _tmux_session_name = None
    _tmux_server = None
    _tmux_session = None
    _tmux_window = None
    
    def __init__(self, session_name, module_name, args=[], working_dir=None):
        self._module_name = module_name
        self._args = args
        self._tmux_session_name = session_name
        self._working_dir = working_dir
        if self._working_dir is None:
            self._working_dir = os.getcwd()
            
    def start(self):
        # FIXME: Panes are not working properly
        # pane = self._find_or_create_tmux_pane()
        self._find_or_create_tmux_window()

    def get_tmux_server(self):
        if self._tmux_server is None:
            self._tmux_server = libtmux.Server()
        return self._tmux_server
    
    def get_server_command(self):
        command_raw_parts = [sys.executable, '-m', self._module_name] + self._args
        commands = [
            ['echo'] + command_raw_parts,
            command_raw_parts,
            ['read', '-p', 'Press enter to continue...'],
        ]
        return combine_commands_via_shell(commands)
    
    def _find_tmux_session(self):
        server = self.get_tmux_server()
        sessions = server.sessions.filter(session_name=self._tmux_session_name)
        if len(sessions) == 0:
            return None
        elif len(sessions) == 1:
            logger.info(f'Found existing tmux session: {sessions[0].name}')
            return sessions[0]
        else:
            logger.error(f'Found multiple tmux sessions with name: {self._tmux_session_name}')
            raise Exception(f'Found multiple tmux sessions with name: {self._tmux_session_name}')

    def _start_tmux_session(self):
        server = self.get_tmux_server()
        logger.info(f'Starting new tmux session: {self._tmux_session_name}')
        session = server.new_session(
            session_name=self._tmux_session_name,
            attach=False,
            start_directory=self._working_dir
        )
        # command = self.get_server_command()
        # logger.info(f'    using command: {command}')
        # session = server.new_session(
        #     session_name=self._tmux_session_name,
        #     attach=False,
        #     start_directory=self._working_dir,
        #     window_name='server',
        #     window_command=command
        # )
        return session

    def _find_or_create_tmux_session(self):
        self._tmux_session = self._find_tmux_session()
        if self._tmux_session is None:
            self._tmux_session = self._start_tmux_session()
        return self._tmux_session

    def _create_tmux_window(self):
        session = self._find_or_create_tmux_session()
        logger.info(f'Creating new tmux window: server')
        command = self.get_server_command()
        logger.info(f'    using command: {command}')
        logger.info(f'    in session: {session}')
        window = session.new_window(
            window_name='server',
            attach=True,
            start_directory=self._working_dir,
            window_shell=command
        )
        sleep(1)
        # Check if window still exists
        chk_window = session.windows.filter(window_name='server')
        if len(chk_window) == 0:
            raise Exception(f'Failed to create tmux window: Window does not exist anymore after 1s')
        return chk_window

    def _find_or_create_tmux_window(self):
        session = self._find_or_create_tmux_session()
        windows = session.windows.filter(window_name='server')
        if len(windows) == 0:
            self._tmux_window = self._create_tmux_window()
        elif len(windows) == 1:
            self._tmux_window = windows[0]
        else:
            logger.error(f'Found multiple tmux windows with name: server')
            raise Exception(f'Found multiple tmux windows with name: server')
        return self._tmux_window
    
    # def _create_tmux_pane(self):
    #     window = self._find_or_create_tmux_window()
    #     logger.info(f'Creating new tmux pane')
    #     command = self.get_server_command()
    #     logger.info(f'    using command: {command}')
    #     logger.info(f'    in window: {window}')
    #     pane = window.split_window(
    #         attach=False,
    #         start_directory=self._working_dir,
    #         vertical=True,
    #         shell=command
    #     )
    #     return pane
    
    # def _find_or_create_tmux_pane(self):
    #     # FIXME: There is no way to identify panes by name - find a workaround
    #     # window = self._find_or_create_tmux_window()
    #     # pane = window.panes
    #     # if len(pane) == 0:
    #     #     self._tmux_pane = self._create_tmux_pane()
    #     #     return self._tmux_pane
    #     # elif len(pane) == 1:
    #     #     self._tmux_pane = pane[0]
    #     #     return self._tmux_pane
    #     # else:
    #     #     logger.error(f'Found multiple tmux panes')
    #     #     raise Exception(f'Found multiple tmux panes')
    #     # FIXME: For now, we will just always create a new pane
    #     self._tmux_pane = self._create_tmux_pane()
    #     return self._tmux_pane
    
    def debug_tmux_sessions(self):
        # logger.warning('Logger level is: ' + str(logger.level))
        logger.debug(f'sys.executable={sys.executable}')
        server = self.get_tmux_server()
        logger.debug(f'Found {len(server.sessions)} tmux sessions:')
        for session in server.sessions:
            logger.debug(f'session.name={session.name}')
            logger.debug(f'session.windows=[')
            for window in session.windows:
                logger.debug(f'    {window.name}{{')
                for pane in window.panes:
                    logger.debug(f'        {pane}')
                logger.debug(f'    }}')
            logger.debug(f']')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.warning('Running this script directly is JUST FOR DEBUGGING')
    controller = TmuxServerController('minecraft', 'minecraft.serverwrapper', ['run'])
    # controller.debug_tmux_sessions()
    controller.start()
