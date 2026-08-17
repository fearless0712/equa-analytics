from app.ai.models import AiContextPayload, AiFinding, AiImportance, AiInsightResponse


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
        )
