from __future__ import annotations

import io
from dataclasses import replace

import pandas as pd
import streamlit as st
from PIL import Image

from conrad_finder.article_numbers import (
    extract_article_numbers,
    normalize_article_number,
)
from conrad_finder.config import AppConfig
from conrad_finder.export import build_export, dataframe_to_excel_friendly_csv
from conrad_finder.importers import dataframe_to_rows, read_csv
from conrad_finder.models import ImportRow, ProductCandidate, SearchOutcome
from conrad_finder.ocr import OcrService, optional_features
from conrad_finder.search import ProductSearchService
from conrad_finder.search.service import run_coroutine
from conrad_finder.state import AppState

from .theme import CSS


def _init() -> None:
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState()
    if "raw_csv" not in st.session_state:
        st.session_state.raw_csv = None


def _state() -> AppState:
    return st.session_state.app_state


def _hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <h1>Conrad Produktfinder</h1>
            <p>Artikelnummern erfassen, passende Produkte prüfen und die Auswahl sauber exportieren.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _sidebar(base: AppConfig) -> AppConfig:
    with st.sidebar:
        st.markdown("## Einstellungen")

        with st.expander("Suche", expanded=True):
            max_results = st.slider("Max. Treffer pro Artikel", 1, 10, base.max_results)
            delay = st.slider(
                "Pause zwischen Suchanfragen (Sek.)",
                0.0,
                3.0,
                float(base.search_delay),
                0.1,
            )
            fallback = st.toggle("Fallback-Suche", value=base.fallback_enabled)
            provider = st.selectbox(
                "Fallback-Anbieter",
                ["duckduckgo", "serper", "bing"],
                index=["duckduckgo", "serper", "bing"].index(base.fallback_provider)
                if base.fallback_provider in {"duckduckgo", "serper", "bing"}
                else 0,
            )

        with st.expander("OCR", expanded=False):
            language = st.selectbox("OCR-Sprache", ["deu+eng", "deu", "eng"])
            dpi = st.select_slider("PDF-DPI", [200, 250, 300, 350, 400], value=base.ocr_dpi)
            tesseract = st.text_input("Tesseract-Pfad", value=base.tesseract_path)
            tessdata = st.text_input("Tessdata-Pfad", value=base.tessdata_path)
            poppler = st.text_input("Poppler-Pfad", value=base.poppler_path)

        st.caption("API-Schlüssel werden ausschließlich aus Umgebungsvariablen gelesen.")

    return replace(
        base,
        max_results=max_results,
        search_delay=delay,
        fallback_enabled=fallback,
        fallback_provider=provider,
        ocr_language=language,
        ocr_dpi=dpi,
        tesseract_path=tesseract,
        tessdata_path=tessdata,
        poppler_path=poppler,
    )


def _render_metrics() -> None:
    state = _state()
    found = sum(1 for result in state.results.values() if result.candidates)
    selected = len(state.selected)

    cols = st.columns(3)
    values = (
        ("Positionen", len(state.rows)),
        ("Mit Treffern", found),
        ("Ausgewählt", selected),
    )
    for col, (label, value) in zip(cols, values):
        col.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _set_rows(rows: list[ImportRow]) -> None:
    state = _state()
    state.rows = rows
    state.reset_search()


