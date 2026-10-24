# report_generator.py -- PDF and CSV advisory report generator
"""
Generates downloadable PDF and CSV reports of farmer diagnosis and fertilizer plans.
Includes technical NPK levels, product active ingredients, brands, and official links.
"""

import io
import csv
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable


def sanitize_text_for_pdf(text: Any) -> str:
    """Ensure text is safe for ReportLab's standard Helvetica font."""
    if text is None:
        return ""
    s = str(text)
    # Replace unicode characters outside Latin-1 with ascii approximations or omit
    safe_chars = []
    for ch in s:
        if ord(ch) < 256:
            safe_chars.append(ch)
        else:
            safe_chars.append(" ")
    clean = "".join(safe_chars).strip()
    return clean if clean else str(text).encode("ascii", "replace").decode("ascii")


def generate_pdf_report(report_data: Dict[str, Any], lang: str = "English") -> bytes:
    """
    Generate an advisory report as a PDF byte stream.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1b5e20"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#555555"),
        spaceAfter=12,
    )
    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#2e7d32"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#222222"),
    )
    bold_style = ParagraphStyle(
        "BoldBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#111111"),
        fontName="Helvetica-Bold",
    )

    story = []

    # Header
    story.append(Paragraph("AgriCare - AI Crop Doctor & Fertilizer Advisory Report", title_style))
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Language: {lang} | User: {sanitize_text_for_pdf(report_data.get('user', 'Farmer'))}",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#2e7d32"), spaceAfter=14))

    # Activity Summary
    activity_type = report_data.get("type", "General Advisory")
    story.append(Paragraph("1. Consultation Summary", h2_style))
    summary_data = [
        [Paragraph("Consultation Type:", bold_style), Paragraph(sanitize_text_for_pdf(activity_type), body_style)],
        [Paragraph("Target Crop:", bold_style), Paragraph(sanitize_text_for_pdf(report_data.get("crop", "N/A")), body_style)],
        [Paragraph("Primary Finding / Recommendation:", bold_style), Paragraph(sanitize_text_for_pdf(report_data.get("result", "N/A")), body_style)],
        [Paragraph("Assessment Confidence / Status:", bold_style), Paragraph(sanitize_text_for_pdf(report_data.get("confidence", "Standard")), body_style)],
    ]
    t1 = Table(summary_data, colWidths=[180, 360])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7faf7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t1)
    story.append(Spacer(1, 10))

    # Detailed Fertilizer or Leaf Advisory
    if "soil_inputs" in report_data:
        story.append(Paragraph("2. Soil & Environmental Measurements", h2_style))
        soil = report_data["soil_inputs"]
        nutrients = report_data.get("nutrient_status", {})

        soil_rows = [
            [
                Paragraph("Parameter", bold_style),
                Paragraph("Value", bold_style),
                Paragraph("Status Evaluation", bold_style)
            ],
            [
                Paragraph("Temperature", body_style),
                Paragraph(f"{soil.get('Temperature', '')} °C", body_style),
                Paragraph("Ambient", body_style)
            ],
            [
                Paragraph("Humidity", body_style),
                Paragraph(f"{soil.get('Humidity', '')} %", body_style),
                Paragraph("Ambient", body_style)
            ],
            [
                Paragraph("Soil Moisture", body_style),
                Paragraph(f"{soil.get('Moisture', '')} %", body_style),
                Paragraph("Root Zone", body_style)
            ],
            [
                Paragraph("Soil Type / Crop", body_style),
                Paragraph(f"{soil.get('Soil Type', '')} / {soil.get('Crop Type', '')}", body_style),
                Paragraph("Field Context", body_style)
            ],
            [
                Paragraph("Nitrogen (N)", body_style),
                Paragraph(f"{soil.get('Nitrogen', '')}", body_style),
                Paragraph(sanitize_text_for_pdf(nutrients.get("Nitrogen", {}).get("status", "N/A")), body_style)
            ],
            [
                Paragraph("Phosphorous (P)", body_style),
                Paragraph(f"{soil.get('Phosphorous', '')}", body_style),
                Paragraph(sanitize_text_for_pdf(nutrients.get("Phosphorous", {}).get("status", "N/A")), body_style)
            ],
            [
                Paragraph("Potassium (K)", body_style),
                Paragraph(f"{soil.get('Potassium', '')}", body_style),
                Paragraph(sanitize_text_for_pdf(nutrients.get("Potassium", {}).get("status", "N/A")), body_style)
            ],
        ]
        t_soil = Table(soil_rows, colWidths=[180, 160, 200])
        t_soil.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f5e9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdcdc")),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_soil)
        story.append(Spacer(1, 10))

    # Product details
    product_info = report_data.get("product_info")
    if product_info:
        story.append(Paragraph("3. Recommended Product Specifications", h2_style))
        lang_p = product_info.get(lang, product_info.get("English", {}))
        prod_rows = [
            [Paragraph("Product Name / Grade:", bold_style), Paragraph(sanitize_text_for_pdf(lang_p.get("title", report_data.get("result", ""))), body_style)],
            [Paragraph("NPK Guaranteed Ratio:", bold_style), Paragraph(sanitize_text_for_pdf(product_info.get("npk_ratio", "N/A")), body_style)],
            [Paragraph("Active Chemical Ingredients:", bold_style), Paragraph(sanitize_text_for_pdf(lang_p.get("ingredients", "")), body_style)],
            [Paragraph("Agronomic Best Fit:", bold_style), Paragraph(sanitize_text_for_pdf(lang_p.get("best_for", "")), body_style)],
            [Paragraph("Verified Market Brands:", bold_style), Paragraph(sanitize_text_for_pdf(product_info.get("brands", "")), body_style)],
            [Paragraph("Application Notice:", bold_style), Paragraph(sanitize_text_for_pdf(lang_p.get("application_note", "")), body_style)],
            [Paragraph("Manufacturer Official Website:", bold_style), Paragraph(sanitize_text_for_pdf(product_info.get("manufacturer_url", "")), body_style)],
        ]
        t_prod = Table(prod_rows, colWidths=[180, 360])
        t_prod.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t_prod)
        story.append(Spacer(1, 10))

    # Advisory card if present
    advisory = report_data.get("advisory")
    if advisory:
        story.append(Paragraph("3. Crop Health & Agronomic Prescription", h2_style))
        adv_rows = [
            [Paragraph("Condition Identified:", bold_style), Paragraph(sanitize_text_for_pdf(advisory.get("condition", "")), body_style)],
            [Paragraph("Probable Etiology / Cause:", bold_style), Paragraph(sanitize_text_for_pdf(advisory.get("cause", "")), body_style)],
            [Paragraph("Treatment / Solution:", bold_style), Paragraph(sanitize_text_for_pdf(advisory.get("solution", "")), body_style)],
            [Paragraph("Available Market Brands:", bold_style), Paragraph(sanitize_text_for_pdf(advisory.get("market_brands", "")), body_style)],
            [Paragraph("Active Ingredients:", bold_style), Paragraph(sanitize_text_for_pdf(advisory.get("ingredients", "")), body_style)],
            [Paragraph("Agronomist Advice / Tips:", bold_style), Paragraph(sanitize_text_for_pdf(advisory.get("tips", "")), body_style)],
        ]
        t_adv = Table(adv_rows, colWidths=[180, 360])
        t_adv.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fff9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c8e6c9")),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t_adv)
        story.append(Spacer(1, 10))

    # Disclaimer
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc"), spaceAfter=8))
    disclaimer_text = (
        "Notice: AgriCare recommendations are based on machine learning models and standard agronomic practices. "
        "Product prices, availability, and precise dosages vary by region. Always corroborate with a certified soil testing laboratory, "
        "local Krishi Vigyan Kendra (KVK), or certified agricultural extension officer."
    )
    story.append(Paragraph(disclaimer_text, ParagraphStyle("Disc", parent=styles["Italic"], fontSize=8, leading=11, textColor=colors.HexColor("#777777"))))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_csv_report(history_entries: List[Dict[str, Any]]) -> str:
    """
    Generate UTF-8 CSV summary of session diagnoses and recommendations.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Timestamp",
        "Activity Type",
        "Crop",
        "Result / Recommendation",
        "Confidence / Status",
        "Details",
        "Official Manufacturer URL"
    ])

    for item in history_entries:
        writer.writerow([
            item.get("timestamp", ""),
            item.get("type", ""),
            item.get("crop", ""),
            item.get("result", ""),
            item.get("confidence", ""),
            item.get("details", ""),
            item.get("url", "")
        ])

    return output.getvalue()
