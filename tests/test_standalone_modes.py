import asyncio
from contextlib import contextmanager
from typing import Collection, Generator, Tuple

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


# Ensure the message matches exactly one sysex from the queue, and remove the corresponding sysex.
def _dequeue_sysex(
    message: "mido.Message", queue: Collection[Tuple[int, ...]]
) -> Collection[Tuple[int, ...]]:
    orig_num_remaining = len(queue)
    queue = [r for r in queue if not matches_sysex(message, r)]
    # Make sure we matched one of the queue elements.
    assert len(queue) == orig_num_remaining - 1
    return queue


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
    # Make sure the device is fully out of standalone mode.
    assert all([t is False for t in device_state.standalone_toggles])

    # Events that need to happen in order. Note the background program shouldn't get
    # sent when transitioning in this direction.
    remaining_standalone_requests = sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS
    received_main_program = False

    with _message_queue(device_state) as queue:
        cc_action(get_cc_for_key(key_number), "release", port=ioport, loop=loop)
        while not received_main_program:
            message = loop.run_until_complete(queue.get())
            message_attrs = message.dict()

            if message_attrs["type"] == "sysex":
                remaining_standalone_requests = _dequeue_sysex(
                    message, remaining_standalone_requests
                )

            elif message_attrs["type"] == "program_change":
                message_program: int = message_attrs["program"]
                if message_program == program:
                    # Make sure the controller has already been put into standalone
                    # mode.
                    assert len(remaining_standalone_requests) == 0
                    # Make sure we got the background program (and therefore also the
                    # switch to standalone mode) prior to the main one.
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
            and all(device_state.standalone_toggles)
            and len(remaining_standalone_requests) == 0
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
    # Make sure we're currently in standalone mode.
    assert all(device_state.standalone_toggles)
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
    # Make sure we're fully in standalone mode to begin.
    assert all(device_state.standalone_toggles)
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
        remaining_hosted_requests = sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS
        while any(remaining_hosted_requests):
            message = loop.run_until_complete(queue.get())
            message_attrs = message.dict()

            if message_attrs["type"] == "sysex":
                remaining_hosted_requests = _dequeue_sysex(
                    message, remaining_hosted_requests
                )

        # Sanity checks.
        assert (
            all([d is False for d in device_state.standalone_toggles])
            and len(remaining_hosted_requests) == 0
        )
