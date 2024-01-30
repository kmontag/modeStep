from typing import Tuple

from ableton.v2.control_surface.elements import ButtonElementMixin
from ableton.v3.control_surface.elements import (
    SysexElement,
)


class SysexButtonElement(SysexElement, ButtonElementMixin):
    def is_momentary(self):
        return False


# "Colored" sysex element configured with two messages, which should
# be on/off messages for a light, mode, etc. in the hardware. The
# element accepts True and False as color values to trigger the on and
# off messages, respectively.
class SysexToggleElement(SysexButtonElement):
    def __init__(
        self,
        on_message: Tuple[int, ...],
        off_message: Tuple[int, ...],
        *a,
        **k,
    ):
        self._on_message = on_message
        self._off_message = off_message

        def send_message_generator(v):
            return self._on_message if v else self._off_message

        super().__init__(
            *a,
            send_message_generator=send_message_generator,
            optimized_send_midi=False,
            # Prevent mysterious crashes if there's mo
            # identifier_bytes() for the component.
            sysex_identifier=on_message,
            **k,
        )

    def set_light(self, value):
        assert isinstance(value, bool)
        self.send_value(value)
