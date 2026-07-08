"""Tests for helpers/receipt.py — the answer evidence trail."""

from helpers.receipt import MetricRef, Receipt


class TestMetricRef:
    def test_renders_name_and_definition(self):
        m = MetricRef(name="revenue", resolved_as="net_revenue (gross − refunds)")
        out = m.render()
        assert "revenue" in out
        assert "net_revenue" in out

    def test_includes_source_when_given(self):
        m = MetricRef("revenue", "net_revenue", source="metrics.yaml#revenue")
        assert "metrics.yaml#revenue" in m.render()

    def test_omits_source_when_absent(self):
        assert "per " not in MetricRef("revenue", "net_revenue").render()


class TestReceipt:
    def test_minimal_l1_receipt(self):
        r = Receipt(
            interpreted_question="How many new users in March?",
            metric=MetricRef("new users", "distinct first-order users"),
            sql="SELECT COUNT(DISTINCT user_id) FROM users",
        )
        out = r.render()
        assert "How many new users in March?" in out
        assert "SELECT COUNT(DISTINCT user_id)" in out
        assert "```sql" in out
        # empty sections are omitted, not rendered blank
        assert "Caveats" not in out
        assert "Assumptions" not in out
        assert "Tables" not in out

    def test_full_receipt_renders_every_section(self):
        r = Receipt(
            interpreted_question="Net revenue Mar vs Feb",
            metric=MetricRef("revenue", "net_revenue", "metrics.yaml#revenue"),
            time_window="Feb vs Mar 2026, IST",
            tables=["orders_daily"],
            filters=["activity_date >= 2026-02-01"],
            assumptions=["Refunds attributed to original month"],
            caveats=["RTO orders net to zero"],
            governance=["PII blocked at query layer"],
            data_through="2026-06-17",
            sql="SELECT 1",
        )
        out = r.render(confidence_badge="A (92/100)")
        assert "Time window" in out
        assert "orders_daily" in out
        assert "activity_date >= 2026-02-01" in out
        assert "Refunds attributed to original month" in out
        assert "RTO orders net to zero" in out
        assert "PII blocked at query layer" in out
        assert "2026-06-17" in out
        assert "A (92/100)" in out

    def test_confidence_badge_optional(self):
        r = Receipt(interpreted_question="Q", sql="SELECT 1")
        assert "Confidence" not in r.render()
        assert "Confidence" in r.render(confidence_badge="B (80/100)")

    def test_collapsible_block(self):
        out = Receipt(interpreted_question="Q").render()
        assert out.strip().startswith("<details>")
        assert out.strip().endswith("</details>")
        assert "Receipt" in out

    def test_metric_ambiguity_surfaced(self):
        """The whole point: the chosen definition is visible in the output."""
        r = Receipt(
            interpreted_question="revenue",
            metric=MetricRef("revenue", "net_revenue, NOT gross", "metrics.yaml#revenue"),
        )
        assert "net_revenue, NOT gross" in r.render()
