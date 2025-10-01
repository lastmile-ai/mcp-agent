from prometheus_client import Counter

authz_attempts_total = Counter(
    "authz_attempts_total",
    "Authorization attempts with allow/deny labels",
    ["decision"]
)
