import argparse, csv, hashlib, json, os, re
from datetime import datetime, date
from typing import Optional
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
import spacy
from spacy.matcher import PhraseMatcher

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
DATE_FMTS = ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y")
DATE_PATTERN = re.compile(r'(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4})|(?:\d{1,2}[/-]\d{1,2}[/-]\d{4})', re.IGNORECASE)
DOLLAR_RANGE_PATTERN = re.compile(r'\$[\d,]+(?:\.\d+)?(?:/\w+)?\s*(?:to|–|-|and)\s+(?:a\s+maximum\s+of\s+)?\$[\d,]+(?:\.\d+)?(?:/\w+)?')

# Hardcoded Ontology , Only for demo purpose
ONTOLOGY = {
    "research_domains": {
        "Quantum Information Science": ["quantum", "qise", "qubit", "entanglement"],
        "Nanotechnology": ["nano", "nanotechnology", "nanoscience", "nanoengineering"],
        "Artificial Intelligence": ["artificial intelligence", "ai", "machine learning", "deep learning"],
        "Semiconductors": ["semiconductor", "chip", "integrated circuit"],
        "Biotechnology": ["biotechnology", "biotech", "biological", "biomedical"],
        "Manufacturing": ["manufacturing", "fabrication", "advanced manufacturing"],
        "Materials Science": ["materials science", "materials research", "thin film"],
        "Computer Science": ["computer science", "computing", "computational"],
        "Engineering": ["engineering", "engineers"],
        "Physics": ["physics", "photonics", "optics"],
        "Chemistry": ["chemistry", "chemical"],
        "Environmental Science": ["environment", "environmental", "climate", "sustainability"],
        "Energy": ["energy", "renewable", "solar", "battery"],
    },
    "methods_approaches": {
        "Fabrication": ["fabrication", "lithography", "deposition", "etching"],
        "Characterization": ["characterization", "spectroscopy", "microscopy", "imaging"],
        "Simulation": ["simulation", "modeling", "computational modeling"],
        "Experimental Research": ["experimental", "laboratory", "lab-based"],
        "User Facility": ["user facility", "open-access", "shared facility"],
        "Network Collaboration": ["network", "collaborative", "partnership", "consortium"],
    },
    "populations": {
        "Undergraduate Students": ["undergraduate", "undergrad"],
        "Graduate Students": ["graduate student", "graduate education", "doctoral"],
        "Postdoctoral Researchers": ["postdoctoral", "postdoc"],
        "Faculty": ["faculty", "principal investigator", "co-pi"],
        "K-12": ["k-12", "k12", "pre-college"],
        "Community College": ["community college", "technical college", "two-year college"],
        "Minority-Serving Institutions": ["minority-serving", "hbcu", "hispanic-serving"],
        "Industry": ["industry", "industrial", "private sector", "commercial"],
        "External Users": ["external user", "external academic"],
    },
    "sponsor_themes": {
        "Workforce Development": ["workforce", "training", "education", "outreach"],
        "Broadening Participation": ["broadening participation", "diversity", "equity", "inclusion"],
        "National Priority": ["national priority", "national security", "critical technology"],
        "Open Science": ["open access", "open-access", "open science"],
        "Infrastructure": ["infrastructure", "instrumentation", "research infrastructure"],
        "International Collaboration": ["international", "global", "cross-border"],
        "Innovation & Translation": ["innovation", "translation", "commercialization"],
    },
}

# Pydantic Models 

class SemanticTags(BaseModel):
    research_domains: list[str] = Field(default_factory=list)
    methods_approaches: list[str] = Field(default_factory=list)
    populations: list[str] = Field(default_factory=list)
    sponsor_themes: list[str] = Field(default_factory=list)

class FOARecord(BaseModel):
    foa_id: str
    title: str
    agency: str = "NSF"
    open_date: Optional[str] = None
    close_date: Optional[dict[str, str]] = None
    eligibility: str = ""
    program_description: str = ""
    award_range: Optional[str] = None
    source_url: str
    solicitation_url: Optional[str] = None
    source_type: str = "nsf_html"
    source_format: str = "html"
    semantic_tags: SemanticTags = Field(default_factory=SemanticTags)

# Utility Helpers 

