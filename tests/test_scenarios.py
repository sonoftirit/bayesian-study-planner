"""Checks the predefined demo scenarios and the actions the planner picks."""

import pytest

from planner.decision import best_action, validate_evidence
from planner.scenarios import SCENARIOS

# What the assignment expects for each demo student. These are checked against
# the model's output; the planner itself never looks at this table.
EXPECTED_ACTIONS = {
    "struggling": "Intense",
    "average": "Light",
    "advanced": "Rest",
}

# The winner must beat the runner-up by at least this many utility points, so a
# small change to one probability cannot quietly flip a demo result.
MIN_MARGIN = 1.0

DIFFICULTIES = ["Difficulty_A", "Difficulty_B", "Difficulty_C"]


def test_the_three_demo_scenarios_exist():
    assert set(SCENARIOS) == set(EXPECTED_ACTIONS)


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_evidence_is_valid(name):
    validate_evidence(SCENARIOS[name])


def test_scenarios_match_the_assignment_profiles():
    struggling = SCENARIOS["struggling"]
    average = SCENARIOS["average"]
    advanced = SCENARIOS["advanced"]

    assert all(struggling[d] == "Hard" for d in DIFFICULTIES)
    assert struggling["DaysLeft"] == "Few"
    assert {average[d] for d in DIFFICULTIES} == {"Easy", "Hard"}  # mixed
    assert average["DaysLeft"] == "Many"
    assert all(advanced[d] == "Easy" for d in DIFFICULTIES)
    assert advanced["DaysLeft"] == "Many"


@pytest.mark.parametrize(("name", "expected"), EXPECTED_ACTIONS.items())
def test_scenario_gets_the_expected_action(name, expected):
    assert best_action(SCENARIOS[name]).action == expected


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario_winner_is_clear(name):
    eus = sorted(best_action(SCENARIOS[name]).expected_utilities.values())
    assert eus[-1] - eus[-2] >= MIN_MARGIN
