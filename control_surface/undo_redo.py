import logging

from ableton.v3.base import task
from ableton.v3.control_surface.components import (
    UndoRedoComponent as UndoRedoComponentBase,
)

from .live import lazy_attribute

logger = logging.getLogger(__name__)


class UndoRedoComponent(UndoRedoComponentBase):
    _tasks: task.TaskGroup  # type: ignore

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._original_undo_color = self.undo_button.color
        self._original_redo_color = self.redo_button.color

    def _can_undo(self):
        return self.song and self.song.can_undo

    def _can_redo(self):
        return self.song and self.song.can_redo

    def update(self):
        super().update()
        self._check_enabled_states()
        if self.is_enabled():
            if self._check_enabled_states_task.is_killed:
                self._check_enabled_states_task.restart()
        elif not self._check_enabled_states_task.is_killed:
            self._check_enabled_states_task.kill()

    # Calls an update function on every display tick while the
    # component is active (i.e. when a control element is
    # bound). Needed as a workaround for no undo/redo state
    # events.
    def _check_enabled_states(self):
        for button, original_color, is_enabled in (
            (self.undo_button, self._original_undo_color, self._can_undo),
            (self.redo_button, self._original_redo_color, self._can_redo),
        ):
            color = original_color if is_enabled() else "UndoRedo.Disabled"
            if button.color != color:
                button.color = color

    @lazy_attribute
    def _check_enabled_states_task(self):
        check_enabled_states_task = self._tasks.add(
            task.loop(task.run(self._check_enabled_states))
        )
        return check_enabled_states_task