def normalize(text: str) -> str:
    if not text: return ""
    return re.sub(r'\s+', ' ', "".join(ch for ch in text if ch.isprintable())).strip()

def parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    for fmt in DATE_FMTS:
        try: return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError: pass
    return None

def fetch_html(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "html.parser")

# Full-Text Extraction Helpers 

def extract_window(text: str, keywords: list[str], window_size: int = 1500) -> str:
    """Find the first occurrence of any keyword and return a surrounding text window."""
    text_lower = text.lower()
    for kw in keywords:
        idx = text_lower.find(kw)
        if idx != -1:
            start = max(0, idx - 50)
            return normalize(text[start:start + window_size])
    return ""

def find_award_range(text: str) -> Optional[str]:
    """Find a dollar range in text, skipping total-budget figures."""
    for m in DOLLAR_RANGE_PATTERN.finditer(text):
        ctx_before = text[max(0, m.start()-50):m.start()].lower()
        ctx_after  = text[m.end():m.end()+50].lower()
        if not any(w in ctx_before or w in ctx_after for w in ["total", "anticipated", "estimated"]):
            return m.group(0)
    return None

def extract_close_dates(text: str) -> Optional[dict[str, str]]:
    """Extract close dates by finding dates and dynamically capturing surrounding deadline labels."""
    date_map = {}
    chunks = re.split(r'\s{2,}|\n', text)
    
    for i, chunk in enumerate(chunks):
        for m in DATE_PATTERN.finditer(chunk):
            parsed = parse_date(m.group(0))
            if not parsed: continue
            
            label = None
            context_chunks = chunks[max(0, i-3):i+1]
            for ctx in reversed(context_chunks):
                ctx_lower = ctx.lower()
                if any(w in ctx_lower for w in ["deadline", "due date", "submission", "due", "letter of intent", "loi", "proposal", "final deadline"]):
                    clean_label = re.sub(DATE_PATTERN, "", ctx).strip()
                    clean_label = re.sub(r'\(.*?\)', '', clean_label)
                    clean_label = re.sub(r':\s*required', '', clean_label, flags=re.IGNORECASE)
                    clean_label = clean_label.strip().rstrip(":-").strip()

                    if len(clean_label) > 60:
                        parts = re.split(r'[,;.]', clean_label)
                        clean_label = parts[-1].strip() if parts[-1].strip() else parts[-2].strip()
                        
                    if clean_label and len(clean_label) > 3:
                        label = normalize(clean_label).title()
                        break
            
            if not label:
                label = "Generic Due Date"
            existing = date_map.get(parsed)
            if not existing or (existing == "Generic Due Date" and label != "Generic Due Date"):
                date_map[parsed] = label

    close = {}
    generic_count = 1
    for d, lbl in sorted(date_map.items()):
        if lbl == "Generic Due Date":
            close[f"Due Date {generic_count}"] = d
            generic_count += 1
        else:
            close[lbl] = d
            
    return close if close else None

# Page-Level Extraction

def extract_from_main_page(soup: BeautifulSoup, url: str) -> dict:
    data: dict = {"source_url": url}
    full_text = soup.get_text("  ", strip=True)
    h1 = soup.find("h1")
    data["title"] = normalize(h1.get_text()) if h1 else ""
    data["program_description"] = extract_window(full_text, ["synopsis", "program description", "overview", "program synopsis", "description", "summary"], 8000)
    data["award_range"] = find_award_range(full_text)
    data["close_date"] = extract_close_dates(full_text)
    m = re.search(r"NSF\s?\d{2}-\d{3}", full_text, re.IGNORECASE)
    data["foa_id"] = m.group(0).replace(" ", " ") if m else None
    sol_url = None
    for a in soup.find_all("a", href=True):
        if "solicitation" in a["href"].lower() or (a.get_text(strip=True) and "solicitation" in a.get_text(strip=True).lower()):
            href = a["href"]
            if href.startswith("/"): href = "https://www.nsf.gov" + href
            elif not href.startswith("http"): href = url.rstrip("/") + "/" + href
            sol_url = href
            break
    data["solicitation_url"] = sol_url

    return data

