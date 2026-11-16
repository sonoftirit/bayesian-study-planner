"""The Bayesian network: structure and hand-crafted CPTs.

Every probability below is explained in docs/design.md.
"""

from itertools import product

from pgmpy.factors.discrete import TabularCPD
from pgmpy.models import DiscreteBayesianNetwork

CONCEPTS = ["A", "B", "C"]

DIFFICULTY_STATES = ["Easy", "Hard"]
DAYS_LEFT_STATES = ["Few", "Many"]
ACTIONS = ["Intense", "Light", "Rest"]
MASTERY_STATES = ["Low", "High"]
STRESS_STATES = ["Low", "High"]
EXAM_STATES = ["Fail", "Pass"]

# P(Mastery = High | Difficulty, Action). Easy concepts are mostly known
# already, so the action matters little; hard concepts need focused study.
P_MASTERY_HIGH = {
    ("Easy", "Intense"): 0.95,
    ("Easy", "Light"): 0.92,
    ("Easy", "Rest"): 0.88,
    ("Hard", "Intense"): 0.85,
    ("Hard", "Light"): 0.60,
    ("Hard", "Rest"): 0.25,
}

# P(Stress = High | Action, DaysLeft). Long sessions and close deadlines both
# raise stress; resting is calming only when there is time to spare.
P_STRESS_HIGH = {
    ("Intense", "Few"): 0.70,
    ("Intense", "Many"): 0.50,
    ("Light", "Few"): 0.35,
    ("Light", "Many"): 0.20,
    ("Rest", "Few"): 0.40,
    ("Rest", "Many"): 0.05,
}

# P(ExamSuccess = Pass) is generated from a rule instead of 16 hand-typed
# numbers: it depends on how many concepts are mastered, minus a penalty for
# high stress. The full resulting table is listed in docs/design.md.
P_PASS_LOW_STRESS = [0.10, 0.35, 0.70, 0.95]  # index = number of concepts mastered
HIGH_STRESS_PENALTY = 0.15
MIN_PASS_PROBABILITY = 0.05


def difficulty_node(concept):
    return f"Difficulty_{concept}"


def mastery_node(concept):
    return f"Mastery_{concept}"


def pass_probability(mastered_count, stress):
    """P(ExamSuccess = Pass) for a number of mastered concepts and a stress level."""
    p = P_PASS_LOW_STRESS[mastered_count]
    if stress == "High":
        p = max(MIN_PASS_PROBABILITY, p - HIGH_STRESS_PENALTY)
    # Rounding keeps values like 0.2 from showing up as 0.19999999999999998.
    return round(p, 2)


def build_model():
    """Build the 10-variable network with all CPTs attached and checked."""
    edges = []
    for concept in CONCEPTS:
        edges.append((difficulty_node(concept), mastery_node(concept)))
        edges.append(("Action", mastery_node(concept)))
        edges.append((mastery_node(concept), "ExamSuccess"))
    edges += [
        ("Action", "Stress"),
        ("DaysLeft", "Stress"),
        ("Stress", "ExamSuccess"),
    ]
    model = DiscreteBayesianNetwork(edges)

    model.add_cpds(
        *[_difficulty_cpd(concept) for concept in CONCEPTS],
        _days_left_cpd(),
        _action_cpd(),
        *[_mastery_cpd(concept) for concept in CONCEPTS],
        _stress_cpd(),
        _exam_success_cpd(),
    )
    model.check_model()
    return model


# Root nodes. Difficulty, DaysLeft and Action are always given as evidence,
# so their priors are uniform: they never affect a query result.


def _difficulty_cpd(concept):
    node = difficulty_node(concept)
    return TabularCPD(node, 2, [[0.5], [0.5]], state_names={node: DIFFICULTY_STATES})


def _days_left_cpd():
    return TabularCPD(
        "DaysLeft", 2, [[0.5], [0.5]], state_names={"DaysLeft": DAYS_LEFT_STATES}
    )


def _action_cpd():
    return TabularCPD(
        "Action", 3, [[1 / 3], [1 / 3], [1 / 3]], state_names={"Action": ACTIONS}
    )


# Child nodes. pgmpy orders CPT columns so the last parent changes fastest,
# which is the same order itertools.product produces.


def _mastery_cpd(concept):
    node = mastery_node(concept)
    parent = difficulty_node(concept)
    high = [P_MASTERY_HIGH[key] for key in product(DIFFICULTY_STATES, ACTIONS)]
    return TabularCPD(
        node,
        2,
        [[1 - p for p in high], high],
        evidence=[parent, "Action"],
        evidence_card=[2, 3],
        state_names={
            node: MASTERY_STATES,
            parent: DIFFICULTY_STATES,
            "Action": ACTIONS,
        },
    )


def _stress_cpd():
    high = [P_STRESS_HIGH[key] for key in product(ACTIONS, DAYS_LEFT_STATES)]
    return TabularCPD(
        "Stress",
        2,
        [[1 - p for p in high], high],
        evidence=["Action", "DaysLeft"],
        evidence_card=[3, 2],
        state_names={
            "Stress": STRESS_STATES,
            "Action": ACTIONS,
            "DaysLeft": DAYS_LEFT_STATES,
        },
    )


def _exam_success_cpd():
    mastery_parents = [mastery_node(concept) for concept in CONCEPTS]
    passes = []
    for *masteries, stress in product(
        MASTERY_STATES, MASTERY_STATES, MASTERY_STATES, STRESS_STATES
    ):
        passes.append(pass_probability(masteries.count("High"), stress))
    return TabularCPD(
        "ExamSuccess",
        2,
        [[1 - p for p in passes], passes],
        evidence=[*mastery_parents, "Stress"],
        evidence_card=[2, 2, 2, 2],
        state_names={
            "ExamSuccess": EXAM_STATES,
            **{parent: MASTERY_STATES for parent in mastery_parents},
            "Stress": STRESS_STATES,
        },
    )
