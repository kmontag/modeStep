from contextlib import contextmanager
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Callable, Dict, Optional

from ableton.v2.control_surface import MIDI_INVALID_TYPE
from ableton.v2.control_surface.elements import ButtonElementMixin
from ableton.v3.base import EventObject, task
from ableton.v3.control_surface.elements import ButtonElement, Color
from ableton.v3.control_surface.midi import CC_STATUS

from ..colors import OFF, ColorInterfaceMixin, Skin
from ..live import lazy_attribute, listens, memoize
from .compound import TransitionalProcessedValueElement

logger = getLogger(__name__)


# Whether the color exists in our main skin.
@memoize
def _is_known_color(name: str):
    is_known = False
    try:
        obj = Skin
        for field in name.split("."):
            obj = getattr(obj, field)
        is_known = True
    except Exception:
        pass

    return is_known


# An output-only element controlling one of the SoftStep's LEDs.
class LightElement(ButtonElement, ColorInterfaceMixin):
    __events__ = ("color",)

    # CCs for the older SoftStep color API, which we use for solid
    # yellow.
    DEPRECATED_LOCATION_CC = 40
    DEPRECATED_COLOR_CC = 41
    DEPRECATED_STATE_CC = 42
    DEPRECATED_CLEAR_CC = 0

    # Key is the physical key number - 1.
    def __init__(self, key: int, name: str, silent: bool = False, *a, **k):
        super().__init__(
            *a,
            name=name,
            msg_type=MIDI_INVALID_TYPE,
            identifier=key,
            optimized_send_midi=False,
            **k,
        )

        self._key = key
        self._tasks: task.TaskGroup

        self._red_to_send: Optional[int] = None
        self._green_to_send: Optional[int] = None
        self._disable_delay: bool = False
        self._silent = silent
        self._last_sent_red: Optional[int] = None
        self._last_sent_green: Optional[int] = None

    def _status_byte(self, channel):
        # Return a status byte that will never be received (valid
        # statuses start at 0x80). We don't want any input values on
        # this element; all messages are sent manually.
        return channel

    def _do_send_value(self, value, channel=None):
        # This only gets invoked externally (e.g. during init), we never want to send
        # values directly.
        pass

    @contextmanager
    def disable_delay(self, disable_delay=True):
        old_disable_delay = self._disable_delay
        self._disable_delay = disable_delay
        try:
            yield
        finally:
            self._disable_delay = old_disable_delay

    @property
    def is_delay_disabled(self):
        return self._disable_delay

    def send_color(self, red: int, green: int, color: Color, delay: bool = False):
        if not self._silent:
            if not self._send_color_task.is_killed:
                self._send_color_task.kill()

            self._red_to_send = red
            self._green_to_send = green

            if delay and not self._disable_delay:
                # Clear out both LEDs so that everything starts in sync on the next tick.
                self._do_send_color(0, 0)
                self._send_color_task.restart()
            else:
                self._do_send_color(red, green)

        self.notify_color(color)

    def _do_send_queued_color(self):
        self._do_send_color(self._red_to_send, self._green_to_send)

    def _do_send_color(self, red, green):
        if red != self._last_sent_red or green != self._last_sent_green:
            red_cc = 20 + self._key
            green_cc = 110 + self._key
            for cc, value in ((red_cc, red), (green_cc, green)):
                if value is not None:
                    self._send_cc(cc, value)
        # Store so we can optimize repeated renders.
        self._last_sent_red = red
        self._last_sent_green = green

    def set_light(self, value):
        if isinstance(value, str) and not _is_known_color(value):
            logger.warning(f"Unrecognized skin color: {value}")

        super().set_light(value)

    def clear_send_cache(self):
        self._last_sent_red = self._last_sent_green = None

    @lazy_attribute
    def _send_color_task(self):
        send_color_task = self._tasks.add(
            task.sequence(task.delay(1), task.run(self._do_send_queued_color))
        )
        send_color_task.kill()
        return send_color_task

    def send_deprecated_color(self, value: int, state: int, color: Color):
        if not self._silent:
            self._red_to_send = None
            self._green_to_send = None

            if not self._send_color_task.is_killed:
                self._send_color_task.kill()

            self._send_cc(self.DEPRECATED_LOCATION_CC, self._key)
            self._send_cc(self.DEPRECATED_COLOR_CC, value)
            self._send_cc(self.DEPRECATED_STATE_CC, state)

            # Send a few empty messages between each LED that we set
            # in this way. Otherwise, when multiple LEDs are set to
            # solid yellow in a short time frame, the SoftStep bugs
            # out and lights LEDs at the wrong positions.
            for _ in range(3):
                self._send_cc(self.DEPRECATED_CLEAR_CC, 0)

        self.clear_send_cache()
        self.notify_color(color)

    def _send_cc(self, cc: int, value: int):
        self.send_midi((CC_STATUS, cc, value))

    def __str__(self) -> str:
        return self.name


