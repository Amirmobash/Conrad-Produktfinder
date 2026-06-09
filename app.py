import asyncio
import base64
import hashlib
import io
import os
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import aiohttp
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import pdf2image
except ImportError:
    pdf2image = None

try:
    from pyzbar.pyzbar import decode
except ImportError:
    decode = None

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


@dataclass
class SearchConfig:
    tesseract_path: str
    tessdata_path: str
    poppler_path: str
    ocr_language: str
    ocr_dpi: int
    search_delay: float
    max_results: int
    fallback_enabled: bool
    search_provider: str
    serper_api_key: Optional[str]
    bing_api_key: Optional[str]
    cache_ttl: int


@dataclass
class ProductResult:
    url: str
    title: str
    article_number: str
    price: Optional[str]
    relevance: int
    source: str


TEXT = {
    "title": "🔍 Conrad Produktfinder",
    "subtitle": "CSV, PDF, manuelle Eingabe oder Webcam – Artikelnummern erkennen und passende Conrad-Produkte finden",
    "data_source": "📁 Datenquelle wählen",
    "csv": "📄 CSV",
    "pdf": "📑 PDF",
    "manual": "✏️ Manuell",
    "webcam": "📸 Webcam",
    "settings": "⚙️ Einstellungen",
    "ocr_settings": "📑 OCR-Einstellungen",
    "search_settings": "🔍 Sucheinstellungen",
    "fallback_settings": "🌐 Web-Fallback",
    "upload_file": "Datei hochladen",
    "preview": "📋 Erkannte Artikel",
    "mapping": "🔧 Spalten zuordnen",
    "quantity": "Menge",
    "article": "Artikel-Nr.",
    "description": "Beschreibung",
    "apply": "Übernehmen",
    "results": "🎯 Suchergebnisse",
    "final": "✅ Ausgewählte Produkte",
    "download": "📥 Ergebnis als CSV herunterladen",
    "not_found": "Nicht gefunden",
}


def optional_support() -> Dict[str, bool]:
    return {
        "ocr": pytesseract is not None,
        "pdf_image": pdf2image is not None,
        "barcode": decode is not None,
        "pdf_text": PdfReader is not None,
    }


