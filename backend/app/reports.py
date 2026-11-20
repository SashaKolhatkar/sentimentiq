"""CSV, Excel and PDF report generation from a completed analysis run."""

from __future__ import annotations

import io
from itertools import islice
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import store
from .utils import truncate

SENTIMENT_COLORS = {
    "positive": "#16a34a", "negative": "#dc2626",
    "neutral": "#64748b", "mixed": "#f59e0b",
}


def _record_iterator(result: dict[str, Any]):
    """Yield enriched records from streaming storage, with a legacy fallback."""
    run_id = result.get("id")
    if run_id:
        try:
            yield from store.iter_filtered_records(run_id, sort="index")
            return
        except (FileNotFoundError, ValueError):
            pass
    yield from result.get("records", [])


def export_csv(
    result: dict[str, Any],
    filters: dict[str, str] | None = None,
    sort: str = "index",
) -> bytes:
    run_id = result.get("id")
    if run_id:
        try:
            return store.records_csv(store.iter_filtered_records(run_id, filters or {}, sort))
        except (FileNotFoundError, ValueError):
            pass
    return store.records_csv(_record_iterator(result))


def _style_sheet(ws, widths: list[int]) -> None:
    header_fill = PatternFill("solid", fgColor="1E293B")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width


def export_excel(result: dict[str, Any]) -> bytes:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    s = result["summary"]
    summary_rows = [
        ["SentimentIQ Report", ""],
        ["Analysis", result.get("name", "")],
        ["Created", result.get("created_at", "")],
        ["Source", result.get("source_type", "")],
        ["Records", s["total_records"]],
        ["Demo data", "Yes" if s.get("is_demo") else "No"],
        ["Average sentiment score", s["average_sentiment_score"]],
        ["Satisfaction score", s["satisfaction_score"]],
        ["Suspicious %", s["spam"]["suspicious_percentage"]],
        ["Automated accounts", s["bots"]["automated_accounts"]],
        ["Analysis engines", ", ".join(s.get("engines", []))],
        ["Privacy", "PII redaction applied" if s.get("redaction_applied") else "Raw text retained"],
    ]
    for row in summary_rows:
        summary.append(row)
    summary["A1"].font = Font(size=16, bold=True, color="1E293B")
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 70

    ws = wb.create_sheet("Records")
    ws.append([name for name, _ in store.RECORD_COLUMNS])
    for record in _record_iterator(result):
        ws.append([store._cell(record.get(key), key) for _, key in store.RECORD_COLUMNS])
    _style_sheet(ws, [14, 70, 16, 18, 22, 14, 14, 16, 16, 16, 20, 14, 16, 50, 22, 14, 50])

    ws = wb.create_sheet("Aspects")
    ws.append(["Aspect", "Mentions", "Positive", "Negative", "Neutral", "Mixed", "Positive Rate", "Negative Rate", "Average Score", "Dominant"])
    for aspect in result["aspects"]["aspects"]:
        ws.append([
            aspect["aspect"], aspect["mentions"], aspect["positive"], aspect["negative"],
            aspect["neutral"], aspect["mixed"], aspect["positive_rate"], aspect["negative_rate"],
            aspect["average_score"], aspect["dominant_sentiment"],
        ])
    _style_sheet(ws, [22, 12, 12, 12, 12, 12, 15, 15, 15, 16])

    ws = wb.create_sheet("Topics")
    ws.append(["Type", "Name", "Count / Value", "Extra"])
    for item in result["topics"]["keywords"]:
        ws.append(["Keyword", item["word"], item["count"], ""])
    for item in result["topics"]["hashtags"]:
        ws.append(["Hashtag", item["tag"], item["count"], ""])
    for cluster in result["topics"]["clusters"]:
        ws.append(["Topic", cluster["label"], cluster["size"], f"negative share {cluster['negative_share']}"])
    _style_sheet(ws, [12, 40, 16, 40])

    ws = wb.create_sheet("Trends")
    ws.append(["Date", "Total", "Positive", "Negative", "Neutral", "Mixed", "Positive Rate", "Negative Rate", "Satisfaction", "Dominant Emotion"])
    for point in result["trends"]["series"]:
        ws.append([
            point["date"], point["total"], point["positive"], point["negative"],
            point["neutral"], point["mixed"], point["positive_rate"],
            point["negative_rate"], point["satisfaction"], point["dominant_emotion"],
        ])
    _style_sheet(ws, [14, 10, 12, 12, 12, 12, 15, 15, 15, 20])

    ws = wb.create_sheet("Insights")
    ws.append(["Type", "Category", "Text", "Evidence / Detail"])
    for item in result["insights"]["insights"]:
        ws.append(["Insight", item["category"], item["text"], item["evidence"]])
    for item in result["insights"]["recommendations"]:
        ws.append(["Recommendation", item["priority"], item["title"], item["detail"]])
    for alert in result["trends"]["alerts"]:
        ws.append(["Alert", alert["severity"], alert["message"], alert["date"]])
    _style_sheet(ws, [16, 18, 70, 70])

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _table(data: list[list[Any]], widths: list[float] | None = None) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _sentiment_pie(result: dict[str, Any]) -> Drawing:
    counts = result["summary"]["sentiment_counts"]
    keys = [k for k in ("positive", "negative", "neutral", "mixed") if counts.get(k)]
    drawing = Drawing(420, 170)
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = 120, 10, 145, 145
    pie.data = [counts[k] for k in keys]
    pie.labels = [k.title() for k in keys]
    pie.slices.strokeWidth = 0.5
    for idx, key in enumerate(keys):
        pie.slices[idx].fillColor = colors.HexColor(SENTIMENT_COLORS[key])
    drawing.add(pie)
    drawing.add(String(10, 155, "Sentiment distribution", fontName="Helvetica-Bold", fontSize=11))
    return drawing


