from app.ai.models import (
    AiContextPayload,
    AiFinding,
    AiImportance,
    AiInsightResponse,
    AiRecommendation,
)

PRIORITY_ORDER = {
    AiImportance.HIGH: 0,
    AiImportance.MEDIUM: 1,
    AiImportance.LOW: 2,
}


def _priority(item: dict[str, object]) -> AiImportance:
    insight_type = str(item["type"])
    severity = str(item["severity"])
    if insight_type in {"potential_outlier", "zero_activity", "data_quality"}:
        if insight_type == "data_quality" and severity == "critical":
            return AiImportance.HIGH
        return AiImportance.MEDIUM
    if insight_type == "insufficient_data":
        return (
            AiImportance.MEDIUM
            if str(item.get("title", "")).startswith("Limited")
            else AiImportance.LOW
        )
    if severity in {"critical", "warning"}:
        return AiImportance.HIGH
    if insight_type in {"sales_stable", "category_stable"}:
        return AiImportance.LOW
    return AiImportance.MEDIUM


def _action(item: dict[str, object]) -> str:
    insight_type = str(item["type"])
    dimension = str(item.get("dimension") or "relevant dimensions")
    actions = {
        "sales_decline": "Compare the latest source month with the preceding source month by product, category, and region to locate the change.",
        "category_decline": "Compare the affected category across the two stated months by product and region.",
        "concentration": f"Compare the leading {dimension} with the remaining {dimension} values and monitor whether concentration persists across periods.",
        "potential_outlier": "Inspect the aggregated distribution and verify whether the flagged source values are expected or require data correction.",
        "data_quality": "Validate the identified source-data condition before relying on affected comparisons.",
        "data_gap": "Confirm whether missing source periods are expected and collect the missing period data when available.",
        "zero_activity": "Verify whether the observed zero activity is expected, then compare it with adjacent source periods.",
        "insufficient_data": "Collect additional comparable periods or dimensions before drawing a stronger conclusion.",
    }
    return actions.get(
        insight_type,
        "Review the calculated signal against its related metric and monitor it in the next comparable period.",
    )


def _recommendations(context: AiContextPayload) -> tuple[AiRecommendation, ...]:
    candidates: list[tuple[int, int, AiRecommendation]] = []
    sequence = 0
    for group in ("business", "quality", "outliers"):
        for item in context.detected_insights.get(group, ()):
            priority = _priority(item)
            metric = str(item["metric_name"]) if item.get("metric_name") else None
            dimension = str(item["dimension"]) if item.get("dimension") else None
            dimension_value = (
                str(item["dimension_value"])
                if item.get("dimension_value")
                else None
            )
            related_dimension = (
                f"{dimension}: {dimension_value}"
                if dimension and dimension_value
                else dimension
            )
            evidence = [str(item["summary"])]
            if item.get("change_amount") is not None:
                evidence.append(
                    f"Calculated change: {item['change_amount']}; percentage change: {item.get('change_pct')}"
                )
            recommendation = AiRecommendation(
                title=f"Review: {item['title']}"[:140],
                priority=priority,
                rationale=str(item["summary"]),
                action=_action(item),
                evidence=tuple(value[:300] for value in evidence[:3]),
                related_metric=metric,
                related_dimension=(
                    related_dimension[:240] if related_dimension else None
                ),
                caution="Use the supplied calculated evidence only; confirm context before making an operational decision.",
            )
            candidates.append((PRIORITY_ORDER[priority], sequence, recommendation))
            sequence += 1
    return tuple(item[2] for item in sorted(candidates)[:5])


class FakeAiProvider:
    def generate(self, context: AiContextPayload) -> AiInsightResponse:
        kpis = context.kpis
        metadata = context.metadata
        findings: list[AiFinding] = []
        for item in context.detected_insights.get("business", ())[:3]:
            findings.append(
                AiFinding(
                    title=str(item["title"]),
                    observation=str(item["summary"]),
                    evidence=f"Calculated signal: {item['type']}",
                    importance=AiImportance.HIGH if item["severity"] in {"critical", "warning"} else AiImportance.MEDIUM,
                )
            )
        if not findings:
            findings.append(
                AiFinding(
                    title="Calculated performance overview",
                    observation=f"The validated dataset contains {kpis['transaction_count']} transactions.",
                    evidence=f"Total sales: {kpis['total_sales']}; total quantity: {kpis['total_quantity']}.",
                    importance=AiImportance.MEDIUM,
                )
            )
        quality_note = (
            f"The analysis covers {metadata['row_count']} valid rows; "
            f"{metadata['imputed_months']} monthly points were imputed."
        )
        return AiInsightResponse(
            executive_summary=(
                f"Calculated results cover {metadata['date_from'] or 'an unspecified start date'} to "
                f"{metadata['date_to'] or 'an unspecified end date'}, with total sales of {kpis['total_sales']}. "
                "These observations describe supplied results and do not establish causes."
            ),
            key_findings=tuple(findings),
            risks_or_watchpoints=("Review detected changes alongside operational context before acting.",),
            recommended_checks=("Confirm source completeness and compare the latest observed periods.",),
            data_quality_note=quality_note,
            recommendations=_recommendations(context),
            optional_next_questions=(
                "Which supplied top-ranked dimension has the largest calculated sales share?",
                "How does the latest observed month compare with the preceding source month?",
            ),
        )
