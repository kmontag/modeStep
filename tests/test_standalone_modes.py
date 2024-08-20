import asyncio
from contextlib import contextmanager
from typing import Collection, Generator, Optional, Tuple, Union

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
from typing_extensions import Never, TypeAlias

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


MessageOrException: TypeAlias = Union[Tuple[mido.Message, None], Tuple[None, Exception]]


@contextmanager
def _message_queue(
    device_state: DeviceState,
) -> Generator[
    asyncio.Queue[MessageOrException],
    Never,
    None,
]:
    queue: asyncio.Queue[MessageOrException] = asyncio.Queue()

    def on_message(msg: Optional[mido.Message], exc: Optional[Exception]):
        if exc is not None:
            assert msg is None
            queue.put_nowait((None, exc))
        else:
            assert msg is not None
            queue.put_nowait((msg, None))

    remove_listener = device_state.add_message_listener(on_message)
    yield queue
    remove_listener()


async def _get_next_message(
    message_queue: asyncio.Queue[MessageOrException],
) -> mido.Message:
    message, exc = await message_queue.get()
    if exc is not None:
        raise exc
    assert message is not None
    return message


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
        num_initial_ccs: int = 0
        while not received_main_program:
            message = loop.run_until_complete(_get_next_message(queue))
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
                # Allow up to a small number of initial CCs due to the interface being
                # updated, since these can potentially get sent between the release CC
                # message and the actual standalone mode activation. The worst case here
                # appears to be 6 CCs in total (4 display CCs and 2 LED CCs).
                assert (
                    len(remaining_standalone_requests)
                    == len(sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS)
                ), f"Received CC message after beginning standalone transition: {message}"

                num_initial_ccs += 1
                assert (
                    num_initial_ccs <= 6
                ), f"Got too many CCs before beginning standalone mode transition: {message}"

            else:
                raise RuntimeError(f"Received unrecognized message: {message}")

        # Sanity check, this should never fail given the business logic above.
        assert (
            all(device_state.standalone_toggles)
            and len(remaining_standalone_requests) == 0
            and received_main_program
        )

        # Wait a little while to make sure no additional CCs or other messages get sent.
        loop.run_until_complete(asyncio.sleep(0.5))
        assert (
            queue.empty()
        ), f"Received additional messages after standalone transition:\n{queue})"


@then("the standalone background program should be active")
def should_have_standalone_background_program_active(device_state: DeviceState):
    assert (
        device_state.standalone_program == BACKGROUND_PROGRAM
    ), f"Expected background program ({BACKGROUND_PROGRAM}) to be active, but got {device_state.standalone_program}"


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
        message = loop.run_until_complete(_get_next_message(queue))
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
        message = loop.run_until_complete(_get_next_message(queue))
        message_attrs = message.dict()
        assert (
            message_attrs["type"] == "program_change"
            and message_attrs["program"] == BACKGROUND_PROGRAM
        )

        # Now make sure we get the right sysex messages.
        remaining_hosted_requests = sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS
        while any(remaining_hosted_requests):
            message = loop.run_until_complete(_get_next_message(queue))
            message_attrs = message.dict()

            assert (
                message_attrs["type"] == "sysex"
            ), f"Got non-sysex message before switching out of standalone mode: {message}"

            remaining_hosted_requests = _dequeue_sysex(
                message, remaining_hosted_requests
            )

        # Sanity checks.
        assert (
            all([d is False for d in device_state.standalone_toggles])
            and len(remaining_hosted_requests) == 0
        )

        # All additional messages to this point should be CCs.
        might_have_more_messages = True
        while might_have_more_messages:
            try:
                message, exception = queue.get_nowait()
                assert exception is None
                assert message is not None
                assert (
                    message.is_cc()
                ), f"Got non-CC message after switching to hosted mode: {message}"
            except asyncio.QueueEmpty:
                might_have_more_messages = False
