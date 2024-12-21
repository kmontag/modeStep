from __future__ import annotations

import asyncio
import functools
import importlib.machinery
import importlib.util
import os
import time
import webbrowser
from contextlib import ExitStack, asynccontextmanager
from enum import Enum
from functools import partial
from threading import Lock
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Collection,
    Concatenate,
    Coroutine,
    Dict,
    Generator,
    List,
    Optional,
    ParamSpec,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

import janus
import mido
from pytest import fixture
from pytest_bdd import given, parsers, then, when
from pytest_bdd.parser import Feature, Step
from rich.console import Console
from rich.table import Table
from rich.text import Text
from typeguard import typechecked
from typing_extensions import Never

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
P = ParamSpec("P")

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

# Exit button in standalone modes.
STANDALONE_EXIT_CC = 80

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
@typechecked
def pytest_bdd_step_error(step: Step, feature: Feature, step_func_args: Dict[str, Any]):
    console = Console()
    console.print(
        f"\n[bright_red bold]{feature.rel_filename}:{step.line_number}:[/bright_red bold] [red]{step.name}[/red]"
    )
    device_state: Optional[DeviceState] = step_func_args.get("device_state")
    if device_state is not None:
        device_state.print()


@typechecked
def pytest_bdd_after_step(step: Step, feature: Feature, step_func_args: Dict[str, Any]):
    if is_debug:
        console = Console()
        console.print(
            f"\n[green bold]{feature.rel_filename}:{step.line_number}:[/green bold] {step.keyword} {step.name}"
        )
        device_state: Optional[DeviceState] = step_func_args.get("device_state")
        if device_state is not None:
            device_state.print()


