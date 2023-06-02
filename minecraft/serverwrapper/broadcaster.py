
import socket
import time

from minecraft.serverwrapper.serverloop.serverloop import WaitingObject

class MinecraftServerInfo:
    name = None
    port = None

    def __init__(self, name, port):
        self.name = name
        self.port = port

    def __eq__(self, other):
        return self.name == other.name and self.port == other.port
    
    def __hash__(self):
        return hash((self.name, self.port))
    
    def __str__(self):
        return '%s (*:%d)' % (self.name, self.port)

class MinecraftServerLANBroadcaster(WaitingObject):
    _servers: list[MinecraftServerInfo] = []
    _broadcast_ip = "255.255.255.255"
    _broadcast_port = 4445
    # Similar to RepeatedCallback
    _interval = None
    _target = None
    
    def __init__(self, interval=1.0):
        self._interval = interval
        self._target = time.time() + interval
        
    def is_waiting_for_timeout(self):
        return self._target

    def do_timeout(self):
        self._target = time.time() + self._interval
        self.send_broadcasts()
    
    def send_broadcasts(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for server in self._servers:
                msg = "[MOTD]%s[/MOTD][AD]%d[/AD]" % (server.name, server.port)
                sock.sendto(bytes(msg, 'UTF-8'), (self._broadcast_ip, self._broadcast_port))
    
    def add_server(self, server: MinecraftServerInfo):
        self._servers.append(server)

    def remove_server(self, server: MinecraftServerInfo):
        self._servers.remove(server)
