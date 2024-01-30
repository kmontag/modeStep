from logging import getLogger
from typing import Any, Callable, Optional

from ableton.v3.base import clamp, const, depends, nop
from ableton.v3.control_surface.components import (
    SessionRingComponent as SessionRingComponentBase,
)

logger = getLogger(__name__)

SessionHighlightCallback = Callable[
    # track offset, scene offset, num tracks, num scenes, include returns
    [int, int, int, int, bool], Any
]


class SessionRingComponent(SessionRingComponentBase):
    preferences_highlight_scenes_key = "session_ring_highlight_scenes"
    preferences_highlight_tracks_key = "session_ring_highlight_tracks"

    @depends(preferences={}, set_session_highlight=(const(nop)))
    def __init__(
        self,
        *a,
        name="Session_Ring",
        num_tracks=0,
        num_scenes=0,
        preferences: Optional[dict] = None,
        set_session_highlight: SessionHighlightCallback = nop,
        **k,
    ):
        assert preferences
        self._preferences = preferences

        # Try and sanitize the input just in case anything gets weird.
        self._highlight_scenes, self._highlight_tracks = [
            clamp(int(preferences[key]), 0, max_value)
            if key in preferences
            else default
            for key, max_value, default in (
                (self.preferences_highlight_scenes_key, num_scenes, 1),
                (self.preferences_highlight_tracks_key, num_tracks, num_tracks),
            )
        ]

        def _set_reduced_session_highlight(
            track_offset, scene_offset, num_tracks, num_scenes, include_returns
        ):
            # Call the real highlighter with our visible window.
            set_session_highlight(
                track_offset,
                scene_offset,
                min(num_tracks, self._highlight_tracks),
                min(num_scenes, self._highlight_scenes),
                include_returns,
            )

        # Just to sanity check types.
        set_reduced_session_highlight: SessionHighlightCallback = (
            _set_reduced_session_highlight
        )

        super().__init__(
            *a,
            name=name,
            num_tracks=num_tracks,
            num_scenes=num_scenes,
            set_session_highlight=set_reduced_session_highlight,
            **k,
        )
        self._highlight_scenes = self.num_scenes
        self._highlight_tracks = self.num_tracks

    @property
    def highlight_scenes(self):
        return self._highlight_scenes

    @highlight_scenes.setter
    def highlight_scenes(self, highlight_scenes: int):
        self._highlight_scenes = highlight_scenes
        self._update_highlight()

    @property
    def highlight_tracks(self):
        return self._highlight_tracks

    @highlight_tracks.setter
    def highlight_tracks(self, highlight_tracks: int):
        self._highlight_tracks = highlight_tracks
        self._update_highlight()