# Read-only view of the SoftStep LED/Display state based on incoming MIDI messages.
class DeviceState:
    class UpdateCategory(Enum):
        lights = "lights"
        display = "display"
        backlight = "backlight"
        mode = "mode"
        program = "program"

    def __init__(self) -> None:
        # Directly-set set LED values, indexed by ((physical key number - 1) % 10),
        # i.e. from the bottom left.
        self._red_values: List[Optional[int]]
        self._green_values: List[Optional[int]]

        # Pending values for setting colors via the older API.
        self._deprecated_led_values: List[Optional[int]]

        # Display characters.
        self._display_values: List[Optional[int]]

        # States of individual toggles for standalone mode. Each one can be true
        # (standalone mode), false (hosted mode), or None if no corresponding message
        # has been received. These messages are expected to be received in succession,
        # so we should never stay in a state with some toggles flipped and some not.
        self._standalone_toggles: List[Optional[bool]]

        # Backlight on/off, or unset (None).
        self._backlight: Optional[bool]

        # Most recent standalone mode program.
        self._standalone_program: Optional[int]

        # Initialize all state values.
        self.reset()

        # Tracker for validation error suppression prior to device init.
        self.__allow_ccs_until_managed: bool = False

    # Reset all properties to unknown/unmanaged.
    def reset(self) -> None:
        self._reset_leds_and_display()

        self._standalone_toggles = [None] * NUM_STANDALONE_TOGGLE_MESSAGES

        self._backlight = None

        # Most recent standalone mode program.
        self._standalone_program = None

    # Reset just the LEDs and display to unknown/unmanaged. This is used when switching
    # to standalone mode, where these values can change based on user actions
    # (i.e. independently of CC messages being sent to the device).
    def _reset_leds_and_display(self) -> None:
        num_keys = hardware.NUM_ROWS * hardware.NUM_COLS

        self._red_values = [None] * num_keys
        self._green_values = [None] * num_keys
        self._deprecated_led_values = [None] * NUM_DEPRECATED_LED_FIELDS

        self._display_values = [None] * DISPLAY_WIDTH

    @property
    def red_values(self) -> Sequence[Optional[int]]:
        return self._red_values

    @property
    def green_values(self) -> Sequence[Optional[int]]:
        return self._green_values

    @property
    def display_text(self) -> Optional[str]:
        assert len(self._display_values) == DISPLAY_WIDTH
        result = ""
        for value in self._display_values:
            # If any character values are unknown, treat the whole display content as
            # unknown.
            if value is None:
                return None
            result += chr(value)
        return result

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

    def receive_message(self, message: mido.Message) -> "DeviceState.UpdateCategory":
        """Validate and process an incoming MIDI message.

        This method imposes strict validation rules, and throws errors in some cases
        that wouldn't cause any hardware issues (e.g. stray program change messages),
        but which indicate something unexpected happening with the control surface.

        """
        msg_type, msg_channel = [
            message.dict().get(field, None) for field in ("type", "channel")
        ]

        # Check whether the message type is generally allowed, based on the current
        # state of the device.
        if len(set(self.standalone_toggles)) == 1:
            # All toggles are the same, we're not in the middle of a transition.
            standalone_status = list(self.standalone_toggles)[0]

            if message.is_cc():
                assert standalone_status is False or (
                    # Check whether we're suppressing these errors during init.
                    #
                    # Note that it should only be possible for this to be `True` when
                    # the standalone status is `None`.
                    self.__allow_ccs_until_managed
                ), f"CC messages are only expected in hosted mode: {message}"
            elif msg_type == "program_change":
                assert (
                    standalone_status is True
                ), f"Program Change messages are only expected in standalone mode: {message}"
            elif msg_type == "sysex":
                # These are allowed.
                pass
            else:
                raise RuntimeError(f"Unexpected message type: {message}")

        else:
            # If the standalone toggles aren't all the same, i.e. if we're in the
            # process of transitioning between standalone and hosted mode, only allow
            # additional standalone toggle messages.
            assert (
                msg_type == "sysex"
            ), f"Non-sysex messages not allowed while switching between standalone and hosted mode: {message}"
            assert any(
                matches_sysex(message, t)
                for t in sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS
                + sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS
            ), f"Invalid sysex message while switching between standalone and hosted mode: {message}"

        # Now handle the message in the interface.
        if message.is_cc():
            assert (
                msg_channel == MIDI_CHANNEL
            ), f"Got CC on unexpected channel: {message}"

            _, cc, value = message.bytes()

            # A few of these get sent immediately after activating LEDs via the
            # deprecated color API, which (evidently) causes the hardware to flush
            # updates and avoids issues when configuring additional LEDs via this API.
            #
            # When we receive one of these messages, commit the LED color from the
            # deprecated API. This isn't an exact replica of the real hardware behavior,
            # which has more edge cases and bugs, but we're only using this feature in a
            # controlled way to render solid yellow.
            if cc == CLEAR_CC:
                if all([value is not None for value in self._deprecated_led_values]):
                    location, color, state = self._deprecated_led_values
                    if color != 2:  # yellow
                        raise RuntimeError("only expected yellow")
                    for values in (self._red_values, self._green_values):
                        assert location is not None
                        assert state is not None
                        values[location] = state
                self._deprecated_led_values = [None] * len(self._deprecated_led_values)
                return DeviceState.UpdateCategory.lights
            else:
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
                        values[cc - base_cc] = value

                        return category

        # Handle program changes, verify that we're in standalone mode.
        elif msg_type == "program_change":
            assert (
                msg_channel == MIDI_CHANNEL
            ), f"Got Program Change on unexpected channel: {message}"

            # We already verified that we're in standalone mode above, but sanity
            # check to be sure.
            assert all(t is True for t in self.standalone_toggles)

            program = message.dict()["program"]
            assert isinstance(program, int)
            self._standalone_program = program
            return DeviceState.UpdateCategory.program

        # Handle backlight toggle messages.
        elif matches_sysex(message, sysex.SYSEX_BACKLIGHT_OFF_REQUEST):
            self._backlight = False
            return DeviceState.UpdateCategory.backlight
        elif matches_sysex(message, sysex.SYSEX_BACKLIGHT_ON_REQUEST):
            self._backlight = True
            return DeviceState.UpdateCategory.backlight

        # The only other allowed messages are the sysexes to toggle between
        # standalone/hosted mode.
        elif msg_type == "sysex":
            # Set standalone toggle flags if appropriate.
            for requests, standalone in (
                (sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS, True),
                (sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS, False),
            ):
                for idx, request in enumerate(requests):
                    if matches_sysex(message, request):
                        self._standalone_toggles[idx] = standalone

                        # Clear the CC validation error suppression if the device mode
                        # is now fully managed.
                        if all(t is not None for t in self._standalone_toggles):
                            self.__allow_ccs_until_managed = False

                        # If we just switched to standalone mode, the LEDs and display
                        # are no longer under our control.
                        if all(t is True for t in self._standalone_toggles):
                            self._reset_leds_and_display()

                        return DeviceState.UpdateCategory.mode

        # If we haven't returned by this point, the message is unrecognized.
        raise ValueError(f"Unrecognized message: {message}")

    # Don't error on incoming CCs as long as the standalone/hosted mode status is
    # unmanaged. Restore the default validation behavior once the status has been set
    # explicitly. If the standalone/hosted mode status is already set explicitly, this
    # is a no-op.
    #
    # This can be used to avoid validation errors when the device is quickly
    # disconnected and reconnected. In such cases, Live seems to send some interface
    # updates prior to `port_settings_changed` being fired, i.e. before it realizes that
    # the device needs to be re-identified.
    #
    # Stray CCs at this stage should be harmless (as the device will be fully
    # reinitialized once `port_settings_changed` eventually fires). At worst they could
    # interfere with transient LED states of the initial standalone mode when the device
    # boots up.
    def allow_ccs_until_managed(self):
        # Only set the variable if the state is at least partially unmanaged.
        if any(t is None for t in self._standalone_toggles):
            self.__allow_ccs_until_managed = True

    # Generate a console-printable representation of the LED states and display text.
    def _create_table(self) -> Table:
        led_state_representations = {
            None: ("??", ""),  # unknown/unmanaged
            0: ("  ", ""),  # off
            1: ("ON", "reverse"),  # on
            2: ("BL", ""),  # normal blink
            3: ("FB", "underline"),  # fast blink
            # flash omitted as it's not used.
        }

        def led(red: Optional[int], green: Optional[int]) -> Union[str, Text]:
            style = ""
            state: Optional[int] = 0

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
            else:  # red and green differ but are both nonzero.
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
                (
                    Text(
                        "?" * DISPLAY_WIDTH
                        if self.display_text is None
                        else self.display_text
                    )
                    # Render the display text on the top row.
                    if base_offset > 0
                    else ""
                ),
            )
        return table

    def print(self, console: Optional[Console] = None):
        if console is None:
            console = Console()

        console.print(self._create_table())


