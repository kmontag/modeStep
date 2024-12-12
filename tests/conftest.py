from __future__ import annotations

import asyncio
import functools
import importlib.machinery
import importlib.util
import os
import queue
import time
import webbrowser
from enum import Enum
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Collection,
    Dict,
    Generator,
    List,
    Optional,
    Protocol,
    Tuple,
    TypeVar,
    Union,
    overload,
)

import mido
from pytest import FixtureRequest, fixture, mark
from pytest_bdd import given, parsers, then, when
from pytest_bdd.parser import Feature, Step
from pytest_bdd.utils import get_args
from rich.console import Console
from rich.table import Table
from rich.text import Text
from typing_extensions import Never, TypeAlias

if TYPE_CHECKING:
    # The type checker sees packages in the project root.
    import control_surface.elements.hardware as hardware
    import control_surface.sysex as sysex
else:
    # Outside the type checker, we don't have direct import access to the main control
    # surface, but the hardware and sysex constants would be too annoying to
    # duplicate. Load it manually from the path, see
    # https://csatlas.com/python-import-file-module/#import_a_file_in_a_different_directory.
    def _load_module_from_path(name: str, path: str):
        path = os.path.join(path, f"{name}.py")
        loader = importlib.machinery.SourceFileLoader(name, path)
        spec = importlib.util.spec_from_loader(name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    hardware = _load_module_from_path(
        "hardware",
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "..",
            "control_surface",
            "elements",
        ),
    )
    sysex = _load_module_from_path(
        "sysex",
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "..",
            "control_surface",
        ),
    )

is_debug = "DEBUG" in os.environ

T = TypeVar("T")

# Standard identity request, see
# http://midi.teragonaudio.com/tech/midispec/identity.htm.
IDENTITY_REQUEST_SYSEX = (0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7)

# Copypasta but we want to isolate the test files from the main module.
RED_LED_BASE_CC = 20
GREEN_LED_BASE_CC = 110

# Solid yellow LEDs get set via an older API.
DEPRECATED_LED_BASE_CC = 40
NUM_DEPRECATED_LED_FIELDS = 3
CLEAR_CC = 0

DISPLAY_BASE_CC = 50
DISPLAY_WIDTH = 4

MIDI_CHANNEL = 0

# The number of seconds to wait after the controller responds to a ping before
# considering it responsive. Particularly when booting Live to open a set, there's
# usually a period where the controller reacts slowly after responding to a ping.
RESPONSIVENESS_DELAY = 1.5

# Time after user actions to wait for potential responses from Live, e.g. when
# considering whether the device state is stable.
MIDI_RESPONSE_DELAY = 0.3

# Time between incoming messages before the device state can be considered stable,
# i.e. fully updated by Live. This should be shorter than the framerate of scrolling
# text, i.e. 0.2s.
STABILITY_DELAY = 0.15

# Seconds to wait to trigger a long press.
LONG_PRESS_DELAY = 0.6

# Time between iterations of polling loops.
POLL_INTERVAL = 0.03

# The number of separate messages, which we'll track individually, which need to be sent
# to switch modes.
NUM_STANDALONE_TOGGLE_MESSAGES = len(sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS)
assert len(sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS) == NUM_STANDALONE_TOGGLE_MESSAGES


# Error handling.
def pytest_bdd_step_error(step: Step, feature: Feature, step_func_args: Dict[str, Any]):
    console = Console()
    console.print(
        f"\n[bright_red bold]{feature.rel_filename}:{step.line_number}:[/bright_red bold] [red]{step.name}[/red]"
    )
    device_state: Optional[DeviceState] = step_func_args.get("device_state")
    if device_state is not None:
        device_state.print()


def pytest_bdd_after_step(step: Step, feature: Feature, step_func_args: Dict[str, Any]):
    if is_debug:
        console = Console()
        console.print(
            f"\n[green bold]{feature.rel_filename}:{step.line_number}:[/green bold] {step.keyword} {step.name}"
        )
        device_state: Optional[DeviceState] = step_func_args.get("device_state")
        if device_state is not None:
            device_state.print()


