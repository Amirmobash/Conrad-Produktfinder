# Conrad Produktfinder

Ein sauber strukturierter Produktfinder für Conrad-Bestellungen mit CSV-, PDF-, manueller und Kamera-Eingabe.

**Entwickelt von Amir Mobasheraghdam**

Die Anwendung liest Artikelnummern aus Bestelldaten, sucht passende Conrad-Produkte, zeigt Kandidaten übersichtlich an und exportiert die getroffene Auswahl als CSV.

## Highlights

- vollständig deutsche Benutzeroberfläche
- helles Weiß/Orange-Design
- CSV-Import mit Spaltenzuordnung
- PDF-Textextraktion mit OCR-Fallback
- Barcode- und OCR-Erkennung per Kamera
- direkte Conrad-Suche
- optionale Fallback-Suche über DuckDuckGo, Serper oder Bing
- Produktdetail-Anreicherung über strukturierte Daten und robuste HTML-Fallbacks
- saubere Service-/Domain-/UI-Trennung
- zentrale Konfiguration über Umgebungsvariablen
- Tests für Kernlogik
- GitHub Actions für Linting und Tests

## Projektstruktur

```text
.
├── app.py
├── pyproject.toml
├── requirements.txt
├── .streamlit/
│   └── config.toml
├── src/
│   └── conrad_finder/
│       ├── config.py
│       ├── models.py
│       ├── state.py
│       ├── article_numbers.py
│       ├── importers.py
│       ├── ocr.py
│       ├── export.py
│       ├── search/
│       │   ├── base.py
│       │   ├── conrad.py
│       │   ├── web.py
│       │   └── service.py
│       └── ui/
│           ├── theme.py
│           └── view.py
└── tests/
```

## Installation

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Dann:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Optionale System-Abhängigkeiten

Für OCR/PDF-Scans werden zusätzlich Tesseract und Poppler benötigt.

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng poppler-utils
```

### Windows

Tesseract und Poppler installieren und die Pfade anschließend in der Seitenleiste oder über Umgebungsvariablen konfigurieren.

## Konfiguration

Eine Vorlage liegt in `.env.example`.

Wichtige Variablen:

```env
TESSERACT_PATH=
TESSDATA_PATH=
POPPLER_PATH=
SEARCH_DELAY=0.5
MAX_RESULTS=5
CACHE_TTL=3600
ENABLE_FALLBACK=true
SERPER_API_KEY=
BING_API_KEY=
```

## Design

Die Oberfläche ist bewusst zurückhaltend gehalten:

- Weiß als Grundfläche
- Orange als Akzentfarbe
- klare Karten
- wenig visuelle Unruhe
- technische Informationen dort, wo sie gebraucht werden

## Hinweis zu externen Webseiten

HTML-Strukturen externer Webseiten können sich ändern. Die Suchlogik ist deshalb modular aufgebaut, sodass einzelne Provider ohne Änderungen an UI oder Importlogik ausgetauscht werden können.

## Entwicklung

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Lizenz

MIT License. Siehe `LICENSE`.

## Autor

**Amir Mobasheraghdam**