def init_state() -> None:
    defaults = {
        "items": None,
        "mapping": {},
        "results": {},
        "selected": {},
        "cache": {},
        "cache_time": {},
        "auto_search_done": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clean_article_number(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = re.sub(r"[^\d-]", "", text)

    if "-" in text:
        text = text.split("-")[0]

    text = re.sub(r"\s+", "", text)

    if text.isdigit() and 5 <= len(text) <= 8:
        return text

    return None


def setup_ocr(config: SearchConfig) -> bool:
    if pytesseract is None:
        return False

    try:
        if config.tesseract_path and os.path.exists(config.tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = config.tesseract_path

        if config.tessdata_path and os.path.exists(config.tessdata_path):
            os.environ["TESSDATA_PREFIX"] = config.tessdata_path

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_barcode(image: Image.Image) -> Optional[str]:
    if decode is None:
        return None

    try:
        for code in decode(image):
            value = code.data.decode("utf-8", errors="ignore").strip()
            article_number = clean_article_number(value)

            if article_number:
                return article_number
    except Exception:
        return None

    return None


def extract_article_with_ocr(image: Image.Image, config: SearchConfig) -> Optional[str]:
    if pytesseract is None or not setup_ocr(config):
        return None

    try:
        gray = image.convert("L")
        options = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789-"
        text = pytesseract.image_to_string(gray, lang=config.ocr_language, config=options)

        for number in re.findall(r"\d{5,8}", text):
            article_number = clean_article_number(number)

            if article_number:
                return article_number
    except Exception:
        return None

    return None


def extract_text_from_pdf(pdf_bytes: bytes, config: SearchConfig) -> str:
    text_parts = []

    if PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))

            for page in reader.pages:
                page_text = page.extract_text() or ""

                if page_text.strip():
                    text_parts.append(page_text)

            if text_parts:
                return "\n".join(text_parts)
        except Exception:
            pass

    if pdf2image is None or pytesseract is None or not setup_ocr(config):
        return ""

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_path = temp_file.name

        poppler_path = config.poppler_path if config.poppler_path and os.path.exists(config.poppler_path) else None

        pages = pdf2image.convert_from_path(
            temp_path,
            dpi=config.ocr_dpi,
            poppler_path=poppler_path,
        )

        for page in pages:
            image = page.convert("L")
            text_parts.append(
                pytesseract.image_to_string(image, lang=config.ocr_language)
            )

    except Exception:
        return ""

    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    return "\n".join(text_parts)


def extract_article_numbers(text: str) -> List[str]:
    if not text:
        return []

    patterns = [
        r"bestell[.\-\s]*nr\.?\s*:?\s*(\d{5,8})",
        r"artikel[.\-\s]*nr\.?\s*:?\s*(\d{5,8})",
        r"conrad\s*art\.?\s*nr\.?\s*:?\s*(\d{5,8})",
        r"\b(\d{5,8})\b",
    ]

    found = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            article_number = clean_article_number(match.group(1))

            if article_number:
                found.add(article_number)

    return sorted(found)


def pdf_to_dataframe(pdf_bytes: bytes, config: SearchConfig) -> Optional[pd.DataFrame]:
    with st.spinner("PDF wird verarbeitet..."):
        text = extract_text_from_pdf(pdf_bytes, config)

    if not text:
        st.error("Aus der PDF konnte kein Text gelesen werden.")
        return None

    article_numbers = extract_article_numbers(text)

    if not article_numbers:
        st.warning("Keine gültigen Conrad-Artikelnummern gefunden.")
        return None

    data = [
        {
            "Menge": 1,
            "Artikel-Nr.": number,
            "Beschreibung": "",
        }
        for number in article_numbers
    ]

    st.success(f"{len(data)} Artikelnummern erkannt.")
    return pd.DataFrame(data)


async def fetch_html(session: aiohttp.ClientSession, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    headers = headers or {"User-Agent": "Mozilla/5.0"}

    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status == 200:
                return await response.text()
    except Exception:
        return None

    return None


async def search_conrad(article_number: str, session: aiohttp.ClientSession) -> List[ProductResult]:
    url = f"https://www.conrad.de/de/search.html?search={quote(article_number)}"
    html = await fetch_html(session, url)

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(r"/de/p/[\w\-]+-\d+\.html", re.IGNORECASE)
    products = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if not pattern.search(href):
            continue

        full_url = urljoin("https://www.conrad.de", href)

        if full_url in seen:
            continue

        seen.add(full_url)

        title = link.get_text(" ", strip=True) or "Conrad Produkt"

        products.append(
            ProductResult(
                url=full_url,
                title=title,
                article_number=article_number,
                price=None,
                relevance=100,
                source="conrad",
            )
        )

    return products


async def search_duckduckgo(article_number: str, session: aiohttp.ClientSession) -> List[ProductResult]:
    query = f"site:conrad.de/de/p/ {article_number} Bestell-Nr"
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    html = await fetch_html(session, url)

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        if "conrad.de/de/p/" not in href:
            continue

        full_url = href if href.startswith("http") else f"https:{href}"

        if full_url in seen:
            continue

        seen.add(full_url)

        title = link.get_text(" ", strip=True) or "Conrad Produkt"

        products.append(
            ProductResult(
                url=full_url,
                title=title,
                article_number=article_number,
                price=None,
                relevance=85,
                source="duckduckgo",
            )
        )

    return products[:5]


async def search_serper(article_number: str, api_key: str, session: aiohttp.ClientSession) -> List[ProductResult]:
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": f"site:conrad.de/de/p/ {article_number}",
        "num": 5,
    }

    try:
        async with session.post(url, headers=headers, json=payload, timeout=15) as response:
            if response.status != 200:
                return []

            data = await response.json()
    except Exception:
        return []

    products = []

    for item in data.get("organic", []):
        link = item.get("link", "")

        if "conrad.de/de/p/" not in link:
            continue

        products.append(
            ProductResult(
                url=link,
                title=item.get("title", "Conrad Produkt"),
                article_number=article_number,
                price=None,
                relevance=95,
                source="serper",
            )
        )

    return products


async def search_bing(article_number: str, api_key: str, session: aiohttp.ClientSession) -> List[ProductResult]:
    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {
        "q": f"site:conrad.de/de/p/ {article_number}",
        "count": 5,
        "responseFilter": "Webpages",
    }

    try:
        async with session.get(url, headers=headers, params=params, timeout=15) as response:
            if response.status != 200:
                return []

            data = await response.json()
    except Exception:
        return []

    products = []

    for item in data.get("webPages", {}).get("value", []):
        link = item.get("url", "")

        if "conrad.de/de/p/" not in link:
            continue

        products.append(
            ProductResult(
                url=link,
                title=item.get("name", "Conrad Produkt"),
                article_number=article_number,
                price=None,
                relevance=95,
                source="bing",
            )
        )

    return products


async def fallback_search(article_number: str, config: SearchConfig, session: aiohttp.ClientSession) -> List[ProductResult]:
    if config.search_provider == "serper" and config.serper_api_key:
        return await search_serper(article_number, config.serper_api_key, session)

    if config.search_provider == "bing" and config.bing_api_key:
        return await search_bing(article_number, config.bing_api_key, session)

    return await search_duckduckgo(article_number, session)


async def load_product_details(product: ProductResult, session: aiohttp.ClientSession) -> ProductResult:
    html = await fetch_html(session, product.url)

    if not html:
        return product

    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1")
    title = title_tag.get_text(" ", strip=True) if title_tag else product.title

    page_text = soup.get_text(" ", strip=True)
    number_match = re.search(r"Bestell[\s\-]*Nr\.?\s*([A-Z0-9\-]+)", page_text, re.IGNORECASE)

    article_number = number_match.group(1) if number_match else product.article_number

    price_tag = soup.select_one(".price__value, .product__price, [data-test='product-price']")
    price = price_tag.get_text(" ", strip=True) if price_tag else product.price

    relevance = 100 if clean_article_number(article_number) == clean_article_number(product.article_number) else product.relevance

    return ProductResult(
        url=product.url,
        title=title,
        article_number=article_number,
        price=price,
        relevance=relevance,
        source=product.source,
    )


async def search_product(article_number: str, config: SearchConfig) -> List[ProductResult]:
    cache_key = hashlib.md5(article_number.encode("utf-8")).hexdigest()
    cached = st.session_state.cache.get(cache_key)
    cached_at = st.session_state.cache_time.get(cache_key, 0)

    if cached and time.time() - cached_at < config.cache_ttl:
        return cached

    async with aiohttp.ClientSession() as session:
        products = await search_conrad(article_number, session)

        if not products and config.fallback_enabled:
            products = await fallback_search(article_number, config, session)

        detailed = []

        for product in products[: config.max_results]:
            detailed.append(await load_product_details(product, session))

        detailed.sort(key=lambda item: item.relevance, reverse=True)

    st.session_state.cache[cache_key] = detailed
    st.session_state.cache_time[cache_key] = time.time()

    return detailed


def run_async_search(article_number: str, config: SearchConfig) -> List[ProductResult]:
    try:
        return asyncio.run(search_product(article_number, config))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            return loop.run_until_complete(search_product(article_number, config))
        finally:
            loop.close()


def automatic_search(dataframe: pd.DataFrame, config: SearchConfig, mapping: Dict[str, str]) -> None:
    article_column = mapping.get("article", "Artikel-Nr.")
    total = len(dataframe)

    progress = st.progress(0)
    status = st.empty()

    for position, (index, row) in enumerate(dataframe.iterrows(), start=1):
        status.text(f"Suche Position {position} von {total}")

        article_number = clean_article_number(row.get(article_column))

        if article_number:
            st.session_state.results[index] = run_async_search(article_number, config)
        else:
            st.session_state.results[index] = []

        progress.progress(position / total)

        if config.search_delay > 0:
            time.sleep(config.search_delay)

    status.text("Suche abgeschlossen.")
    st.session_state.auto_search_done = True


def build_sidebar_config() -> SearchConfig:
    support = optional_support()

    st.sidebar.title(TEXT["settings"])

    st.sidebar.subheader(TEXT["ocr_settings"])

    tesseract_path = st.sidebar.text_input(
        "Tesseract-Pfad",
        value=os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    )

    tessdata_path = st.sidebar.text_input(
        "Tessdata-Pfad",
        value=os.getenv("TESSDATA_PATH", r"C:\Program Files\Tesseract-OCR\tessdata"),
    )

    poppler_path = st.sidebar.text_input(
        "Poppler-Pfad",
        value=os.getenv("POPPLER_PATH", r"C:\poppler\Library\bin"),
    )

    ocr_language = "deu+eng"
    ocr_dpi = 300

    if support["ocr"]:
        ocr_language = st.sidebar.selectbox("OCR-Sprache", ["deu+eng", "deu", "eng"])

    if support["pdf_image"]:
        ocr_dpi = st.sidebar.selectbox("OCR-DPI", [200, 300, 400], index=1)

    st.sidebar.subheader(TEXT["search_settings"])

    search_delay = st.sidebar.number_input(
        "Verzögerung zwischen Suchanfragen",
        min_value=0.0,
        max_value=5.0,
        value=float(os.getenv("SEARCH_DELAY", "0.5")),
        step=0.25,
    )

    max_results = st.sidebar.number_input(
        "Maximale Ergebnisse pro Artikel",
        min_value=1,
        max_value=10,
        value=int(os.getenv("MAX_RESULTS", "5")),
    )

    st.sidebar.subheader(TEXT["fallback_settings"])

    fallback_enabled = st.sidebar.checkbox(
        "Fallback-Suche aktivieren",
        value=os.getenv("ENABLE_FALLBACK", "true").lower() == "true",
    )

    search_provider = st.sidebar.selectbox(
        "Fallback-Anbieter",
        ["duckduckgo", "serper", "bing"],
    )

    serper_key = None
    bing_key = None

    if search_provider == "serper":
        serper_key = st.sidebar.text_input(
            "Serper API Key",
            value=os.getenv("SERPER_API_KEY", ""),
            type="password",
        )

    if search_provider == "bing":
        bing_key = st.sidebar.text_input(
            "Bing API Key",
            value=os.getenv("BING_API_KEY", ""),
            type="password",
        )

    cache_ttl = int(os.getenv("CACHE_TTL", "3600"))
    st.sidebar.info(f"Cache gültig für {cache_ttl} Sekunden.")

    return SearchConfig(
        tesseract_path=tesseract_path,
        tessdata_path=tessdata_path,
        poppler_path=poppler_path,
        ocr_language=ocr_language,
        ocr_dpi=ocr_dpi,
        search_delay=search_delay,
        max_results=max_results,
        fallback_enabled=fallback_enabled,
        search_provider=search_provider,
        serper_api_key=serper_key,
        bing_api_key=bing_key,
        cache_ttl=cache_ttl,
    )


def show_csv_input() -> None:
    uploaded = st.file_uploader(TEXT["upload_file"], type=["csv"])

    if not uploaded:
        return

    try:
        dataframe = pd.read_csv(uploaded)
    except Exception as error:
        st.error(f"CSV konnte nicht gelesen werden: {error}")
        return

    st.session_state.items = dataframe
    st.session_state.results = {}
    st.session_state.selected = {}
    st.session_state.auto_search_done = False


def show_pdf_input(config: SearchConfig) -> None:
    uploaded = st.file_uploader(TEXT["upload_file"], type=["pdf"])

    if not uploaded:
        return

    dataframe = pdf_to_dataframe(uploaded.getvalue(), config)

    if dataframe is not None:
        st.session_state.items = dataframe
        st.session_state.mapping = {
            "quantity": "Menge",
            "article": "Artikel-Nr.",
            "description": "Beschreibung",
        }
        st.session_state.results = {}
        st.session_state.selected = {}
        st.session_state.auto_search_done = False


def show_manual_input() -> None:
    count = st.number_input("Anzahl Produkte", min_value=1, max_value=50, value=3)
    rows = []

    for index in range(count):
        with st.expander(f"Produkt {index + 1}", expanded=index == 0):
            col1, col2, col3 = st.columns([1, 2, 3])

            quantity = col1.number_input("Menge", min_value=1, max_value=999, value=1, key=f"qty_{index}")
            article = col2.text_input("Artikel-Nr.", key=f"art_{index}")
            description = col3.text_input("Beschreibung", key=f"desc_{index}")

            article_number = clean_article_number(article)

            if article and not article_number:
                st.warning("Ungültige Artikelnummer.")

            if article_number:
                rows.append(
                    {
                        "Menge": quantity,
                        "Artikel-Nr.": article_number,
                        "Beschreibung": description,
                    }
                )

    if rows and st.button("Liste übernehmen"):
        st.session_state.items = pd.DataFrame(rows)
        st.session_state.mapping = {
            "quantity": "Menge",
            "article": "Artikel-Nr.",
            "description": "Beschreibung",
        }
        st.session_state.results = {}
        st.session_state.selected = {}
        st.session_state.auto_search_done = False
        st.rerun()


def show_webcam_input(config: SearchConfig) -> None:
    image_file = st.camera_input("Artikelnummer oder Barcode scannen")

    if not image_file:
        return

    image = Image.open(image_file)

    article_number = extract_barcode(image)

    if not article_number:
        article_number = extract_article_with_ocr(image, config)

    if not article_number:
        st.warning("Keine gültige Conrad-Artikelnummer erkannt.")
        return

    st.success(f"Erkannte Artikelnummer: {article_number}")

    if st.button("Zur Liste hinzufügen"):
        new_row = pd.DataFrame(
            [
                {
                    "Menge": 1,
                    "Artikel-Nr.": article_number,
                    "Beschreibung": "",
                }
            ]
        )

        if st.session_state.items is None:
            st.session_state.items = new_row
        else:
            st.session_state.items = pd.concat([st.session_state.items, new_row], ignore_index=True)

        st.session_state.mapping = {
            "quantity": "Menge",
            "article": "Artikel-Nr.",
            "description": "Beschreibung",
        }
        st.session_state.auto_search_done = False
        st.rerun()


def show_mapping(dataframe: pd.DataFrame, source: str) -> None:
    if source != TEXT["csv"]:
        st.session_state.mapping = {
            "quantity": "Menge",
            "article": "Artikel-Nr.",
            "description": "Beschreibung",
        }
        st.info("Die Spalten sind bereits passend zugeordnet.")
        return

    st.subheader(TEXT["mapping"])

    columns = [""] + list(dataframe.columns)
    col1, col2, col3 = st.columns(3)

    quantity = col1.selectbox(TEXT["quantity"], columns)
    article = col2.selectbox(TEXT["article"], columns)
    description = col3.selectbox(TEXT["description"], columns)

    if st.button(TEXT["apply"]):
        if not article:
            st.warning("Bitte eine Spalte für die Artikelnummer auswählen.")
            return

        st.session_state.mapping = {
            "quantity": quantity or "Menge",
            "article": article,
            "description": description or "Beschreibung",
        }
        st.session_state.auto_search_done = False
        st.success("Spaltenzuordnung gespeichert.")


def source_label(source: str) -> str:
    labels = {
        "conrad": "Conrad direkt",
        "duckduckgo": "Web-Fallback",
        "serper": "Serper API",
        "bing": "Bing API",
    }

    return labels.get(source, source)


def show_results_for_row(index: int, row: pd.Series, mapping: Dict[str, str]) -> None:
    results = st.session_state.results.get(index, [])

    if not results:
        st.write(TEXT["not_found"])
        return

    options = []

    for result in results:
        options.append(
            f"{result.title} | {result.article_number} | {result.price or 'N/A'} | {source_label(result.source)}"
        )

    selected_index = st.radio(
        "Produkt auswählen",
        range(len(options)),
        format_func=lambda value: options[value],
        key=f"select_{index}",
    )

    selected = results[selected_index]
    st.session_state.selected[index] = selected

    col1, col2 = st.columns([3, 1])

    col1.write(f"**Titel:** {selected.title}")
    col1.write(f"**Bestell-Nr.:** {selected.article_number}")
    col1.write(f"**Preis:** {selected.price or 'N/A'}")
    col1.write(f"**Quelle:** {source_label(selected.source)}")

    col2.link_button("Öffnen", selected.url)


def final_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for index, row in dataframe.iterrows():
        data = row.to_dict()
        selected = st.session_state.selected.get(index)

        if selected:
            data["Conrad URL"] = selected.url
            data["Bestell-Nr. Conrad"] = selected.article_number
            data["Titel Conrad"] = selected.title
            data["Preis Conrad"] = selected.price or ""
            data["Status"] = "Gefunden"
        else:
            data["Conrad URL"] = ""
            data["Bestell-Nr. Conrad"] = ""
            data["Titel Conrad"] = ""
            data["Preis Conrad"] = ""
            data["Status"] = TEXT["not_found"]

        rows.append(data)

    return pd.DataFrame(rows)


def download_dataframe(dataframe: pd.DataFrame) -> None:
    csv = dataframe.to_csv(index=False, encoding="utf-8-sig")
    encoded = base64.b64encode(csv.encode("utf-8-sig")).decode("utf-8")

    st.markdown(
        f'<a href="data:file/csv;base64,{encoded}" download="conrad_ergebnisse.csv">{TEXT["download"]}</a>',
        unsafe_allow_html=True,
    )


def render_items(config: SearchConfig, source: str) -> None:
    dataframe = st.session_state.items

    if dataframe is None:
        return

    st.subheader(TEXT["preview"])
    st.dataframe(dataframe, use_container_width=True)

    show_mapping(dataframe, source)

    if st.session_state.mapping and not st.session_state.auto_search_done:
        with st.spinner("Automatische Suche läuft..."):
            automatic_search(dataframe, config, st.session_state.mapping)

    if st.session_state.results:
        st.subheader(TEXT["results"])

        for index, row in dataframe.iterrows():
            article_column = st.session_state.mapping.get("article", "Artikel-Nr.")
            article_number = row.get(article_column, "?")

            with st.expander(f"Position {index + 1}: {article_number}"):
                show_results_for_row(index, row, st.session_state.mapping)

    if st.session_state.selected:
        st.subheader(TEXT["final"])
        output = final_dataframe(dataframe)
        st.dataframe(output, use_container_width=True)
        download_dataframe(output)


def main() -> None:
    st.set_page_config(
        page_title="Conrad Produktfinder",
        page_icon="🔍",
        layout="wide",
    )

    init_state()

    st.title(TEXT["title"])
    st.markdown(f"### {TEXT['subtitle']}")

    config = build_sidebar_config()
    support = optional_support()

    sources = [TEXT["csv"], TEXT["manual"]]

    if support["pdf_text"] or support["pdf_image"]:
        sources.append(TEXT["pdf"])

    if support["barcode"] or support["ocr"]:
        sources.append(TEXT["webcam"])

    source = st.radio(TEXT["data_source"], sources, horizontal=True)

    if source == TEXT["csv"]:
        show_csv_input()

    elif source == TEXT["pdf"]:
        show_pdf_input(config)

    elif source == TEXT["manual"]:
        show_manual_input()

    elif source == TEXT["webcam"]:
        show_webcam_input(config)

    render_items(config, source)


if __name__ == "__main__":
    main()
```
