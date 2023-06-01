
import socket
import time

from serverloop.serverloop import WaitingObject


class MinecraftServerLANBroadcaster(WaitingObject):
    _servers = [
        ["Moritz' Minecraft Server", 25565],
    ]
    _broadcast_ip = "255.255.255.255"
    _broadcast_port = 4445
    # Similar to RepeatedCallback
    _interval = None
    _target = None
    
    def __init__(self, interval=1.5):
        self._interval = interval
        self._target = time.time() + interval
        
    def is_waiting_for_timeout(self):
        return self._target

    def do_timeout(self):
        self._target = time.time() + self._interval
        self.send_broadcasts()
    
    def send_broadcasts(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)        
        for server in self._servers:
            msg = "[MOTD]%s[/MOTD][AD]%d[/AD]" % (server[0], server[1])
            sock.sendto(bytes(msg, 'UTF-8'), (self._broadcast_ip, self._broadcast_port))
        sock.close()
    
    def add_server(self, name, port):
        self._servers.append([name, port])

    def remove_server(self, name, port):
        self._servers.remove([name, port])
