"""Inference and decision: which action gives the best expected outcome.

Inference task: for each action a, compute

    P(ExamSuccess, Stress | Difficulty_A, Difficulty_B, Difficulty_C,
                            DaysLeft, Action=a)

ExamSuccess and Stress are the query variables. They are queried jointly
because the utility function scores each (ExamSuccess, Stress) pair.

Decision: the expected utility of an action is the probability-weighted
average of those scores, and the planner picks the action with the highest one.
"""

from functools import cache
from typing import NamedTuple

from pgmpy.inference import VariableElimination

from planner.network import (
    ACTIONS,
    CONCEPTS,
    DAYS_LEFT_STATES,
    DIFFICULTY_STATES,
    build_model,
    difficulty_node,
)

QUERY_VARIABLES = ["ExamSuccess", "Stress"]

# The observed variables and their allowed states. The planner always needs
# every one of them: if one were missing, pgmpy would quietly average over it
# and return a plausible-looking but wrong answer.
EVIDENCE_STATES = {
    **{difficulty_node(concept): DIFFICULTY_STATES for concept in CONCEPTS},
    "DaysLeft": DAYS_LEFT_STATES,
}

# U(ExamSuccess, Stress). Passing matters most; low stress is a bonus.
UTILITY = {
    ("Pass", "Low"): 100,
    ("Pass", "High"): 70,
    ("Fail", "Low"): 20,
    ("Fail", "High"): 0,
}


class Decision(NamedTuple):
    """The chosen action plus the expected utility of every action."""

    action: str
    expected_utilities: dict[str, float]


@cache
def get_inference():
    """Build the model and its inference engine once, then reuse them."""
    return VariableElimination(build_model())


def validate_evidence(evidence):
    """Raise ValueError unless `evidence` sets exactly the observed variables."""
    missing = EVIDENCE_STATES.keys() - evidence.keys()
    unexpected = evidence.keys() - EVIDENCE_STATES.keys()
    if missing or unexpected:
        raise ValueError(
            f"Evidence must set exactly {sorted(EVIDENCE_STATES)}; "
            f"missing {sorted(missing)}, unexpected {sorted(unexpected)}."
        )
    for variable, state in evidence.items():
        if state not in EVIDENCE_STATES[variable]:
            raise ValueError(
                f"{variable} must be one of {EVIDENCE_STATES[variable]}, got {state!r}."
            )


def query_outcomes(evidence, action):
    """Return P(ExamSuccess, Stress | evidence, Action=action) as a dict.

    `evidence` maps each Difficulty node and DaysLeft to a state, for example
    {"Difficulty_A": "Hard", ..., "DaysLeft": "Few"}. The result maps each
    (exam_success, stress) pair, such as ("Pass", "Low"), to its probability.
    """
    validate_evidence(evidence)
    if action not in ACTIONS:
        raise ValueError(f"Action must be one of {ACTIONS}, got {action!r}.")

    joint = get_inference().query(
        QUERY_VARIABLES,
        evidence={**evidence, "Action": action},
        joint=True,
        show_progress=False,
    )
    return {
        (success, stress): float(joint.get_value(ExamSuccess=success, Stress=stress))
        for success in joint.state_names["ExamSuccess"]
        for stress in joint.state_names["Stress"]
    }


def expected_utility(outcomes):
    """EU = sum of P(outcome) * U(outcome) over the four outcomes."""
    return sum(p * UTILITY[outcome] for outcome, p in outcomes.items())


def best_action(evidence):
    """Score every action and return the one with the highest expected utility.

    On an exact tie the action listed first in ACTIONS wins, because max()
    keeps the first maximum it sees. That makes the result deterministic.
    """
    expected_utilities = {
        action: expected_utility(query_outcomes(evidence, action)) for action in ACTIONS
    }
    action = max(expected_utilities, key=expected_utilities.get)
    return Decision(action, expected_utilities)
