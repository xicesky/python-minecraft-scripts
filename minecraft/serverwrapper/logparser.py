
import logging
import re

minecraft_log_levels = {
    'UNKNOWN': (logging.CRITICAL, 'UNKNOWN'),
    'FATAL': (logging.CRITICAL, 'FATAL'),
    'ERROR': (logging.ERROR, 'ERROR'),
    'WARN': (logging.WARNING, 'WARN'),
    'INFO': (logging.INFO, 'INFO'),
    'DEBUG': (logging.DEBUG, 'DEBUG'),
    'TRACE': (logging.DEBUG, 'TRACE'),
}

def parse_level(level: str) -> tuple[int, str]:
    try:
        return minecraft_log_levels[level.upper()]
    except KeyError:
        return minecraft_log_levels['UNKNOWN']


class MinecraftLogMessage:
    level: tuple[int, str] = None
    message: str = None
    
    def __init__(self, level: tuple[int, str] or str or None, message: str):
        if level is None:
            self.level = minecraft_log_levels['UNKNOWN']
        elif isinstance(level, str):
            self.level = parse_level(level)
        elif isinstance(level, tuple) and len(level) == 2 and isinstance(level[0], int) and isinstance(level[1], str):
            self.level = level
        else:
            raise ValueError('level must be a tuple of (int, str) or a string')
        self.message = message
    
    def __str__(self):
        return '%s: %s' % (self.level[1], self.message)


class MinecraftServerStartMessage(MinecraftLogMessage):
    host: str = None
    port: int = None
    
    def __init__(self, level: tuple[int, str] or str or None, message: str, host: str, port: int):
        super().__init__(level, message)
        self.host = host
        self.port = port
    
    def __str__(self):
        return '%s: %s (%s:%d)' % (self.level[1], self.message, self.host, self.port)


class MinecraftLogParser:
    # state
    _state: int = 0
    _last_level: str = None

    # callbacks
    _cb: callable = lambda x: None

    # Startup message: Starting net.fabricmc.loader.impl.game.minecraft.BundlerClassPathCapture
    _startup_line_pattern = re.compile('Starting (.*)')
    # Normal log message: [20:13:56] [main/INFO]: Loading Minecraft 1.19.2 with Fabric Loader 0.14.17
    _normal_line_pattern = re.compile('\[([0-9]{2}:[0-9]{2}:[0-9]{2})\] \[(.*)/(.*)\]: (.*)')
    # Starting Minecraft server on *:25565
    _server_start_pattern = re.compile('Starting Minecraft server on ([^:]*):([0-9]*)')
    
    def __init__(self, cb: callable):
        self._state = 0
        self._cb = cb


    def add_line(self, line):
        if self._state == 0:
            if line.startswith('['):
                # End of startup messages
                self._state = 1
            else:
                return self.handle_message(MinecraftLogMessage('INFO', line))

        if self._state == 1:
            m = self._normal_line_pattern.match(line)
            if m:
                message = MinecraftLogMessage(m.group(3), m.group(4))
                self._last_level = message.level
                return self.handle_message(message)
            else:
                return self.handle_message(MinecraftLogMessage(self._last_level, line))
        
        raise NotImplementedError('state %d not implemented' % self._state)
    
    
    def handle_message(self, message: MinecraftLogMessage):
        m = self._server_start_pattern.match(message.message)
        if m:
            message = MinecraftServerStartMessage(message.level, message.message, m.group(1), int(m.group(2)))
        self._cb(message)
