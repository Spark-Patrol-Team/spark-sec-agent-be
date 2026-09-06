from sec_agent.deep_agent.tools.knowledge import _collapse_gate_strength


def test_gate_strength_mapping():
    cases = {
        "OUT_OF_SCOPE": "out_of_scope",
        "BENIGN_LIKE": "out_of_scope",
        "IN_SCOPE_CONFIRMED": "in_scope",
        "IN_SCOPE_WEAK": "weak_signal",
        "MIXED": "weak_signal",
        "INDETERMINATE": "weak_signal",
    }

    for source, expected in cases.items():
        assert _collapse_gate_strength(source) == expected