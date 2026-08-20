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
    """Usuwa polskie znaki diakrytyczne."""
    if not isinstance(text, str): text = str(text)
    replacements = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
                    'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'}
    for pl, lat in replacements.items(): text = text.replace(pl, lat)
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def create_location_map_image(lat, lon, station_name):
    """Generuje profesjonalny wycinek mapy z zaznaczoną stacją."""
    plt.clf()  # Zresetuj wykres
    plt.figure(figsize=(5, 3))
    plt.plot(lon, lat, 'ro', markersize=10, label='Lokalizacja', zorder=10)
    plt.text(lon + 0.02, lat + 0.02, remove_polish_chars(station_name), fontsize=9, fontweight='bold')
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.xlim(lon - 0.3, lon + 0.3)
    plt.ylim(lat - 0.2, lat + 0.2)
    plt.xlabel("Dlugosc [Lon]")
    plt.ylabel("Szerokosc [Lat]")
    plt.title(remove_polish_chars(f"Lokalizacja: {station_name}"), fontsize=10)
    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=100)
    plt.close()
    img_buffer.seek(0)
    return img_buffer


def create_chart_image(df_data):
    """Generuje wykres matplotlib ze średnimi godzinnymi."""
    plt.clf()
    plt.figure(figsize=(7, 3.0))
    for col in df_data.columns:
        clean_col = remove_polish_chars(col)
        plt.plot(df_data.index, df_data[col], label=clean_col, linewidth=1.5, marker='o', markersize=3)
    plt.title(remove_polish_chars("Wykres zanieczyszczen (srednie godzinne)"), fontsize=9)
    plt.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1, 1))
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=100)
    plt.close()
    img_buffer.seek(0)
    return img_buffer


def generate_general_pdf_report(title, subtitle, df_data=None, details_dict=None, lat=None, lon=None,
                                station_name="Obszar"):
    """
    Uniwersalny generator raportów PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)

    story = []
    styles = getSampleStyleSheet()

    # 1. Nagłówki
    story.append(Paragraph(f"RDOS Monitoring - {remove_polish_chars(title)}", styles['Heading1']))
    story.append(Paragraph(remove_polish_chars(subtitle), styles['Normal']))
    story.append(Spacer(1, 12))

    # 2. Mapa
    if lat is not None and lon is not None:
        try:
            map_buf = create_location_map_image(float(lat), float(lon), station_name)
            story.append(Image(map_buf, width=300, height=180))
            story.append(Spacer(1, 12))
        except Exception as e:
            print(f"Błąd mapy: {e}")

    # 3. Szczegóły
    if details_dict:
        for k, v in details_dict.items():
            story.append(
                Paragraph(f"<b>{remove_polish_chars(str(k))}:</b> {remove_polish_chars(str(v))}", styles['Normal']))
        story.append(Spacer(1, 12))

    # 4. Wykres i Tabela (dane)
    if df_data is not None and not df_data.empty:
        df_processed = df_data.copy()
        try:
            # Upewnij się, że indeks jest czasowy
            df_processed.index = pd.to_datetime(df_processed.index)
            # Rygorystyczne odcięcie przyszłości
            current_time = pd.Timestamp.now()
            df_processed = df_processed[df_processed.index <= current_time]
            # Resample do godzin
            df_processed = df_processed.resample('h').mean().dropna(how='all')
        except Exception as e:
            print(f"Błąd przetwarzania danych: {e}")

        if not df_processed.empty:
            # Dodaj wykres
            try:
                img_buf = create_chart_image(df_processed)
                story.append(Image(img_buf, width=400, height=180))
                story.append(Spacer(1, 12))
            except Exception as e:
                print(f"Błąd wykresu: {e}")

            # Dodaj tabelę
            df_table = df_processed.reset_index()
            df_table[df_table.columns[0]] = df_table[df_table.columns[0]].dt.strftime('%H:00 (%d.%m)')
            df_table.columns = [remove_polish_chars(c) for c in df_table.columns]

            table_data = [df_table.columns.tolist()] + df_table.astype(str).values.tolist()
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 6),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f0f0"))
            ]))
            story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()