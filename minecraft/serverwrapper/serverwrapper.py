
import logging
from pathlib import Path
import sys
import os
import subprocess
import shutil
from time import sleep
import zipfile
from minecraft.serverwrapper.broadcaster import MinecraftServerInfo, MinecraftServerLANBroadcaster
from minecraft.serverwrapper.logparser import MinecraftLogParser, MinecraftServerStartMessage
from minecraft.serverwrapper.serverloop.buffers import LineInputBuffer, OutputBuffer
from minecraft.serverwrapper.serverloop.serverloop import RepeatedCallback, ServerLoop, WaitingObject

logger = logging.getLogger(__name__)

# Fabric server urls are built like this:
# https://meta.fabricmc.net/v2/versions/loader/1.19.2/0.14.17/0.11.2/server/jar
def fabric_server_url(minecraft_version, loader_version, launcher_version):
    return f'https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{loader_version}/{launcher_version}/server/jar'

def fabric_server_jar_name(minecraft_version, loader_version, launcher_version):
    return f'fabric-server-mc.{minecraft_version}-loader.{loader_version}-launcher.{launcher_version}.jar'

def find_mod_dir_in_zip(zip_file: zipfile.ZipFile, current_path: zipfile.Path = None) -> zipfile.Path or None:
    if current_path is None:
        current_path = zipfile.Path(zip_file)
    if not current_path.is_dir():
        raise MinecraftServerWrapperException('find_mod_dir_in_zip called with a non-directory path.')
    if (current_path / 'mods').is_dir():
        return current_path / 'mods'
    
    # Check if there is only one directory in the current path
    dirs = [x for x in current_path.iterdir() if x.is_dir()]
    if len(dirs) == 1:
        # There is only one directory in the current path, so we can just go down one level
        return find_mod_dir_in_zip(zip_file, dirs[0])
    # Check for ony of the following directories: .minecraft
    if (current_path / '.minecraft').is_dir():
        return find_mod_dir_in_zip(zip_file, current_path / '.minecraft')
    return None

def copy_mod_from_zip(mod_path: zipfile.Path, dest_dir: Path):
    with open(dest_dir / mod_path.name, 'wb') as destf:
        with mod_path.open('rb') as srcf:
            shutil.copyfileobj(srcf, destf)

class MinecraftServerWrapperException(Exception):
    pass


