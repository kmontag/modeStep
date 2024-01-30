from logging import getLogger
from typing import Iterable, Optional

from ableton.v3.base import task
from ableton.v3.control_surface import CompoundElement, InputControlElement

logger = getLogger(__name__)


# A compound element that allows processing of the incoming values from its inputs,
# rather than passing them up directly.
class ProcessedValueElement(CompoundElement):
    def __init__(
        self,
        control_elements: Optional[Iterable[InputControlElement]] = None,
        *a,
        **k,
    ):
        super().__init__(control_elements, *a, **k)

        self._last_committed_value: Optional[int] = None

        # Helper for the type checker.
        self._tasks: task.TaskGroup

    # Subclasses should override this with their actual value handling logic.
    def _on_value(self, value, control: InputControlElement):
        raise NotImplementedError

    # Update the value of the element as a whole, and forward it to any controls if it
    # has changed.
    def _commit_value(self, value):
        if value != self._last_committed_value:
            self.notify_value(value)
            self._last_committed_value = value

    # Helper to get the current values of all child inputs.
    def _owned_values(self) -> Iterable[int]:
        return map(
            # If an input has never received a value, treat it as a zero.
            lambda el: 0 if el.value is None else el.value,
            filter(lambda el: hasattr(el, "value"), self.owned_control_elements()),
        )

    def on_nested_control_element_received(self, control):  # noqa: ARG002
        # Reset the value when changing controls.
        self._last_committed_value = None
        # logger.info(f"{self} received control element")

    def on_nested_control_element_value(self, value, control: InputControlElement):
        # logger.info(f"{self} nested value {value}")
        self._on_value(value, control)

    def __str__(self):
        return f"{self.__class__.__name__}:{self.name}"


# When an element's children get re-bound (e.g. when a button changes to a slider),
# suppress inputs until it's been fully released. This prevents buttons from firing
# immediately when changing modes.
class TransitionalProcessedValueElement(ProcessedValueElement):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._is_transitioning = False

    def on_nested_control_element_received(self, control):
        super().on_nested_control_element_received(control)
        if (
            hasattr(control, "value")
            and control.value is not None
            and control.value > 0
        ):
            self._is_transitioning = True

    def on_nested_control_element_value(self, value, control):
        if self._is_transitioning:
            # Clear the transitional state once all inputs have been completely
            # released.
            self._is_transitioning = not all(
                [value == 0 for value in self._owned_values()]
            )
        else:
            super().on_nested_control_element_value(value, control)
