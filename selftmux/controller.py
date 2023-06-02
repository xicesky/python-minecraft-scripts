
import logging
import sys
import os
import libtmux

logger = logging.getLogger(__name__)


class TmuxServerController:
    _working_dir = None
    _module_name = None
    _tmux_session_name = None
    _tmux_server = None
    _tmux_session = None
    
    def __init__(self, session_name, module_name, working_dir=None):
        self._module_name = module_name
        self._tmux_session_name = session_name
        self._working_dir = working_dir
        if self._working_dir is None:
            self._working_dir = os.getcwd()
        # Find session now
        self._tmux_session = self._find_tmux_session()
            
    def start(self):
        self._find_or_start_tmux_session()

    def get_tmux_server(self):
        if self._tmux_server is None:
            self._tmux_server = libtmux.Server()
        return self._tmux_server
    
    def _find_tmux_session(self):
        for session in self.get_tmux_server().sessions:
            if session.name == self._tmux_session_name and len(session.windows) == 1 and len(session.windows[0].panes) == 1:
                logger.info(f'Found existing tmux session: {session.name}')
                return session
        return None

    def _start_tmux_session(self):
        command=f'{sys.executable} -m {self._module_name}'
        session = self.get_tmux_server().new_session(
            session_name=self._tmux_session_name,
            attach=False,
            start_directory=self._working_dir,
            window_name='server',
            window_command=command
        )
        logger.info(f'Started new tmux session: {session.name}')
        logger.debug(f'    using command: {command}')
        return session

    def _find_or_start_tmux_session(self):
        if self._tmux_session is None:
            self._tmux_session = self._start_tmux_session()
    
    def debug_tmux_sessions(self):
        logger.debug(f'# sys.executable={sys.executable}')
        server = self.get_tmux_server()
        for session in server.sessions:
            logger.debug(f'# session.name={session.name}')
            logger.debug(f'# session.windows=[')
            for window in session.windows:
                logger.debug(f'#   {window.name}\{{')
                for pane in window.panes:
                    logger.debug(f'#       {pane}')
                logger.debug(f'#   }}')
            logger.debug(f'# ]')


if __name__ == '__main__':
    controller = TmuxServerController()
    # controller.debug_tmux_sessions()
    controller.start()
