from typing import Collection, Optional, Tuple

from ableton.v2.control_surface.elements import ButtonElementMixin
from ableton.v3.control_surface.elements import (
    SysexElement,
)


class SysexButtonElement(SysexElement, ButtonElementMixin):
    def is_momentary(self):
        return False


# "Colored" sysex element configured with two collections of messages, which should be on/off
# messages for a light, mode, etc. in the hardware. The element accepts True and False
# as color values to trigger the on and off messages, respectively.
class SysexToggleElement(SysexButtonElement):
    def __init__(
        self,
        on_messages: Collection[Tuple[int, ...]],
        off_messages: Collection[Tuple[int, ...]],
        *a,
        **k,
    ):
        self._on_messages = on_messages
        self._off_messages = off_messages
        assert len(on_messages) > 0 and len(off_messages) > 0

        # Store the last value to `set_light` to avoid sending unnecessary messages.
        self._last_value: Optional[bool] = None

        super().__init__(
            *a,
            # Messages just get passed directly to send_value.
            send_message_generator=lambda msg: msg,
            optimized_send_midi=False,
            # Prevent mysterious crashes if there's mo
            # identifier_bytes() for the component.
            sysex_identifier=list(on_messages)[0],
            **k,
        )

    def _on_resource_received(self, client, *a, **k):
        # Make sure we send our initial message. Since sending sysexes can cause
        # momentary performance issues and other weirdness on the device, try to avoid
        # disconnecting/reconnecting resources too often.
        self._last_value = None
        return super()._on_resource_received(client, *a, **k)

    def set_light(self, value):
        assert isinstance(value, bool)

        # Avoid re-sending these on every update.
        if value != self._last_value:
            messages = self._on_messages if value else self._off_messages
            for message in messages:
                self.send_value(message)
        self._last_value = value
