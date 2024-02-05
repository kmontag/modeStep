Feature: Clip launch grid
  Scenario: Using a 1x8 clip launch grid
    Given the wide_clip_launch set is open
    And the SS2 is initialized

    When I press key 0
    Then the mode select screen should be active
    And light 5 should be blinking red

    When I press key 5
    Then the display should be "Clip"
    # Scene 1 should have clips on tracks 1 and 6
    And light 6 should be solid green
    And lights 7-9 should be off
    And light 1 should be off
    And light 2 should be solid green
    And lights 3-4 should be off

    # Scene 2 should just have a clip on track 3
    When I press nav down
    Then the display should be "_  2"
    And lights 6-7 should be off
    And light 8 should be solid green
    And light 9 should be off
    And lights 1-4 should be off