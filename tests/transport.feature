Feature: Basic usage
  Background:
    Given the SS2 is connected
    And the default set is open
    And the SS2 is initialized

  Scenario: Toggling transport controls
    Then the display should be "Trns"
    And key 4 should toggle the "Met" status
    And key 8 should toggle the "Aut" status

  Scenario: Playing and stopping the transport
    Then the display should be "Trns"

    # Play selected scene.
    And light 1 should be solid green
    # Play/stop.
    And light 3 should be solid green
    # Stop all clips.
    And light 6 should be solid red

    # Toggle main play/stop.
    When I press key 3
    Then light 3 should be blinking green
    And light 1 should be solid green
    And light 6 should be solid red

    When I press key 3
    Then light 3 should be solid green

    # Select the first track for a more consistent appearance regardless of whether
    # auto-arm is enabled (since the auto-arm state might also be controlled by other
    # surfaces).
    When I hold nav left
    And I wait for 3.0s
    And I release nav left
    And I press nav right
    And I press nav left

    Then the display should be scrolling "1-MIDI"

    # Check that no clips are playing.
    When I press key 0
    Then the mode select screen should be active

    When I press key 5
    Then the display should be "Clip"

    And light 6 should be solid green
    And light 3 should be solid green
    # Light 1 might be red depending on the auto-arm state.
    And light 2 should be off
    And light 4 should be off
    And lights 7-9 should be off

    # Return to the transport mode.
    When I long-press key 0
    Then the display should be "Trns"
    And light 1 should be solid green
    And light 3 should be solid green

    # Play the current scene (i.e. scene 1).
    When I press key 1
    Then light 1 should be solid green
    And light 3 should be blinking green
    And light 6 should be solid red
    And the display should be ">  1"

    # Check the clip view again.
    When I long-press key 0
    Then the display should be "Clip"
    And light 6 should be blinking green
    And light 3 should be solid green

    # Go back to transport mode.
    When I long-press key 0
    Then the display should be "Trns"

    # Select the next scene.
    When I press nav down
    Then the display should be "#  2"

    # Stop and start, so that the fast-blink shows up while the scene is waiting to
    # start after launching it.
    When I press key 3
    Then light 3 should be solid green
    When I press key 3
    Then light 3 should be blinking green

    When I press key 1
    Then light 1 should be fast-blinking green
    And the display should be ">  2"

    # Wait 4 beats at 120bpm, plus a buffer. After this, the scene should have been
    # triggered.
    When I wait for 3.0s
    Then light 1 should be solid green

    # Check that the playing clips have changed.
    When I long-press key 0
    Then the display should be "Clip"
    And light 6 should be solid green
    And light 3 should be blinking green

    When I long-press key 0
    Then the display should be "Trns"

    # Sanity check the transport button state again.
    And light 1 should be solid green
    And light 3 should be blinking green
    And light 6 should be solid red

    # Toggle play/pause again for more consistent timing to check the stop-clips blink.
    When I press key 3
    And I press key 3
    Then light 3 should be blinking green

    # Stop all clips.
    When I press key 6
    Then the display should be "StAl"
    And light 6 should be fast-blinking red

    When I wait for 3.0s
    Then light 6 should be solid red

    # Check that all clips have stopped.
    When I long-press key 0
    Then the display should be "Clip"
    And light 6 should be solid green
    And light 3 should be solid green

    # Switch back to transport mode and check that stop-clips now doesn't trigger a
    # blink.
    When I long-press key 0
    Then the display should be "Trns"
    And light 3 should be blinking green
    And light 6 should be solid red

    When I press key 6
    Then the display should be "StAl"
    And light 6 should be solid red

    # Stop the transport so we can close the set cleanly.
    When I press key 3
    Then light 3 should be solid green
