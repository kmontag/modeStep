from itertools import count
from logging import getLogger
from typing import Any

from ableton.v3.base import depends, task
from ableton.v3.control_surface.components import (
    SessionComponent as SessionComponentBase,
)
from ableton.v3.control_surface.controls import ButtonControl

from .live import lazy_attribute, listens, listens_group

logger = getLogger(__name__)


class SessionComponent(SessionComponentBase):
    _tasks: task.TaskGroup  # type: ignore

    # This already exists on the parent, but we need to override its `pressed` listener.
    #
    # It would be nice if we could make the color more dynamic (e.g. off when no tracks
    # playing and blinking while tracks are stopping), but the base component only
    # invokes update methods on changes to the stop-clips status for tracks within the
    # session ring, whereas we'd need to update the color on changes to the status for
    # any track in the set.
    stop_all_clips_button: Any = ButtonControl(
        color="Session.StopAllClips", pressed_color="Session.StopAllClipsPressed"
    )

    @depends(session_ring=None)
    def __init__(
        self,
        *a,
        name="Session",
        session_ring=None,
        scene_component_type=None,
        clip_slot_component_type=None,
        clipboard_component_type=None,
        **k,
    ):
        super().__init__(
            *a,
            name=name,
            session_ring=session_ring,
            scene_component_type=scene_component_type,
            clip_slot_component_type=clip_slot_component_type,
            clipboard_component_type=clipboard_component_type,
            **k,
        )

        # Updated when the stop-all-clips button is pressed, and again when all clips
        # have stopped. Tracks whether the button should be blinking.
        self.__is_stopping_all_clips: bool = False

        assert self.song
        self.__on_tracks_changed.subject = self.song
        self._reassign_track_listeners()

    def set_launch_selected_scene_button(self, button):
        self.selected_scene().set_launch_button(button)

    def set_clip_launch_buttons(self, buttons):
        assert self._session_ring
        for y, scene in enumerate(self._scenes):
            for x in range(self._session_ring.num_tracks):
                # The parent throws an error on an out-of-bounds button here, e.g. with
                # the flat grid matrices. Just simulate null elements instead.
                button = (
                    buttons.get_button(y, x)
                    if buttons and y < buttons.height()
                    else None
                )
                scene.clip_slot(x).set_launch_button(button)

    @stop_all_clips_button.pressed  # type: ignore
    def stop_all_clips_button(self, _):
        assert self.song
        self.notify(self.notifications.Session.stop_all_clips)
        self.song.stop_all_clips()

        # We'll get notified via the fired/playing slot index listeners once the stop
        # has actually been triggered. The listeners get invoked regardless of wether
        # any clips were actually already playing.
        self.__is_stopping_all_clips = True

    def update(self):
        super().update()
        self._update_stop_all_clips_led()

    @listens_group("fired_slot_index")
    def __on_any_fired_slot_index_changed(self, _):
        self.__throttled_update_stop_all_clips_led()

    @listens_group("playing_slot_index")
    def __on_any_playing_slot_index_changed(self, _):
        self.__throttled_update_stop_all_clips_led()

    @listens("tracks")
    def __on_tracks_changed(self):
        self._reassign_track_listeners()

    # The Stop All Clips button needs to get updates from every track in the set to
    # check when it can stop appearing as triggered.
    def _reassign_track_listeners(self):
        assert self.song
        assert self.__on_any_fired_slot_index_changed

        tracks = self.song.tracks
        self.__on_any_fired_slot_index_changed.replace_subjects(tracks, count())
        self.__on_any_playing_slot_index_changed.replace_subjects(tracks, count())

    def __throttled_update_stop_all_clips_led(self):
        # We don't want to compute the triggered state for every listener update, since
        # the computation is O(n) with the number of tracks. Instead, use a task to
        # throttle updates.
        if self._update_stop_all_clips_led_task.is_killed:
            # Perform the update once at the head of the delay to get immediate LED
            # feedback. In general this should already set the button state correctly.
            self._update_stop_all_clips_led()
            # Perform another update on the next tick, just in case the stopping state
            # changed somehow in the meantime.
            self._update_stop_all_clips_led_task.restart()

    @lazy_attribute
    def _update_stop_all_clips_led_task(self):
        update_stop_all_clips_led_task = self._tasks.add(
            task.run(self._update_stop_all_clips_led)
        )
        update_stop_all_clips_led_task.kill()
        return update_stop_all_clips_led_task

    def _update_stop_all_clips_led(self):
        color = "Session.StopAllClips"

        # Check for the triggered state, or clear the stopping status if the triggered
        # state is no longer active.
        #
        # Note the Stop All Clips button in the Live UI has slightly different behavior:
        # if the transport is playing but no clips are playing when it's pressed, it
        # will blink until playback reaches the next launch quanitization point
        # (e.g. the next bar). With our logic in this case, the button won't ever reach
        # a blinking state. There doesn't appear to be a good way to listen for reaching
        # the next quanitzation point during playback.
        if self.__is_stopping_all_clips:
            if self._is_stop_all_clips_maybe_triggered():
                color = "Session.StopAllClipsTriggered"
            else:
                self.__is_stopping_all_clips = False

        if self.stop_all_clips_button.color != color:
            self.stop_all_clips_button.color = color

    # Returns true iff:
    #
    # - at least one clip has stop triggered
    # - no clips are playing without a triggered stop
    #
    # These conditions can also be met without pressing "Stop All Clips" (e.g. when
    # playing a single clip and then stopping it), so this logic should generally be
    # combined with tracking of actual presses of the stop-all-clips button.
    def _is_stop_all_clips_maybe_triggered(self) -> bool:
        # This gets the full list of tracks in the set. Unclear what the difference is
        # between this and `song.tracks`, but this seems to be more canonical for this
        # context.
        assert self._session_ring
        tracks_to_use = self._session_ring.tracks_to_use()

        # There doesn't seem to be a good way to detect the
        # stop-all-clips state (or event) directly.
        is_stop_triggered = False
        for track in tracks_to_use:
            # The `fired_slot_index` will be -2 for a track when its
            # stop button is triggered, or -1 otherwise.
            if track.playing_slot_index >= 0 and track.fired_slot_index != -2:
                # Once we find one playing clip that isn't
                # stopping, we can return immediately.
                return False
            elif track.fired_slot_index == -2:
                # Once we find a stopping clip, we need to keep iterating to see if
                # there are any other clips which are playing and not triggered to stop.
                is_stop_triggered = True

        # If we get here, no clips are playing without a triggered stop. Return whether
        # at least one clip is currently triggered.
        return is_stop_triggered
