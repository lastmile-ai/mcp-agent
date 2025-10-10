from mcp_agent.runloop.policy import PatchSizing, compute_patch_sizing


def test_patch_sizing_clamps_iteration_bounds() -> None:
    assert compute_patch_sizing(0) == PatchSizing(iterations=1, implementation_budget_s=0)
    assert compute_patch_sizing(10) == PatchSizing(iterations=4, implementation_budget_s=2.5)
    assert compute_patch_sizing(840) == PatchSizing(iterations=7, implementation_budget_s=120.0)


def test_patch_sizing_scales_with_budget() -> None:
    sizing = compute_patch_sizing(400)
    assert sizing.iterations == 4
    assert sizing.implementation_budget_s == 100.0

    sizing = compute_patch_sizing(600)
    assert sizing.iterations == 5
    assert sizing.implementation_budget_s == 120.0
