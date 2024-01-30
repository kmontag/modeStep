from logging import getLogger
from typing import Tuple

from ableton.v3.base import depends
from ableton.v3.control_surface.components import (
    SessionNavigationComponent as SessionNavigationComponentBase,
)
from ableton.v3.control_surface.display import Renderable

logger = getLogger(__name__)


class SessionNavigationComponent(SessionNavigationComponentBase, Renderable):
    @depends(session_ring=None)
    def __init__(self, session_ring=None, *a, **k):
        super().__init__(*a, session_ring=session_ring, **k)
        assert session_ring
        self._session_ring = session_ring

        # Horizontal, vertical.
        self._last_offsets: Tuple[int, int] = self._current_offsets()

    def _update_changed(self):
        if self.is_enabled():
            offsets = self._current_offsets()
            for index, notification in enumerate(
                (
                    self.notifications.SessionNavigation.horizontal,
                    self.notifications.SessionNavigation.vertical,
                )
            ):
                if offsets[index] != self._last_offsets[index]:
                    self.notify(notification, offsets[index])
                    break

            self._last_offsets = offsets

    def _current_offsets(self):
        return (self._session_ring.track_offset, self._session_ring.scene_offset)

    def _update_vertical(self):
        self._update_changed()
        super()._update_vertical()

    def _update_horizontal(self):
        self._update_changed()
        super()._update_horizontal()
