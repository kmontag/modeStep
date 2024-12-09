import Live
from collections import deque
from logging import getLogger
from time import time
from typing import Callable, Optional, Union

from ableton.v2.base import linear
from ableton.v2.control_surface.defaults import TIMER_DELAY
from ableton.v3.base import clamp, nop, task
from ableton.v3.control_surface import InputControlElement
from ableton.v3.control_surface.display import Renderable

from ..live import lazy_attribute, listens
from ..xy import get_xy_value
from .light import LightedTransitionalProcessedValueElement

logger = getLogger(__name__)


class ProcessedSliderElement(LightedTransitionalProcessedValueElement, Renderable):
    """Impelements an interface similar to the built-in encoder/slider
    elements. Elements of this type can be used with
    `MappedSensitivitySettingControl`s and similar.

    """

    __events__ = ("normalized_value",)

    def __init__(
        self,
        *a,
        enable_popups: bool = True,
        **k,
    ):
        super().__init__(*a, **k)
        self._last_normalized_value = None
        self._connected_parameter = None
        self._enable_popups = enable_popups

    @property
    def enable_popups(self) -> bool:
        return self._enable_popups

    @enable_popups.setter
    def enable_popups(self, enable_popups: bool):
        self._enable_popups = enable_popups

    # Mirror the encoder interface, where both a raw and a normalized
    # value are triggered.
    def notify_value(self, value):
        super().notify_value(value)
        if self.normalized_value_listener_count():
            self.notify_normalized_value(self.normalize_value(value))

    def normalize_value(self, value):
        return value

    def connect_to(self, parameter):
        self._connected_parameter = parameter

        # Force a grab of the nested elements by adding a no-op value
        # listener. This ultimately causes
        # `_on_value` to be called on input
        # events.
        if parameter is not None:
            self.add_value_listener(nop)

        # As values come in, send the normalized versions directly to
        # the mapped parameter. This replaces the direct MIDI mappings
        # that normally get used for encoder-like controls.
        assert self.__on_normalized_value  # For the type checker.
        self.__on_normalized_value.subject = self

    def release_parameter(self):
        # We need to check for `None` here. Otherwise, the internal
        # tracker `self._listen_nested_requests` somehow gets
        # decremented below zero when moving between a non-existent
        # parameter and a real one, which causes
        # `_connect_nested_control_elements` not to fire in the the
        # next time a parameter is connected. This would cause issues
        # with, for example, volume sliders not being successfully
        # connected when new tracks are added.
        if self._connected_parameter is not None:
            self.remove_value_listener(nop)
        assert self.__on_normalized_value  # For the type checker.
        self.__on_normalized_value.subject = None
        self._connected_parameter = None

    def message_map_mode(self):
        # Could override if it's ever necessary, but for now all controls are absolute.
        return Live.MidiMap.MapMode.absolute

    @listens("normalized_value")
    def __on_normalized_value(self, value, **_k):
        self._on_normalized_value(value)

    def _on_normalized_value(self, value):
        self._last_normalized_value = value
        if self._connected_parameter is not None:
            clamped_value = clamp(value, 0, 127)
            self._connected_parameter.value = linear(
                self._connected_parameter.min,
                self._connected_parameter.max,
                clamped_value / 127,
            )

    def _commit_value(self, value):
        super()._commit_value(value)
        self._update_popup()

    def _update_popup(self):
        if self._connected_parameter is not None and self._enable_popups:
            self.notify(self.notifications.Slider.value, str(self._connected_parameter))