# Decorator for async Device instance methods, which causes any errors during parallel
# message handling to be thrown immediately.
def guard_message_exceptions(
    fn: Callable[Concatenate["Device", P], Coroutine[Any, Any, T]],
) -> Callable[Concatenate["Device", P], Awaitable[T]]:
    @functools.wraps(fn)
    async def wrapper(*a, **k):
        device = a[0]
        assert isinstance(device, Device)

        async def raise_exception():
            await device._exception_event.wait()

            exc = device._exception
            assert exc is not None
            raise exc

        async with asyncio.TaskGroup() as task_group:
            # If this throws an exception, it will be raised and the whole group will be
            # destroyed.
            exception_task = task_group.create_task(raise_exception())

            # If this finishes before an exception is raised, we can cancel the
            # exception task to tear down the group.
            result = await task_group.create_task(fn(*a, **k))
            exception_task.cancel()

            return result

    return wrapper


# Device emulation with disconnect/reconnect functionality.
#
# This should be used within an async `with` statement to ensure that the message
# handler is properly started and cleaned up, and all interaction should occur within
# the same async loop.
class Device:
    def __init__(
        self,
        # If provided, forward all incoming MIDI messages to these ports. Used for
        # visual feedback on the connected hardware, if any.
        relay_ports: Collection[mido.ports.BaseOutput] = [],
    ):
        self._ioport: Optional[mido.ports.BaseIOPort] = None
        self._device_state: DeviceState = DeviceState()

        self._relay_ports = relay_ports

        # Message queues into which incoming messages should be placed. This includes
        # the main queue used by `_process_messages` to handle internal updates and
        # functionality, plus any active `incoming_messages` queues.
        #
        # `None` will be pushed when the device is torn down, i.e. no more messages can
        # be received.
        self.__queues: Dict[int, janus.Queue[mido.Message]] = {}
        self.__queues_lock = Lock()

        # Background task for processing incoming messages.
        self.__process_messages_task: Optional[asyncio.Task] = None

        # Trackers for exceptions thrown while processing incoming messages.
        self._exception_event = asyncio.Event()
        self._exception: Optional[Exception] = None

        # Trackers for messages that aren't part of the main device state.
        self.__identity_request_event = asyncio.Event()
        self.__ping_event = asyncio.Event()

        # Last update times by category, so we can detect whether the device is being
        # actively updated.
        self.__update_times: Dict[DeviceState.UpdateCategory, float] = {}
        for category in DeviceState.UpdateCategory:
            self.__update_times[category] = 0.0

    @asynccontextmanager
    async def incoming_messages(
        self,
    ) -> AsyncGenerator[janus.AsyncQueue[mido.Message], Never]:
        queue: janus.Queue[mido.Message] = janus.Queue()
        queue_id: int
        with self.__queues_lock:
            # Get a unique ID for this queue.
            queue_id = max([0, *self.__queues.keys()]) + 1

            # Store the queue so that it will be populated by the incoming message
            # handler.
            self.__queues[queue_id] = queue

        try:
            yield queue.async_q
        finally:
            # Remove the queue from future message handling.
            with self.__queues_lock:
                del self.__queues[queue_id]

            # Clean up background tasks.
            await queue.aclose()

    @property
    def device_state(self) -> DeviceState:
        return self._device_state

    @property
    def is_connected(self) -> bool:
        return self._ioport is not None

    def connect(self):
        if self._ioport is not None:
            raise RuntimeError("Emulated device is already connected")

        port_name = "modeStep test"
        self._ioport = mido.open_ioport(  # type: ignore
            port_name, virtual=True, callback=self.__on_message
        )

    def disconnect(self):
        if self._ioport is None:
            raise RuntimeError("Emulated device is not connected")

        self._ioport.close()
        self._ioport = None

        self.reset()

    # Reset all state to unmanaged, and forget whether an identity request has been
    # received. This allows waiting for the device to be re-initialized (for example
    # when opening a new set), even if it hasn't been disconnected.
    def reset(self):
        self.device_state.reset()
        self.__identity_request_event.clear()

    def send(self, message: mido.Message):
        if self._ioport is None:
            raise RuntimeError("Emulated device is not connected")
        self._ioport.send(message)

    # Root-level MIDI message handler, invoked by mido in a separate thread.
    def __on_message(self, message: mido.Message):
        with self.__queues_lock:
            for queue in self.__queues.values():
                # Thread-safe synchronous queue view. The main thread will receive these
                # via the async view.
                queue.sync_q.put(message)

    # Process all incoming messages (including across disconnects/reconnects), and send
    # responses (e.g. to identity requests) as necessary. This is intended to run as a
    # background task as long as the device is active.
    async def _process_messages(self):
        async with self.incoming_messages() as queue:
            while True:
                message = await queue.get()

                # Exit once the device is cleaned up.
                if message is None:
                    break

                try:
                    self._process_message(message)
                except Exception as exc:
                    # Store the exception and notify anyone listening. This causes
                    # methods decorated with `guard_message_actions` to exit
                    # immediately.
                    self._exception = exc
                    self._exception_event.set()

                    # Propagate up the chain.
                    raise exc

    # Process a single message internally:
    #
    # - update the device state
    # - respond to identity requests
    # - notify about ping responses
    def _process_message(self, message: mido.Message):
        # Forward to any relays for hardware visual feedback.
        for relay_port in self._relay_ports:
            relay_port.send(message)

        # Identity request sent by Live during startup (potentially more than once)
        # and when MIDI ports change.
        if matches_sysex(message, IDENTITY_REQUEST_SYSEX):
            # Send a response immediately.

            # Greeting request flag gets set forever (until a disconnect) once the
            # message has been received.
            if not self.__identity_request_event.is_set():
                self.__identity_request_event.set()

            self.send(
                mido.Message(
                    "sysex",
                    data=(
                        (0x7E, 0x7F, 0x06, 0x02)
                        + sysex.MANUFACTURER_ID_BYTES
                        + sysex.DEVICE_FAMILY_BYTES
                    ),
                )
            )

        # Response to a ping request. This validates that we're actually connected with
        # modeStep, and not a different control surface.
        elif matches_sysex(message, sysex.SYSEX_PING_RESPONSE):
            # Ping response flag gets cleared immediately after notifying any
            # current listeners.
            self.__ping_event.set()
            self.__ping_event.clear()

        # Any other messages are expected to be device state updates. This will throw an
        # error if the message is unrecognized or unexpected in the current state.
        else:
            update_category: DeviceState.UpdateCategory = (
                self._device_state.receive_message(message)
            )
            self.__update_times[update_category] = time.time()

    @guard_message_exceptions
    async def wait_for_identity_request(self):
        await self.__identity_request_event.wait()

    @guard_message_exceptions
    async def wait_for_ping_response(self):
        await self.__ping_event.wait()

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
                    self.__update_times[category] <= needs_stability_since
                    for category in categories
                ]
            ):
                break
            await asyncio.sleep(POLL_INTERVAL)

    @guard_message_exceptions
    async def wait_for_initialization(
        self, require_display: bool, timeout: float = 30.0
    ):
        async with asyncio.timeout(timeout):
            # Wait until the device is explicitly placed into standalone or hosted mode.
            while any(t is None for t in self.device_state.standalone_toggles):
                await asyncio.sleep(POLL_INTERVAL)

            if require_display:
                # Wait until something gets rendered to the display.
                while not (self.device_state.display_text or "").strip():
                    await asyncio.sleep(POLL_INTERVAL)

            # Wait until the control surface starts responding to inputs (this can take a second
            # or so if Live was just started).
            received_pong = False

            async def send_pings():
                while not received_pong:
                    self.send(
                        mido.Message("sysex", data=sysex.SYSEX_PING_REQUEST[1:-1])
                    )
                    await asyncio.sleep(0.3)

            send_pings_task = asyncio.create_task(send_pings())
            await self.wait_for_ping_response()
            received_pong = True

            # Throw any exceptions.
            await send_pings_task

            # Another brief delay to make sure the control surface is responsive (there are intermittent
            # issues if we don't add this).
            await asyncio.sleep(RESPONSIVENESS_DELAY)

    # Use this object within an asyn `with` context to run the message processor in the
    # background.
    async def __aenter__(self) -> Device:
        if self.__process_messages_task is not None:
            raise RuntimeError("Message processing task is already running")
        self.__process_messages_task = asyncio.create_task(self._process_messages())
        return self

    async def __aexit__(self, *args):
        if self.is_connected:
            self.disconnect()

        if self.__process_messages_task is None:
            raise RuntimeError("Message processing task is not running")
        self.__process_messages_task.cancel()

        # Ensure the task has actually been cancelled to avoid errors on exit, see
        # https://stackoverflow.com/questions/77974525/what-is-the-right-way-to-await-cancelling-an-asyncio-task.
        try:
            await self.__process_messages_task
        except asyncio.CancelledError:
            # We expect the task to be cancelled. Any other errors should be bubbled up.
            pass
        self.__process_messages_task = None

        # If we reached this point, we expect that the processing task finished
        # successfully, i.e. no exceptions were thrown.
        assert not self._exception_event.is_set()


