
import sys
import os
import subprocess
import shutil
from minecraft.broadcaster import MinecraftServerLANBroadcaster

from serverloop.serverloop import ServerLoop

# Fabric server urls are built like this:
# https://meta.fabricmc.net/v2/versions/loader/1.19.2/0.14.17/0.11.2/server/jar
def fabric_server_url(minecraft_version, loader_version, launcher_version):
    return f'https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{loader_version}/{launcher_version}/server/jar'

def fabric_server_jar_name(minecraft_version, loader_version, launcher_version):
    return f'fabric-server-mc.{minecraft_version}-loader.{loader_version}-launcher.{launcher_version}.jar'


class MinecraftServerWrapperException(Exception):
    pass


class MinecraftServerWrapper:
    _serverloop = None
    _working_dir = None
    _minecraft_version = '1.19.2'
    _fabric_loader_version = '0.14.17'
    _fabric_launcher_version = '0.11.2'
    _auto_accept_eula = True
    _java_executable = None
    _java_args = \
        [   '-Xms8G'
        ,   '-Xmx8G'
        ,   '-Xmn512m'
        ,  '-XX:+UnlockExperimentalVMOptions'
        ,   '-XX:+DisableExplicitGC'
        ,   '-XX:+UseG1GC'
        ,   '-XX:G1NewSizePercent=20'
        ,   '-XX:G1ReservePercent=20'
        ,   '-XX:MaxGCPauseMillis=50'
        ,   '-XX:G1HeapRegionSize=16M'
        # ,   '-Xnoclassgc'                 # I really don't recommend using this
        ]
    _current_jar_path = None
    _server_subprocess = None
    _terminal_stdin = None
    _minecraft_stdin = None
    _minecraft_stdout = None
    _minecraft_stderr = None
    _lan_broadcaster = None
    
    def __init__(self):
        if self._working_dir is None:
            self._working_dir = os.getcwd() + '/.minecraft-server'
        self._terminal_stdin = sys.stdin
        if self._java_executable is None:
            self._java_executable = shutil.which('java')
        if not os.path.exists(self._java_executable):
            raise MinecraftServerWrapperException('Java executable not found.')
        self._lan_broadcaster = MinecraftServerLANBroadcaster()
    
    def start(self):
        self.create_working_dir()
        if self._auto_accept_eula:
            self.accept_eula()
        self.download_launcher()
        
        self._serverloop = ServerLoop()
        self._serverloop.call_after(1.0, self.start_minecraft_server)
        # FIXME: Start LAN broadcaster only after finding out the server port
        self._serverloop.add_waiting_object(self._lan_broadcaster)
        self._serverloop.run()

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
        commandline = [self._java_executable] + self._java_args + ['-jar', self._current_jar_path, 'nogui']
        
        self._server_subprocess = subprocess.Popen(commandline, cwd=self._working_dir, bufsize=1, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self._minecraft_stdin = self._server_subprocess.stdin
        self._minecraft_stdout = self._server_subprocess.stdout
        self._minecraft_stderr = self._server_subprocess.stderr
        
        self._serverloop.call_when_ready_to_receive(self._minecraft_stdout, lambda: self.handle_minecraft_server_output('stdout', self._minecraft_stdout.readline().rstrip()), name='minecraft-stdout')
        self._serverloop.call_when_ready_to_receive(self._minecraft_stderr, lambda: self.handle_minecraft_server_output('stderr', self._minecraft_stderr.readline().rstrip()), name='minecraft-stderr')
        self._serverloop.call_when_ready_to_receive(self._terminal_stdin, lambda: self.handle_terminal_input(self._terminal_stdin.readline().rstrip()), name='terminal')
        self._serverloop.call_repeatedly(1.0, self.tick, name='tick')
        self._serverloop.call_on_keyboard_interrupt(self.stop_minecraft_server, name='keyboard-interrupt')
        
    def tick(self):
        self.log('tick', 'tick')

    def handle_minecraft_server_output(self, pipename, line):
        self.log(f'mc-{pipename}', line)
        
    def handle_terminal_input(self, line):
        self.log('terminal', line)
        self.send_to_mc(line)

    def log(self, source, line):
        print('{:10s}: {:s}'.format(source, line))
        
    def send_to_mc(self, command):
        # self.log_traffic('to-server', command)
        # FIXME: Blocking
        self._minecraft_stdin.write(command + '\n')
    
    def stop_minecraft_server(self):
        self.log('terminal', 'KeyboardInterrupt')
        try:
            self.send_to_mc('/stop')
        except BrokenPipeError:
            pass
        # Set a timeout and then call self._server_subprocess.terminate()
        self._serverloop.call_after(30.0, self._server_subprocess.terminate)

    def kill_minecraft_server(self):
        self._server_subprocess.terminate
        self._serverloop.stop()
        
    def check_minecraft_server(self):
        rc = self._server_subprocess.poll()
        if rc is not None:
            self.log('mc-exit', 'Server exited with rc={:d}'.format(rc))
            self._serverloop.stop()

if __name__ == '__main__':
    MinecraftServerWrapper().start()