class LatchableSliderElement(ProcessedSliderElement):

    """Generic slider control for immitating SoftStep's "live" sources, e.g. pressure or
    XY position. Latching can optionally be enabled.
    """

    def __init__(
        self,
        min_input: int = 0,
        max_input: int = 127,
        min_output: int = 0,
        max_output: int = 127,
        latch_delay: float = 0.0,
        latch_zero: float = 0.0,
        *a,
        **k,
    ):
        super().__init__(*a, **k)

        self._min_input = min_input
        self._max_input = max_input

        self._min_output = min_output
        self._max_output = max_output

        self._latch_delay = latch_delay
        self._latch_event_queue = deque(maxlen=20)
        self._latch_zero = latch_zero
        self._is_latched = False

        self._tasks: task.TaskGroup

    @lazy_attribute
    def _drain_latch_event_queue_task(self):
        t = self._tasks.add(
            task.loop(
                task.wait(self._latch_delay),
                task.run(self._drain_latch_event_queue),
            )
        )
        t.kill()
        return t

    def _net_value(self) -> float:
        raise NotImplementedError

    # Interpolate/clamp raw physical values from the input range to the output range.
    def normalize_value(self, value):
        position = (value - self._min_input) / (self._max_input - self._min_input)
        interpolated_value = linear(self._min_output, self._max_output, position)
        return clamp(interpolated_value, self._min_output, self._max_output)

    def _on_value(self, value, control):  # noqa: ARG002
        net_value = self._net_value()
        if self._latch_delay > 0:
            if int(net_value) is int(self._latch_zero):
                self._drain_latch_event_queue()
                self._latch_event_queue.clear()
                if not self._drain_latch_event_queue_task.is_killed:
                    self._drain_latch_event_queue_task.kill()
                self._is_latched = True
            else:
                self._queue_latch_event(net_value)
                self._drain_latch_event_queue()
                self._is_latched = False
                if self._drain_latch_event_queue_task.is_killed:
                    self._drain_latch_event_queue_task.resume()

        else:
            self._commit_value(net_value)

    def _queue_latch_event(self, value: float):
        self._latch_event_queue.append((time(), value))

    def _drain_latch_event_queue(self):
        # Commit any events for which the latch delay has expired,
        # or which are increasing in distance from
        # `_latch_zero`. This gets called every time a message is
        # received, and also on a timer if the element is sending
        # non-zero values.
        cutoff_timestamp = time() - self._latch_delay

        while (len(self._latch_event_queue) > 0) and (
            self._latch_event_queue[0][0] < cutoff_timestamp
            or
            # This should be caught by the conditions below, but as a
            # sanity check, make sure that we're sending the first
            # value after a latch event.
            self._is_latched
            or self._last_committed_value is None
            or abs(self._latch_event_queue[0][1] - self._latch_zero)
            >= abs(self._last_committed_value - self._latch_zero)
        ):
            (__timestamp__, value) = self._latch_event_queue.popleft()
            self._commit_value(value)

        self._update_popup()


class PressureSliderElement(LatchableSliderElement):
    def _net_value(self):
        max_value = max(self._owned_values())
        return 0 if max_value is None else max_value


class XYSliderElement(LatchableSliderElement):
    def __init__(
        self,
        left_input: InputControlElement,
        right_input: InputControlElement,
        latch_zero: float = float(get_xy_value(0, 0)),
        *a,
        **k,
    ):
        super().__init__(
            *a,
            control_elements=(left_input, right_input),
            # We read XY values from a table, so full_pressure isn't really relevant
            # here.
            min_input=0,
            max_input=127,
            latch_zero=latch_zero,
            **k,
        )
        self._left_input = left_input
        self._right_input = right_input

    def _net_value(self):
        (left_value, right_value) = [
            clamp(input.value or 0, self._min_input, self._max_input)
            for input in (self._left_input, self._right_input)
        ]

        value = get_xy_value(left_value, right_value)
        # TODO: This is seems to be getting scaled up somewhere in the chain.
        result = clamp(
            value,
            self._min_input,
            self._max_input,
        )
        logger.info(f"xy got {left_value} {right_value} -> {value} -> {result}")
        return result


class ExpressionSliderElement(PressureSliderElement):
    def __init__(
        self,
        input: InputControlElement,
        *a,
        movement_threshold: Optional[int] = None,
        **k,
    ):
        super().__init__(*a, control_elements=(input,), **k)

        self._movement_threshold = movement_threshold

        # Track the last known physical value of the pedal, clamped
        # within our range. Clamping this value simplifies
        # movement-detection logic at the edges.
        self._last_clamped_value: Union[int, None] = None

    def on_nested_control_element_received(self, control):
        super().on_nested_control_element_received(control)
        self._last_clamped_value = self._clamp_value(control.value)

        # The expression pedal doesn't need to be zeroed out before we
        # start processing values.
        self._is_transitioning = False

    def _on_value(self, value, control: InputControlElement):
        clamped_value = self._clamp_value(value)

        # If this is the first value our control element has received,
        # just treat it as the base for the movement threshold.
        if self._last_clamped_value is None:
            self._last_clamped_value = clamped_value

        is_at_edge = (
            clamped_value == self._min_input or clamped_value == self._max_input
        )

        if (
            self._movement_threshold is None
            or is_at_edge
            and clamped_value != self._last_clamped_value
            or
            # Use >=, since a threshold of zero should always be met.
            abs(clamped_value - self._last_clamped_value) >= self._movement_threshold
        ):
            self._last_clamped_value = clamped_value
            super()._on_value(value, control)

    def _clamp_value(self, value):
        if value is None:
            return value
        else:
            return clamp(
                value,
                min(self._min_input, self._max_input),
                max(self._min_input, self._max_input),
            )


