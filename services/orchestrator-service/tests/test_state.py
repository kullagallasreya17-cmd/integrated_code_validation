from app.aggregation.finding_aggregator import aggregate, summarize


def test_aggregate_sorts_by_severity():
    security = [{"file": "a.py", "line_number": 1, "issue": "sql_injection", "severity": "critical"}]
    quality = [{"file": "b.py", "line_number": 2, "issue": "unused_var", "severity": "low"}]
    resource = [{"file": "c.py", "line_number": 3, "issue": "memory_leak", "severity": "high"}]

    merged = aggregate(security, quality, resource)

    assert [f["severity"] for f in merged] == ["critical", "high", "low"]


def test_aggregate_deduplicates_identical_findings():
    dup = {"file": "a.py", "line_number": 1, "issue": "sql_injection", "severity": "critical"}
    merged = aggregate([dup], [dup], [])
    assert len(merged) == 1


def test_summarize_counts_by_severity():
    findings = [
        {"severity": "critical"},
        {"severity": "high"},
        {"severity": "high"},
        {"severity": "low"},
    ]
    summary = summarize(findings)
    assert summary["total"] == 4
    assert summary["by_severity"]["high"] == 2
