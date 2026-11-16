"""Checks that inference results are valid and move in sensible directions."""

import pytest

from planner.decision import get_inference, query_outcomes
from planner.network import ACTIONS


def evidence(a="Easy", b="Easy", c="Easy", days_left="Many"):
    return {
        "Difficulty_A": a,
        "Difficulty_B": b,
        "Difficulty_C": c,
        "DaysLeft": days_left,
    }


def p_pass(outcomes):
    return outcomes[("Pass", "Low")] + outcomes[("Pass", "High")]


def p_high_stress(outcomes):
    return outcomes[("Pass", "High")] + outcomes[("Fail", "High")]


def test_result_has_all_four_outcomes():
    outcomes = query_outcomes(evidence(), "Light")
    assert set(outcomes) == {
        ("Pass", "Low"),
        ("Pass", "High"),
        ("Fail", "Low"),
        ("Fail", "High"),
    }


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("days_left", ["Few", "Many"])
def test_probabilities_sum_to_one(action, days_left):
    outcomes = query_outcomes(evidence("Hard", "Easy", "Hard", days_left), action)
    assert sum(outcomes.values()) == pytest.approx(1.0)
    assert all(0 <= p <= 1 for p in outcomes.values())


@pytest.mark.parametrize("action", ACTIONS)
def test_harder_concepts_lower_the_chance_of_passing(action):
    all_easy = p_pass(query_outcomes(evidence("Easy", "Easy", "Easy"), action))
    one_hard = p_pass(query_outcomes(evidence("Hard", "Easy", "Easy"), action))
    all_hard = p_pass(query_outcomes(evidence("Hard", "Hard", "Hard"), action))
    assert all_easy > one_hard > all_hard


@pytest.mark.parametrize("difficulty", ["Easy", "Hard"])
def test_intense_gives_higher_mastery_than_rest(difficulty):
    def p_mastered(action):
        result = get_inference().query(
            ["Mastery_A"],
            evidence={"Difficulty_A": difficulty, "Action": action},
            show_progress=False,
        )
        return result.get_value(Mastery_A="High")

    assert p_mastered("Intense") > p_mastered("Light") > p_mastered("Rest")


@pytest.mark.parametrize("action", ACTIONS)
def test_few_days_left_raises_stress(action):
    few = p_high_stress(query_outcomes(evidence(days_left="Few"), action))
    many = p_high_stress(query_outcomes(evidence(days_left="Many"), action))
    assert few > many


def test_intense_raises_the_chance_of_passing_for_hard_concepts():
    hard = evidence("Hard", "Hard", "Hard", "Few")
    assert p_pass(query_outcomes(hard, "Intense")) > p_pass(
        query_outcomes(hard, "Rest")
    )


def test_matches_a_hand_calculation():
    # All concepts Easy, Rest, Many days left. Each concept is mastered with
    # probability 0.88, and stress is High with probability 0.05.
    m = 0.88
    p_count = [
        (1 - m) ** 3,
        3 * m * (1 - m) ** 2,
        3 * m**2 * (1 - m),
        m**3,
    ]
    pass_low = [0.10, 0.35, 0.70, 0.95]
    pass_high = [0.05, 0.20, 0.55, 0.80]
    expected_pass_low = 0.95 * sum(
        p * q for p, q in zip(p_count, pass_low, strict=True)
    )
    expected_pass_high = 0.05 * sum(
        p * q for p, q in zip(p_count, pass_high, strict=True)
    )

    outcomes = query_outcomes(evidence(), "Rest")

    assert outcomes[("Pass", "Low")] == pytest.approx(expected_pass_low)
    assert outcomes[("Pass", "High")] == pytest.approx(expected_pass_high)
