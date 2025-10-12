from mcp_agent.feature.estimator import estimate_budget
from mcp_agent.feature.models import FeatureSpec


def test_iterations_and_caps_increase_with_complexity():
    small_spec = FeatureSpec(
        summary="Add status badge",
        details="Render status badge on dashboard",
        targets=["src/ui/dashboard.py"],
        risks=[],
    )
    complex_spec = FeatureSpec(
        summary="Implement secure export",
        details="Provide CSV export with authentication and audit logging. Include migration and payment hooks." * 2,
        targets=["src/api/export.py", "src/payments/hooks.py", "src/db/migrations/001.sql"],
        risks=["security review", "database migration"],
    )

    small = estimate_budget(small_spec)
    large = estimate_budget(complex_spec)

    assert 4 <= small.iterations <= 7
    assert 4 <= large.iterations <= 7
    assert large.seconds > small.seconds
    assert large.caps["max_iterations"] >= small.caps["max_iterations"]


def test_risk_multiplier_affects_seconds():
    baseline = FeatureSpec(summary="Add info", details="Simple text change")
    risky = FeatureSpec(summary="Update auth", details="Touch authentication and security", risks=["security"])

    base_estimate = estimate_budget(baseline)
    risky_estimate = estimate_budget(risky)

    assert risky_estimate.seconds > base_estimate.seconds