# A group of light controls which share an LED, and need to be managed as a unit.
# The behavior is:
#
# - when all lights in the group have been turned off via `send_color`, they should all
#   render off.
# - when any light in the group has been set to a non-off color via `send_color`, they
#   should all render with that color. (If more than one light has been turned on,
#   they'll have precedence in the order that they were registered.)
class LightGroup:
    off_color = OFF

    class LightListener(EventObject):
        def __init__(
            self,
            light: LightElement,
            on_color: Callable[[LightElement, Color], Any],
            *a,
            **k,
        ):
            super().__init__(*a, **k)
            self._light = light
            self._on_color = on_color

            assert self.__on_color
            self.__on_color.subject = self._light

        @listens("color")
        def __on_color(self, color):
            self._on_color(self._light, color)

    @dataclass
    class LightState:
        element: LightElement
        # Last color that was set by something other than this light group.
        last_external_color: Optional[Color] = None
        # Last color that was actually drawn.
        last_color: Optional[Color] = None

    def __init__(self):
        # Keys are element names, values are the color that was most recently set externally.
        self._light_colors: Dict[str, LightGroup.LightState] = {}
        self._is_updating_lights = False

    def register(self, light: LightElement):
        LightGroup.LightListener(light, self._on_color)
        if light.name in self._light_colors:
            raise ValueError(f"duplicate light name: {light.name}")

        # Initialize state with a null color.
        self._light_colors[light.name] = LightGroup.LightState(element=light)

    def _on_color(self, light: LightElement, color: Color):
        state = self._light_colors[light.name]

        # Always save the last color that was actually drawn, so we can avoid redrawing
        # unless necessary.
        state.last_color = color

        if not self._is_updating_lights:
            # Only save the "real" color of the light, i.e. don't modify this while
            # we're in the middle of an update.
            state.last_external_color = color
            # logger.info(f"{light.name} set explicitly to {color}")
            target_color = self._get_current_color()

            with self._updating_lights():
                for other_state in list(self._light_colors.values()):
                    # Don't need to re-update elements repeatedly. Since we're in this
                    # method due to an update from `light`, we should be able to assume
                    # that `other_color` is the "real" color of the light at the moment.
                    if other_state.last_color != target_color:
                        # Propagate the current delay disabled status.
                        with other_state.element.disable_delay(light.is_delay_disabled):
                            target_color.draw(other_state.element)

    def _get_current_color(self):
        # This should iterate in the order that lights were registered.
        for state in self._light_colors.values():
            color = state.last_external_color
            if color is not None and color != self.off_color:
                return color
        return self.off_color

    @contextmanager
    def _updating_lights(self):
        old_is_updating_lights = self._is_updating_lights
        self._is_updating_lights = True
        try:
            yield
        finally:
            self._is_updating_lights = old_is_updating_lights


class LightedTransitionalProcessedValueElement(
    TransitionalProcessedValueElement, ButtonElementMixin
):
    def __init__(
        self, control_elements=None, light: Optional[LightElement] = None, *a, **k
    ):
        all_control_elements = [
            *(control_elements or []),
            *([light] if light else []),
        ]
        super().__init__(*a, control_elements=all_control_elements, **k)
        self._light = light

    def on_nested_control_element_value(self, value, control):
        # Every time a value is received for a button, a redraw will
        # be triggered, which is visually annoying if the redraw is a
        # blink and would normally be synchronized to the timer.
        #
        # Instead, temporarily force delayed values to be sent immediately. In practice,
        # this means that LEDs will receive an OFF message followed immediately (rather
        # than at a later synchronized time) by a color value, which doesn't seem to
        # interrupt the timing if the LED is already blinking.
        @contextmanager
        def nop_context():
            yield

        with self._light.disable_delay() if self._light else nop_context():
            super().on_nested_control_element_value(value, control)

    # Implement the button interface, which we also use for other element types.
    def set_light(self, value):
        if self._light is not None:
            self._light.set_light(value)
