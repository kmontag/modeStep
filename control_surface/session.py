from enum import Enum
from logging import getLogger

from ableton.v3.base import task
from ableton.v3.control_surface.components import (
    SessionComponent as SessionComponentBase,
)

from .live import lazy_attribute

logger = getLogger(__name__)


# We want to be able to enable/disable the stop all clips button depending on whether
# clips are playing, and show a triggered indication while clips are stopping. The Live
# API doesn't expose the necessary properties/events, so we need to compute the status
# manually.
class StopAllClipsStatus(Enum):
    enabled = "enabled"
    disabled = "disabled"
    triggered = "triggered"


class SessionComponent(SessionComponentBase):
    _tasks: task.TaskGroup  # type: ignore

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

    def _update_stop_clips_led(self, index):
        super()._update_stop_clips_led(index)

        # We don't want to compute the triggered state for every LED update, since it's
        # O(n) with the number of tracks. Instead, use a task to throttle updates.
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
        status = self._stop_all_clips_status()
        color = "Session.StopAllClips"
        enabled = True

        if status == StopAllClipsStatus.disabled:
            enabled = False
        elif status == StopAllClipsStatus.triggered:
            color = "Session.StopAllClipsTriggered"

        if self.stop_all_clips_button.enabled != enabled:
            self.stop_all_clips_button.enabled = enabled

        if self.stop_all_clips_button.color != color:
            self.stop_all_clips_button.color = color

    def _stop_all_clips_status(self) -> StopAllClipsStatus:
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
                return StopAllClipsStatus.enabled
            elif track.fired_slot_index == -2:
                # We need to keep iterating to see if there are any
                # other clips which are playing and not triggered to
                # stop.
                is_stop_triggered = True

        return (
            StopAllClipsStatus.triggered
            if is_stop_triggered
            else StopAllClipsStatus.disabled
        )
