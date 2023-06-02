
import sys
import os
import subprocess
import shutil
from time import sleep
from minecraft.broadcaster import MinecraftServerLANBroadcaster
from serverloop.buffers import LineInputBuffer, OutputBuffer
from serverloop.serverloop import RepeatedCallback, ServerLoop, WaitingObject

# Fabric server urls are built like this:
# https://meta.fabricmc.net/v2/versions/loader/1.19.2/0.14.17/0.11.2/server/jar
def fabric_server_url(minecraft_version, loader_version, launcher_version):
    return f'https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{loader_version}/{launcher_version}/server/jar'

def fabric_server_jar_name(minecraft_version, loader_version, launcher_version):
    return f'fabric-server-mc.{minecraft_version}-loader.{loader_version}-launcher.{launcher_version}.jar'


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
    
    def __init__(self):
        if self._working_dir is None:
            self._working_dir = os.getcwd() + '/.minecraft-server'
        if self._java_executable_path is None:
            self._java_executable_path = shutil.which('java')
        if not os.path.exists(self._java_executable_path):
            raise MinecraftServerWrapperException('Java executable not found.')
        self._lan_broadcaster = MinecraftServerLANBroadcaster()
    
    def start(self):
        self.create_working_dir()
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
            os.mkdir(self._working_dir)
        else:
            print('Working directory already exists, skipping creation.')

    def accept_eula(self):
        # Replace "eula=false" with "eula=true" in eula.txt
        print('Accepting EULA...')
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
            print('Launcher jar already exists, skipping download.')
        else:
            print('Downloading launcher jar...')
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
        self._wo_minecraft_stdout = sl.add_waiting_object(LineInputBuffer(self._server_subprocess.stdout, lambda line: self.handle_minecraft_server_output('stdout', line), name='minecraft-stdout'))
        self._wo_minecraft_stderr = sl.add_waiting_object(LineInputBuffer(self._server_subprocess.stderr, lambda line: self.handle_minecraft_server_output('stderr', line), name='minecraft-stderr'))
        sl.call_repeatedly(1.0, self.check_minecraft_server, name='check-minecraft-server')
        
    def tick(self):
        #self.log('tick', 'tick')
        pass

    def handle_minecraft_server_output(self, pipename, line):
        self.log(f'mc-{pipename}', line)
        
    def handle_terminal_input(self, line):
        self.log('terminal', line)
        if self._server_subprocess is None:
            self.log('terminal', '!! Server not running, ignoring input !!')
        else:
            self.send_to_mc(line)

    def handle_keyboard_interrupt(self):
        self.log('terminal', 'KeyboardInterrupt')
        self.stop_minecraft_server()

    def log(self, source, line):
        print('{:10s}: {:s}'.format(source, line))
        
    def send_to_mc(self, command):
        # self.log_traffic('to-server', command)
        if self._server_subprocess is None:
            self.log('ERROR', '!! Server not running, ignoring input !!')
        else:
            self._wo_minecraft_stdin.send_line(command)
    
    def stop_minecraft_server(self):
        if self._server_subprocess is None:
            # FIXME: This does not really belong here but should be an async construct called after the server stops
            self._serverloop.stop()
            return
        try:
            self.send_to_mc('/stop')
        except BrokenPipeError:
            pass
        # Set a timeout and then hard-kill the server
        self._serverloop.call_after(30.0, self._server_subprocess.terminate)

    def kill_minecraft_server(self):
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
            self.log('mc-exit', 'Server exited with rc={:d}'.format(rc))
            self._serverloop.stop()

if __name__ == '__main__':
    MinecraftServerWrapper().start()
