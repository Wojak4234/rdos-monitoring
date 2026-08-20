# report_generator.py

import io
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def generate_general_pdf_report(title, subtitle, df_data=None, details_dict=None):
    """
    Uniwersalny generator raportów PDF dla dowolnego modułu w aplikacji.
    Zwraca strumień bajtów (bytes) gotowy do pobrania w Streamlit.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        fontSize=15,
        textColor=colors.HexColor("#1b4332"),
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=12
    )

    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        spaceAfter=4
    )

    story.append(Paragraph(f"🌱 RDOŚ Monitoring - {title}", title_style))
    story.append(Paragraph(subtitle, subtitle_style))
    story.append(Spacer(1, 6))

    # Sekcja z dodatkowymi metadanymi / parametrami
    if details_dict:
        for k, v in details_dict.items():
            story.append(Paragraph(f"<b>{k}:</b> {v}", normal_style))
        story.append(Spacer(1, 8))

    # Tabela z danymi (jeśli dostarczono DataFrame)
    if df_data is not None and not df_data.empty:
        display_df = df_data.copy()
        if isinstance(display_df.index, pd.DatetimeIndex):
            display_df.reset_index(inplace=True)
            date_col = display_df.columns[0]
            display_df[date_col] = pd.to_datetime(display_df[date_col]).dt.strftime('%Y-%m-%d %H:%M')

        table_data = [display_df.columns.tolist()] + display_df.astype(str).values.tolist()

        t = Table(table_data, hAlign='CENTER')
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f3f5")])
        ]))

        story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()