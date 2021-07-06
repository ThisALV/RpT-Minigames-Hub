from rptminigameshub.__main__ import *
import rptminigameshub.__main__
import rptminigameshub.checkout
import rptminigameshub.network
import asyncio
import pytest
import pathlib
import json.encoder


class TestMain:
    """Unit tests for program entry point."""

    @pytest.fixture
    @pytest.mark.asyncio
    def reset_stop_required(self, mocker, event_loop):
        """Resets stop_required to a new instance running on the next async unit test event's loop to emulates a new server run."""

        # New Event() instance will run on current loop generated using event_loop and pytest.mark.asyncio to avoid RuntimeError at wait() return
        mocker.patch.object(rptminigameshub.__main__, "stop_required", asyncio.Event())

    def test_require_stop(self, mocker):
        mocked_print = mocker.patch("builtins.print")
        mocked_event_set = mocker.patch("asyncio.Event.set")

        require_stop()

        mocked_print.assert_called_once_with("\b\b", end="")  # Should have erased the ^C trace inside console
        mocked_event_set.assert_called_once()  # Should have trigger the event that run_until_stopped() is awaiting for

    @pytest.mark.asyncio
    async def test_run_until_stopped(self, mocker, reset_stop_required):
        async def updater_task_mock():  # Mocks the whole servers checkout process, here we just want a cancel() callable method
            pass

        async def server_task_mock():  # Mocks the whole clients serving process, here we just want a cancel() callable method to check if it was called
            pass

        updater_task = asyncio.create_task(updater_task_mock())
        server_task = asyncio.create_task(server_task_mock())

        # Keeps the current method implement but spies it, on a specific object to keep the self argument working
        mocked_event_wait = mocker.patch.object(rptminigameshub.__main__.stop_required, "wait", wraps=rptminigameshub.__main__.stop_required.wait)

        mocked_updater_task_cancel = mocker.patch.object(updater_task, "cancel")  # Checks if task was cancelled at coroutine end as expected
        mocked_server_task_cancel = mocker.patch.object(server_task, "cancel")  # Same thing the for the mocked serving task

        # Will run in concurrency with run_until_stopped to check for this coroutine to be awaiting Event stop_required
        async def assert_awaiting_then_set():
            await asyncio.sleep(0)  # Ensures run_until_stopped await statement is reach before continuing this coroutine exec
            mocked_event_wait.assert_called_once()  # Should be waiting for the stop_required event
            # Should not have been stopped, expects pending tasks to not have been cancelled yet
            mocked_updater_task_cancel.assert_not_called()
            mocked_server_task_cancel.assert_not_called()

            rptminigameshub.__main__.stop_required.set()  # Then, finally fires stop_required so run_until_stopped will no longer be awaiting

        await asyncio.gather(  # Will run assert_awaiting_then_set() while run_until_stopped() is awaiting, then run that last one
            asyncio.create_task(run_until_stopped(server_task, updater_task)),
            asyncio.create_task(assert_awaiting_then_set())
        )

        assert rptminigameshub.__main__.stop_required.is_set()  # Should have been finally set because run_until_stopped() returned
        mocked_updater_task_cancel.assert_called_once()  # run_until_stopped() should have cancelled checkouts when server is stopped
        mocked_server_task_cancel.assert_called_once()  # It should also have cancelled clients serving process

    def test_load_servers_data(self, mocker):
        # Mocks open() to spy it without performing OS calls but still returning a spied file object
        mocked_file = mocker.patch("io.IOBase")
        mocker.patch("builtins.open", return_value=mocked_file)
        # Mocks a json loading using string instead, so we can control the mocked servers.json content and still manipulate
        # an "original" json returned object (for this program, only port property is required for server to be working)
        mocker.patch("json.load", return_value=json.loads("""
            {
                "servers": [
                    { "port": 35555 },
                    { "port": 35557 },
                    { "port": 35559 },
                    { "port": 35561 }
                ]
            }
        """))

        servers = load_servers_data(pathlib.PurePath("data/servers.json"))

        # Data file should have been open and closed
        mocked_file.__enter__.assert_called_once()
        mocked_file.__exit__.assert_called_once()

        assert servers == [  # JSON content should have been parsed to give the servers property array
            {"port": 35555},
            {"port": 35557},
            {"port": 35559},
            {"port": 35561},
        ]

    def test_local_ports(self):
        testing_servers_1 = json.loads("""
            [
                { "port": 35555 },
                { "port": 35557 },
                { "port": 35559 },
                { "port": 35561 }
            ]
        """)

        testing_servers_2 = json.loads("""
            [
                { "name": "Açores",     "port": 35557 },
                { "name": "Canaries",   "port": 35561 }
            ]
        """)

        testing_servers_3 = json.loads("""
            []
        """)

        # For each JSON array, checks if every port property of each object element is returned inside list
        assert local_ports(testing_servers_1) == [35555, 35557, 35559, 35561]
        assert local_ports(testing_servers_2) == [35557, 35561]
        assert local_ports(testing_servers_3) == []

    @pytest.mark.asyncio
    async def test_run_server_updater_crashed(self, mocker, reset_stop_required):
        mocked_signal_handler = mocker.patch.object(asyncio.get_running_loop(), "add_signal_handler")

        updater_throw = asyncio.Event()  # Will be set when updater.start() mocked coroutine can throw an error

        # Will wait for updater_throw to be set then raises an error
        async def mocked_updating():
            await updater_throw.wait()
            raise RuntimeError("A random error")

        # Will do nothing, here we're only interested by updating task
        async def mocked_serving():
            pass

        mocked_updater = mocker.patch("rptminigameshub.checkout.StatusUpdater")  # Creates a mockable StatusUpdater
        mocked_updater_start = mocker.patch.object(mocked_updater, "start", wraps=mocked_updating)  # On this StatusUpdater, mocks start()

        mocked_server = mocker.patch("rptminigameshub.network.ClientsListener")  # Creates a mockable ClientListener
        mocker.patch.object(mocked_server, "start", wraps=mocked_serving)  # On this ClientListener, mocks start()

        async def assert_updater_started_crash_it():
            # Before trying to gather running and updating tasks, we should have prepared a way to stop the running task by handling Ctrl+C
            mocked_signal_handler.assert_called_once_with(signal.SIGINT, require_stop)

            await asyncio.sleep(0)  # Ensures this coroutines is run after run_server() has begun to be awaiting

            mocked_updater_start.assert_called_once_with()  # Ensures run_server() is awaiting for updater to crash
            updater_throw.set()  # Causes mocked start() routine to continue execution and throw

        with pytest.raises(RuntimeError):  # We expect run_server to throw, which will propagates outside asyncio.gather()
            await asyncio.gather(  # An error will be thrown from updater.start() coroutine while run_server() is awaiting for it
                asyncio.create_task(run_server(mocked_server, mocked_updater)),
                asyncio.create_task(assert_updater_started_crash_it())
            )

        assert not rptminigameshub.__main__.stop_required.is_set()  # Should not have been caused by a server normal stop

    @pytest.mark.asyncio
    async def test_run_server_serving_crashed(self, mocker, reset_stop_required):
        mocked_signal_handler = mocker.patch.object(asyncio.get_running_loop(), "add_signal_handler")

        serving_throw = asyncio.Event()  # Will be set when server.start() mocked coroutine can throw an error

        # Will wait for serving_throw to be set then raises an error
        async def mocked_serving():
            await serving_throw.wait()
            raise RuntimeError("A random error")

        # Will do nothing, here we're only interested by serving task
        async def mocked_updating():
            pass

        mocked_updater = mocker.patch("rptminigameshub.checkout.StatusUpdater")  # Creates a mockable StatusUpdater
        mocker.patch.object(mocked_updater, "start", wraps=mocked_updating)  # On this StatusUpdater, mocks start()

        mocked_server = mocker.patch("rptminigameshub.network.ClientsListener")  # Creates a mockable ClientListener
        mocker_server_start = mocker.patch.object(mocked_server, "start", wraps=mocked_serving)  # On this ClientListener, mocks start()

        async def assert_server_started_crash_it():
            # Before trying to gather running and updating tasks, we should have prepared a way to stop the running task by handling Ctrl+C
            mocked_signal_handler.assert_called_once_with(signal.SIGINT, require_stop)

            await asyncio.sleep(0)  # Ensures this coroutines is run after run_server() has begun to be awaiting

            mocker_server_start.assert_called_once_with()  # Ensures run_server() is awaiting for server to crash
            serving_throw.set()  # Causes mocked start() routine to continue execution and throw

        with pytest.raises(RuntimeError):  # We expect run_server to throw, which will propagates outside asyncio.gather()
            await asyncio.gather(  # An error will be thrown from updater.start() coroutine while run_server() is awaiting for it
                asyncio.create_task(run_server(mocked_server, mocked_updater)),
                asyncio.create_task(assert_server_started_crash_it())
            )

        assert not rptminigameshub.__main__.stop_required.is_set()  # Should not have been caused by a server normal stop

    @pytest.mark.asyncio
    async def test_run_server_stopped(self, mocker, reset_stop_required):
        mocked_signal_handler = mocker.patch.object(asyncio.get_running_loop(), "add_signal_handler")

        # Will wait indefinitely, allowing us to mock Ctrl+C while updating task is emulated and awaited
        async def mocked_updating():
            await asyncio.Event().wait()  # This event will never be set

        # Same thing for serving task
        async def mocked_serving():
            await asyncio.Event().wait()

        mocked_updater = mocker.patch("rptminigameshub.checkout.StatusUpdater")  # Creates a mockable StatusUpdater
        mocker.patch.object(mocked_updater, "start", wraps=mocked_updating)  # On this StatusUpdater, mocks start()

        mocked_server = mocker.patch("rptminigameshub.network.ClientsListener")  # Creates a mockable ClientListener
        mocker.patch.object(mocked_server, "start", wraps=mocked_serving)  # On this ClientListener, mocks start()

        # Used to check if server has been started without modifying running task behavior
        spied_run_until_stopped = mocker.patch("rptminigameshub.__main__.run_until_stopped", wraps=run_until_stopped)

        async def assert_server_run_stop_it():
            # Before trying to gather running and updating tasks, we should have prepared a way to stop the running task by handling Ctrl+C
            mocked_signal_handler.assert_called_once_with(signal.SIGINT, require_stop)

            await asyncio.sleep(0)  # Ensures this coroutines is run after run_until_stopped() launched by run_server() is awaiting for stop

            spied_run_until_stopped.assert_called_once()  # Ensures run_server() is running run_until_stopped task, also called running task
            require_stop()  # Now stops the server

        await asyncio.gather(  # Starts server, running task will be stopped when assert_server_run_stop_it will set the Event
            asyncio.create_task(run_server(mocked_server, mocked_updater)),
            asyncio.create_task(assert_server_run_stop_it())
        )

        assert rptminigameshub.__main__.stop_required.is_set()  # Checks for running step to have been stopped because of appropriate Event
        # Then an error will be thrown if unit test exits with running or updating task still pending, otherwise if both are cancelled
        # that means it completed gracefully

    @pytest.mark.asyncio
    async def test_main(self, mocker, reset_stop_required):
        # Avoid to really catch system signals on testing
        mocker.patch.object(asyncio.get_running_loop(), "add_signal_handler")

        # Fake command line arguments
        port_arg = "3555"
        certificate_arg = "/path/to/crt.crt"
        privkey_arg = "/path/to/key.key"
        checkout_interval_arg = "5000"
        # Emulates arguments array using appropriate arg order, 1st elem doesn't matter as it should contain the unused started program path
        fake_argv = ["", port_arg, certificate_arg, privkey_arg, checkout_interval_arg]

        mocker.patch.object(rptminigameshub.__main__, "__file__", "/home/test/some-dir/__main__.py")  # Emulates a fake startup script file used to forms up relative paths
        mocked_data_loader = mocker.patch("rptminigameshub.__main__.load_servers_data")  # Used to retrieved path for data servers file

        # Mocks Subject and SSLContext because we just want to test server setting up here, so we don't want real objects to be created
        mocker.patch("rptminigameshub.checkout.Subject")
        mocker.patch("ssl.SSLContext")

        async def wait_indefinitely():
            await asyncio.Event().wait()  # This will never be set, causing coroutine to await forever

        # Spies these function to check if SIGINT listening, clients serving and updating tasks are both started as expected when server
        # is running, and suppress their implementation to avoid heavy IO operations to take place during this unit test
        mocked_updater = mocker.patch.object(rptminigameshub.checkout.StatusUpdater, "start", wraps=wait_indefinitely)
        mocked_server = mocker.patch.object(rptminigameshub.network.ClientsListener, "start", wraps=wait_indefinitely)

        async def assert_server_started_then_stop_it():
            await asyncio.sleep(0)  # Ensures this coroutine is running when run_server() is already awaiting

            # Checks for server setup to have been done correctly
            mocked_data_loader.assert_called_once_with(pathlib.PurePath("/home/test/some-dir/data/servers.json"))

            # Checks for server tasks to be running
            mocked_updater.assert_called_once()
            mocked_server.assert_called_once()

            # Then stops server
            require_stop()

        await asyncio.gather(  # Starts main, then when server is expected to run, checks if it is the case
            asyncio.create_task(main(fake_argv)),
            asyncio.create_task(assert_server_started_then_stop_it())
        )

        # Will throw an exception if some tasks are still pending at this point
