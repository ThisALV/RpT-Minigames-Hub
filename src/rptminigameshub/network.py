import ssl
import logging
import rptminigameshub.checkout


# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)


class ClientsListener:
    """Listens for incoming WSS connections on given port, then uses established connections with StatusEmitter."""

    def __init__(self, port: int, security_ctx: ssl.SSLContext, status_source: rptminigameshub.checkout.Subject):
        """Configures shortly started server to listen on given port with given security context configuration. New status are obtained
        from given source Subject."""
        pass

    async def start(self):
        """Starts a WSS server with instance configuration. Will automatically closes WSS server when exited."""
        pass