class MessageListener(Protocol):
    # The message or the exception can be present, but not both.
    @overload
    def __call__(self, msg: mido.Message, exc: None) -> Any:
        ...

    @overload
    def __call__(self, msg: None, exc: Exception) -> Any:
        ...

    def __call__(self, msg: Optional[mido.Message], exc: Optional[Exception]) -> Any:
        ...


def guard_message_exceptions(
    fn: Callable[["DeviceState"], Awaitable[T]],
):
    @functools.wraps(fn)
    async def wrapper(*a, **k):
        device_state = a[0]
        assert isinstance(device_state, DeviceState)

        async def raise_exception():
            await device_state.exception_event.wait()

            exc = device_state.exception
            assert exc is not None
            raise exc

        # The type checker thinks we're on an earlier python version, so it doesn't know
        # that TaskGroup exists.
        async with asyncio.TaskGroup() as task_group:  # type: ignore
            # If this throws an exception, it will be raised and the whole group will be
            # destroyed.
            exception_task = task_group.create_task(raise_exception())

            # If this finishes before an exception is raised, we can cancel the
            # exception task to tear down the group.
            result = await task_group.create_task(fn(*a, **k))
            exception_task.cancel()

            return result

    return wrapper


# Emulation of the SoftStep LED/Display state based on incoming MIDI messages.
class DeviceState:
    class UpdateCategory(Enum):
        lights = "lights"
        display = "display"

    def __init__(self) -> None:
        # Indexed by (physical key number - 1), i.e. from the bottom left.
        num_keys = hardware.NUM_ROWS * hardware.NUM_COLS
        self._red_values: List[int] = [0] * num_keys
        self._green_values: List[int] = [0] * num_keys

        # Pending values for setting colors via the older API.
        self._deprecated_led_values: List[Optional[int]] = [
            None
        ] * NUM_DEPRECATED_LED_FIELDS

        # Display initially filled with spaces.
        self._display_values: List[int] = [32] * DISPLAY_WIDTH

        # States of individual toggles for standalone mode. Each one can be true
        # (standalone mode), false (hosted mode), or None if no corresponding message
        # has been received. These messages are expected to be received in succession,
        # so we should never stay in a state with some toggles flipped and some not.
        self._standalone_toggles: List[Optional[bool]] = [
            None
        ] * NUM_STANDALONE_TOGGLE_MESSAGES

        # Backlight on/off, or unset (None).
        self._backlight: Optional[bool] = None

        # Most recent standalone mode program.
        self._standalone_program: Optional[int] = None

        # Trackers for exceptions thrown while receiving messages.
        self._exception_event = asyncio.Event()
        self._exception: Optional[Exception] = None

        self._identity_request_event = asyncio.Event()
        self._ping_event = asyncio.Event()

        # Last update times by category, so we can detect whether the device is being
        # actively updated.
        self._update_times: Dict[DeviceState.UpdateCategory, float] = {}
        for category in DeviceState.UpdateCategory:
            self._update_times[category] = 0.0

        # Additional message handlers.
        self._message_listeners: List[Optional[MessageListener]] = []

    @property
    def exception_event(self):
        return self._exception_event

    @property
    def exception(self):
        return self._exception

    @property
    def red_values(self):
        return self._red_values

    @property
    def green_values(self):
        return self._green_values

    @property
    def display_text(self) -> str:
        return "".join(chr(value) for value in self._display_values)

    # Individual trackers for the various messages that need to be sent to enter/exit
    # standalone mode.
    @property
    def standalone_toggles(self) -> Collection[Optional[bool]]:
        return self._standalone_toggles

    # The most recent program sent while the controller was in standalone mode.
    @property
    def standalone_program(self) -> Optional[int]:
        return self._standalone_program

    @property
    def backlight(self) -> Optional[bool]:
        return self._backlight

    # Returns a remove function.
    def add_message_listener(self, listener: MessageListener) -> Callable[[], None]:
        index = len(self._message_listeners)
        self._message_listeners.append(listener)

        def remove():
            self._message_listeners[index] = None

        return remove

    def receive_message(self, msg: mido.Message):
        """Receive, validate, and process a MIDI message.

        This method imposes strict validation rules, and throws errors in some cases
        that wouldn't cause any hardware issues (e.g. stray program change messages),
        but which indicate something unexpected happening with the control surface.

        After init, this is the only entrypoint for modifying the device state.

        """
        try:
            msg_type, msg_channel = [
                msg.dict().get(field, None) for field in ("type", "channel")
            ]

            # Check whether the message type is generally allowed, based on the current
            # state of the device.
            if len(set(self.standalone_toggles)) == 1:
                # All toggles are the same, we're not in the middle of a transition.
                standalone_status = list(self.standalone_toggles)[0]

                if msg.is_cc():
                    assert (
                        standalone_status is False
                    ), f"CC messages are only expected in hosted mode: {msg}"
                elif msg_type == "program_change":
                    assert (
                        standalone_status is True
                    ), f"Program Change messages are only expected in standalone mode: {msg}"
                elif msg_type == "sysex":
                    # These are allowed.
                    pass
                else:
                    raise RuntimeError(f"Unexpected message type: {msg}")

            else:
                # If the standalone toggles aren't all the same, i.e. if we're in the
                # process of transitioning between standalone and hosted mode, only allow
                # additional standalone toggle messages.
                assert (
                    msg_type == "sysex"
                ), f"Non-sysex messages not allowed while switching between standalone and hosted mode: {msg}"
                assert any(
                    matches_sysex(msg, t)
                    for t in sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS
                    + sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS
                ), f"Invalid sysex message while switching between standalone and hosted mode: {msg}"

            # Now handle the message in the interface.
            if msg.is_cc():
                assert (
                    msg_channel == MIDI_CHANNEL
                ), f"Got CC on unexpected channel: {msg}"

                _, cc, value = msg.bytes()
                is_cc_recognized = False

                # Commit the LED color from the deprecated API. This isn't an exact replica
                # of the real hardware behavior, which has more edge cases and bugs, but
                # we're only using this feature in a controlled way to render solid yellow.
                if cc == CLEAR_CC:
                    is_cc_recognized = True
                    if all(
                        [value is not None for value in self._deprecated_led_values]
                    ):
                        location, color, state = self._deprecated_led_values
                        if color != 2:  # yellow
                            raise RuntimeError("only expected yellow")
                        for values in (self._red_values, self._green_values):
                            assert location is not None
                            assert state is not None
                            values[location] = state
                    self._deprecated_led_values = [None] * len(
                        self._deprecated_led_values
                    )

                # Detect values that update internal arrays.
                for base_cc, values, category in (
                    (
                        DEPRECATED_LED_BASE_CC,
                        self._deprecated_led_values,
                        DeviceState.UpdateCategory.lights,
                    ),
                    (
                        RED_LED_BASE_CC,
                        self._red_values,
                        DeviceState.UpdateCategory.lights,
                    ),
                    (
                        GREEN_LED_BASE_CC,
                        self._green_values,
                        DeviceState.UpdateCategory.lights,
                    ),
                    (
                        DISPLAY_BASE_CC,
                        self._display_values,
                        DeviceState.UpdateCategory.display,
                    ),
                ):
                    if base_cc <= cc < base_cc + len(values):
                        is_cc_recognized = True
                        values[cc - base_cc] = value
                        self._update_times[category] = time.time()

                assert is_cc_recognized, f"Got unrecognized CC message: {msg}"

            elif msg_type == "program_change":
                assert (
                    msg_channel == MIDI_CHANNEL
                ), f"Got Program Change on unexpected channel: {msg}"

                # We already verified that we're in standalone mode above, but sanity
                # check to be sure.
                assert all(t is True for t in self.standalone_toggles)

                program = msg.dict()["program"]
                assert isinstance(program, int)
                self._standalone_program = program

            # Identity request sent by Live during startup (potentially more than once)
            # and when MIDI ports change.
            elif matches_sysex(msg, IDENTITY_REQUEST_SYSEX):
                # Greeting request flag gets set forever once the message has been
                # received.
                if not self._identity_request_event.is_set():
                    self._identity_request_event.set()
            elif matches_sysex(msg, sysex.SYSEX_PING_RESPONSE):
                # Ping response flag gets cleared immediately after notifying any
                # current listeners.
                self._ping_event.set()
                self._ping_event.clear()
            elif matches_sysex(msg, sysex.SYSEX_BACKLIGHT_OFF_REQUEST):
                self._backlight = False
            elif matches_sysex(msg, sysex.SYSEX_BACKLIGHT_ON_REQUEST):
                self._backlight = True
            elif msg_type == "sysex":
                is_standalone_sysex = False
                # Set standalone toggle flags if appropriate.
                for requests, standalone in (
                    (sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS, True),
                    (sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS, False),
                ):
                    for idx, request in enumerate(requests):
                        if matches_sysex(msg, request):
                            is_standalone_sysex = True
                            self._standalone_toggles[idx] = standalone

                assert is_standalone_sysex, f"Sysex message not recognized: {msg}"
            else:
                raise RuntimeError(f"Unrecognized message: {msg}")
        except Exception as exc:
            # Save exception locally and notify anyone who cares...
            self._exception = exc
            self._exception_event.set()

            # ...send exception to listeners...
            for message_listener in self._message_listeners:
                if message_listener:
                    message_listener(None, exc)

            # ...then propagate it up the chain. This should also halt the listener
            # task.
            raise exc

        for message_listener in self._message_listeners:
            if message_listener:
                message_listener(msg, None)

    @guard_message_exceptions
    async def wait_for_identity_request(self):
        await self._identity_request_event.wait()

    @guard_message_exceptions
    async def wait_for_ping_response(self):
        await self._ping_event.wait()

    # Wait until no updates to the given state type(s) have been received for the given
    # duration. Timing is imprecise (but should never give false positives), as this
    # uses polling rather than proper async notifications.
    @guard_message_exceptions
    async def wait_until_stable(
        self,
        categories: Optional[Collection[DeviceState.UpdateCategory]] = None,
        duration: float = STABILITY_DELAY,
    ):
        if categories is None:
            categories = list(DeviceState.UpdateCategory)

        while True:
            current_time = time.time()
            needs_stability_since = current_time - duration
            if all(
                [
                    self._update_times[category] <= needs_stability_since
                    for category in categories
                ]
            ):
                break
            await asyncio.sleep(POLL_INTERVAL)

    def _create_table(self) -> Table:
        led_state_representations = {
            0: ("  ", ""),  # off
            1: ("ON", "reverse"),  # on
            2: ("BL", ""),  # normal blink
            3: ("FB", "underline"),  # fast blink
            # flash omitted as it's not used.
        }

        def led(red: int, green: int) -> Union[str, Text]:
            style = ""
            state = 0
            if red == 0 and green == 0:
                pass
            elif red == 0:
                style = "green"
                state = green
            elif green == 0:
                style = "red"
                state = red
            elif red == green:
                style = "yellow"
                state = red  # either way.
            else:
                raise RuntimeError("mixed LED states not supported")

            text, state_style = led_state_representations[state]
            return Text(text, style=f"{style} {state_style}")

        table = Table(show_header=False, show_lines=True)
        num_key_cols = hardware.NUM_COLS
        for base_offset in (num_key_cols, 0):
            table.add_row(
                *[
                    led(
                        *[
                            values[base_offset + index]
                            for values in (self._red_values, self._green_values)
                        ]
                    )
                    for index in range(num_key_cols)
                ],
                Text(self.display_text) if base_offset > 0 else "",
            )
        return table

    def print(self, console: Optional[Console] = None):
        if console is None:
            console = Console()

        console.print(self._create_table())


