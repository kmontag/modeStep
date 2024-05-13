import logging
from typing import Any, Callable, Optional, Union

from ableton.v2.control_surface.control.sysex import ColorSysexControl
from ableton.v3.base import depends
from ableton.v3.control_surface.component import Component
from ableton.v3.control_surface.controls import ButtonControl

logger = logging.getLogger(__name__)


# A sysex which accepts a null color to represent an unmanaged property.
class NullableColorSysexControl(ColorSysexControl):
    class State(ColorSysexControl.State):
        def __init__(self, color=None, *a, **k):
            super().__init__(color, *a, **k)

            # The parent sets this to "DefaultButton.Disabled" by default, override with
            # actual `None`.
            if color is None:
                self.color = color

        def _send_current_color(self):
            if self.color is not None:
                return super()._send_current_color()


class HardwareComponent(Component):
    # These are expected to be mapped to `ToggleSysexElement`s or,
    # more specifically, to sysex elements which accept boolean values
    # as colors.
    backlight_sysex: ColorSysexControl.State = NullableColorSysexControl(color=None)  # type: ignore
    standalone_sysex: ColorSysexControl.State = ColorSysexControl(color=False)  # type: ignore

    ping_button: Any = ButtonControl()

    @depends(send_midi=None)
    def __init__(
        self,
        *a,
        send_midi: Union[Callable[..., bool], None] = None,
        **k,
    ):
        super().__init__(*a, **k)

        assert send_midi is not None
        self._send_midi = send_midi

        # The program change to send when switching into standalone mode.
        self._standalone_program: Optional[int] = None

        # Initial values for device properties - these will get set externally when
        # actually setting up this component.
        self._backlight: Optional[bool] = None  # None for unmanaged.
        self._standalone: bool = False

    @property
    def backlight(self) -> Optional[bool]:
        return self._backlight

    @backlight.setter
    def backlight(self, backlight: bool):
        self._backlight = backlight
        self._update_backlight()

    @property
    def standalone(self):
        return self._standalone

    @standalone.setter
    def standalone(self, standalone: bool):
        self._standalone = standalone
        self._update_standalone()

    # This gets sent as a PC message whenever entering standalone
    # mode.
    @property
    def standalone_program(self) -> Union[int, None]:
        return self._standalone_program

    # If we're currently in standalone mode, the setter sends the PC
    # immediately (as well as in the future when we re-enter
    # standalone mode).
    @standalone_program.setter
    def standalone_program(self, standalone_program: Union[int, None]):
        self._standalone_program = standalone_program
        self._update_standalone_program()

    @ping_button.pressed
    def ping_input(self, _):
        logger.info("ponging ping")
        self.ping_button.control_element.send_value(True)

    def update(self):
        super().update()
        self._update_standalone()
        self._update_backlight()

    def _update_backlight(self):
        if self.is_enabled():
            self.backlight_sysex.color = self.backlight

    def _update_standalone(self):
        if self.is_enabled():
            self.standalone_sysex.color = self._standalone
            self._update_standalone_program()

    def _update_standalone_program(self):
        if self.is_enabled() and self._standalone:
            if self._standalone_program is not None:
                self._send_midi((0xC0, self._standalone_program), optimized=False)
