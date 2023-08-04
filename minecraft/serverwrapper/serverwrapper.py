
import logging
from pathlib import Path
import sys
import os
import shutil
from time import sleep
from minecraft.serverwrapper import util
from minecraft.serverwrapper.broadcaster import MinecraftServerInfo, MinecraftServerLANBroadcaster
from minecraft.serverwrapper.config import ConfigDict
from minecraft.serverwrapper.logparser import MinecraftLogParser, MinecraftServerStartMessage
from minecraft.serverwrapper.serverloop.buffers import LineInputBuffer, OutputBuffer
from minecraft.serverwrapper.serverloop.process import Process
from minecraft.serverwrapper.serverloop.serverloop import RepeatedCallback, ServerLoop
from minecraft.serverwrapper.util.archive import copy_mod_from_zip, deepsearch_for_mods_dir
from minecraft.serverwrapper.util.exceptions import MinecraftServerWrapperException

logger = logging.getLogger(__name__)


# Fabric server urls are built like this:
# https://meta.fabricmc.net/v2/versions/loader/1.19.2/0.14.17/0.11.2/server/jar
def fabric_server_url(minecraft_version, loader_version, launcher_version):
    return f'https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{loader_version}/{launcher_version}/server/jar'


def fabric_server_jar_name(minecraft_version, loader_version, launcher_version):
    return f'fabric-server-mc.{minecraft_version}-loader.{loader_version}-launcher.{launcher_version}.jar'


def java_args_for_memory(memory_mibs: int) -> list[str]:
    # See https://www.oracle.com/java/technologies/javase/vmoptions-jsp.html
    memory_mibs = int(memory_mibs)
    smaller_memory_mibs = memory_mibs >> 4
    # if smaller_memory_mibs < 128:
    #     smaller_memory_mibs = 128
    return \
        [   f'-Xms{memory_mibs}m'
        ,   f'-Xmx{memory_mibs}m'
        ,   f'-Xmn{smaller_memory_mibs}m'
        ,   '-XX:+UnlockExperimentalVMOptions'
        ,   '-XX:+DisableExplicitGC'
        ,   '-XX:+UseG1GC'
        ,   '-XX:G1NewSizePercent=20'
        ,   '-XX:G1ReservePercent=20'
        ,   '-XX:MaxGCPauseMillis=50'
        ,   '-XX:G1HeapRegionSize=16M'
        # ,   '-Xnoclassgc'                 # I really don't recommend using this
        ]