# Convert an async step to sync. Adapted from
# https://github.com/pytest-dev/pytest-bdd/issues/223#issuecomment-332084037.
#
# Hack also adapted from pytest_bdd's _get_scenario_decorator to automatically get the
# loop fixture while still injecting other fixtures.
def sync(*args: Callable[..., Awaitable[T]]) -> Callable[..., T]:
    [fn] = args
    func_args = get_args(fn)

    # Tell pytest about the original fixtures.
    @mark.usefixtures(*func_args)
    def synced_fn(request: FixtureRequest, loop: asyncio.AbstractEventLoop):
        fixture_values = [request.getfixturevalue(arg) for arg in func_args]
        return loop.run_until_complete(fn(*fixture_values))

    return synced_fn


def matches_sysex(
    message: mido.Message, sysex_bytes: Union[List[int], Tuple[int, ...]]
):
    message_attrs = message.dict()
    if message_attrs["type"] != "sysex":
        return False
    data = message_attrs["data"]
    # Strip the F0/F7 at the start/end of the byte list.
    return all(x == y for x, y in zip(data, sysex_bytes[1:-1]))


def _cleanup_runnable(runnable: asyncio.Future, loop: asyncio.AbstractEventLoop):
    runnable.cancel()

    # Ensure the task has actually been cancelled to avoid errors on exit, see
    # https://stackoverflow.com/questions/77974525/what-is-the-right-way-to-await-cancelling-an-asyncio-task.
    try:
        loop.run_until_complete(asyncio.gather(runnable))
    except asyncio.CancelledError:
        # We expect the task to be cancelled. Any other errors should be bubbled up.
        pass


