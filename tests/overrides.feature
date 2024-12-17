Feature: Overrides from config
  Background:
    Given the SS2 is connected
    And the overrides set is open
    And the SS2 is initialized

  Scenario: Element overrides
    Then the display should be "Trns"

    # Key 2 should be overridden with left/right session ring
    # navigation, and nothing on the vertical axis.
    And light 2 should be solid yellow

    # Start playing, so that if there's a problem and button 2's
    # normal function (arrangement record) gets triggered somehow,
    # we'll push unsaved changes to the set to signal that something
    # went wrong.
    When I press key 3
    Then light 3 should be blinking green

    # Try navigating left and right.
    When I press key 2 right
    Then the display should be "|  2"

    When I press key 2 left
    Then the display should be "|  1"

    # Make sure the vertical directions don't do anything.
    When I wait for the popup to clear
    And I press key 2 down
    Then the display should be "Trns"

    When I press key 2 up
    Then the display should be "Trns"

    # Make sure the navigation is actually working by checking one of
    # the track controls presets.
    When I press key 0
    Then the mode select screen should be active

    When I press key 1
    Then lights 6-9 should be solid
    And lights 1-3 should be solid
    And light 4 should be off

    # Go back to transport mode and navigate to the right.
    When I press key 0
    And I press key 9
    And I press key 2 right
    # Go back to the preset and check that it's been updated.
    And I press key 0
    And I press key 1

    Then lights 6-9 should be solid
    And lights 1-2 should be solid
    And lights 3-4 should be off

    # Go back to transport to stop playing.
    When I press key 0
    And I press key 9
    And I press key 3

    Then light 3 should be solid green

  Scenario: Key safety strategy override: adjacent lockout
    Then the display should be "Trns"

    When I press key 0
    Then the mode select screen should be active

    # adjacent_lockout safety strategy.
    When I press key 1
    Then the display should be "SeL"

    # Select track 6 and check light state.
    When I press key 2
    Then lights 6-9 should be solid red
    And light 1 should be solid red
    And light 2 should be solid green
    And light 3 should be solid red
    And light 4 should be off

    # Try pressing all adjacent keys while holding this one.
    When I hold key 2
    Then light 2 should be solid green

    When I press key 8
    And I hold key 3
    And I press key 7
    And I hold key 6
    And I release key 3
    And I press key 1
    And I release key 6
    # Make sure the selection didn't change.
    Then light 2 should be solid green

    # Pressing a non-adjacent key should be switch the selection.
    When I press key 9
    Then light 9 should be solid green
    And light 2 should be solid red

    When I release key 2
    Then light 9 should be solid green

    # Sanity check that we can still change the selection.
    When I press key 3
    Then light 3 should be solid green
    And light 9 should be solid red

  Scenario: Key safety strategy override: single key
    Then the display should be "Trns"

    When I press key 0
    Then the mode select screen should be active

    # single_key safety strategy.
    When I press key 2
    Then the display should be "SeL"

    # Select track 1 and check light state.
    When I press key 6
    Then light 6 should be solid green
    And lights 7-9 should be solid red
    And lights 1-3 should be solid red
    And light 4 should be off

    # Try pressing all other keys while holding this one.
    When I hold key 6
    Then light 6 should be solid green

    When I press key 1
    And I hold key 2
    And I press key 5
    And I press key 4
    And I release key 2
    And I press key 3
    And I hold key 7
    And I press key 9
    And I release key 7
    And I press key 8
    Then light 6 should be solid green

    When I press key 0
    Then light 6 should be solid green
    And the display should be "SeL"

    # Make sure we can still change the selection.
    When I release key 6
    Then light 6 should be solid green

    When I press key 3
    Then light 3 should be solid green
    And light 6 should be solid red

  Scenario: Key safety strategy override: all keys
    Then the display should be "Trns"

    When I press key 0
    Then the mode select screen should be active

    # all_keys safety strategy
    When I press key 3
    Then the display should be "SeL"

    # Select track 6 and check light state.
    When I press key 2
    Then lights 6-9 should be solid red
    And light 1 should be solid red
    And light 2 should be solid green
    And light 3 should be solid red
    And light 4 should be off

    # Press a bunch of keys while holding key 2, and make sure the
    # selection changes.
    When I hold key 2
    Then light 2 should be solid green

    When I hold key 3
    Then light 3 should be solid green
    And light 2 should be solid red

    When I press key 6
    Then light 6 should be solid green
    And light 3 should be solid red

    When I release key 3
    Then light 3 should be solid red
    And light 6 should be solid green

    When I press key 9
    Then light 9 should be solid green
    And light 3 should be solid red

    # Make sure we can get to the mode select screen while holding the
    # key.
    When I press key 0
    Then the mode select screen should be active

    When I release key 2
    Then the mode select screen should be active

    When I press key 3
    Then the display should be "SeL"
    And light 9 should be solid green

  Scenario: Mode overrides
    Then the display should be "Trns"

    When I press key 0
    Then the mode select screen should be active
    # Disabled key.
    And light 8 should be off

    When I press key 8
    Then the mode select screen should be active
    And light 6 should be blinking yellow
    And light 7 should be blinking green
    And light 8 should be off

    # Overridden key with alternate long-press mode.
    When I press key 6
    Then the display should be "Util"

    When I press key 0
    Then the mode select screen should be active

    When I long-press key 6
    Then the display should be "Incr"

    When I long-press key 0
    Then the display should be "Util"

    When I press key 0
    Then the mode select screen should be active

    # Key with no alternate long-press mode.
    When I press key 7
    Then the display should be "Expr"

    When I press key 0
    Then the mode select screen should be active

    When I long-press key 7
    Then the display should be "Expr"

  Scenario: Track control overrides
    Then the display should be "Trns"

    When I press key 0
    Then the mode select screen should be active

    # Track-select controls with play button as action.
    When I press key 3
    Then the display should be "SeL"
    And lights 6-9 should be solid
    And lights 1-3 should be solid
    And light 4 should be off
    And light 5 should be solid green

    # Check that a track can be selected.
    When I press key 6
    Then light 6 should be solid green
    And lights 7-9 should be solid red
    And lights 1-3 should be solid red
    And light 4 should be off

    # Test that the play button works.
    When I press key 5
    Then light 5 should be blinking green

    When I press key 5
    Then light 5 should be solid green

    When I press key 0
    Then the mode select screen should be active

    # Combo controls with backlight as an action.
    When I press key 4
    Then the display should be "MuSt"
    And lights 6-9 should be solid green
    And lights 1-4 should be solid yellow
    And light 5 should be solid red

    When I press key 5
    Then light 5 should be solid green
    And the display should be "+BaK"
    And the backlight should be on

    # Make sure the action gets preserved when we edit the controls.
    When I press key 0
    And I long-press key 4
    Then the display should be "4Top"

    When I press key 4
    And I press key 4
    Then the display should be "Mute"
    And light 5 should be solid green

    When I press key 5
    Then light 5 should be solid red
    And the display should be "-BaK"
    And the backlight should be off

    # Disabled controls.
    When I press key 0
    Then the mode select screen should be active
    And light 5 should be off

    When I press key 5
    Then the mode select screen should be active
    And light 5 should be off

    # Make sure we can still edit them.
    When I long-press key 5
    Then the display should be "5Top"

    When I press key 1
    And I press key 1
    Then The display should be "Vol"
    And lights 6-9 should be solid yellow
    And lights 1-3 should be solid yellow
    And light 4 should be off
    # Session record by default.
    And light 5 should be solid red
