import logging

from ableton.v3.control_surface.components import DeviceComponent as DeviceComponentBase

from .device_parameters import DeviceParametersComponent

logger = logging.getLogger(__name__)

NUM_BANK_BUTTONS = 8


class DeviceComponent(DeviceComponentBase):
    def __init__(
        self,
        parameters_component_type=DeviceParametersComponent,
        *a,
        **k,
    ):
        super().__init__(
            *a,
            parameters_component_type=parameters_component_type,
            **k,
        )

        # Add notifications on device lock toggle.
        orig_toggle_lock = self._toggle_lock
        assert orig_toggle_lock

        def toggle_lock():
            orig_toggle_lock()
            if self._device_provider:
                attr = (
                    "locked"
                    if self._device_provider.is_locked_to_device
                    else "unlocked"
                )
                self.notify(
                    getattr(self.notifications.Device, attr),
                    self.device.name if self.device else "",
                )

        self._toggle_lock = toggle_lock

        self._parameters_component: DeviceParametersComponent

        # Create an alternate parameters component with a different
        # skin for latching controls. Having both of these available
        # also allows us to use both latching and non-latching
        # controls on the XY mode.
        self._alt_parameters_component = parameters_component_type(
            name=f"{self._parameters_component.name}_Alt"
        )
        self._alt_parameters_component.parameter_provider = self
        self._alt_parameters_component.parameter_on_color = "Device.AltParameterOn"
        self._alt_parameters_component.parameter_off_color = "Device.AltParameterOff"
        self.add_children(self._alt_parameters_component)

    # Forward some controls to the parameters components.
    def set_expression_pedal(self, control):
        self._parameters_component.set_expression_pedal(control)

    def set_expression_mapping_buttons(self, controls):
        self._parameters_component.set_expression_mapping_buttons(controls)

    def set_alt_parameter_controls(self, controls):
        self._alt_parameters_component.set_parameter_controls(controls)