@fixture
def loop():
    # Create a top-level event loop to avoid deprecation warnings like
    # https://stackoverflow.com/questions/73361664/asyncio-get-event-loop-deprecationwarning-there-is-no-current-event-loop.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_debug(True)
    return loop


# MIDI I/O controller.
@fixture
def ioport():
    port_name = "modeStep test"
    with mido.open_ioport(port_name, virtual=True) as ioport:  # type: ignore
        yield ioport


# Cheap thrills - relay the test port to the physical device for visual feedback during
# tests, if available.
@fixture
def relay_port() -> Generator[Optional[mido.ports.BaseOutput], Never, None]:
    port_name = "SoftStep Control Surface"
    try:
        with mido.open_output(port_name) as relay_port:  # type: ignore
            yield relay_port
    except Exception:
        yield None  # No problem if we can't get it.


MessageQueue: TypeAlias = "asyncio.Queue[mido.Message]"


# Async queue for MIDI messages received from Live.
@fixture
def message_queue(
    ioport: mido.ports.BaseInput,
    loop: asyncio.AbstractEventLoop,
    relay_port: Optional[mido.ports.BaseOutput],
) -> Generator[MessageQueue, Never, None]:
    # The async queue isn't thread safe, so we need a wrapper.
    threaded_queue: queue.Queue[mido.Message] = queue.Queue()

    def receive_all_messages():
        # Simply iterating over the ioport doesn't exit cleanly when the port is closed.
        while not ioport.closed:
            # Drain all unprocessed messages.
            while True:
                message = ioport.poll()
                if message is None:
                    break
                else:
                    threaded_queue.put(message)

            time.sleep(POLL_INTERVAL)

    # Receive messages on the thread-safe queue in the background.
    receive_all_messages_executor = loop.run_in_executor(None, receive_all_messages)

    # Main async message queue.
    message_queue: MessageQueue = asyncio.Queue()

    # Repeatedly poll the threaded queue and add items to the async queue.
    async def poll_messages():
        while not ioport.closed:
            while not threaded_queue.empty():
                message = threaded_queue.get_nowait()
                assert message is not None
                await message_queue.put(message)
                if relay_port is not None:
                    relay_port.send(message)

            # Yield the async loop execution.
            await asyncio.sleep(POLL_INTERVAL)

    poll_messages_task = loop.create_task(poll_messages())
    yield message_queue

    for runnable in (poll_messages_task, receive_all_messages_executor):
        _cleanup_runnable(runnable, loop)


