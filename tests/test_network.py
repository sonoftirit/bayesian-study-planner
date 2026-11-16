"""Checks that the network matches the design in docs/design.md."""

from itertools import product

import numpy as np
import pytest

from planner.network import (
    ACTIONS,
    CONCEPTS,
    P_MASTERY_HIGH,
    P_STRESS_HIGH,
    build_model,
    pass_probability,
)


@pytest.fixture(scope="module")
def model():
    return build_model()


def test_model_is_valid(model):
    assert model.check_model()


def test_model_size_fits_assignment(model):
    nodes = set(model.nodes())
    # The assignment allows up to 10 variables; this design uses exactly 10.
    assert len(nodes) == 10
    assert len([n for n in nodes if n.startswith("Difficulty_")]) >= 3


def test_edges_match_design(model):
    expected = {
        ("Difficulty_A", "Mastery_A"),
        ("Difficulty_B", "Mastery_B"),
        ("Difficulty_C", "Mastery_C"),
        ("Action", "Mastery_A"),
        ("Action", "Mastery_B"),
        ("Action", "Mastery_C"),
        ("Action", "Stress"),
        ("DaysLeft", "Stress"),
        ("Mastery_A", "ExamSuccess"),
        ("Mastery_B", "ExamSuccess"),
        ("Mastery_C", "ExamSuccess"),
        ("Stress", "ExamSuccess"),
    }
    assert set(model.edges()) == expected


def test_every_cpt_column_sums_to_one(model):
    for cpd in model.get_cpds():
        column_sums = cpd.get_values().sum(axis=0)
        assert np.allclose(column_sums, 1.0), cpd.variable


def test_every_probability_is_between_zero_and_one(model):
    for cpd in model.get_cpds():
        values = cpd.get_values()
        assert (values >= 0).all() and (values <= 1).all(), cpd.variable


def test_states_are_named(model):
    expected = {
        "DaysLeft": ["Few", "Many"],
        "Action": ACTIONS,
        "Stress": ["Low", "High"],
        "ExamSuccess": ["Fail", "Pass"],
    }
    for concept in CONCEPTS:
        expected[f"Difficulty_{concept}"] = ["Easy", "Hard"]
        expected[f"Mastery_{concept}"] = ["Low", "High"]
    for node, states in expected.items():
        assert model.get_cpds(node).state_names[node] == states, node


@pytest.mark.parametrize("concept", CONCEPTS)
def test_mastery_cpt_values_land_in_the_right_columns(model, concept):
    cpd = model.get_cpds(f"Mastery_{concept}")
    for (difficulty, action), p_high in P_MASTERY_HIGH.items():
        states = {
            f"Mastery_{concept}": "High",
            f"Difficulty_{concept}": difficulty,
            "Action": action,
        }
        assert cpd.get_value(**states) == pytest.approx(p_high)


def test_stress_cpt_values_land_in_the_right_columns(model):
    cpd = model.get_cpds("Stress")
    for (action, days_left), p_high in P_STRESS_HIGH.items():
        value = cpd.get_value(Stress="High", Action=action, DaysLeft=days_left)
        assert value == pytest.approx(p_high)


def test_exam_success_cpt_uses_the_pass_rule_in_all_16_columns(model):
    cpd = model.get_cpds("ExamSuccess")
    for a, b, c, stress in product(["Low", "High"], repeat=4):
        value = cpd.get_value(
            ExamSuccess="Pass", Mastery_A=a, Mastery_B=b, Mastery_C=c, Stress=stress
        )
        mastered = [a, b, c].count("High")
        assert value == pytest.approx(pass_probability(mastered, stress))


def test_pass_probability_rises_with_each_mastered_concept():
    for stress in ["Low", "High"]:
        values = [pass_probability(k, stress) for k in range(4)]
        assert values == sorted(values)
        assert len(set(values)) == 4


def test_high_stress_never_helps_and_stays_positive():
    for k in range(4):
        assert pass_probability(k, "High") <= pass_probability(k, "Low")
        assert pass_probability(k, "High") >= 0.05


def test_mastery_is_higher_for_easy_concepts_and_more_study():
    for action in ACTIONS:
        assert P_MASTERY_HIGH[("Easy", action)] > P_MASTERY_HIGH[("Hard", action)]
    for difficulty in ["Easy", "Hard"]:
        intense, light, rest = (P_MASTERY_HIGH[(difficulty, a)] for a in ACTIONS)
        assert intense > light > rest


def test_stress_is_higher_when_the_exam_is_close():
    for action in ACTIONS:
        assert P_STRESS_HIGH[(action, "Few")] > P_STRESS_HIGH[(action, "Many")]