# Convert an async step to sync. Adapted from
# https://github.com/pytest-dev/pytest-bdd/issues/223#issuecomment-1646969954.
#
# This only needs to be used with test steps (given, when, etc.). Async fixtures are
# handled automatically by pytest-asyncio.
def sync(fn: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, T]:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> T:
        return asyncio.get_event_loop().run_until_complete(fn(*args, **kwargs))

    return wrapper


def matches_sysex(
    message: mido.Message, sysex_bytes: Union[List[int], Tuple[int, ...]]
):
    message_attrs = message.dict()
    if message_attrs["type"] != "sysex":
        return False
    data = message_attrs["data"]
    # Strip the F0/F7 at the start/end of the byte list.
    return all(x == y for x, y in zip(data, sysex_bytes[1:-1], strict=True))


# Cheap thrills - relay the test port to the physical device for visual feedback during
# tests, if available.
@fixture
@typechecked
def relay_port() -> Generator[Optional[mido.ports.BaseOutput], None, None]:
    port_name = "SoftStep Control Surface"
    with ExitStack() as stack:
        relay_port: Optional[mido.ports.BaseOutput] = None
        try:
            relay_port = stack.enter_context(mido.open_output(port_name))  # type: ignore
        except Exception:
            pass  # No problem if we can't get it.
        yield relay_port


