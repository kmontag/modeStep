from __future__ import absolute_import, print_function, unicode_literals

from enum import Enum
from functools import partial
from logging import getLogger
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
)

from ableton.v2.base import linear
from ableton.v2.control_surface.defaults import (
    TIMER_DELAY,
)
from ableton.v3.base import clamp, depends, flatten
from ableton.v3.control_surface import (
    MIDI_CC_TYPE,
    ControlElement,
    ElementsBase,
)
from ableton.v3.control_surface.elements import (
    ButtonMatrixElement,
)

from .. import sysex
from ..live import lazy_attribute
from ..types import KeySafetyStrategy, TypedDict
from .button import LightedButtonElement
from .display import DisplayElement
from .hardware import NUM_COLS, NUM_ROWS, KeyDirection, get_cc_for_key, get_cc_for_nav
from .input_control import (
    InputLock,
    PressureInputElement,
)
from .light import LightElement, LightGroup
from .slider import (
    ExpressionSliderElement,
    IncrementalSliderElement,
    PressureSliderElement,
    XYSliderElement,
)
from .sysex import SysexButtonElement, SysexToggleElement

if TYPE_CHECKING:
    from ..configuration import Configuration

logger = getLogger(__name__)

LATCH_DELAY = TIMER_DELAY * 2


# Number of columns in the "grid" portion of the controller on the left side.
NUM_GRID_COLS = 4


class KeySafetyManager:
    def __init__(self, strategy: KeySafetyStrategy):
        InputLockState = TypedDict(
            "InputLockState",
            {
                "lock": InputLock,
                "friend_ids": Iterable[str],
                "enemy_ids": Iterable[str],
            },
        )
        self._input_lock_states: Dict[str, InputLockState] = {}
        self._strategy: KeySafetyStrategy = strategy

    @property
    def strategy(self) -> KeySafetyStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, strategy: KeySafetyStrategy):
        self._strategy = strategy

    # Friends are allowed to be simultaneously locked even with the "single_key"
    # strategy. Enemies aren't allowed to be mutually locked in the "adjacent_key"
    # strategy.
    def create_input_lock(
        self, id: str, friend_ids: Iterable[str], enemy_ids: Iterable[str]
    ):
        if id in self._input_lock_states:
            raise ValueError(f"lock already exists: {id}")
        lock = InputLock(partial(self._can_acquire, id))
        self._input_lock_states[id] = {
            "lock": lock,
            "friend_ids": friend_ids,
            "enemy_ids": enemy_ids,
        }
        return lock

    def _can_acquire(self, id: str):
        lock_state = self._input_lock_states[id]
        if self.strategy == "all_keys":
            return True
        elif self.strategy == "adjacent_lockout":
            return not any(
                [
                    self._input_lock_states[enemy_id]["lock"].is_acquired
                    for enemy_id in lock_state["enemy_ids"]
                ]
            )
        elif self.strategy == "single_key":
            return not any(
                [
                    other_lock_state["lock"].is_acquired
                    and other_id != id
                    and other_id not in lock_state["friend_ids"]
                    for other_id, other_lock_state in self._input_lock_states.items()
                ]
            )
        else:
            raise ValueError(f"unknown key safety strategy: {self.strategy}")


_KeyMatrixCategory = TypeVar("_KeyMatrixCategory", bound=Enum)


# One for each key direction. The states of lights on the same key get grouped
# together and linked up.
class LightCategory(Enum):
    # "Real" light that sends CC messages.
    default = "default"
    # Non-CC-sending lights that propagate colors to the group.
    silent_1 = "silent_1"
    silent_2 = "silent_2"
    silent_3 = "silent_3"


class Orientation(Enum):
    horizontal = "horizontal"
    vertical = "vertical"


