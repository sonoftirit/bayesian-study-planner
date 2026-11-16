"""Inference: what each action is likely to lead to.

Inference task: for each action a, compute

    P(ExamSuccess, Stress | Difficulty_A, Difficulty_B, Difficulty_C,
                            DaysLeft, Action=a)

ExamSuccess and Stress are the query variables. They are queried jointly
because the utility function (Stage 4) scores each (ExamSuccess, Stress) pair.
"""

from functools import cache

from pgmpy.inference import VariableElimination

from planner.network import build_model

QUERY_VARIABLES = ["ExamSuccess", "Stress"]


@cache
def get_inference():
    """Build the model and its inference engine once, then reuse them."""
    return VariableElimination(build_model())


def query_outcomes(evidence, action):
    """Return P(ExamSuccess, Stress | evidence, Action=action) as a dict.

    `evidence` maps each Difficulty node and DaysLeft to a state, for example
    {"Difficulty_A": "Hard", ..., "DaysLeft": "Few"}. The result maps each
    (exam_success, stress) pair, such as ("Pass", "Low"), to its probability.
    """
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