# After setting up the MIDI message queue, create a device state emulator and start
# parsing incoming MIDI messages.
@fixture
def device_state(
    message_queue: MessageQueue,
    ioport: mido.ports.BaseOutput,
    loop: asyncio.AbstractEventLoop,
) -> Generator[DeviceState, Never, None]:
    device_state = DeviceState()

    async def receive_messages():
        while True:
            message = await message_queue.get()
            device_state.receive_message(message)

            # Respond to all identity requests. Live sometimes (unclear exactly under
            # what circumstances) sends these multiple times during startup/connection
            # events, and we need to respond to all of them to ensure that the control
            # surface doesn't get deactivated.
            #
            # This handler probably belongs elsewhere (e.g. an I/O version of the
            # DeviceState class) but it works here for now.
            if matches_sysex(message, IDENTITY_REQUEST_SYSEX):
                ioport.send(
                    mido.Message(
                        "sysex",
                        # Identity response.
                        data=(
                            (0x7E, 0x7F, 0x06, 0x02)
                            + sysex.MANUFACTURER_ID_BYTES
                            + sysex.DEVICE_FAMILY_BYTES
                        ),
                    )
                )

    receive_messages_task = loop.create_task(receive_messages())
    yield device_state

    _cleanup_runnable(receive_messages_task, loop)


