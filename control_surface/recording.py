import Live
from functools import partial
from logging import getLogger
from typing import Any, Callable, Optional

from ableton.v3.control_surface.components import (
    BasicRecordingMethod,
)
from ableton.v3.control_surface.components import (
    RecordingComponent as RecordingComponentBase,
)
from ableton.v3.control_surface.controls import ButtonControl

logger = getLogger(__name__)


# There doesn't seem to be a way to detect when the session record button has entered
# the "stopping" state, so we need to track this manually. This will only catch stops
# when the button is actually pressed; if ever needed, we could get a fully accurate
# state using a task executing on every tick.
class StoppingRecordingMethod(BasicRecordingMethod):
    is_recording_stopping = False

    def __init__(
        self, *a, on_recording_stopping: Optional[Callable[[], Any]] = None, **k
    ):
        super().__init__(*a, **k)
        # Would be nice to use `EventObject` instead of passing a callback, but it
        # appears incompatible with an abstract base class.
        assert on_recording_stopping
        self._on_recording_stopping = on_recording_stopping

    def stop_recording(self):
        did_stop: bool = super().stop_recording()
        assert self.song

        # There's no clear way to get the stopping status from the
        # song object, so we mark it manually whenever the stop method
        # is called. This gets reset when the session record status
        # changes to something other than `on`.
        if (
            did_stop
            and self.song.session_record_status == Live.Song.SessionRecordStatus.on
            or self.song.session_record
        ):
            self.is_recording_stopping = True
            self._on_recording_stopping()

        return did_stop

    # Clear the record-stopping flag if we've moved away from the `on` session record
    # status. This is expected to be called by the parent component whenever the song's
    # session record status changes.
    def update(self):
        assert self.song
        if self.is_recording_stopping:
            if self.song.session_record_status != Live.Song.SessionRecordStatus.on:
                self.is_recording_stopping = False


class RecordingComponent(RecordingComponentBase):
    # Equivalent to Push's "Duplicate" button when used while clips are playing.
    capture_and_insert_scene_button: ButtonControl.State = ButtonControl(  # type: ignore
        color="Recording.CaptureAndInsertScene",
        pressed_color="Recording.CaptureAndInsertScenePressed",
    )

    def __init__(self, recording_method_type=StoppingRecordingMethod, *a, **k):
        super().__init__(
            *a,
            recording_method_type=partial(
                recording_method_type,
                on_recording_stopping=self._update_session_record_button,
            ),
            **k,
        )
        self._recording_method: StoppingRecordingMethod

    def _update_session_record_button(self):
        self._recording_method.update()
        if self._recording_method.is_recording_stopping:
            self.session_record_button.color = "Recording.SessionRecordStopping"
        else:
            super()._update_session_record_button()

    @capture_and_insert_scene_button.pressed
    def capture_and_insert_scene_button(self, _):
        assert self.song
        try:
            self.song.capture_and_insert_scene(
                # Or, to duplicate all but the current track's clip:
                #
                # Live.Song.CaptureMode.all_except_selected
            )
            self.notify(self.notifications.Recording.capture_and_insert_scene)
        except Live.Base.LimitationError:
            logger.warning("could not create new scene, reached scene limit")