@fixture
@typechecked
async def device(
    relay_port: mido.ports.BaseOutput,
) -> AsyncGenerator[Device, None]:
    async with Device(relay_ports=[relay_port]) as device:
        yield device


# After setting up the MIDI message queue, create a device state emulator and start
# parsing incoming MIDI messages.
@fixture
@typechecked
def device_state(
    device: Device,
) -> DeviceState:
    return device.device_state


# Wait to receive an identity request from Live, then send a response back.
@fixture
@typechecked
async def device_identified(
    device: Device,
) -> bool:
    await device.wait_for_identity_request()
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


async def action_hold(cc: int, device: Device):
    device.send(_cc_message(cc, 1))


async def action_release(cc: int, device: Device):
    device.send(_cc_message(cc, 0))


async def action_press(cc: int, device: Device, duration: float):
    await action_hold(cc, device)
    await asyncio.sleep(duration)
    await action_release(cc, device)


# Generic action runner for statements like "When I press key 0", which all have some
# common setup.
async def cc_action(
    cc: int,
    action: str,
    device: Device,
):
    handlers: Dict[str, Callable[[int, Device], Awaitable[Any]]] = {
        "press": partial(action_press, duration=0.05),
        "long-press": partial(action_press, duration=LONG_PRESS_DELAY),
        "hold": action_hold,
        "release": action_release,
    }
    if action not in handlers:
        raise ValueError(f"Unrecognized action: {action}")

    await handlers[action](cc, device)