# Wait to receive an identity request from Live, then send a response back.
@fixture
@sync
async def device_identified(
    device_state: DeviceState,
):
    await device_state.wait_for_identity_request()
    return True


# Open a Live set by name. This will reload the control surface, resetting the mode and
# session ring position.
#
# See the Live project in this directory (and the python helper there) for the available
# sets.
def _open_live_set(set_name: str):
    dir = os.path.dirname(os.path.realpath(__file__))
    set_name = os.path.normpath(set_name)
    assert "/" not in set_name  # sanity check
    set_file = os.path.join(dir, "modeStep_tests_project", f"{set_name}.als")
    assert os.path.isfile(set_file)

    # Opens as if it were double clicked in the file browser. Unfortunately setting
    # autoraise doesn't seem to successfully prevent focus.
    webbrowser.open(f"file://{set_file}", autoraise=False)


# Do this in a Background to get a clean control surface at the beginning of each
# scenario.
@given(parsers.parse("the {set_name} set is open"))
def given_set_is_open(set_name):
    _open_live_set(set_name)


# Wait for Live to send initial CC updates after the device has been identified.
@given("the SS2 is initialized")
@sync
async def given_control_surface_is_initialized(
    device_identified: bool,
    device_state: DeviceState,
    loop: asyncio.AbstractEventLoop,
    ioport: mido.ports.BaseOutput,
):
    # Inner function so we can get the message exceptions guard.
    #
    # TODO: This whole setup can probably be reworked with pytest-asyncio.
    @guard_message_exceptions
    async def run(device_state: DeviceState):
        # This was added in python 3.11. The type-checker is set to an earlier version for
        # the main application, but the tests themselves run with a version where this is
        # available.
        async with asyncio.timeout(30):  # type: ignore
            assert device_identified

            # Wait until something gets rendered to the display.
            while not device_state.display_text.strip():
                await asyncio.sleep(POLL_INTERVAL)

            # Wait until the control surface starts responding to inputs (this can take a second
            # or so if Live was just started).
            received_pong = False

            async def send_pings():
                while not received_pong:
                    ioport.send(
                        mido.Message("sysex", data=sysex.SYSEX_PING_REQUEST[1:-1])
                    )
                    await asyncio.sleep(0.3)

            send_pings_task = loop.create_task(send_pings())
            await device_state.wait_for_ping_response()
            received_pong = True

            # Throw any exceptions.
            await send_pings_task

            # Another brief delay to make sure the control surface is responsive (there are intermittent
            # issues if we don't add this).
            await asyncio.sleep(RESPONSIVENESS_DELAY)

    await run(device_state)