def extract_from_solicitation(soup: BeautifulSoup) -> dict:
    data: dict = {}
    full_text = soup.get_text("  ", strip=True)

    # Open date
    for kw in ["posted:", "release date:", "publish date:"]:
        idx = full_text.lower().find(kw)
        if idx != -1:
            m = DATE_PATTERN.search(full_text[idx:idx+200])
            if m: data["open_date"] = parse_date(m.group(0)); break

    data["eligibility"] = extract_window(full_text, ["who may submit proposals", "eligibility information", "eligibility", "eligible applicants", "who may apply"], 6000)
    desc = extract_window(full_text, ["ii. program description", "synopsis of program", "program description", "overview", "program synopsis", "description", "summary"], 15000)
    if len(desc) > 50: data["program_description"] = desc
    award = find_award_range(full_text)
    if award: data["award_range"] = award

    close = extract_close_dates(full_text)
    if close: data["close_date"] = close

    return data

 
# spaCy Tagger

def build_phrase_matcher(nlp):
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    label_map = {}
    for category, terms in ONTOLOGY.items():
        for label, keywords in terms.items():
            match_id = f"{category}||{label}"
            patterns = [nlp.make_doc(kw) for kw in keywords]
            matcher.add(match_id, patterns)
            label_map[match_id] = (category, label)
    return matcher, label_map

def apply_tags(text: str, nlp, matcher, label_map) -> SemanticTags:
    doc = nlp(text.lower()[:100000])
    matches = matcher(doc)
    tags: dict[str, set[str]] = {cat: set() for cat in ONTOLOGY}
    for match_id, _, _ in matches:
        mid = nlp.vocab.strings[match_id]
        cat, label = label_map[mid]
        tags[cat].add(label)
    return SemanticTags(**{k: sorted(v) for k, v in tags.items()})


# Export

def export_json(record: FOARecord, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record.model_dump(), f, indent=2, ensure_ascii=False)

def export_csv(record: FOARecord, path: str):
    data = record.model_dump()
    tags = data.pop("semantic_tags", {})
    for k, v in tags.items(): data[f"tag_{k}"] = " | ".join(v)
    close = data.pop("close_date", None)
    data["close_date"] = json.dumps(close) if close else ""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=data.keys())
        w.writeheader()
        w.writerow(data)

# Orchestrator 

def ingest_foa(url: str) -> FOARecord:
    nlp = spacy.blank("en")
    matcher, label_map = build_phrase_matcher(nlp)

    main_soup = fetch_html(url)
    main_text = main_soup.get_text(" ", strip=True)
    main_data = extract_from_main_page(main_soup, url)

    sol_url = main_data.get("solicitation_url")
    sol_data: dict = {}
    sol_text = ""
    if sol_url:
        sol_soup = fetch_html(sol_url)
        sol_text = sol_soup.get_text(" ", strip=True)
        sol_data = extract_from_solicitation(sol_soup)


    merged = {**main_data, **{k: v for k, v in sol_data.items() if v}}
    open_d = merged.get("open_date")
    if open_d and merged.get("close_date"):
        merged["close_date"] = {k: v for k, v in merged["close_date"].items() if v != open_d}
        if not merged["close_date"]:
            merged["close_date"] = None
            
    all_text = main_text + " " + sol_text

    record = FOARecord(
        foa_id=merged.get("foa_id") or "FOA-" + hashlib.sha256(url.encode()).hexdigest()[:10].upper(),
        title=merged.get("title", ""),
        open_date=merged.get("open_date"),
        close_date=merged.get("close_date"),
        eligibility=merged.get("eligibility", ""),
        program_description=merged.get("program_description", ""),
        award_range=merged.get("award_range"),
        source_url=url,
        solicitation_url=sol_url,
    )
    record.semantic_tags = apply_tags(all_text, nlp, matcher, label_map)
    return record

def main():
    parser = argparse.ArgumentParser(description="Ingest NSF FOA, extract fields, tag, export.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--out_dir", default="./out")
    args = parser.parse_args()
    record = ingest_foa(args.url)
    os.makedirs(args.out_dir, exist_ok=True)
    export_json(record, os.path.join(args.out_dir, "foa.json"))
    export_csv(record, os.path.join(args.out_dir, "foa.csv"))
    print(f"Done! -> {os.path.abspath(args.out_dir)}")

if __name__ == "__main__":
    main()