# Wait for the device LED state to stabilize after pressing a key.
async def stabilize_after_cc_action(
    device: Device,
    duration: float = STABILITY_DELAY,
    initial_duration: float = MIDI_RESPONSE_DELAY,
):
    # Add a pause beforehand, to allow CCs to start coming in.
    await asyncio.sleep(initial_duration)

    # Wait until the device state has stabilized.
    await device.wait_until_stable(duration=duration)

    # Add a pause after for good measure.
    await asyncio.sleep(duration)


@given(parsers.parse("the SS2 is connected"))
@when(parsers.parse("I connect the SS2"))
@typechecked
def given_device_is_connected(device: Device):
    device.connect()


@given(parsers.parse("the {set_name} set is open"))
@when(parsers.parse("I open the {set_name} set"))
@typechecked
def given_set_is_open(set_name: str):
    _open_live_set(set_name)


# Wait for Live to send initial CC updates after the device has been identified.
@given("the SS2 is initialized")
@when("I wait for the SS2 to be initialized")
@sync
@typechecked
async def given_device_is_initialized(
    device_identified: bool,
    device: Device,
):
    assert device_identified
    await device.wait_for_initialization(require_display=True)


@given("the SS2 is initialized in standalone mode")
@when("I wait for the SS2 to be initialized in standalone mode")
@sync
@typechecked
async def given_device_is_initialized_in_standalone_mode(
    device_identified: bool,
    device: Device,
):
    assert device_identified
    await device.wait_for_initialization(require_display=False)


# No-op step. This allows for optional steps when using multiple `Examples`, e.g. by
# templatizing the step text.
@when(parsers.parse("I do nothing"))
@typechecked
def when_noop():
    pass


@when(parsers.parse("I disconnect the SS2"))
@typechecked
def when_disconnect(device: Device):
    device.disconnect()


@when(parsers.parse("I forget the SS2's state"))
@typechecked
def when_forget_state(device: Device):
    device.reset()


@when(parsers.parse("I allow stray interface updates until initialization"))
@typechecked
def when_allow_ccs_until_managed(device_state: DeviceState):
    device_state.allow_ccs_until_managed()


@when(parsers.parse("I {action} key {key_number:d}"))
@sync
@typechecked
async def when_key_action(
    key_number: int,
    action: str,
    device: Device,
):
    cc = get_cc_for_key(key_number)
    await cc_action(cc, action, device)
    await stabilize_after_cc_action(device)