def _get_index_for_key(key_number: int):
    return (key_number - 1) % (hardware.NUM_ROWS * hardware.NUM_COLS)


# CC in hosted mode for a physical key number.
def get_cc_for_key(
    key_number: int, direction: hardware.KeyDirection = hardware.KeyDirection.up
) -> int:
    # Index from bottom left.
    index = _get_index_for_key(key_number)
    row = 0 if index >= hardware.NUM_COLS else 1
    col = index % hardware.NUM_COLS
    return hardware.get_cc_for_key(row=row, col=col, direction=direction)


def _cc_message(control: int, value: int):
    return mido.Message("control_change", control=control, value=value)


async def action_hold(cc: int, port: mido.ports.BaseOutput):
    port.send(_cc_message(cc, 1))


async def action_release(cc: int, port: mido.ports.BaseOutput):
    port.send(_cc_message(cc, 0))


async def action_press(cc: int, port: mido.ports.BaseOutput, duration):
    await action_hold(cc, port)
    await asyncio.sleep(duration)
    await action_release(cc, port)


# Generic action runner for statements like "When I press key 0", which all have some
# common setup.
def cc_action(
    cc: int,
    action: str,
    port: mido.ports.BaseOutput,
    loop: asyncio.AbstractEventLoop,
):
    handlers: Dict[str, Callable[[int, mido.ports.BaseOutput], Any]] = {
        "press": partial(action_press, duration=0.05),
        "long-press": partial(action_press, duration=LONG_PRESS_DELAY),
        "hold": action_hold,
        "release": action_release,
    }
    if action not in handlers:
        raise ValueError(f"Unrecognized action: {action}")
    loop.run_until_complete(handlers[action](cc, port))


# Wait for the device LED state to stabilize after pressing a key.
def stabilize_after_cc_action(
    loop: asyncio.AbstractEventLoop,
    device_state: DeviceState,
    duration: float = STABILITY_DELAY,
    initial_duration: float = MIDI_RESPONSE_DELAY,
):
    # Add a pause beforehand, to allow CCs to start coming in.
    loop.run_until_complete(asyncio.sleep(initial_duration))

    # Wait until the device state has stabilized.
    loop.run_until_complete(device_state.wait_until_stable(duration=duration))

    # Add a pause after for good measure.
    loop.run_until_complete(asyncio.sleep(duration))


@when(parsers.parse("I {action} key {key_number:d}"))
def when_key_action(
    key_number: int,
    action: str,
    ioport: mido.ports.BaseOutput,
    loop: asyncio.AbstractEventLoop,
    device_state: DeviceState,
):
    cc = get_cc_for_key(key_number)
    cc_action(cc, action, ioport, loop)
    stabilize_after_cc_action(loop, device_state)


# Take an action and don't wait for the device state to stabilize. Useful for short
# invocations of the "hold" action in particular, to avoid potentially triggering a
# long-press.
@when(parsers.parse("I {action} key {key_number:d} without waiting"))
def when_key_action_without_waiting(
    key_number: int,
    action: str,
    ioport: mido.ports.BaseOutput,
    loop: asyncio.AbstractEventLoop,
):
    cc = get_cc_for_key(key_number)
    cc_action(cc, action, ioport, loop)