def _emotion_bar(result: dict[str, Any]) -> Drawing:
    distribution = result["summary"]["emotion_distribution"][:8]
    drawing = Drawing(420, 180)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 40, 35, 355, 125
    chart.data = [[item["count"] for item in distribution]]
    chart.categoryAxis.categoryNames = [item["emotion"][:9] for item in distribution]
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = colors.HexColor("#6366F1")
    drawing.add(chart)
    drawing.add(String(10, 168, "Emotion distribution", fontName="Helvetica-Bold", fontSize=11))
    return drawing


def _trend_line(result: dict[str, Any]) -> Drawing | None:
    series = result["trends"]["series"][-20:]
    if len(series) < 2:
        return None
    drawing = Drawing(420, 170)
    chart = HorizontalLineChart()
    chart.x, chart.y, chart.width, chart.height = 45, 35, 350, 115
    chart.data = [[p["positive_rate"] * 100 for p in series], [p["negative_rate"] * 100 for p in series]]
    chart.categoryAxis.categoryNames = [p["date"][-5:] for p in series]
    chart.categoryAxis.labels.fontSize = 6.5
    chart.lines[0].strokeColor = colors.HexColor("#16A34A")
    chart.lines[1].strokeColor = colors.HexColor("#DC2626")
    drawing.add(chart)
    drawing.add(String(10, 158, "Positive vs negative over time (%)", fontName="Helvetica-Bold", fontSize=11))
    return drawing


