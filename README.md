# Conrad Product Finder 🔍

A **Streamlit** web application that helps you **reconstruct Conrad orders** by extracting Conrad article numbers from CSV or PDF documents and matching them to current product pages on [conrad.de](https://www.conrad.de). It supports OCR for scanned PDFs and can optionally fall back to web search if the Conrad search returns no results.

**Author:** Amir Mobasheraghdam

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
  - [Python Dependencies](#python-dependencies)
  - [System Dependencies](#system-dependencies)
- [Configuration](#configuration)
- [Usage](#usage)
  - [1. Run the App](#1-run-the-app)
  - [2. Choose Data Source](#2-choose-data-source)
  - [3. Preview Extracted Data](#3-preview-extracted-data)
  - [4. Map Columns (CSV only)](#4-map-columns-csv-only)
  - [5. Search for Products](#5-search-for-products)
  - [6. Review and Select Candidates](#6-review-and-select-candidates)
  - [7. Export Final Selection](#7-export-final-selection)
- [Limitations & Notes](#limitations--notes)
- [How to Contribute](#how-to-contribute)
- [License](#license)

---

## Features

- **Multiple input sources**
  - Upload a **CSV** file containing article numbers and other columns.
  - Upload a **Conrad order/cart PDF** (OCR is used to extract article numbers).
  - **Manual entry**: enter article numbers directly in the UI.

- **OCR support for PDFs**
  - Uses **Tesseract OCR** via `pytesseract`.
  - Uses **pdf2image** to convert PDF pages to images.
  - Configurable DPI and OCR language (German/English).

- **Conrad product search by article number**
  - Searches conrad.de with the article number.
  - Parses the search result page and product pages using **BeautifulSoup**.
  - Extracts product URL, title, article number, and price (if available).
  - Basic relevance scoring to rank results.

- **Web search fallback (optional)**
  - If no direct result is found on Conrad, the app can use:
    - **DuckDuckGo HTML search** (no API key required).
    - **Serper.dev** (Google Search API).
    - **Bing Web Search** (Azure).
  - Only Conrad product URLs are kept from the web search.

- **Interactive UI**
  - Built with **Streamlit**.
  - Sidebar configuration for OCR and search behavior.
  - Per-row expanders to review each input item.
  - For each row, view all candidate products and select the correct one.
  - Open selected product in a new browser tab.

- **Export of final selection**
  - After selecting products, export a final CSV with:
    - Original row data.
    - Selected Conrad URL.
    - Selected article number.
    - Selected title.
    - Selected price.
    - Status (Found / Not found).
    - Source (Conrad / Web fallback).

---

## Tech Stack

- **Python** 3.8+
- **Streamlit** – web UI framework
- **Pandas** – data handling for CSV/rows
- **Requests** – HTTP requests for Conrad and web search
- **BeautifulSoup (bs4)** – HTML parsing
- **pdf2image** – convert PDF pages to images (for OCR)
- **pytesseract** – OCR engine interface
- **Pillow (PIL)** – image handling
- **fuzzywuzzy + python-Levenshtein** – (available for possible fuzzy matching, though not heavily used in current version)
- **lxml** – HTML parsing backend

All Python dependencies are listed in `requirements.txt`.

---

## Project Structure

```text
.
├── app.py             # Main Streamlit app (Conrad Product Finder)
├── requirements.txt   # Python dependencies
└── README.md          # Project documentation (this file)
```

---

## Installation

### Python Dependencies

1. **Clone the repository** (or download the source code):
   ```bash
   git clone https://github.com/<your-username>/conrad-product-finder.git
   cd conrad-product-finder
   ```

2. **Create and activate a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```

3. **Install Python packages**:
   ```bash
   pip install -r requirements.txt
   ```

   The `requirements.txt` file includes:
   ```
   streamlit
   pandas
   requests
   beautifulsoup4
   lxml
   pdf2image
   pytesseract
   pillow
   fuzzywuzzy
   python-Levenshtein
   ```

### System Dependencies

The app uses **Tesseract OCR** and **Poppler** (for PDF to image conversion). You must install them on your system.

#### Tesseract OCR

- **Windows**:
  - Download the installer from [GitHub UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
  - Install to a known location (e.g., `C:\Program Files\Tesseract-OCR`).
  - Ensure the installation includes the **German** and **English** language data (`.traineddata` files). You can select them during installation or download them separately.
- **macOS**:
  ```bash
  brew install tesseract
  brew install tesseract-lang  # for additional languages
  ```
- **Linux** (Debian/Ubuntu):
  ```bash
  sudo apt update
  sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng
  ```

#### Poppler

- **Windows**:
  - Download the latest binary from [poppler for Windows](http://blog.alivate.com.au/poppler-windows/).
  - Extract to a folder (e.g., `C:\poppler\poppler-23.11.0\Library\bin`).
- **macOS**:
  ```bash
  brew install poppler
  ```
- **Linux**:
  ```bash
  sudo apt install poppler-utils
  ```

After installation, note the paths to:
- `tesseract.exe` (or the Tesseract executable)
- The `tessdata` directory (containing `.traineddata` files)
- The Poppler `bin` directory (containing `pdftoppm.exe`)

You will provide these paths in the Streamlit sidebar (see [Configuration](#configuration)).

---

## Configuration

All configuration is done via the **sidebar** in the Streamlit app. Expand the sidebar (top-left) to access the settings.

### OCR Configuration

- **Tesseract path** – Full path to the Tesseract executable.  
  *Default:* `C:\Program Files\Tesseract-OCR\tesseract.exe` (Windows)
- **tessdata path** – Path to the `tessdata` folder containing language files.  
  *Default:* `C:\Program Files\Tesseract-OCR\tessdata`
- **Poppler path** – Path to Poppler binaries (e.g., `pdftoppm.exe`).  
  *Default:* `C:\poppler\poppler-23.11.0\Library\bin`
- **OCR Language** – Language(s) for OCR.  
  *Options:* `deu+eng`, `deu`, `eng` (recommend `deu+eng` for German PDFs).
- **OCR DPI** – Resolution for converting PDF pages to images. Higher DPI yields better text recognition but slower processing.  
  *Options:* 200–400 (default 300).

### Search Settings

- **Delay between search requests (seconds)** – To avoid hitting rate limits.  
  *Default:* 2.0 seconds.
- **Max results per product** – Number of candidate products to fetch per article number.  
  *Default:* 5.

### Web Search Fallback

- **Enable Fallback** – Toggle web search if Conrad search returns no results.
- **Search Provider** – Choose the fallback search engine:
  - **DuckDuckGo** (no API key required)
  - **Serper.dev** (Google Search API) – requires API key
  - **Bing Web Search** (Azure) – requires API key
- **API keys** – Enter the required key if using Serper.dev or Bing.

---

## Usage

### 1. Run the App

From the project directory (with virtual environment activated):

```bash
streamlit run app.py
```

This opens the app in your default web browser (usually at `http://localhost:8501`).

### 2. Choose Data Source

At the top of the app, select one of the following radio options:

- **CSV upload**
  - Upload a `.csv` file containing article numbers (and optionally quantity, description, etc.).
  - The app reads the CSV into a dataframe.

- **PDF upload** (only shown if OCR support is available)
  - Upload a Conrad order/cart PDF.
  - The app runs OCR to extract **Conrad article numbers** (Bestell-Nr. / Artikel-Nr.).
  - It creates a simple table with:
    - `quantity` = 1 (default)
    - `article_no` = extracted article number
    - `description` = empty
  - A success message shows how many article numbers were extracted.

- **Manual entry**
  - Specify the number of products you want to enter (max 50).
  - For each product, fill in:
    - Quantity
    - Article number
    - Optional description
  - Click **“Apply products”** to store them.

### 3. Preview Extracted Data

- A dataframe displays all extracted/entered items.
- The total count of items is shown.

### 4. Map Columns (CSV only)

If you uploaded a CSV, your column names may differ from the expected `quantity`, `article_no`, `description`. Use the dropdowns to assign:

- **Quantity** column
- **Conrad Article No.** column
- **Description** column (optional)

Click **“Apply mapping”** to save. The mapping is stored for subsequent searches.

### 5. Search for Products

You have two search options:

- **“Search all items”** – runs a bulk search for every article number (respecting the configured delay).
- **Per-row search** – expand any row (e.g., `Position 1: Artikelnr. 1234567`) and click **“Search this item”** to search only that article number.

During search:

- The article number is cleaned (removing non‑digit characters and suffixes).
- The app queries Conrad with the article number.
- If no direct result is found and fallback is enabled, it runs a web search for Conrad product pages.

Progress bars and status messages show the current search activity.

### 6. Review and Select Candidates

For each row, after searching:

- Candidate products are displayed as a list of radio buttons. Each candidate shows:
  - Title
  - Article number
  - Price (if available)
  - Source (e.g., `[Web-Fallback]`, `[Serper API]`, etc.)
- Select the correct product by clicking its radio button.
- A preview of the selected product appears with:
  - Title
  - Conrad article number
  - Price
  - Source
  - A button **“Open in new tab”** to view the product page directly.

Your selection is stored in the session.

### 7. Export Final Selection

Once you have selected products for some (or all) rows, a **“Final selection”** section appears.

- A final dataframe is shown that includes:
  - All original columns (from CSV/manual input)
  - **Gewählte Conrad URL** – the URL of the selected product
  - **Gewählte Bestell-Nr.** – the selected article number
  - **Gewählter Titel** – product title
  - **Gewählter Preis** – product price
  - **Status** – “Gefunden” or “Nicht gefunden”
  - **Quelle** – source of the result (e.g., `conrad_direct`, `web_fallback`, etc.)

- Click the **“Download CSV”** link to save the final data as `conrad_bestellung.csv` (UTF‑8 with BOM for Excel compatibility).

---

## Limitations & Notes

- The app relies on the **HTML structure** of conrad.de and search engines. If the website layout changes, scraping may need updates.
- **OCR quality** strongly depends on:
  - PDF scan quality
  - DPI settings
  - Correct Tesseract installation and language files
- **Network access** is required for:
  - Conrad search
  - Web search fallback (DuckDuckGo / Serper.dev / Bing)
- Only **Conrad Germany** (`conrad.de`) URLs are targeted by default.
- The app is designed for **non‑commercial use** and should respect the websites’ terms of service. Use responsibly and consider adding delays to avoid overloading servers.

---

## How to Contribute

Contributions are welcome! Ideas for improvement:

- Better error handling and logging.
- More robust parsing of Conrad pages (using more selectors).
- Support for additional export formats (Excel, JSON).
- Internationalization of the UI (English/German toggle).
- Improved relevance scoring (e.g., fuzzy matching on titles).

Please open an issue or submit a pull request on the [GitHub repository](https://github.com/<your-username>/conrad-product-finder).

https://www.linkedin.com/posts/amirmobasher_python-opencv-computervision-activity-7464584127930036225-ueH2?utm_source=share&utm_medium=member_desktop&rcm=ACoAAA7tqwMBdIETigYQYzFJUPJd118UwwaoL_k

---

## License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

---

## Author

**Amir Mobasheraghdam**  
