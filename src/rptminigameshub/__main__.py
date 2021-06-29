import json
import logging
import sys
import pathlib
import asyncio
import rptminigameshub.checkout
import rptminigameshub.network
import ssl
import signal


# Relative path from this module to access servers list
SERVERS_LIST_RELATIVE_PATH = "data/servers.json"

# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)

# Fired when Ctrl+C is hit to stop the server
stop_required = asyncio.Event()


def require_stop():
    """Stops the server, and subsequently the program, as soon as event's loop run again."""

    print("\b\b", end="")  # Avoids ^C trace in console
    stop_required.set()


async def run_until_stopped(updater_task: asyncio.Task):
    """Awaits stop event to run event's loop until server stop is required by Ctrl+C. When stopped, cancels given updater task."""

    await stop_required.wait()
    updater_task.cancel()  # Avoids checkouts to repeat indefinitely even if server has been stopped


async def main(argv: 'list[str]'):
    """Parses command line options and servers list data, then checkout on given delay basis servers inside list to provides clients connected to given
    local port."""

    servers_list_path = pathlib.PurePath(__file__).joinpath(SERVERS_LIST_RELATIVE_PATH)
    logger.debug(f"Parsing servers list from {servers_list_path}...")

    # Tries to open servers list data from current module file using paths concatenation
    with open(servers_list_path, "r") as servers_list_file:
        servers = json.load(servers_list_file)["servers"]  # Loads servers list from open stream

    logger.debug("Parsed servers list.")

    # Tries to parse port number, certificate and private key file, and checkouts interval in milliseconds
    logger.debug("Parsing command line options...")
    port = int(argv[1])
    certificate_path = argv[2]
    privkey_path = argv[3]
    checkouts_interval = int(argv[4])
    logger.debug("Parsed options.")

    # Shared between ClientsListener and StatusUpdater to communicates about latest retrieved status
    current_servers_status = rptminigameshub.checkout.Subject()

    # Configures SSL features for a TLS-based server with parsed options
    logger.debug(f"Configuring context for TLS crt at {certificate_path} and for private key at {privkey_path}...")
    security_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    security_ctx.load_cert_chain(certificate_path, privkey_path)
    logger.debug("Security context configured.")

    # Starts hub server listening clients and automatically closes it when program stops
    async with rptminigameshub.network.ClientsListener(port, security_ctx, current_servers_status):
        # Obtains local servers port list from loaded servers data
        local_servers = [game_server["port"] for game_server in servers]
        # Configures periodic checkout with created ports list to start it later
        updater = rptminigameshub.checkout.StatusUpdater(checkouts_interval, local_servers, current_servers_status)

        # Stops the server when Ctrl+C is hit
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, require_stop)
        # Runs server until it is stopped by Ctrl+C OR until status checkout crashes
        updater_task = asyncio.create_task(updater.start())  # Must be cancellable if server stops
        wait_for_sigint_task = asyncio.create_task(run_until_stopped(updater_task))
        try:  # Handle case where updater_task is cancelled
            await asyncio.gather(wait_for_sigint_task, updater_task)
        except asyncio.CancelledError as cancellation_err:
            if not updater_task.cancelled() and stop_required.is_set():  # If stopped, it is perfectly normal that checkouts have been cancelled
                logger.info("Server stopped.")
            else:  # If still running, then it is an error and server must be closed by stopping the event's loop when leaving main() coroutine
                raise cancellation_err


try:
    asyncio.run(main(sys.argv))  # Runs program in asyncio single thread event's loop
except Exception as err:  # Print errors with application logging instead of raw stacktrace
    logger.critical(f"Fatal: {type(err)} {err.args[0]}")
