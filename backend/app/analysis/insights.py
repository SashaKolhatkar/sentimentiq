"""Natural-language insight generation from computed analysis results.

No numbers are invented: every statement is derived from the same result object
that feeds the dashboard charts.
"""

from __future__ import annotations

from typing import Any


def generate_insights(result: dict[str, Any]) -> dict[str, Any]:
    summary = result["summary"]
    aspects = result["aspects"]
    topics = result["topics"]
    trends = result["trends"]
    spam = result["spam"]
    bots = result["bots"]

    total = max(summary["total_records"], 1)
    insights: list[dict[str, str]] = []
    recommendations: list[dict[str, str]] = []

    def add(category: str, text: str, evidence: str) -> None:
        insights.append({"category": category, "text": text, "evidence": evidence})

    def recommend(priority: str, title: str, detail: str) -> None:
        recommendations.append({"priority": priority, "title": title, "detail": detail})

    pos = summary["sentiment_percentages"]["positive"]
    neg = summary["sentiment_percentages"]["negative"]
    neu = summary["sentiment_percentages"]["neutral"]
    mixed = summary["sentiment_percentages"]["mixed"]

    if pos >= 60:
        add("Sentiment", f"Customers are generally positive: {pos}% of {total} items are positive.",
            f"Positive count: {summary['sentiment_counts'].get('positive', 0)}.")
    elif neg >= 35:
        add("Sentiment", f"Negative sentiment is elevated at {neg}% of analysed content.",
            f"Negative count: {summary['sentiment_counts'].get('negative', 0)}.")
    else:
        add("Sentiment", f"Opinion is balanced, with {pos}% positive, {neg}% negative and {neu}% neutral.",
            "Based on the full dataset after NLP classification.")

    if mixed >= 10:
        add("Sentiment", f"{mixed}% of items contain mixed sentiment, usually praise combined with a complaint.",
            "Detected from contrast clauses such as 'but' and 'however'.")

    if aspects["most_appreciated"]:
        best = aspects["most_appreciated"][0]
        add("Customer Insights", f"{best['aspect']} is the most appreciated area ({best['positive_rate']:.0%} positive across {best['mentions']} mentions).",
            "Aspect-based sentiment over detected clauses.")
        recommend("growth", f"Amplify {best['aspect'].lower()} in marketing",
                  "Use the positively received aspect in product pages and campaigns, and train support teams to reference it.")

    if aspects["top_complaints"]:
        worst = aspects["top_complaints"][0]
        add("Complaints", f"{worst['aspect']} is the leading complaint ({worst['negative']} negative mentions).",
            f"Negative rate {worst['negative_rate']:.0%} for this aspect.")
        recommend("high", f"Investigate {worst['aspect'].lower()}",
                  "Review the flagged examples, identify the root cause, and publish an action plan or response template.")

    if topics["keywords"]:
        top_words = ", ".join(k["word"] for k in topics["keywords"][:5])
        add("Topics", f"The most discussed themes are: {top_words}.",
            f"Computed from {topics['unique_terms']} unique terms after stop-word removal.")
    if topics["emerging"]:
        rising = topics["emerging"][0]
        add("Emerging", f"'{rising['word']}' is emerging in recent content (from {rising['early']} to {rising['late']} mentions).",
            "Compared the first and last third of dated records.")

    if spam["suspicious_percentage"] >= 15:
        add("Integrity", f"{spam['suspicious_percentage']}% of content shows suspicious patterns.",
            f"{spam['flagged_count']} item(s) flagged with explanations.")
        recommend("high", "Investigate suspicious review activity",
                  "Prioritise records with duplicate timing or promotional patterns; verify against account and order data before taking action.")
    else:
        add("Integrity", "Suspicious-content signals are low in this dataset.",
            f"Likely Spam: {spam['labels'].get('Likely Spam', 0)}; "
            f"Potentially Suspicious: {spam['labels'].get('Potentially Suspicious', 0)}.")

    if bots["automated_accounts"] > 0:
        add("Automation", f"{bots['automated_accounts']} account(s) show automation indicators.",
            "Aggregated from timing regularity, repetition, coordination and account metadata.")
        recommend("medium", "Review automated accounts",
                  "Inspect the listed indicators manually; do not take enforcement action from a single signal.")

    for alert in trends.get("alerts", []):
        if alert["type"] == "negative_increase":
            add("Trend", alert["message"], f"Detected on {alert['date']}.")
            recommend("high", "Respond to the recent negative trend",
                      "Review the newest negative reviews, acknowledge common issues publicly, and monitor the next period.")
        elif alert["type"] == "discussion_spike":
            add("Trend", alert["message"], f"Detected on {alert['date']}.")
            recommend("medium", "Explain the discussion spike",
                      "Check whether the spike relates to a campaign, launch, incident or external event before interpreting sentiment.")

    if suggestions := aspects["suggestions"]:
        add("Customer Voice", f"{len(suggestions)} improvement suggestion(s) were detected.",
            f"Example: {suggestions[0]['text'][:120]}")
        recommend("medium", "Turn suggestions into a backlog",
                  "Group the suggestion texts by aspect and assign owners to the most repeated requests.")

    if not recommendations:
        recommend("low", "Maintain current quality standards",
                  "No urgent issue was detected. Continue monitoring sentiment and aspect trends on a regular cadence.")

    priority_order = {"high": 0, "medium": 1, "growth": 2, "low": 3}
    recommendations.sort(key=lambda r: priority_order.get(r["priority"], 9))

    return {
        "insights": insights[:14],
        "recommendations": recommendations[:10],
        "generated_by": "SentimentIQ deterministic insight engine over model outputs",
        "notice": "Insights are generated from the same computed metrics shown in the dashboard; review before acting.",
    }