# Take an action and don't wait for the device state to stabilize. Useful for short
# invocations of the "hold" action in particular, to avoid potentially triggering a
# long-press.
@when(parsers.parse("I {action} key {key_number:d} without waiting"))
@sync
@typechecked
async def when_key_action_without_waiting(
    key_number: int,
    action: str,
    device: Device,
):
    cc = get_cc_for_key(key_number)
    await cc_action(cc, action, device)


@when(parsers.parse("I {action} the standalone exit button"))
@sync
@typechecked
async def when_standalone_exit_action(
    action: str,
    device: Device,
):
    await cc_action(STANDALONE_EXIT_CC, action, device)
    await stabilize_after_cc_action(device)


@when(parsers.parse("I {action} the standalone exit button without waiting"))
@sync
@typechecked
async def when_standalone_exit_action_without_waiting(
    action: str,
    device: Device,
):
    await cc_action(STANDALONE_EXIT_CC, action, device)


@when(parsers.parse("I {action} key {key_number:d} {direction:w}"))
@sync
@typechecked
async def when_directional_action(
    key_number: int,
    action: str,
    direction: str,
    device: Device,
):
    cc = get_cc_for_key(key_number, direction=getattr(hardware.KeyDirection, direction))
    await cc_action(cc, action, device)
    await stabilize_after_cc_action(device)


@when(parsers.parse("I {action} nav {direction:w}"))
@sync
@typechecked
async def when_nav_action(
    action: str,
    direction: str,
    device: Device,
):
    cc = hardware.get_cc_for_nav(getattr(hardware.KeyDirection, direction))
    await cc_action(cc, action, device)
    await stabilize_after_cc_action(device)


@when(parsers.parse("I wait for the popup to clear"))
@sync
@typechecked
async def when_wait_for_popup():
    await asyncio.sleep(0.8)


@when(parsers.parse("I wait to trigger a long-press"))
@sync
@typechecked
async def when_wait_for_long_press():
    await asyncio.sleep(LONG_PRESS_DELAY)


# Parameters in the parser breaks `@sync` currently.
@when(parsers.parse("I wait for {delay:f}s"))
@sync
@typechecked
async def when_wait(delay: float):
    await asyncio.sleep(delay)


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
@typechecked
def should_be_color(key_number: int, color: str, device_state: DeviceState):
    assert_matches_color(key_number, color, device_state)


@then(parsers.parse("lights {start:d}-{end:d} should be {color}"))
@typechecked
def should_be_colors(start: int, end: int, color: str, device_state: DeviceState):
    for i in range(start, end + 1):
        assert_matches_color(i, color, device_state)


@then(parsers.parse('the display should be "{text}"'))
@typechecked
def should_be_text(
    text: str,
    device_state: DeviceState,
):
    assert device_state.display_text is not None, "Display text not yet set"
    assert (
        device_state.display_text.strip() == text
    ), f'Expected display text to be "{text}", but was "{device_state.display_text.strip()}"'


@then(parsers.parse('the display should be scrolling "{text}"'))
@typechecked
def should_be_scrolling_text(text: str, device_state: DeviceState):
    assert device_state.display_text is not None
    assert device_state.display_text in text


@then(parsers.parse("the mode select screen should be active"))
@typechecked
def should_be_mode_select(device_state: DeviceState):
    assert device_state.display_text in (" __ ", "__  ", "_  _", "  __")


@then("the backlight should be on")
@typechecked
def should_be_backlight_on(device_state: DeviceState):
    assert device_state.backlight is True


@then("the backlight should be off")
@typechecked
def should_be_backlight_off(device_state: DeviceState):
    assert device_state.backlight is False


@then("the backlight should be unmanaged")
@typechecked
def should_be_backlight_unmanaged(device_state: DeviceState):
    assert device_state.backlight is None


@then("the SS2 should be in standalone mode")
@typechecked
def should_be_standalone_mode(device_state: DeviceState):
    assert all([t is True for t in device_state.standalone_toggles])


@then("the SS2 should be in hosted mode")
@typechecked
def should_be_hosted_mode(device_state: DeviceState):
    assert all([t is False for t in device_state.standalone_toggles])


@then(parsers.parse("standalone program {standalone_program:d} should be active"))
@typechecked
def should_be_standalone_program(standalone_program: int, device_state: DeviceState):
    assert device_state.standalone_program == standalone_program
