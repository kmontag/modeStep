from ableton.v3.control_surface.components import (
    ViewControlComponent as ViewControlComponentBase,
)
from ableton.v3.live import liveobj_name, scene_index


class ViewControlComponent(ViewControlComponentBase):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)

        # The parent sets this up for tracks, but not scenes.
        def notify_scenes_scrolled():
            assert self.song
            scene = self.song.view.selected_scene
            name = liveobj_name(scene)
            self.notify(self.notifications.Scene.select, name, scene_index(scene))

        self.register_slot(self, notify_scenes_scrolled, "scene_selection_scrolled")
