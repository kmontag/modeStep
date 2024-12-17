Feature: Configuration settings (besides overrides)
  Scenario: Alternate initial mode and initial previous mode
    Given the SS2 is connected
    And the alt_initial_mode set is open
    And the SS2 is initialized

    Then the display should be "Util"
    And light 8 should be off
    And light 0 should be solid green

    When I long-press key 0
    Then the display should be "XY"
