"""Predefined student profiles used for the demo and the results.

Each scenario is only evidence. The recommended action is never stored here:
it always comes from the network and the utility function.
"""

SCENARIOS = {
    # Every concept is hard and the exam is close.
    "struggling": {
        "Difficulty_A": "Hard",
        "Difficulty_B": "Hard",
        "Difficulty_C": "Hard",
        "DaysLeft": "Few",
    },
    # One hard concept among easy ones, with time to spare.
    "average": {
        "Difficulty_A": "Easy",
        "Difficulty_B": "Hard",
        "Difficulty_C": "Easy",
        "DaysLeft": "Many",
    },
    # Every concept is easy and the exam is far away.
    "advanced": {
        "Difficulty_A": "Easy",
        "Difficulty_B": "Easy",
        "Difficulty_C": "Easy",
        "DaysLeft": "Many",
    },
}