def export_pdf(result: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"SentimentIQ - {result.get('name', 'Analysis')}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#0F172A"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceBefore=10, textColor=colors.HexColor("#1E293B"))
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=13)
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=7.5, leading=10)
    center = ParagraphStyle("center", parent=styles["BodyText"], alignment=TA_CENTER, fontSize=8)

    story: list[Any] = []
    story.append(Paragraph("SentimentIQ Analysis Report", h1))
    story.append(Paragraph(f"<b>{truncate(result.get('name', 'Analysis'), 90)}</b>", body))
    story.append(Paragraph(
        f"Generated {result.get('created_at', '')} · Source: {result.get('source_type', '')} · "
        f"Records: {result['summary']['total_records']} · "
        f"{'DEMO DATA' if result.get('is_demo') else 'ANALYSED DATA'}", small
    ))
    story.append(Spacer(1, 8))

    s = result["summary"]
    kpis = [
        ["Total Records", str(s["total_records"]), "Positive", f"{s['sentiment_percentages']['positive']}%"],
        ["Negative", f"{s['sentiment_percentages']['negative']}%", "Neutral", f"{s['sentiment_percentages']['neutral']}%"],
        ["Avg Score", str(s["average_sentiment_score"]), "Satisfaction", f"{s['satisfaction_score']}%"],
        ["Suspicious", f"{s['spam']['suspicious_percentage']}%", "Automated Accounts", str(s["bots"]["automated_accounts"])],
    ]
    story.append(_table(kpis, [80, 60, 90, 60]))
    story.append(Spacer(1, 10))
    story.append(KeepTogether([_sentiment_pie(result), _emotion_bar(result)]))

    trend_chart = _trend_line(result)
    if trend_chart:
        story.append(KeepTogether([trend_chart]))

    story.append(PageBreak())
    story.append(Paragraph("AI-Generated Insights", h2))
    for insight in result["insights"]["insights"][:10]:
        story.append(Paragraph(f"• <b>{insight['category']}:</b> {insight['text']}", body))
        story.append(Paragraph(f"&nbsp;&nbsp;Evidence: {truncate(insight['evidence'], 180)}", small))

    story.append(Paragraph("Recommendations", h2))
    rec_rows = [["Priority", "Action", "Detail"]]
    for rec in result["insights"]["recommendations"]:
        rec_rows.append([rec["priority"].upper(), Paragraph(rec["title"], small), Paragraph(rec["detail"], small)])
    story.append(_table(rec_rows, [50, 130, 280]))

    if result["trends"]["alerts"]:
        story.append(Paragraph("Alerts", h2))
        for alert in result["trends"]["alerts"]:
            story.append(Paragraph(f"• [{alert['severity'].upper()}] {alert['message']}", body))

    story.append(Paragraph("Customer Aspect Summary", h2))
    aspect_rows = [["Aspect", "Mentions", "Positive", "Negative", "Dominant"]]
    for aspect in result["aspects"]["aspects"][:12]:
        aspect_rows.append([
            aspect["aspect"], aspect["mentions"], aspect["positive"],
            aspect["negative"], aspect["dominant_sentiment"],
        ])
    story.append(_table(aspect_rows, [140, 70, 70, 70, 90]))

    story.append(PageBreak())
    story.append(Paragraph("Trending Topics", h2))
    topic_rows = [["Type", "Name", "Count"]]
    for item in result["topics"]["keywords"][:15]:
        topic_rows.append(["Keyword", item["word"], item["count"]])
    for item in result["topics"]["hashtags"][:10]:
        topic_rows.append(["Hashtag", item["tag"], item["count"]])
    story.append(_table(topic_rows, [80, 230, 70]))

    story.append(Paragraph("Spam & Suspicious Content", h2))
    spam_rows = [["Label", "Count"]]
    for key, value in sorted(s["spam"]["labels"].items()):
        spam_rows.append([key, value])
    story.append(_table(spam_rows, [180, 70]))
    story.append(Paragraph(result["spam"]["warning"], small))

    story.append(Paragraph("Bot Detection", h2))
    bot_rows = [["Account", "Posts", "Classification", "Score", "Indicators"]]
    for account in result["bots"]["accounts"][:12]:
        bot_rows.append([
            truncate(account["author"], 22), account["posts"], account["label"],
            account["score"], ", ".join(i["name"] for i in account["indicators"][:3]) or "—",
        ])
    story.append(_table(bot_rows, [90, 40, 110, 40, 180]))

    story.append(Paragraph("Sample Analysed Records", h2))
    record_rows = [["Text", "Sentiment", "Emotion", "Spam", "Automation"]]
    for record in islice(_record_iterator(result), 18):
        record_rows.append([
            Paragraph(truncate(record["text"], 140), small),
            record["sentiment"], record["emotion"], record["spam_label"],
            record["automation_label"],
        ])
    story.append(_table(record_rows, [230, 55, 55, 75, 80]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Method: Hugging Face transformers for sentiment, emotion and zero-shot evidence; "
        "scikit-learn for topics and similarity. Suspicion and automation verdicts include "
        "uncertainty and are not proof of fake content or bot ownership.", center
    ))

    doc.build(story)
    return buffer.getvalue()
