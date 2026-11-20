"""Checks that inference results are valid and move in sensible directions."""

from itertools import product

import pytest

import planner.decision as decision_module
from planner.decision import (
    UTILITY,
    best_action,
    expected_utility,
    get_inference,
    query_outcomes,
    validate_evidence,
)
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


# --- Input checks ------------------------------------------------------------


def test_complete_evidence_is_accepted():
    validate_evidence(evidence())


def test_missing_evidence_is_rejected():
    # Without this check pgmpy would silently average over DaysLeft.
    incomplete = evidence()
    del incomplete["DaysLeft"]
    with pytest.raises(ValueError, match=r"missing \['DaysLeft'\]"):
        query_outcomes(incomplete, "Light")


def test_unexpected_evidence_is_rejected():
    with pytest.raises(ValueError, match=r"unexpected \['Mastery_A'\]"):
        query_outcomes({**evidence(), "Mastery_A": "High"}, "Light")


def test_unknown_state_is_rejected():
    with pytest.raises(ValueError, match="Difficulty_A must be one of"):
        query_outcomes(evidence(a="hard"), "Light")


def test_unknown_action_is_rejected():
    with pytest.raises(ValueError, match="Action must be one of"):
        query_outcomes(evidence(), "Nap")


# --- Utility and expected utility --------------------------------------------


def test_utility_table_matches_the_specification():
    assert UTILITY == {
        ("Pass", "Low"): 100,
        ("Pass", "High"): 70,
        ("Fail", "Low"): 20,
        ("Fail", "High"): 0,
    }


@pytest.mark.parametrize("outcome", list(UTILITY))
def test_a_certain_outcome_is_worth_its_utility(outcome):
    certain = {other: 0.0 for other in UTILITY}
    certain[outcome] = 1.0
    assert expected_utility(certain) == pytest.approx(UTILITY[outcome])


def test_expected_utility_small_hand_example():
    outcomes = {
        ("Pass", "Low"): 0.5,
        ("Pass", "High"): 0.2,
        ("Fail", "Low"): 0.2,
        ("Fail", "High"): 0.1,
    }
    # 0.5*100 + 0.2*70 + 0.2*20 + 0.1*0 = 50 + 14 + 4 + 0
    assert expected_utility(outcomes) == pytest.approx(68.0)


def test_expected_utility_matches_a_hand_calculation_easy_concepts():
    # All concepts Easy, Rest, Many days left (the advanced student resting).
    # Each concept is mastered with probability 0.88, so the number mastered
    # (0, 1, 2, 3) has probabilities 0.001728, 0.038016, 0.278784, 0.681472.
    #   P(Pass | Low stress)  = 0.10*0.001728 + 0.35*0.038016
    #                         + 0.70*0.278784 + 0.95*0.681472 = 0.8560256
    #   P(Pass | High stress) = 0.05*0.001728 + 0.20*0.038016
    #                         + 0.55*0.278784 + 0.80*0.681472 = 0.7061984
    # Stress is High with probability 0.05, so:
    #   P(Pass, Low)  = 0.95 * 0.8560256       = 0.81322432
    #   P(Pass, High) = 0.05 * 0.7061984       = 0.03530992
    #   P(Fail, Low)  = 0.95 * (1 - 0.8560256) = 0.13677568
    #   EU = 100*0.81322432 + 70*0.03530992 + 20*0.13677568 + 0*P(Fail, High)
    #      = 86.52964
    eu = expected_utility(query_outcomes(evidence(), "Rest"))
    assert eu == pytest.approx(86.52964)


def test_expected_utility_matches_a_hand_calculation_hard_concepts():
    # All concepts Hard, Intense, Few days left (the struggling student).
    # Each concept is mastered with probability 0.90, so the number mastered
    # (0, 1, 2, 3) has probabilities 0.001, 0.027, 0.243, 0.729.
    #   P(Pass | Low stress)  = 0.10*0.001 + 0.35*0.027
    #                         + 0.70*0.243 + 0.95*0.729 = 0.8722
    #   P(Pass | High stress) = 0.05*0.001 + 0.20*0.027
    #                         + 0.55*0.243 + 0.80*0.729 = 0.7223
    # Stress is High with probability 0.70, so:
    #   P(Pass, Low)  = 0.30 * 0.8722       = 0.26166
    #   P(Pass, High) = 0.70 * 0.7223       = 0.50561
    #   P(Fail, Low)  = 0.30 * (1 - 0.8722) = 0.03834
    #   EU = 100*0.26166 + 70*0.50561 + 20*0.03834 + 0*P(Fail, High)
    #      = 62.3255
    hard = evidence("Hard", "Hard", "Hard", "Few")
    eu = expected_utility(query_outcomes(hard, "Intense"))
    assert eu == pytest.approx(62.3255)


# --- Best action -------------------------------------------------------------


ALL_EVIDENCE = [
    evidence(a, b, c, days)
    for a, b, c, days in product(
        ["Easy", "Hard"], ["Easy", "Hard"], ["Easy", "Hard"], ["Few", "Many"]
    )
]


def evidence_id(case):
    """Short test name such as 'E-H-E-Many', so a failure shows its evidence."""
    difficulties = [case[f"Difficulty_{c}"][0] for c in "ABC"]
    return "-".join([*difficulties, case["DaysLeft"]])


@pytest.mark.parametrize("case", ALL_EVIDENCE, ids=evidence_id)
def test_best_action_picks_the_highest_expected_utility(case):
    result = best_action(case)
    eus = result.expected_utilities
    assert list(eus) == ACTIONS
    assert all(0 <= eu <= 100 for eu in eus.values())
    assert eus[result.action] == max(eus.values())


def test_best_action_can_be_unpacked():
    action, eus = best_action(evidence())
    assert action in ACTIONS
    assert set(eus) == set(ACTIONS)


def test_exact_tie_goes_to_the_first_action(monkeypatch):
    same = {outcome: 0.25 for outcome in UTILITY}
    monkeypatch.setattr(
        decision_module, "query_outcomes", lambda _evidence, _action: same
    )
    assert best_action(evidence()).action == ACTIONS[0]


def test_best_action_rejects_incomplete_evidence():
    with pytest.raises(ValueError):
        best_action({"DaysLeft": "Few"})
