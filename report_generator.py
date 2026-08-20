# report_generator.py

import io
import unicodedata
import pandas as pd
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def remove_polish_chars(text):
    """Usuwa polskie znaki diakrytyczne dla kompatybilności z Helvetica w ReportLab."""
    if not isinstance(text, str): text = str(text)
    replacements = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
                    'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'}
    for pl, lat in replacements.items(): text = text.replace(pl, lat)
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def create_chart_image(df_data):
    """Generuje czytelny wykres liniowy ze średnimi godzinnymi."""
    plt.clf()
    plt.figure(figsize=(7, 3.2))
    for col in df_data.columns:
        clean_col = remove_polish_chars(col)
        plt.plot(df_data.index, df_data[col], label=clean_col, linewidth=1.5, marker='o', markersize=3)

    plt.title(remove_polish_chars("Wykres zanieczyszczen (srednie godzinne)"), fontsize=9, fontweight='bold')
    plt.xlabel(remove_polish_chars("Czas"), fontsize=8)
    plt.ylabel(remove_polish_chars("Wartosc / Stzenie"), fontsize=8)
    plt.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1, 1))
    plt.xticks(rotation=25, fontsize=7)
    plt.yticks(fontsize=7)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    plt.close()
    img_buffer.seek(0)
    return img_buffer


def generate_general_pdf_report(title, subtitle, df_data=None, details_dict=None, lat=None, lon=None,
                                station_name="Obszar"):
    """
    Profesjonalny generator raportów PDF (bez amatorskich wykresów punktowych).
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
        fontSize=13,
        textColor=colors.HexColor("#1b4332"),
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#555555"),
        spaceAfter=10
    )

    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#333333"),
        spaceAfter=5
    )

    # 1. Nagłówek raportu
    story.append(Paragraph(f"RDOS Monitoring - {remove_polish_chars(title)}", title_style))
    story.append(Paragraph(remove_polish_chars(subtitle), subtitle_style))
    story.append(Spacer(1, 4))

    # 2. Blok informacji / metadanych (w tym lokalizacja tekstowa zamiast brzydkiej kropki)
    if lat is not None and lon is not None:
        story.append(Paragraph(
            f"<b>Lokalizacja / Wspolrzedne:</b> Szerokosc: {lat}, Dlugosc: {lon} ({remove_polish_chars(station_name)})",
            normal_style))

    if details_dict:
        for k, v in details_dict.items():
            ck = remove_polish_chars(str(k))
            cv = remove_polish_chars(str(v))
            story.append(Paragraph(f"<b>{ck}:</b> {cv}", normal_style))
        story.append(Spacer(1, 8))

    # 3. Wykres i Tabela danych (tylko dla danych pomiarowych / szeregów)
    if df_data is not None and not df_data.empty:
        df_processed = df_data.copy()
        try:
            df_processed.index = pd.to_datetime(df_processed.index)
            if df_processed.index.tz is not None:
                df_processed.index = df_processed.index.tz_localize(None)

            # Rygorystyczne odcięcie przyszłości
            current_time = pd.Timestamp.now()
            df_processed = df_processed[df_processed.index <= current_time]

            # Średnie godzinne
            df_processed = df_processed.resample('h').mean().dropna(how='all')
        except Exception as e:
            print(f"Blod przetwarzania danych w PDF: {e}")

        if not df_processed.empty:
            # Dodanie wykresów
            try:
                img_buf = create_chart_image(df_processed)
                story.append(Image(img_buf, width=450, height=190))
                story.append(Spacer(1, 10))
            except Exception as e:
                print(f"Blod generowania wykresu do PDF: {e}")

            # Przygotowanie tabeli
            df_table = df_processed.copy()
            df_table.reset_index(inplace=True)
            date_col = df_table.columns[0]

            try:
                df_table[date_col] = pd.to_datetime(df_table[date_col]).dt.strftime('%H:00 (%d.%m)')
            except Exception:
                pass

            new_columns = [remove_polish_chars(col) for col in df_table.columns]
            df_table.columns = new_columns

            table_data = [df_table.columns.tolist()] + df_table.astype(str).values.tolist()

            t = Table(table_data, hAlign='CENTER')
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 7),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('FONTSIZE', (0, 1), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f3f5")])
            ]))
            story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()