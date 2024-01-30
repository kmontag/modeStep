from typing import Tuple

from ableton.v3.control_surface import midi
from ableton.v3.control_surface.elements import DisplayLineElement

from ..display import DISPLAY_WIDTH


class DisplayElement(DisplayLineElement):
    def __init__(self, *a, **k):
        super().__init__(self._render, *a, **k)

    def _render(self, chars: Tuple[int, ...]):
        # The SoftStep renders characters sent as MIDI CC messages on consecutive
        display_base_cc = 50

        for index in range(DISPLAY_WIDTH):
            # 32 is the ASCII space character.
            char = chars[index] if len(chars) > index else 32
            self.send_midi((midi.CC_STATUS, display_base_cc + index, char))
