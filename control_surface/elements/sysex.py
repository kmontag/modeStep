import logging
from typing import Collection, Tuple

from ableton.v2.control_surface.elements import ButtonElementMixin
from ableton.v3.control_surface.elements import (
    SysexElement,
)

logger = logging.getLogger(__name__)


class SysexButtonElement(SysexElement, ButtonElementMixin):
    def is_momentary(self):
        return False


# "Colored" sysex element configured with two collections of messages, which should be on/off
# messages for a light, mode, etc. in the hardware. The element accepts True and False
# as color values to trigger the on and off messages, respectively.
class SysexToggleElement(SysexButtonElement):
    # Fires after all the messages for the given on/off value have been sent.
    __events__ = ("send_value",)

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

        super().__init__(
            *a,
            # Messages just get passed directly to the parent's send_value.
            send_message_generator=lambda msg: msg,
            optimized_send_midi=False,
            # Prevent mysterious crashes if there's mo
            # identifier_bytes() for the component.
            sysex_identifier=list(on_messages)[0],
            **k,
        )

    # This can get called via `set_light`, or from elsewhere within the framework.
    def send_value(self, *a, **k):
        assert len(a) == 1
        value = a[0]
        assert isinstance(value, bool)

        # Send multiple messages by calling the parent repeatedly.
        messages = self._on_messages if value else self._off_messages
        for message in messages:
            super().send_value(message, *a[1:], **k)

        self.notify_send_value(value)

    def set_light(self, value):
        self.send_value(value)