class IncrementalSliderElement(ProcessedSliderElement):
    def __init__(
        self,
        right_input: InputControlElement,
        left_input: InputControlElement,
        *a,
        scroll_step_delay: float = TIMER_DELAY,
        scroll_initial_delay: float = 2 * TIMER_DELAY,
        scroll_quantized_step_delay: float = 2 * TIMER_DELAY,
        # Receives the raw pressure on the scrolling key, and returns
        # the fraction of a parameter's range to scroll through per
        # second. The SoftStep default is 15 CC steps per second,
        # i.e. 15/127 as a fractional rate.
        scroll_rate: Callable[[int], float] = lambda _: (15 / 127),
        **k,
    ):
        assert scroll_quantized_step_delay >= 0
        assert scroll_initial_delay >= 0

        super().__init__((left_input, right_input), *a, **k)
        self._right_input = right_input
        self._left_input = left_input

        self._scroll_step_delay = scroll_step_delay
        self._scroll_initial_delay = scroll_initial_delay
        self._scroll_quantized_step_delay = scroll_quantized_step_delay
        self._scroll_rate = scroll_rate

        # Cache this result.
        self.__scroll_rate_multiplier = scroll_step_delay * 127

    @lazy_attribute
    def _scroll_task(self) -> task.Task:
        scroll_task = self._tasks.add(
            task.sequence(
                task.wait(self._scroll_initial_delay),
                task.loop(
                    task.wait(self._scroll_step_delay), task.run(self._on_scroll)
                ),
            )
        )
        scroll_task.kill()
        return scroll_task

    @lazy_attribute
    def _quantized_scroll_task(self) -> task.Task:
        quantized_scroll_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.wait(self._scroll_quantized_step_delay),
                    task.run(self._on_scroll),
                )
            )
        )
        quantized_scroll_task.kill()
        return quantized_scroll_task

    def on_nested_control_element_lost(self, control):
        super().on_nested_control_element_lost(control)
        self._ensure_not_scrolling()

    def _ensure_not_scrolling(self):
        if not self._scroll_task.is_killed:
            self._scroll_task.kill()
        if not self._quantized_scroll_task.is_killed:
            self._quantized_scroll_task.kill()

    def _on_value(self, value, control: InputControlElement):  # noqa: ARG002
        if any([value > 0 for value in self._owned_values()]):
            parameter = self._connected_parameter
            if parameter is not None and parameter.is_enabled:
                scroll_task = (
                    self._quantized_scroll_task
                    if parameter.is_quantized
                    else self._scroll_task
                )
                if scroll_task.is_killed:
                    # Make sure the other task is killed as well.
                    self._ensure_not_scrolling()

                    # Force an initial small scroll event (the
                    # equivalent of changing the CC value by 1). This
                    # allows for fine-grained stepping by tapping the
                    # up/down buttons.
                    self._on_scroll(1)

                    scroll_task.restart()

        else:
            self._ensure_not_scrolling()
            self._update_popup()

    # If a magnitude is given, it will override the computed magnitude
    # of this scroll step in the non-quantized case.
    def _on_scroll(self, magnitude: Union[int, float, None] = None):
        parameter = self._connected_parameter
        if parameter is not None and parameter.is_enabled:
            down_value, up_value = [
                element.value or 0 for element in (self._left_input, self._right_input)
            ]

            increment: int = 0
            scroll_rate: float = 0
            if up_value > 0 and down_value > 0:
                increment = 0
            elif up_value > 0:
                scroll_rate = self._scroll_rate(up_value)
                increment = 1
            elif down_value > 0:
                scroll_rate = self._scroll_rate(down_value)
                increment = -1

            if magnitude is None:
                if parameter.is_quantized:
                    parameter_range: float = parameter.max - parameter.min
                    magnitude = 127 / (parameter_range)
                else:
                    magnitude = scroll_rate * self.__scroll_rate_multiplier

            self._scroll_value = clamp(
                linear(
                    0,
                    127,
                    (parameter.value - parameter.min) / (parameter.max - parameter.min),
                )
                + increment * magnitude,
                0,
                127,
            )
            self._commit_value(self._scroll_value)
