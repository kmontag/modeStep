from ableton.v3.control_surface.components import SceneComponent as SceneComponentBase
from ableton.v3.live import liveobj_name, scene_index


class SceneComponent(SceneComponentBase):
    def _do_launch_scene(self):
        super()._do_launch_scene()

        # Send a notification.
        scene = self._scene
        self.notify(
            self.notifications.Scene.launch, liveobj_name(scene), scene_index(scene)
        )
