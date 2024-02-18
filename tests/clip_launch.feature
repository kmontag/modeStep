Feature: Clip launch grid
  Scenario: Using a 1x8 clip launch grid
    Given the wide_clip_launch set is open
    And the SS2 is initialized

    # Make sure track 1 is selected, to avoid any inconsistencies if
    # auto-arm is enabled by some other connected device. Note the
    # selected track is saved somewhere in Live's preferences, rather
    # than in the .als file itself, so when we open the file, any of
    # the 10 tracks (7 + sends + master) might be selected.
    When I press nav left
    And I press nav left
    And I press nav left
    And I press nav left
    And I press nav left
    And I press nav left
    And I press nav left
    And I press nav left
    And I press nav left
    # After 9 presses, track 1 is now selected, but the popup might
    # have already scrolled or disappeared. Change back and forth
    # between track 1 and 2 so we can sanity check the selected track
    # name.
    And I press nav right
    And I press nav left
    Then the display should be "1-MI"

    When I press key 0
    Then the mode select screen should be active
    And light 5 should be blinking red

    When I press key 5
    Then the display should be "Clip"
    # Scene 1 should have clips on tracks 1 and 6.
    And light 6 should be solid green
    And lights 7-9 should be off
    And light 1 should be off
    And light 2 should be solid green
    And lights 3-4 should be off

    # Scene 2 should just have a clip on track 3.
    When I press nav down
    Then the display should be "_  2"
    # Light 6 might be off or red, depending on the auto-arm state;
    # just skip checking it.
    And light 7 should be off
    And light 8 should be solid green
    And light 9 should be off
    And lights 1-4 should be off