def _csv_input() -> None:
    uploaded = st.file_uploader("CSV-Datei auswählen", type=["csv"], key="csv_upload")
    if not uploaded:
        return

    try:
        dataframe = read_csv(uploaded.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        return

    st.session_state.raw_csv = dataframe
    st.dataframe(dataframe.head(50), use_container_width=True)

    columns = list(dataframe.columns)
    if not columns:
        st.warning("Die CSV enthält keine Spalten.")
        return

    c1, c2, c3 = st.columns(3)
    article_col = c1.selectbox("Spalte Artikel-Nr.", columns)
    quantity_col = c2.selectbox("Spalte Menge", ["—"] + columns)
    description_col = c3.selectbox("Spalte Beschreibung", ["—"] + columns)

    if st.button("CSV übernehmen", type="primary", use_container_width=True):
        rows = dataframe_to_rows(
            dataframe,
            article_column=article_col,
            quantity_column=None if quantity_col == "—" else quantity_col,
            description_column=None if description_col == "—" else description_col,
        )
        _set_rows(rows)
        st.success(f"{len(rows)} gültige Positionen übernommen.")


def _pdf_input(config: AppConfig) -> None:
    uploaded = st.file_uploader("PDF-Datei auswählen", type=["pdf"], key="pdf_upload")
    if not uploaded:
        return

    service = OcrService(config)
    with st.spinner("PDF wird ausgewertet …"):
        text = service.extract_pdf_text(uploaded.getvalue())

    numbers = extract_article_numbers(text)
    if not numbers:
        st.warning("Keine passenden Artikelnummern erkannt.")
        return

    st.write("Erkannte Artikelnummern:")
    st.code("\n".join(numbers))

    if st.button("Erkannte Nummern übernehmen", type="primary"):
        _set_rows([ImportRow(article_number=n) for n in numbers])
        st.success(f"{len(numbers)} Positionen übernommen.")


def _manual_input() -> None:
    with st.form("manual_form", clear_on_submit=False):
        count = st.number_input("Anzahl Positionen", 1, 30, 3)
        rows: list[ImportRow] = []

        for index in range(int(count)):
            c1, c2, c3 = st.columns([1, 2, 4])
            qty = c1.number_input("Menge", 1, 999, 1, key=f"m_qty_{index}")
            article = c2.text_input("Artikel-Nr.", key=f"m_article_{index}")
            desc = c3.text_input("Beschreibung", key=f"m_desc_{index}")
            normalized = normalize_article_number(article)
            if normalized:
                rows.append(
                    ImportRow(
                        quantity=int(qty),
                        article_number=normalized,
                        description=desc.strip(),
                    )
                )

        submitted = st.form_submit_button("Liste übernehmen", type="primary")
        if submitted:
            if not rows:
                st.warning("Bitte mindestens eine gültige Artikelnummer eingeben.")
            else:
                _set_rows(rows)
                st.success(f"{len(rows)} Positionen übernommen.")


def _camera_input(config: AppConfig) -> None:
    image_file = st.camera_input("Barcode oder Artikelnummer aufnehmen")
    if not image_file:
        return

    image = Image.open(io.BytesIO(image_file.getvalue()))
    article = OcrService(config).extract_from_image(image)
    if not article:
        st.warning("Keine Artikelnummer erkannt.")
        return

    st.success(f"Erkannt: {article}")
    if st.button("Zur Liste hinzufügen", type="primary"):
        state = _state()
        state.rows.append(ImportRow(article_number=article))
        state.reset_search()


def _data_source(config: AppConfig) -> None:
    features = optional_features()
    options = ["CSV", "Manuell"]
    if features.pdf_text or (features.pdf_images and features.tesseract):
        options.append("PDF")
    if features.barcode or features.tesseract:
        options.append("Kamera")

    source = st.segmented_control(
        "Datenquelle",
        options,
        default=options[0],
        selection_mode="single",
    )

    if source == "CSV":
        _csv_input()
    elif source == "PDF":
        _pdf_input(config)
    elif source == "Manuell":
        _manual_input()
    elif source == "Kamera":
        _camera_input(config)


def _rows_table() -> None:
    state = _state()
    if not state.rows:
        return

    st.markdown("### Positionen")
    dataframe = pd.DataFrame(
        [
            {
                "Pos.": i + 1,
                "Menge": row.quantity,
                "Artikel-Nr.": row.article_number,
                "Beschreibung": row.description,
            }
            for i, row in enumerate(state.rows)
        ]
    )
    st.dataframe(dataframe, use_container_width=True, hide_index=True)


def _search(config: AppConfig) -> None:
    state = _state()
    if not state.rows:
        return

    left, right = st.columns([1, 3])
    start = left.button("Alle Artikel suchen", type="primary", use_container_width=True)
    right.caption(
        "Die Suche läuft bewusst nacheinander, damit externe Dienste nicht unnötig belastet werden."
    )

    if not start:
        return

    service = ProductSearchService(config)
    progress = st.progress(0.0)
    status = st.empty()

    def update(current: int, total: int, article: str) -> None:
        progress.progress(current / max(total, 1))
        status.caption(f"Suche {current}/{total}: {article}")

    outcomes = run_coroutine(
        service.search_many([row.article_number for row in state.rows], update)
    )
    state.results = {index: outcome for index, outcome in enumerate(outcomes)}
    state.selected.clear()
    status.caption("Suche abgeschlossen.")


def _render_candidate(index: int, candidate: ProductCandidate) -> None:
    state = _state()
    label = candidate.display_label()
    selected = state.selected.get(index)

    cols = st.columns([5, 1])
    with cols[0]:
        st.markdown(
            f"""
            <div class="product-card">
                <strong>{candidate.title}</strong><br>
                <span class="badge">{candidate.source.value}</span>
                &nbsp; Artikel-Nr.: {candidate.article_number}
                &nbsp; · &nbsp; {candidate.price or "Preis nicht erkannt"}
                &nbsp; · &nbsp; Trefferwert {candidate.score}
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        if st.button(
            "Ausgewählt" if selected and selected.url == candidate.url else "Wählen",
            key=f"choose_{index}_{abs(hash(candidate.url))}",
            type="primary" if selected and selected.url == candidate.url else "secondary",
            use_container_width=True,
        ):
            state.selected[index] = candidate
            st.rerun()

        st.link_button("Öffnen", candidate.url, use_container_width=True)


def _results() -> None:
    state = _state()
    if not state.results:
        return

    st.markdown("### Suchergebnisse")

    for index, row in enumerate(state.rows):
        outcome: SearchOutcome | None = state.results.get(index)
        if outcome is None:
            continue

        with st.expander(
            f"Position {index + 1} · {row.article_number}",
            expanded=index < 3,
        ):
            if outcome.error:
                st.warning(f"Suche nicht vollständig: {outcome.error}")

            if not outcome.candidates:
                st.info("Kein passender Treffer gefunden.")
                continue

            for candidate in outcome.candidates:
                _render_candidate(index, candidate)


def _export() -> None:
    state = _state()
    if not state.rows:
        return

    st.markdown("### Export")
    dataframe = build_export(state.rows, state.selected)
    st.dataframe(dataframe, use_container_width=True, hide_index=True)

    st.download_button(
        "Ergebnis als CSV herunterladen",
        data=dataframe_to_excel_friendly_csv(dataframe),
        file_name="conrad_ergebnisse.csv",
        mime="text/csv",
        type="primary",
    )


def run_app() -> None:
    st.set_page_config(
        page_title="Conrad Produktfinder",
        page_icon="🟠",
        layout="wide",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    _init()
    _hero()

    config = _sidebar(AppConfig.from_env())

    _render_metrics()
    st.markdown("### Daten erfassen")
    _data_source(config)
    _rows_table()
    _search(config)
    _results()
    _export()

    st.markdown(
        '<div class="footer">Conrad Produktfinder · Entwickelt von Amir Mobasheraghdam</div>',
        unsafe_allow_html=True,
    )
