Feature: Track controls modes
  Background:
    Given the SS2 is connected
    And the default set is open
    And the SS2 is initialized

  Scenario: Volume buttons
    When I press key 0
    Then the mode select screen should be active

    When I press key 1
    Then the display should be "Vol"
    And lights 6-9 should be solid yellow
    And lights 1-3 should be solid yellow
    And light 4 should be off

    When I press nav right
    Then lights 6-9 should be solid yellow
    And lights 1-2 should be solid yellow
    And lights 3-4 should be off

  Scenario: Configuring single track controls
    When I press key 0
    Then the mode select screen should be active

    # Edit track controls 1.
    When I long-press key 1
    Then the display should be "1Top"
    And light 7 should be off
    And lights 1-4 should be blinking
    And light 5 should be solid

    # Choose a double select control.
    When I press key 6
    Then the display should be "SeL"

    When I wait for the popup to clear
    Then the display should be "1Bot"

    When I press key 6
    Then the display should be "SeL"
    And lights 6-9 should be solid
    And lights 1-3 should be solid
    And light 4 should be off
    And light 5 should be solid red

  Scenario: Configuring double track controls
    When I press key 0
    Then the mode select screen should be active

    # Edit slot 3.
    When I long-press key 3
    Then the display should be "3Top"

    When I press key 3
    Then the display should be "Solo"

    When I wait for the popup to clear
    Then the display should be "3Bot"

    When I press key 4
    # No popup on exit.
    Then the display should be "SoMu"
    And lights 6-9 should be solid red
    And lights 1-4 should be solid green
    And light 5 should be solid red

    # Scroll session ring.
    When I press nav right
    And I press nav right
    And I press nav right
    And I press nav right
    Then the display should be "|  5"
    And lights 6-8 should be solid red
    And light 9 should be off
    And lights 1-3 should be solid green
    And light 4 should be off

    # Try entering back into the mode.
    When I press key 0
    And I press key 3
    Then the display should be "SoMu"

  Scenario Outline: Configuring track control actions by <gesture>ing the edit action key.
    When I press key 0
    Then the mode select screen should be active

    # Edit track controls 4.
    When I long-press key 4
    Then the display should be "4Top"

    # Open action select.
    When I <gesture> key 5
    Then the display should be "4<desc>"
    And lights 6-9 should be blinking
    And lights 1-5 should be blinking

    # Select the action from the example.
    When I press key <action_key>
    Then the display should be "<action_text>"

    # Make sure we're back at the top edit screen.
    When I wait for the popup to clear
    Then the display should be "4Top"

    # Select top.
    When I press key 8
    Then the display should be "Stop"

    When I wait for the popup to clear
    Then the display should be "4Bot"

    # Select bottom and return to main track controls.
    When I press key 8
    Then the display should be "Stop"
    And lights 6-9 should be solid
    And lights 1-3 should be solid
    And light 4 should be off
    # Check that the action was set.
    And light 5 should be <init_color>

    # Make sure the action works.
    When I press key 5
    Then light 5 should be <pressed_color>

    When I press key 5
    Then light 5 should be <init_color>

  Examples:
    | gesture    | desc | action_key | action_text | init_color  | pressed_color  |
    | press      | Act  |          3 | Play        | solid green | blinking green |
    | long-press | Utl  |          6 | BaK         | solid red   | solid green    |

  # Make sure popups work for all actions.
  Scenario Outline: Selecting any action after <gesture>ing the edit action key
    When I press key 0
    Then the mode select screen should be active

    # Make sure all actions show the right popup.
    When I long-press key 1
    Then the display should be "1Top"

    When I <gesture> key 5
    And I press key 1
    Then the display should be "<k1>"

    When I <gesture> key 5
    And I press key 2
    Then the display should be "<k2>"

    When I <gesture> key 5
    And I press key 3
    Then the display should be "<k3>"

    When I <gesture> key 5
    And I press key 4
    Then the display should be "<k4>"

    When I <gesture> key 5
    And I press key 5
    Then the display should be "<k5>"

    When I <gesture> key 5
    And I press key 6
    Then the display should be "<k6>"

    When I <gesture> key 5
    And I press key 7
    Then the display should be "<k7>"

    When I <gesture> key 5
    And I press key 8
    Then the display should be "<k8>"

    When I <gesture> key 5
    And I press key 9
    Then the display should be "<k9>"

    # Make sure we cancel out of action selection into the correct
    # place.
    When I wait for the popup to clear
    Then the display should be "1Top"

    When I <gesture> key 5
    And I press key 0
    Then the display should be "1Top"

    When I press key 4
    And I wait for the popup to clear
    Then the display should be "1Bot"

    When I <gesture> key 5
    And I press key 0
    Then the display should be "1Bot"

  # This will need to change if the layouts or notification texts
  # change.
  Examples:
    | gesture    | k1   | k2   | k3   | k4   | k5   | k6   | k7   | k8   | k9   |
    | press      | LnSc | Rec  | Play | Met  | SRec | StAl | ArmT | Aut  | TapT |
    | long-press | AAr  | Undo | CpMD | CpSc | SRec | BaK  | Redo | Quan | NwCl |

  Scenario: Navigating through track control edit screens
    When I press key 0
    Then the mode select screen should be active

    # Edit track controls 2.
    When I long-press key 2
    Then the display should be "2Top"

    # Exit to the mode screen.
    When I press key 0
    Then the mode select screen should be active

    # Go back to editing.
    When I long-press key 2
    Then the display should be "2Top"

    # Start editing action, then cancel.
    When I press key 5
    Then the display should be "2Act"

    When I press key 0
    Then the display should be "2Top"

    # Select a top control, then cancel.
    When I press key 3
    Then the display should be "Solo"

    When I press key 0
    Then the display should be "2Top"

    # Select an action.
    When I long-press key 5
    Then the display should be "2Utl"
    And light 4 should be blinking green

    When I press key 4
    Then the display should be "CpSc"

    When I wait for the popup to clear
    Then the display should be "2Top"

    # Exit, select controls, and make sure the action wasn't preserved
    # after exit.
    When I press key 0
    Then the mode select screen should be active

    When I long-press key 2
    Then the display should be "2Top"

    When I press key 1
    Then the display should be "Vol"

    When I press key 3
    Then the display should be "VoSo"
    # Check that the action was cleared, this would be green otherwise.
    And light 5 should be solid red
    # Check main lights too.
    And lights 6-9 should be solid yellow
    And lights 1-4 should be solid red

    # Re-enter the edit window and select a top action.
    When I press key 0
    Then the mode select screen should be active

    When I long-press key 2
    Then the display should be "2Top"

    When I press key 3
    Then the display should be "Solo"

    When I wait for the popup to clear
    Then the display should be "2Bot"

    # Set the action, then press cancel and make sure we get back to
    # the top edit window.
    When I press key 5
    Then the display should be "2Act"
    And light 5 should be blinking red

    When I press key 5
    Then the display should be "SRec"

    When I press key 0
    Then the display should be "2Top"

    # Select a control and get to the bottom window.
    When I press key 9
    Then the display should be "Clip"

    # Start setting another action, but cancel and make sure we get
    # back to the bottom edit window.
    When I long-press key 5
    Then the display should be "2Utl"

    When I press key 0
    Then the display should be "2Bot"

    # Cancel back to the mode select screen.
    When I press key 0
    Then the display should be "2Top"

    When I press key 0
    Then the mode select screen should be active

    # Make sure the config wasn't changed.
    When I press key 2
    Then the display should be "VoSo"
    And light 5 should be solid red

  Scenario: Deleting track controls
    When I press key 0
    Then the mode select screen should be active

    When I long-press key 5
    Then the display should be "5Top"

    # Wait to trigger the delete warning, then release the key.
    When I hold key 0
    And I wait to trigger a long-press
    Then light 0 should be fast-blinking red

    When I release key 0
    Then light 0 should be solid red
    And the display should be "5Top"

    # Go to the bottom controls and actually perform the delete.
    When I press key 1
    Then the display should be "Vol"

    When I hold key 0
    And I wait to trigger a long-press
    Then light 0 should be fast-blinking red

    # Wait for the delete.
    When I wait for 0.8s
    Then light 0 should be solid red
    And the display should be "DeL5"
    And light 5 should be off

    When I release key 0
    And I wait for the popup to clear
    Then the mode select screen should be active

    # Make sure nothing happens when we try to select the mode.
    When I press key 5
    Then the mode select screen should be active
    And light 5 should be off

    # Make sure we can recreate the mode.
    When I long-press key 5
    Then the display should be "5Top"

    When I press key 4
    And I press key 4
    Then the display should be "Mute"
    And lights 6-9 should be solid green
    And lights 1-3 should be solid green
    And light 4 should be off
    # Session record by default.
    And light 5 should be solid red
