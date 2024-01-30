import asyncio
from contextlib import contextmanager
from typing import Generator

import mido
from conftest import (
    DeviceState,
    cc_action,
    get_cc_for_key,
    matches_sysex,
    stabilize_after_cc_action,
    sysex,
)
from pytest_bdd import parsers, scenarios, then, when
from typing_extensions import Never

# Standalone background program configured in the standalone Live set.
BACKGROUND_PROGRAM = 10

# Exit button in standalone modes.
STANDALONE_EXIT_CC = 80

scenarios("standalone_modes.feature")


@contextmanager
def _message_queue(
    device_state: DeviceState,
) -> Generator["asyncio.Queue[mido.Message]", Never, None]:
    queue: asyncio.Queue[mido.Message] = asyncio.Queue()

    def on_message(message: mido.Message):
        queue.put_nowait(message)

    remove_listener = device_state.add_message_listener(on_message)
    yield queue
    remove_listener()


@when("I hold the standalone exit button")
def when_hold_standalone_exit(
    ioport: mido.ports.BaseOutput, loop: asyncio.AbstractEventLoop
):
    cc_action(STANDALONE_EXIT_CC, "hold", port=ioport, loop=loop)


@then(
    parsers.parse(
        "releasing key {key_number:d} should enter standalone program {program:d}"
    )
)
def should_enter_standalone_program(
    key_number: int,
    program: int,
    loop: asyncio.AbstractEventLoop,
    ioport: mido.ports.BaseOutput,
    device_state: DeviceState,
):
    assert device_state.standalone is False
    assert device_state.tether is True

    # Events that need to happen in order.
    received_standalone_sysex = False
    received_tether_sysex = False
    received_background_program = False
    received_main_program = False

    with _message_queue(device_state) as queue:
        cc_action(get_cc_for_key(key_number), "release", port=ioport, loop=loop)
        while not received_main_program:
            message = loop.run_until_complete(queue.get())
            message_attrs = message.dict()

            if message_attrs["type"] == "sysex":
                # The background program comes after all sysexes.
                assert not received_background_program
                if matches_sysex(message, sysex.SYSEX_STANDALONE_MODE_ON_REQUEST):
                    assert not received_standalone_sysex
                    received_standalone_sysex = True
                elif matches_sysex(message, sysex.SYSEX_TETHER_OFF_REQUEST):
                    assert not received_tether_sysex
                    received_tether_sysex = True
                else:
                    raise RuntimeError(f"received unrecognized sysex: {message}")

            elif message_attrs["type"] == "program_change":
                message_program: int = message_attrs["program"]
                if message_program == BACKGROUND_PROGRAM:
                    # Make sure the controller has already been put into standalone
                    # mode.
                    assert received_standalone_sysex and received_tether_sysex
                    # Assert no duplicates.
                    assert not received_background_program
                    received_background_program = True
                elif message_program == program:
                    # Make sure we got the background program (and therefore also the
                    # switch to standalone mode) prior to the main one.
                    assert received_background_program
                    received_main_program = True
                else:
                    raise RuntimeError(f"received unexpected program change: {message}")
            elif message.is_cc():
                # CCs can be received as long as the main standalone program hasn't been
                # sent.
                pass
            else:
                raise RuntimeError(f"received unrecognized message: {message}")

        # Sanity check, this should never fail given the business logic above.
        assert (
            queue.empty()
            and device_state.standalone is True
            and received_standalone_sysex
            and received_tether_sysex
            and received_background_program
            and received_main_program
        )

        # Wait a little while to make sure no CCs get sent.
        loop.run_until_complete(asyncio.sleep(0.5))
        assert queue.empty()


@then(
    parsers.parse(
        "releasing the standalone exit button should switch directly to standalone program {program:d}"
    )
)
def should_switch_directly_to_standalone_program(
    program: int,
    device_state: DeviceState,
    loop: asyncio.AbstractEventLoop,
    ioport: mido.ports.BaseOutput,
):
    assert device_state.standalone is True
    assert device_state.tether is False
    with _message_queue(device_state) as queue:
        cc_action(STANDALONE_EXIT_CC, "release", port=ioport, loop=loop)
        # Make sure we get one message for the program change.
        message = loop.run_until_complete(queue.get())
        message_attrs = message.dict()
        assert message_attrs["type"] == "program_change"
        assert message_attrs["program"] == program

        # Wait a little while, and make sure we haven't gotten any other messages.
        loop.run_until_complete(asyncio.sleep(0.5))
        assert queue.empty()


@then("releasing the standalone exit button should enter hosted mode")
def should_enter_hosted_mode(
    loop: asyncio.AbstractEventLoop,
    ioport: mido.ports.BaseOutput,
    device_state: DeviceState,
):
    assert device_state.standalone is True
    assert device_state.tether is False
    with _message_queue(device_state) as queue:
        cc_action(STANDALONE_EXIT_CC, "release", port=ioport, loop=loop)
        stabilize_after_cc_action(loop=loop, device_state=device_state)

        # First message needs to be the background program.
        message = loop.run_until_complete(queue.get())
        message_attrs = message.dict()
        assert (
            message_attrs["type"] == "program_change"
            and message_attrs["program"] == BACKGROUND_PROGRAM
        )

        # Now make sure we get the right sysex messages.
        received_hosted_sysex = False
        received_tether_sysex = False
        while not (received_hosted_sysex and received_tether_sysex):
            message = loop.run_until_complete(queue.get())
            message_attrs = message.dict()

            if message_attrs["type"] == "sysex":
                if matches_sysex(message, sysex.SYSEX_STANDALONE_MODE_OFF_REQUEST):
                    assert not received_hosted_sysex
                    received_hosted_sysex = True
                elif matches_sysex(message, sysex.SYSEX_TETHER_ON_REQUEST):
                    assert not received_tether_sysex
                    received_tether_sysex = True
                else:
                    raise RuntimeError(f"received unrecognized sysex: {message}")

        # Sanity checks.
        assert (
            device_state.standalone is False
            and device_state.tether is True
            and received_hosted_sysex
            and received_tether_sysex
        )