class MinecraftServerWrapper:
    _serverloop : ServerLoop = None
    _working_dir : str = None
    _minecraft_version : str = '1.19.2'
    _fabric_loader_version : str = '0.14.17'
    _fabric_launcher_version : str = '0.11.2'
    _auto_accept_eula : bool = True
    _java_executable_path : str = None
    # See https://www.oracle.com/java/technologies/javase/vmoptions-jsp.html
    _java_args : list[str] = \
        [   '-Xms8G'
        ,   '-Xmx8G'
        ,   '-Xmn512m'
        ,   '-XX:+UnlockExperimentalVMOptions'
        ,   '-XX:+DisableExplicitGC'
        ,   '-XX:+UseG1GC'
        ,   '-XX:G1NewSizePercent=20'
        ,   '-XX:G1ReservePercent=20'
        ,   '-XX:MaxGCPauseMillis=50'
        ,   '-XX:G1HeapRegionSize=16M'
        # ,   '-Xnoclassgc'                 # I really don't recommend using this
        ]
    _current_jar_path : str = None
    _server_subprocess : subprocess = None
    _wo_tick : RepeatedCallback = None
    _wo_terminal_stdin : OutputBuffer = None
    _wo_minecraft_stdin : LineInputBuffer = None
    _wo_minecraft_stdout : LineInputBuffer = None
    _wo_minecraft_stderr : LineInputBuffer = None
    _lan_broadcaster : MinecraftServerLANBroadcaster = None
    _server_name = "Moritz' Minecraft Server"
    _server_info = None
    _autoload_modpack : bool = True
    _logparser : MinecraftLogParser = None
    
    def __init__(self):
        if self._working_dir is None:
            self._working_dir = os.getcwd() + '/.minecraft-server'
        if self._java_executable_path is None:
            self._java_executable_path = shutil.which('java')
        if not os.path.exists(self._java_executable_path):
            raise MinecraftServerWrapperException('Java executable not found.')
        self._lan_broadcaster = MinecraftServerLANBroadcaster()
        self._logparser = MinecraftLogParser(self.handle_minecraft_log_message)
    
    def start(self):
        logger.info('Starting Minecraft server wrapper...')
        self.create_working_dir()
        self.sync_modpack()
        if self._auto_accept_eula:
            self.accept_eula()
        self.download_launcher()
        
        sl = self._serverloop = ServerLoop()
        self._wo_terminal_stdin = sl.add_waiting_object(LineInputBuffer(sys.stdin, self.handle_terminal_input, name='terminal'))
        self._wo_tick = sl.call_repeatedly(1.0, self.tick, name='tick')
        sl.call_on_keyboard_interrupt(self.stop_minecraft_server, name='keyboard-interrupt')
        
        sl.call_after(1.0, self.start_minecraft_server)
        # FIXME: Start LAN broadcaster only after finding out the server port
        sl.add_waiting_object(self._lan_broadcaster)
        sl.run()

    def create_working_dir(self):
        if not os.path.exists(self._working_dir):
            logger.info('Creating working directory: {:s}'.format(self._working_dir))
            os.mkdir(self._working_dir)
        else:
            logger.info('Working directory already exists, skipping creation.')

    def find_modpack_zip(self, directory) -> str or None:
        # Find zip file
        zip_files = []
        for file in os.listdir('.'):
            if not file.endswith('.zip'):
                continue
            if not zipfile.is_zipfile(file):
                logger.warning('Found file {:s} that is not a valid zip file, skipping.'.format(file))
                continue
            zip_files.append(file)
        if len(zip_files) > 1:
            raise MinecraftServerWrapperException('Found more than one zip file in current directory.')
        elif len(zip_files) == 1:
            return zip_files[0]
        return None
    
    def sync_modpack(self):
        # TODO: Handle either zip file or "modpack"/"mods" directory
        mod_zip = self.find_modpack_zip(".")
        if mod_zip is None:
            # No modpack zip found
            logger.info('No modpack zip found, not syncing mods.')
            return
        modpack_mod_dir = find_mod_dir_in_zip(mod_zip)
        if modpack_mod_dir is None:
            logger.info('No mods directory found in modpack zip, not syncing mods.')
            return
        filename = str(modpack_mod_dir.filename)
        logger.info('Syncing mods from {:s}'.format(filename))
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

    def download_launcher(self):
        if self._current_jar_path is None:
            self._current_jar_path = self._working_dir + '/' + fabric_server_jar_name(self._minecraft_version, self._fabric_loader_version, self._fabric_launcher_version)
        if os.path.exists(self._current_jar_path):
            logger.info('Launcher jar already exists, skipping download.')
        else:
            logger.info('Downloading launcher jar...')
            r = os.system(f'wget -O "{self._current_jar_path}" "{fabric_server_url(self._minecraft_version, self._fabric_loader_version, self._fabric_launcher_version)}"')
            if r != 0:
                raise MinecraftServerWrapperException(f'Failed to download launcher jar (wget returned non-zero exit code: {r}).')
            # Check if download was successful
            if not os.path.exists(self._current_jar_path):
                raise MinecraftServerWrapperException(f'Failed to download launcher jar: File {self._current_jar_path} does not exist.')

    def start_minecraft_server(self):
        #commandline = ['cat']
        commandline = [self._java_executable_path] + self._java_args + ['-jar', self._current_jar_path, 'nogui']
        
        self._server_subprocess = subprocess.Popen(commandline, cwd=self._working_dir, bufsize=1, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        sl = self._serverloop
        self._wo_minecraft_stdin = sl.add_waiting_object(OutputBuffer(self._server_subprocess.stdin, name='minecraft-stdin'))
        self._wo_minecraft_stdout = sl.add_waiting_object(LineInputBuffer(self._server_subprocess.stdout, lambda line: self.handle_minecraft_server_output(line), name='minecraft-stdout'))
        self._wo_minecraft_stderr = sl.add_waiting_object(LineInputBuffer(self._server_subprocess.stderr, lambda line: self.handle_minecraft_server_stderr(line), name='minecraft-stderr'))
        sl.call_repeatedly(1.0, self.check_minecraft_server, name='check-minecraft-server')
        
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
        if self._server_subprocess is None:
            logger.warn(f'terminal: Server not running, ignoring input!')
        else:
            self.send_to_mc(line)

    def handle_keyboard_interrupt(self):
        logger.info('KeyboardInterrupt')
        self.stop_minecraft_server()

    def log(self, source, line):
        logger.info('{:10s}: {:s}'.format(source, line))
        
    def send_to_mc(self, command):
        if self._server_subprocess is None:
            raise MinecraftServerWrapperException('Server not running, cannot send command to server.')
        else:
            self._wo_minecraft_stdin.send_line(command)
    
    def stop_minecraft_server(self):
        if self._server_subprocess is None:
            # FIXME: This does not really belong here but should be an async construct called after the server stops
            self._serverloop.stop()
            return
        try:
            self.handle_minecraft_server_stop()
            self.send_to_mc('/stop')
        except BrokenPipeError:
            pass
        # Set a timeout and then hard-kill the server
        self._serverloop.call_after(30.0, self.kill_minecraft_server)

    def kill_minecraft_server(self):
        logger.warn('Killing Minecraft server...')
        self._server_subprocess.terminate()
        sleep(1.0)
        self._server_subprocess.kill()
        # TODO: Save return code?
        self._server_subprocess.wait()
        self._server_subprocess = None
        # FIXME: This does not really belong here but should be an async construct called after the server stops
        self._serverloop.stop()
        
    def check_minecraft_server(self):
        if self._server_subprocess is None:
            return False
        rc = self._server_subprocess.poll()
        if rc is not None:
            logger.info('Server exited with rc={:d}'.format(rc))
            self.handle_minecraft_server_stop()
            self._serverloop.stop()
    
    def handle_minecraft_server_start(self, host, port):
        if not self._server_info is None:
            logger.warn('Server broadcast already started, re-registering.')
            self.handle_minecraft_server_stop()
        self._server_info = MinecraftServerInfo(self._server_name, port)
        logger.warn('Starting server broadcast: {:s}'.format(str(self._server_info)))
        self._lan_broadcaster.add_server(self._server_info)

    def handle_minecraft_server_stop(self):
        if self._server_info is None:
            logger.warn('Server broadcast not started, ignoring.')
            return
        logger.warn('Stopping server broadcast: {:s}'.format(str(self._server_info)))
        self._lan_broadcaster.remove_server(self._server_info)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.warning('Running this script directly is JUST FOR DEBUGGING')
    MinecraftServerWrapper().start()
