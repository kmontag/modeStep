import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Collection, Generator, Optional, Tuple, Union

import janus
import mido
from conftest import (
    Device,
    DeviceState,
    cc_action,
    get_cc_for_key,
    matches_sysex,
    stabilize_after_cc_action,
    sync,
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


@asynccontextmanager
async def _message_queue(
    device: Device,
) -> AsyncGenerator[
    janus.AsyncQueue[mido.Message],
    Never,
]:
    async with device.incoming_messages() as queue:
        yield queue


async def _get_next_message(
    message_queue: janus.AsyncQueue[mido.Message], timeout: float = 5.0
) -> mido.Message:
    return await asyncio.wait_for(message_queue.get(), timeout=timeout)


@when("I hold the standalone exit button")
@sync
async def when_hold_standalone_exit(
    device: Device,
):
    await cc_action(STANDALONE_EXIT_CC, "hold", device)


@then(
    parsers.parse(
        "releasing key {key_number:d} should enter standalone program {program:d}"
    )
)
@sync
async def should_enter_standalone_program(
    key_number: int, program: int, device: Device, device_state: DeviceState
):
    # Make sure the device is fully out of standalone mode.
    assert all([t is False for t in device_state.standalone_toggles])

    # Events that need to happen in order. Note the background program shouldn't get
    # sent when transitioning in this direction.
    remaining_standalone_requests = sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS
    received_main_program = False

    async with _message_queue(device) as queue:
        await cc_action(get_cc_for_key(key_number), "release", device)
        num_initial_ccs: int = 0
        while not received_main_program:
            message = await _get_next_message(queue)
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
        await asyncio.sleep(0.5)
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
@sync
async def should_switch_directly_to_standalone_program(
    program: int,
    device: Device,
    device_state: DeviceState,
):
    # Make sure we're currently in standalone mode.
    assert all(device_state.standalone_toggles)
    async with _message_queue(device) as queue:
        await cc_action(STANDALONE_EXIT_CC, "release", device)
        # Make sure we get one message for the program change.
        message = await _get_next_message(queue)
        message_attrs = message.dict()
        assert message_attrs["type"] == "program_change"
        assert message_attrs["program"] == program

        # Wait a little while, and make sure we haven't gotten any other messages.
        await asyncio.sleep(0.5)
        assert (
            queue.empty()
        ), f"Received additional messages after direct standalone transition:\n{queue})"


@then("releasing the standalone exit button should enter hosted mode")
@sync
async def should_enter_hosted_mode(
    device: Device,
    device_state: DeviceState,
):
    # Make sure we're fully in standalone mode to begin.
    assert all(device_state.standalone_toggles)
    async with _message_queue(device) as queue:
        await cc_action(STANDALONE_EXIT_CC, "release", device)
        await stabilize_after_cc_action(device)

        # First message needs to be the background program.
        message = await _get_next_message(queue)
        message_attrs = message.dict()
        assert (
            message_attrs["type"] == "program_change"
            and message_attrs["program"] == BACKGROUND_PROGRAM
        )

        # Now make sure we get the right sysex messages.
        remaining_hosted_requests = sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS
        while any(remaining_hosted_requests):
            message = await _get_next_message(queue)
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
        while not queue.empty():
            message = queue.get_nowait()
            assert (
                message.is_cc()
            ), f"Got non-CC message after switching to hosted mode: {message}"