class MinecraftServerWrapper:
    _config: ConfigDict = None
    _serverloop: ServerLoop = None
    _working_dir: str = None
    _current_jar_path: str = None
    _minecraft: Process = None
    _wo_tick: RepeatedCallback = None
    _wo_terminal_stdin: OutputBuffer = None
    _lan_broadcaster: MinecraftServerLANBroadcaster = None
    _server_info = None
    _logparser: MinecraftLogParser = None

    def __init__(self, config: ConfigDict = None):
        if config is None:
            # Check if file exists
            if os.path.exists('minecraft.yaml'):
                config = ConfigDict.load_from_yaml_file("minecraft.yaml")
        self._config = ConfigDict.default_config() | (config or {})
        self._working_dir = self._config['wrapper']['working-directory'] or os.getcwd() + '/.minecraft-server'
        self._java_executable_path = self._config['wrapper']['java-executable-path']
        if self._java_executable_path is None:
            self._java_executable_path = shutil.which('java')
        if not os.path.exists(self._java_executable_path):
            raise MinecraftServerWrapperException('Java executable not found.')
        if self._config['minecraft']['server']['broadcast-to-lan']:
            self._lan_broadcaster = MinecraftServerLANBroadcaster()
        self._logparser = MinecraftLogParser(self.handle_minecraft_log_message)

    def start(self):
        logger.info('Starting Minecraft server wrapper...')
        self.create_working_dir()
        self.sync_instance()

        sl = self._serverloop = ServerLoop()
        self._wo_terminal_stdin = sl.add_waiting_object(LineInputBuffer(sys.stdin, self.handle_terminal_input, name='terminal'))
        self._wo_tick = sl.call_repeatedly(1.0, self.tick, name='tick')
        sl.call_on_keyboard_interrupt(self.stop_minecraft_server, name='keyboard-interrupt')

        sl.call_after(1.0, self.start_minecraft_server)
        if self._lan_broadcaster is not None:
            sl.add_waiting_object(self._lan_broadcaster)
        sl.run()

    def create_working_dir(self):
        if not os.path.exists(self._working_dir):
            logger.info('Creating working directory: {:s}'.format(self._working_dir))
            os.mkdir(self._working_dir)
        else:
            logger.info('Working directory already exists, skipping creation.')

    def sync_instance(self):
        self.sync_config()
        if self._config['minecraft']['modpack']['auto-load']:
            self.sync_modpack()
        self.download_launcher()

    def sync_config(self):
        if self._config['wrapper']['auto-accept-eula']:
            self.accept_eula()
        for filename in ["whitelist.json", "ops.json"]:
            if os.path.exists(filename):
                logger.info(f"Installing link to global {filename}")
                dest = self._working_dir + "/" + filename
                util.symlink(filename, self._working_dir, overwrite=True)
        # TODO: Set stuff in server.properties (like pvp=false)

    def accept_eula(self):
        # Replace "eula=false" with "eula=true" in eula.txt
        logger.info('Accepting EULA...')
        if os.path.exists(self._working_dir + '/eula.txt'):
            with open(self._working_dir + '/eula.txt', 'r') as f:
                lines = f.readlines()
            with open(self._working_dir + '/eula.txt', 'w') as f:
                for line in lines:
                    if line.startswith('eula=false'):
                        line = 'eula=true\n'
                    f.write(line)
        else:
            # Write eula.txt
            with open(self._working_dir + '/eula.txt', 'w') as f:
                f.write('eula=true\n')

    def sync_modpack(self):
        modpack_mod_dir = deepsearch_for_mods_dir(".")
        if modpack_mod_dir is None:
            logger.info('No mods directory or modpack zip found, not syncing mods.')
            return
        logger.info('Syncing mods from {:s}'.format(str(modpack_mod_dir)))
        mod_dir = Path(self._working_dir) / 'mods'
        if not mod_dir.exists():
            logger.info('Creating mods directory: {:s}'.format(str(mod_dir)))
            os.mkdir(mod_dir)
        if not mod_dir.is_dir():
            raise MinecraftServerWrapperException('"mods" is not a directory.')

        current_mods = [x.name for x in mod_dir.iterdir() if x.is_file()]
        logger.debug('Current mods:\n    {:s}'.format('\n    '.join(current_mods)))
        modpack_mods = [x.name for x in modpack_mod_dir.iterdir() if x.is_file()]
        logger.debug('Modpack mods:\n    {:s}'.format('\n    '.join(modpack_mods)))
        for current_mod in current_mods:
            if current_mod in modpack_mods:
                continue
            logger.info('Removing mod {:s}...'.format(current_mod))
            # Remove jar file
            # shutil.rmtree(mod_dir / current_mod)
            os.remove(mod_dir / current_mod)
        for modpack_mod in modpack_mods:
            if modpack_mod in current_mods:
                continue
            logger.info('Copying mod {:s}...'.format(modpack_mod))
            copy_mod_from_zip(modpack_mod_dir / modpack_mod, mod_dir)
        logger.info('Done syncing mods.')

    def download_launcher(self):
        minecraft_version = self._config['minecraft']['version']
        fabric_loader_version = self._config['minecraft']['fabric']['loader-version']
        fabric_launcher_version = self._config['minecraft']['fabric']['launcher-version']
        if self._current_jar_path is None:
            self._current_jar_path = self._working_dir + '/' + fabric_server_jar_name(minecraft_version, fabric_loader_version, fabric_launcher_version)
        if os.path.exists(self._current_jar_path):
            logger.info('Launcher jar already exists, skipping download.')
        else:
            logger.info('Downloading launcher jar...')
            r = os.system(f'wget -O "{self._current_jar_path}" "{fabric_server_url(minecraft_version, fabric_loader_version, fabric_launcher_version)}"')
            if r != 0:
                raise MinecraftServerWrapperException(f'Failed to download launcher jar (wget returned non-zero exit code: {r}).')
            # Check if download was successful
            if not os.path.exists(self._current_jar_path):
                raise MinecraftServerWrapperException(f'Failed to download launcher jar: File {self._current_jar_path} does not exist.')

    def start_minecraft_server(self):
        # commandline = ['cat']
        commandline = [self._java_executable_path] \
            + java_args_for_memory(int(self._config.wrapper['java-args']['optimize-for-memory-mibs'])) \
            + ['-jar', self._current_jar_path, 'nogui']
        logger.info('Starting Minecraft server with the following command line:')
        for arg in commandline:
            logger.info('    {:s}'.format(arg))
        self._minecraft = Process(
            commandline=commandline,
            working_dir=self._working_dir,
            stdout_callback=self.handle_minecraft_server_output,
            stderr_callback=self.handle_minecraft_server_stderr,
            exit_callback=self.handle_minecraft_server_stop,
        )

    def tick(self):
        logger.debug('tick')
        pass

    def handle_minecraft_server_output(self, line):
        self._logparser.add_line(line)

    def handle_minecraft_log_message(self, message):
        logger.log(message.level[0], '{:s}'.format(message.message))
        if isinstance(message, MinecraftServerStartMessage):
            self.handle_minecraft_server_start(message.host, message.port)

    def handle_minecraft_server_stderr(self, line):
        logger.error(f'mc-stderr: {line}')

    def handle_terminal_input(self, line):
        logger.debug(f'terminal: {line}')
        if self._minecraft is None:
            logger.warn('terminal: Server not running, ignoring input!')
        else:
            self.send_to_mc(line)

    def handle_keyboard_interrupt(self):
        logger.info('KeyboardInterrupt')
        self.stop_minecraft_server()

    def log(self, source, line):
        logger.info('{:10s}: {:s}'.format(source, line))

    def send_to_mc(self, command):
        if self._minecraft is None:
            raise MinecraftServerWrapperException('Server not running, cannot send command to server.')
        else:
            self._minecraft.send_line(command)

    def stop_minecraft_server(self):
        if self._minecraft is None:
            # FIXME: This does not really belong here but should be an async construct called after the server stops
            self._serverloop.stop()
            return
        try:
            self.send_to_mc('/stop')
        except BrokenPipeError:
            pass
        # Set a timeout and then hard-kill the server
        minecraft = self._minecraft     # Bind to current process
        self._serverloop.call_after(30.0, lambda: minecraft.term_kill())

    def kill_minecraft_server(self):
        logger.warn('Killing Minecraft server...')
        self._minecraft.terminate()
        sleep(1.0)
        self._minecraft.kill()

    def handle_minecraft_server_start(self, host, port):
        if self._server_info is not None and self._lan_broadcaster is not None:
            logger.warn('Server broadcast already started, re-registering.')
            self._lan_broadcaster.remove_server(self._server_info)

        self._server_info = MinecraftServerInfo(self._config['minecraft']['server']['name'], port)
        if self._lan_broadcaster is not None:
            logger.warn('Starting server broadcast: {:s}'.format(str(self._server_info)))
            self._lan_broadcaster.add_server(self._server_info)

    def handle_minecraft_server_stop(self, rc=None):
        if self._server_info is not None and self._lan_broadcaster is not None:
            logger.warn('Stopping server broadcast: {:s}'.format(str(self._server_info)))
            self._lan_broadcaster.remove_server(self._server_info)
        self._server_info = None
        self._minecraft = None
        # TODO: For now, exit if minecraft exitted - later we might want to re-start or sth
        self._serverloop.stop()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.warning('Running this script directly is JUST FOR DEBUGGING')
    MinecraftServerWrapper().start()
