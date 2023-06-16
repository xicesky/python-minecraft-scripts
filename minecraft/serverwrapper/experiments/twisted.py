import logging
from twisted.internet import reactor, protocol, endpoints
from twisted.protocols import basic

logger = logging.getLogger(__name__)

class PubProtocol(basic.LineReceiver):
    remote_address = None

    def __init__(self, factory):
        self.delimiter = b"\n"
        self.factory = factory

    def connectionMade(self):
        self.remote_address = self.transport.getPeer()
        logger.info("New connection from {}".format(self.remote_address))
        self.factory.clients.add(self)

    def connectionLost(self, reason):
        logger.info("Lost connection from {}".format(self.remote_address))
        self.factory.clients.remove(self)

    def lineReceived(self, line):
        logger.info("Received line from {}: {}".format(self.remote_address, line))
        for c in self.factory.clients:
            logger.info("Sending line to {}: {}".format(c.remote_address, line))
            source = u"<{}> ".format(self.transport.getHost()).encode("ascii")
            c.sendLine(source + line)

class PubFactory(protocol.Factory):
    def __init__(self):
        self.clients = set()

    def buildProtocol(self, addr):
        return PubProtocol(self)

def run_experiment():
    endpoints.serverFromString(reactor, "tcp:1025").listen(PubFactory())
    reactor.run()
