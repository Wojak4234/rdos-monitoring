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
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
    }
    for pl, lat in replacements.items():
        text = text.replace(pl, lat)
    nfkd_form = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def create_location_map_image(lat, lon, station_name):
    """Generuje mapę punktową stacji pomiarowej do wklejenia do raportu PDF."""
    plt.figure(figsize=(6, 2.2))
    plt.scatter([lon], [lat], color='#2d6a4f', s=120, zorder=5, marker='o', label='Stacja pomiarowa')
    plt.title(remove_polish_chars(f"Lokalizacja stacji: {station_name}"), fontsize=9, fontweight='bold')
    plt.xlabel(remove_polish_chars("Dlugosc geograficzna (Lon)"), fontsize=8)
    plt.ylabel(remove_polish_chars("Szerokosc geograficzna (Lat)"), fontsize=8)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.xlim(lon - 0.15, lon + 0.15)
    plt.ylim(lat - 0.15, lat + 0.15)
    plt.legend(fontsize=7, loc='upper right')
    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150)
    plt.close()
    img_buffer.seek(0)
    return img_buffer


def create_chart_image(df_data):
    plt.figure(figsize=(7, 3.0))
    for col in df_data.columns:
        clean_col = remove_polish_chars(col)
        plt.plot(df_data.index, df_data[col], label=clean_col, linewidth=1.5, marker='o', markersize=3)

    plt.title(remove_polish_chars("Wykres zanieczyszczen (srednie godzinne)"), fontsize=9, fontweight='bold')
    plt.xlabel(remove_polish_chars("Czas"), fontsize=8)
    plt.ylabel(remove_polish_chars("Stzenie / Wartosc"), fontsize=8)
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
                                station_name=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30
    )

    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('ReportTitle', parent=styles['Heading1'], fontSize=14,
                                 textColor=colors.HexColor("#1b4332"), spaceAfter=6)
    subtitle_style = ParagraphStyle('ReportSubtitle', parent=styles['Normal'], fontSize=9,
                                    textColor=colors.HexColor("#555555"), spaceAfter=10)
    normal_style = ParagraphStyle('NormalText', parent=styles['Normal'], fontSize=8,
                                  textColor=colors.HexColor("#333333"), spaceAfter=6)

    story.append(Paragraph(f"RDOS Monitoring - {remove_polish_chars(title)}", title_style))
    story.append(Paragraph(remove_polish_chars(subtitle), subtitle_style))
    story.append(Spacer(1, 4))

    # Wklejenie mapy lokalizacji stacji, jeśli podano współrzędne
    if lat is not None and lon is not None:
        try:
            s_name = station_name if station_name else "Stacja"
            map_buf = create_location_map_image(float(lat), float(lon), s_name)
            story.append(Image(map_buf, width=400, height=140))
            story.append(Spacer(1, 6))
        except Exception as e:
            print(f"Blod generowania mapy do PDF: {e}")

    if details_dict:
        for k, v in details_dict.items():
            ck = remove_polish_chars(str(k))
            cv = remove_polish_chars(str(v))
            story.append(Paragraph(f"<b>{ck}:</b> {cv}", normal_style))
        story.append(Spacer(1, 6))

    if df_data is not None and not df_data.empty:
        df_processed = df_data.copy()
        try:
            if not isinstance(df_processed.index, pd.DatetimeIndex):
                df_processed.index = pd.to_datetime(df_processed.index)
            if df_processed.index.tz is not None:
                df_processed.index = df_processed.index.tz_localize(None)
        except Exception:
            pass

        if isinstance(df_processed.index, pd.DatetimeIndex):
            current_time = pd.Timestamp.now().tz_localize(None)
            df_processed = df_processed[df_processed.index <= current_time]
            df_processed = df_processed.resample('h').mean().dropna(how='all')

        if not df_processed.empty:
            try:
                img_buf = create_chart_image(df_processed)
                story.append(Image(img_buf, width=450, height=180))
                story.append(Spacer(1, 6))
            except Exception as e:
                print(f"Blod generowania wykresu do PDF: {e}")

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