@when(parsers.parse("I {action} key {key_number:d} {direction:w}"))
def when_directional_action(
    key_number: int,
    action: str,
    direction: str,
    ioport: mido.ports.BaseOutput,
    loop: asyncio.AbstractEventLoop,
    device_state: DeviceState,
):
    cc = get_cc_for_key(key_number, direction=getattr(hardware.KeyDirection, direction))
    cc_action(cc, action, ioport, loop)
    stabilize_after_cc_action(loop, device_state)


@when(parsers.parse("I {action} nav {direction:w}"))
def when_nav_action(
    action: str,
    direction: str,
    ioport: mido.ports.BaseOutput,
    loop: asyncio.AbstractEventLoop,
    device_state: DeviceState,
):
    cc = hardware.get_cc_for_nav(getattr(hardware.KeyDirection, direction))
    cc_action(cc, action, ioport, loop)
    stabilize_after_cc_action(loop, device_state)


@when(parsers.parse("I wait for the popup to clear"))
@sync
async def when_wait_for_popup():
    await asyncio.sleep(0.8)


@when(parsers.parse("I wait to trigger a long-press"))
@sync
async def when_wait_for_long_press():
    await asyncio.sleep(LONG_PRESS_DELAY)


# Parameters in the parser breaks `@sync` currently.
@when(parsers.parse("I wait for {delay:f}s"))
def when_wait(delay, loop):
    loop.run_until_complete(asyncio.sleep(delay))


def get_color(key_number: int, device_state: DeviceState):
    index = _get_index_for_key(key_number)
    red_state, green_state = [
        values[index] for values in (device_state.red_values, device_state.green_values)
    ]
    if red_state == 0 and green_state == 0:
        return "off"
    else:
        target_state = None
        color = None
        if green_state == 0:
            target_state = red_state
            color = "red"
        elif red_state == 0:
            target_state = green_state
            color = "green"
        else:
            assert red_state == green_state
            target_state = red_state
            color = "yellow"

        prefixes = {
            1: "solid",
            2: "blinking",
            3: "fast-blinking",
        }
        assert color is not None and target_state in prefixes
        return f"{prefixes[target_state]} {color}"


def assert_matches_color(key_number: int, color: str, device_state: DeviceState):
    real_color = get_color(key_number, device_state)
    assert (
        # exact match
        color == real_color
        # allow just providing "solid", "blinking" or "fast-blinking"
        or real_color.startswith(f"{color} ")
    )


@then(parsers.parse("light {key_number:d} should be {color}"))
def should_be_color(key_number: int, color: str, device_state: DeviceState):
    assert_matches_color(key_number, color, device_state)


@then(parsers.parse("lights {start:d}-{end:d} should be {color}"))
def should_be_colors(start: int, end: int, color: str, device_state: DeviceState):
    for i in range(start, end + 1):
        assert_matches_color(i, color, device_state)


@then(parsers.parse('the display should be "{text}"'))
def should_be_text(
    text: str,
    device_state: DeviceState,
):
    assert device_state.display_text.rstrip() == text


@then(parsers.parse("the mode select screen should be active"))
def should_be_mode_select(device_state: DeviceState):
    assert device_state.display_text in (" __ ", "__  ", "_  _", "  __")


@then("the backlight should be on")
def should_be_backlight_on(device_state: DeviceState):
    assert device_state.backlight is True


@then("the backlight should be off")
def should_be_backlight_off(device_state: DeviceState):
    assert device_state.backlight is False


@then("the backlight should be unmanaged")
def should_be_backlight_unmanaged(device_state: DeviceState):
    assert device_state.backlight is None


@then("the SS2 should be in standalone mode")
def should_be_standalone_mode(device_state: DeviceState):
    assert all([t is True for t in device_state.standalone_toggles])


@then("the SS2 should be in hosted mode")
def should_be_hosted_mode(device_state: DeviceState):
    assert all([t is False for t in device_state.standalone_toggles])
