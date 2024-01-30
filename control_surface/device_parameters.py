from __future__ import annotations

import logging
from functools import partial
from itertools import zip_longest
from typing import TYPE_CHECKING, Optional, Union

from ableton.v3.base import depends
from ableton.v3.control_surface.components import (
    DeviceParametersComponent as DeviceParametersComponentBase,
)
from ableton.v3.control_surface.controls import (
    ButtonControl,
    MappedSensitivitySettingControl,
)
from ableton.v3.control_surface.controls.control_list import ControlList

if TYPE_CHECKING:
    from .configuration import Configuration

logger = logging.getLogger(__name__)


NUM_CONTROLS = 8


class DeviceParametersComponent(DeviceParametersComponentBase):
    # Expression pedal as a slider.
    expression_pedal = MappedSensitivitySettingControl()  # type: ignore

    # Buttons to map the expression pedal to a parameter index.
    expression_mapping_buttons = ControlList(ButtonControl, NUM_CONTROLS)  # type: ignore

    parameter_on_color = "Device.ParameterOn"
    parameter_off_color = "Device.ParameterOff"

    @depends(configuration=None)
    def __init__(self, *a, configuration: Optional["Configuration"] = None, **k):
        assert configuration
        self._expression_index = configuration.initial_expression_parameter
        super().__init__(*a, **k)

        self._expression_mapping_button_slots = [
            self.register_slot(
                None,
                partial(self._on_expression_mapping_button_pressed, index),
                "value",
            )
            for index in range(NUM_CONTROLS)
        ]

        # Explicit typings for members that get modified during `__get__`.
        self.controls: ControlList.State
        self.expression_pedal: MappedSensitivitySettingControl.State
        self.expression_mapping_buttons: ControlList.State

    def _connect_parameters(self):
        super()._connect_parameters()

        self._update_leds()

        parameters = self._parameter_provider.parameters[:NUM_CONTROLS]
        if self.expression_pedal:
            if self._expression_index is None:
                self.expression_pedal.mapped_parameter = None
            elif (
                self._expression_index < len(parameters)
                and parameters[self._expression_index]
            ):
                parameter = parameters[self._expression_index].parameter
                if parameter:
                    self.expression_pedal.mapped_parameter = parameter

    def set_expression_pedal(self, control):
        self.expression_pedal.set_control_element(control)

    def set_expression_mapping_buttons(self, expression_buttons):
        expression_buttons = expression_buttons or [None for _ in range(NUM_CONTROLS)]
        for slot, button in zip_longest(
            self._expression_mapping_button_slots, expression_buttons
        ):
            if slot:
                slot.subject = button
        self._update_expression_mapping_buttons()

    def _on_expression_mapping_button_pressed(self, index, value):
        if self.is_enabled():
            if value > 0:
                # Disconnect if this index is already selected.
                if index is self._expression_index:
                    self.set_expression_index(None)
                else:
                    self.set_expression_index(index)

    def set_expression_index(self, expression_index: Union[int, None]):
        self._expression_index = expression_index

        self._update_expression_mapping_buttons()
        self._connect_parameters()

    def _update_expression_mapping_buttons(self):
        if self.is_enabled():
            # Helper for the type checker.
            def __slot_subject(slot):
                assert slot
                return slot.subject

            buttons = [
                __slot_subject(slot) for slot in self._expression_mapping_button_slots
            ]
            for index, button in enumerate(buttons):
                color = (
                    "Device.ExprOn"
                    if index is self._expression_index
                    else "Device.ExprOff"
                )
                if button:
                    button.set_light(color)

    def _update_leds(self):
        parameters = self._parameter_provider.parameters[:NUM_CONTROLS]
        led_enabled_states = [False] * NUM_CONTROLS
        for idx, parameter_info in enumerate(parameters):
            if parameter_info and parameter_info.parameter:
                led_enabled_states[idx] = True

        for control, enabled in zip_longest(self.controls, led_enabled_states):
            if control:
                control_element = control.control_element
                # Our encoder controls respond directly to `set_light`, similar to
                # button elements.
                if control_element and hasattr(control_element, "set_light"):
                    color = (
                        self.parameter_on_color if enabled else self.parameter_off_color
                    )
                    control_element.set_light(color)

    def update(self):
        super().update()
        self._update_expression_mapping_buttons()
        self._update_leds()
