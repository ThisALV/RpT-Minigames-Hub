import json
import logging
import sys
import pathlib
import asyncio
import rptminigameshub.checkout
import rptminigameshub.network
import ssl
import signal
import os
import typing


# Relative path from this module to access servers list
SERVERS_LIST_RELATIVE_PATH = "data/servers.json"

# Initializes and retrieves this module logger
logger = logging.getLogger(__name__)

# Asyncio Event: Fired when Ctrl+C is hit to stop the server, will be initialized when we are inside an Asyncio event's loop
stop_required: "typing.Union[asyncio.Event, None]" = None


def require_stop():
    """Stops the server, and subsequently the program, as soon as event's loop run again."""

    print("\b\b", end="")  # Avoids ^C trace in console
    stop_required.set()


async def run_until_stopped(serving_task: asyncio.Task, updater_task: asyncio.Task):
    """Awaits stop event to run event's loop until server stop is required by Ctrl+C. When stopped, cancels given updater and server tasks."""

    await stop_required.wait()
    updater_task.cancel()  # Avoids checkouts to repeat indefinitely even if server has been stopped
    serving_task.cancel()


def load_servers_data(data_path: os.PathLike):
    """Returns servers list parsed from JSON data of property "servers" for file at given location."""

    # Tries to open file in read-only mode
    with open(data_path, "r") as file:
        return json.load(file)["servers"]  # Retrieves "servers" field, return will make file to be closed as we're inside a with-context


def make_security_context(certificate_path: os.PathLike, private_key_path: os.PathLike) -> ssl.SSLContext:
    """Returns a configured TLS features context for a TLS certified server loading cert and privkey at given locations."""

    security_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    security_ctx.load_cert_chain(certificate_path, private_key_path)

    return security_ctx


def local_ports(servers_list) -> "list[int]":
    """Maps given JSON servers array into a server ports list using "port" property."""

    return [game_server["port"] for game_server in servers_list]


async def run_server(server: rptminigameshub.network.ClientsListener, updater: rptminigameshub.checkout.StatusUpdater):
    """Runs event's main loop for serving, SIGINT listening and updating tasks until SIGINT is handled or until status updater crashes,
    will throw if it happens."""

    # Stops the server when Ctrl+C is hit
    asyncio.get_running_loop().add_signal_handler(signal.SIGINT, require_stop)
    # Runs server until it is stopped by Ctrl+C OR until status checkout crashes
    serving_task = asyncio.create_task(server.start())
    updater_task = asyncio.create_task(updater.start())  # Must be cancellable if server stops
    wait_for_sigint_task = asyncio.create_task(run_until_stopped(serving_task, updater_task))  # Must be cancellable if server stops

    stopped_gracefully = False  # Set to True when finally clause is reach, means it is normal if coroutine tasks are cancelled
    try:  # Handles case where one of the two tasks stops unexpectedly
        try:  # Handles case where updater_task is cancelled
            await asyncio.gather(wait_for_sigint_task, updater_task, serving_task)
        except asyncio.CancelledError:
            # If updater_task or serving_task have been cancelled but not from final clause or running task post-await statement,
            # then this CancelledError is unexpected and must be propagated
            if not stopped_gracefully and (updater_task.cancelled() and serving_task.cancelled()) and not wait_for_sigint_task.done():  # End of running task: updating is cancelled
                raise
    finally:  # Ensures both tasks will be stop before program to avoid destroying them as pending
        stopped_gracefully = True  # Cancelling tasks will cause them to raise a CancelledError, we notifies except clause it is expected
        # Gracefully shutdown
        serving_task.cancel()
        updater_task.cancel()
        wait_for_sigint_task.cancel()


async def main(argv: "list[str]"):
    """Parses command line options and servers list data, then checkout on given delay basis servers inside list to provides clients connected to given
    local port."""

    global stop_required  # Assigns this global variable from our event's loop coroutine
    stop_required = asyncio.Event()  # Now, as we're inside an event's loop, we can initialize this Event

    servers_list_path = pathlib.PurePath(__file__).parent.joinpath(SERVERS_LIST_RELATIVE_PATH)
    logger.debug(f"Loading servers list from {servers_list_path}...")
    # Tries to open servers list data from current module file using paths concatenation
    servers = load_servers_data(servers_list_path)
    logger.debug("Loaded servers list.")

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
    security_ctx = make_security_context(pathlib.PurePath(certificate_path), pathlib.PurePath(privkey_path))
    logger.debug("Security context configured.")

    # Configures periodic checkout with created ports list to start it later
    updater = rptminigameshub.checkout.StatusUpdater(checkouts_interval, local_ports(servers), current_servers_status)
    # Configures server with listening port and configured TLS features
    server = rptminigameshub.network.ClientsListener(port, security_ctx, current_servers_status)

    logger.info("Start hub server.")
    await run_server(server, updater)
    logger.info("Stopped hub server.")


try:
    asyncio.run(main(sys.argv))  # Runs program in asyncio single thread event's loop
except Exception as err:  # Print errors with application logging instead of raw stacktrace
    logger.critical(f"Fatal: {type(err).__name__} {err.args[0]}")
    exit(1)