class Elements(ElementsBase):
    @depends(configuration=None)
    def __init__(self, *a, configuration: Optional["Configuration"], **k):
        super().__init__(*a, **k)
        assert configuration
        self._configuration = configuration

        self._create_nav_buttons()
        self._create_key_buttons()
        self._create_pressure_sliders()
        self._create_xy_sliders()
        self._create_incremental_sliders()
        self._create_expression_slider()
        self._create_display()
        self._create_sysex()

    # Add a matrix with a factory that receives (row, col) instead of a single
    # identifier. This creates:
    #
    # - {base_name}: the main matrix element
    # - {base_name}_raw: a flattened array of the elements created by the factory
    # - grid_{base_name}: a submatrix corresponding to the left four columns of keys on
    #   the SoftStep.
    # - grid_{top|bottom|left|right}_{base_name}: submatrices for sections of the grid.
    #
    # If a categories list is provided, these objects (other than the raw elements) will
    # also be created for each category, e.g. {category.name}_{base_name},
    # grid_{category.name}_{base_name}.
    #
    # The return value is an object like:
    #
    #   { None: all_categories_matrix, category_1_name: category_1_matrix, ... }
    # jk
    def add_key_matrix(
        self,
        base_name: str,
        element_factory: Callable[[int, int], ControlElement],
        # If provided, interleave multiple elements at each step. Use this for XY
        # controls which have more than one element per key, for example. The
        # category's corresponding attrs object will be provided to the factory.
        categories: Optional[Collection[Tuple[_KeyMatrixCategory, dict]]] = None,
        *a,
        **k,
    ) -> Dict[Optional[_KeyMatrixCategory], ButtonMatrixElement]:
        def create_element(identifier: Tuple[int, int, dict], *a, **k):
            row, col, kwargs = identifier
            return element_factory(row, col, *a, **kwargs, **k)

        def name_factory(name: str, col: int, row: int):
            category_modifier = (
                ""
                if categories is None
                else f"{list(categories)[col % len(categories)][0].name}_"
            )
            # Match the default behavior, but include the current category modifier.
            return f"{category_modifier}{name}_{row}_{col}"

        # Create the main matrix.
        identifiers = [
            list(
                flatten(
                    [
                        [
                            (row, col, category[1])
                            for category in (categories or [(None, {})])
                        ]
                        for col in range(NUM_COLS)
                    ]
                )
            )
            for row in range(NUM_ROWS)
        ]

        self.add_matrix(
            *a,
            identifiers=identifiers,
            base_name=base_name,
            element_factory=create_element,
            name_factory=name_factory,
            **k,
        )

        # The add_matrix helper adds fields directly to this object.
        matrix: ButtonMatrixElement = getattr(self, base_name)

        # Add grid submatrices for a matrix that spans the whole controller.
        def add_submatrices(
            matrix: ButtonMatrixElement,
            controls_per_key: int,
            category_name: Optional[_KeyMatrixCategory] = None,
        ):
            category_base_name = f"{'' if category_name is None else f'{category_name.name}_'}{base_name}"
            grid_submatrix_name = f"grid_{category_base_name}"

            # Full grid.
            self.add_submatrix(
                matrix,
                grid_submatrix_name,
                columns=(0, NUM_GRID_COLS * controls_per_key),
            )
            grid: ButtonMatrixElement = getattr(self, grid_submatrix_name)

            # Segments.
            for segment_name, attrs in {
                "top": {"rows": (0, 1)},
                "bottom": {"rows": (1, 2)},
                "left": {"columns": (0, int(NUM_GRID_COLS * controls_per_key / 2))},
                "right": {
                    "columns": (
                        int(NUM_GRID_COLS * controls_per_key / 2),
                        NUM_GRID_COLS * controls_per_key,
                    )
                },
            }.items():
                segment_submatrix_name = f"grid_{segment_name}_{category_base_name}"
                self.add_submatrix(grid, segment_submatrix_name, **attrs)

            # Flat 1x8 version.
            wide_rows = [list(flatten(grid._orig_buttons))]
            wide_grid = ButtonMatrixElement(rows=wide_rows)
            self.add_submatrix(wide_grid, f"grid_wide_{category_base_name}")

        # Add grid submatrices for the main matrix, e.g. grid_left_{base_name}.
        add_submatrices(matrix, 1 if categories is None else len(categories))
        results: Dict[Optional[_KeyMatrixCategory], ButtonMatrixElement] = {}
        results[None] = matrix

        # Create submatrices for each category, and add their own grid submatrices, e.g
        # grid_left_{category_name}_{base_name}.
        if categories is not None:
            for index, category in enumerate(categories):
                category_name: _KeyMatrixCategory = category[0]
                category_submatrix_name = f"{category_name.name}_{base_name}"
                # Create the submatrix manually, since the helper doesn't accept
                # slices. This slices the matrix columns in steps of the number of
                # categories.
                category_submatrix = matrix.submatrix[index :: len(categories), :]
                # Now add the submatrix using the built-in helper for automatic property
                # name generation and any other boilerplate.
                self.add_submatrix(category_submatrix, category_submatrix_name)
                category_submatrix_from_prop: ButtonMatrixElement = getattr(
                    self, category_submatrix_name
                )

                results[category_name] = category_submatrix_from_prop

                add_submatrices(
                    getattr(self, category_submatrix_name), 1, category_name
                )

        return results

    def _get_cc_for_key(self, row: int, col: int, direction: KeyDirection):
        return get_cc_for_key(row=row, col=col, direction=direction)

    def _get_cc_for_nav(self, direction: KeyDirection):
        return get_cc_for_nav(direction)

    # Get the physical key number - 1, i.e. the key's CC offset for setting LEDs.
    def _get_key_for_light(self, row: int, col: int):
        inverted_row = NUM_ROWS - row - 1
        return (col + NUM_COLS * inverted_row) % (NUM_ROWS * NUM_COLS)

    @lazy_attribute
    def key_safety_manager(self):
        return KeySafetyManager("all_keys")

    def _key_safety_manager_lock_id(
        self, row: int, col: int, key_direction: KeyDirection
    ):
        return f"{row}_{col}_{key_direction.value}"

    # Matrices of raw input elements for each key direction.
    @lazy_attribute
    def _key_inputs(
        self,
    ) -> Dict[Optional[KeyDirection], ButtonMatrixElement]:
        def create_input(
            row: int, col: int, key_direction: Optional[KeyDirection] = None, *a, **k
        ):
            assert key_direction
            input_lock_id = self._key_safety_manager_lock_id(row, col, key_direction)

            # No issue with adding our own ID here.
            friend_ids = [
                self._key_safety_manager_lock_id(row, col, key_direction)
                for key_direction in KeyDirection
            ]

            # Get inputs for adjacent keys.
            enemy_ids: List[str] = []
            for enemy_row in range(row - 1, row + 2):
                for enemy_col in range(col - 1, col + 2):
                    if (
                        0 <= enemy_row < NUM_ROWS
                        and 0 <= enemy_col < NUM_COLS
                        and not (enemy_row == row and enemy_col == col)
                    ):
                        for enemy_key_direction in KeyDirection:
                            enemy_ids.append(
                                self._key_safety_manager_lock_id(
                                    enemy_row, enemy_col, enemy_key_direction
                                )
                            )

            input_lock = self.key_safety_manager.create_input_lock(
                input_lock_id, friend_ids=friend_ids, enemy_ids=enemy_ids
            )
            cc_identifier = self._get_cc_for_key(row, col, key_direction)
            return PressureInputElement(
                *a,
                identifier=cc_identifier,
                input_lock=input_lock,
                is_feedback_enabled=False,
                **k,
            )

        return self.add_key_matrix(
            base_name="key_inputs",
            element_factory=create_input,
            categories=[(k, dict(key_direction=k)) for k in KeyDirection],
            msg_type=MIDI_CC_TYPE,
        )

    @lazy_attribute
    def _lights(self) -> Dict[Optional[LightCategory], ButtonMatrixElement]:
        light_groups: Dict[int, Dict[int, LightGroup]] = {}

        def create_light(row: int, col: int, *a, **k):
            key = self._get_key_for_light(row, col)
            light = LightElement(*a, key=key, **k)
            if row not in light_groups:
                light_groups[row] = {}
            if col not in light_groups[row]:
                light_groups[row][col] = LightGroup()
            light_groups[row][col].register(light)
            return light

        return self.add_key_matrix(
            base_name="lights",
            element_factory=create_light,
            # Create multiple light elements for each LED, which will be managed as a group.
            categories=[
                # Lights from any non-default categories won't actually send any
                # messages, but setting their color will affect the group color overall.
                (light_category, {"silent": light_category != LightCategory.default})
                for light_category in LightCategory
            ],
            is_feedback_enabled=False,
        )

    # Create a combo element from all the inputs at a given position.
    def _create_combo_element(
        self,
        factory: Callable[..., ControlElement],
        row: int,
        col: int,
        light_category: LightCategory = LightCategory.default,
        key_directions: Iterable[KeyDirection] = list(KeyDirection),
        # Discard parameters from `add_matrix` that aren't recognized by `ComboElement`.
        channel=0,  # noqa: ARG002
        *a,
        **k,
    ):
        # The button matrix has a `get_button` method, but it returns `None` unless the
        # element is bound, so we have to look into the `_orig_buttons` (or access the
        # `{matrix}_raw` property, but that makes the lazy init more complicated).
        def get_raw_button(matrix: ButtonMatrixElement, row: int, col: int):
            return matrix._orig_buttons[row][col]

        inputs = [
            get_raw_button(self._key_inputs[key_direction], row, col)
            for key_direction in key_directions
        ]
        light = None
        if light_category:
            light = get_raw_button(self._lights[light_category], row, col)

        return factory(*a, control_elements=inputs, light=light, **k)

    def _create_nav_buttons(self):
        # Nav buttons.
        for key_direction in KeyDirection:
            base_name = f"nav_{key_direction.name}"
            input_name = f"{base_name}_input"

            # Raw input element.
            self.add_element(
                input_name,
                PressureInputElement,
                is_feedback_enabled=False,
                identifier=self._get_cc_for_nav(key_direction),
                channel=self._global_channel,
                msg_type=MIDI_CC_TYPE,
            )

            # High-level button element.
            self.add_element(
                f"nav_{key_direction.name}_button",
                LightedButtonElement,
                control_elements=[getattr(self, input_name)],
            )

    def _create_key_buttons(self):
        # Button matrices for full keys and individual key corners.
        for name, kwargs in (
            ("buttons", None),
            *[
                (
                    f"{key_direction.name}_buttons",
                    dict(
                        key_directions=[key_direction],
                        # Group the lights for all corners.
                        light_category=list(LightCategory)[index],
                    ),
                )
                for index, key_direction in enumerate(list(KeyDirection))
            ],
        ):
            self.add_key_matrix(
                base_name=name,
                element_factory=partial(
                    self._create_combo_element, LightedButtonElement
                ),
                categories=None,
                **(kwargs or {}),
            )

    def _create_pressure_sliders(self):
        # Pressure sliders.
        for is_latching in [True, False]:
            base_name = "pressure"
            attrs: Dict[str, Any] = {}
            if is_latching:
                base_name = f"{base_name}_latching"
                attrs["latch_delay"] = LATCH_DELAY
            base_name = f"{base_name}_sliders"
            self.add_key_matrix(
                base_name=base_name,
                element_factory=partial(
                    self._create_combo_element,
                    PressureSliderElement,
                    max_input=self._configuration.full_pressure,
                    **attrs,
                ),
            )

    @lazy_attribute
    def _orientation_categories(self):
        # Categories for controls with horizontal and vertical variants.
        return (
            (
                Orientation.horizontal,
                dict(
                    key_directions=[KeyDirection.left, KeyDirection.right],
                    light_category=LightCategory.default,
                ),
            ),
            (
                Orientation.vertical,
                dict(
                    key_directions=[KeyDirection.down, KeyDirection.up],
                    light_category=LightCategory.silent_1,
                ),
            ),
        )

    def _create_xy_sliders(self):
        # XY sliders.
        for is_latching in [True, False]:
            # Create a big matrix of elements in both orientations.
            base_name = "xy"
            attrs: Dict[str, Any] = {}
            if is_latching:
                base_name = f"{base_name}_latching"
                attrs["latch_delay"] = LATCH_DELAY
            base_name = f"{base_name}_sliders"

            def create_xy_element(control_elements, *a, **k):
                assert len(control_elements) == 2
                return XYSliderElement(
                    *a,
                    left_input=control_elements[0],
                    right_input=control_elements[1],
                    # This would get confusing with two parameters changing.
                    enable_popups=False,
                    **k,
                )

            self.add_key_matrix(
                base_name=base_name,
                element_factory=partial(
                    self._create_combo_element,
                    create_xy_element,
                    **attrs,
                ),
                categories=self._orientation_categories,
            )

    def _create_incremental_sliders(self):
        def create_incremental_slider_element(control_elements, *a, **k):
            assert len(control_elements) == 2
            return IncrementalSliderElement(
                *a, left_input=control_elements[0], right_input=control_elements[1], **k
            )

        # Incremental sliders.
        self.add_key_matrix(
            base_name="incremental_sliders",
            element_factory=partial(
                self._create_combo_element,
                create_incremental_slider_element,
                scroll_rate=self._incremental_scroll_rate,
            ),
            categories=self._orientation_categories,
        )

    def _create_expression_slider(self):
        base_name = "expression_slider"
        raw_input_name = f"{base_name}_input"
        self.add_element(
            raw_input_name,
            partial(
                PressureInputElement,
                identifier=86,
                msg_type=MIDI_CC_TYPE,
                channel=self._global_channel,
            ),
        )
        raw_input = getattr(self, raw_input_name)
        self.add_element(
            base_name,
            partial(
                ExpressionSliderElement,
                raw_input,
                # These get enabled manually in the expression pedal
                # mode. They're distracting if they appear elsewhere.
                enable_popups=False,
                min_input=self._configuration.expression_pedal_range[0],
                max_input=self._configuration.expression_pedal_range[1],
                movement_threshold=self._configuration.expression_pedal_movement_threshold,
            ),
        )

    def _create_display(self):
        self.display = DisplayElement()

    def _create_sysex(self):
        # Sysex toggles for device functions.
        self.add_element(
            "backlight_sysex",
            SysexToggleElement,
            on_messages=[sysex.SYSEX_BACKLIGHT_ON_REQUEST],
            off_messages=[sysex.SYSEX_BACKLIGHT_OFF_REQUEST],
            optimized=True,
            default_value=False,
        )

        self.add_element(
            "standalone_sysex",
            SysexToggleElement,
            on_messages=sysex.SYSEX_STANDALONE_MODE_ON_REQUESTS,
            off_messages=sysex.SYSEX_STANDALONE_MODE_OFF_REQUESTS,
            optimized=True,
            default_value=True,
        )

        # Sysex input used by the test mode to check whether the control surface is
        # responsive.
        self.add_element(
            "ping_sysex",
            SysexButtonElement,
            sysex_identifier=sysex.SYSEX_PING_REQUEST,
            send_message_generator=lambda _: sysex.SYSEX_PING_RESPONSE,
        )

    def _incremental_scroll_rate(self, value: int) -> float:
        scroll_rate_bounds = self._configuration.incremental_steps_per_second
        full_pressure = self._configuration.full_pressure

        # Add a buffer in the low pressure range before we start
        # increasing the scroll rate.
        scroll_increase_start = full_pressure * 0.3
        return (
            linear(
                scroll_rate_bounds[0],
                scroll_rate_bounds[1],
                clamp(
                    (value - scroll_increase_start)
                    / (full_pressure - scroll_increase_start),
                    0,
                    1,
                ),
            )
            / 127
        )
