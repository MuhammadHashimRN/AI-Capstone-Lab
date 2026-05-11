"""
Final Exam Part B — Knowledge Base Ingestion (Self-RAG)
========================================================
Parses the 5 university PDFs in ./data/ and indexes them into a dedicated
ChromaDB collection (`university_kb`).

Chunking strategy
-----------------
The PDFs have three distinct structures, so a one-size-fits-all chunker
would lose signal. We chunk per *semantic unit*:

  • Department course catalogs (CS/EE/BBA): one chunk per course block.
    A course block starts at a line matching <DEPT>-<NUM>: <TITLE> and
    ends just before the next match. The intro paragraph is kept as a
    separate "department_overview" chunk.

  • University_Academic_Policies.pdf: one chunk per numbered policy
    section (e.g. "1. Grading System", "2. GPA and CGPA").

  • Faculty_Directory.pdf: one chunk per faculty row, plus a footer
    chunk for contact details.

Metadata
--------
Every chunk carries:
  doc_type           catalog | policy | faculty
  department         CS | EE | BBA | university | <faculty's dept>
  source_file        original PDF filename
  course_code        e.g. "CS-301"           (catalog chunks only)
  course_level       undergraduate | graduate | n/a
  section_title      e.g. "Grading System"   (policy chunks only)
  faculty_name       e.g. "Dr. hmed aza"     (faculty chunks only)
  chunk_id           stable hash of (source, ordinal)
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Iterable

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
CHROMA_DIR = HERE / "chroma_db"
COLLECTION_NAME = "university_kb"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ─── PDF text extraction ────────────────────────────────────────────────────

def read_pdf(path: Path) -> str:
    """Extract text from a PDF, concatenating all pages with form-feed separators."""
    reader = PdfReader(str(path))
    return "\n\f\n".join((p.extract_text() or "") for p in reader.pages)


# ─── Per-document chunkers ──────────────────────────────────────────────────

COURSE_HEADER_RE = re.compile(
    r"^(?P<code>[A-Z]{2,4}-\d{3}):\s*(?P<title>.+?)$", re.MULTILINE
)
POLICY_SECTION_RE = re.compile(
    r"^(?P<num>\d{1,2})\.\s+(?P<title>[A-Z][^\n]{2,80})$", re.MULTILINE
)


def chunk_department_catalog(text: str, department: str, source_file: str) -> list[dict]:
    """Split a department catalog into (intro, per-course) chunks."""
    matches = list(COURSE_HEADER_RE.finditer(text))
    chunks: list[dict] = []

    # Department overview = everything before the first course header
    if matches:
        intro = text[: matches[0].start()].strip()
        if intro:
            chunks.append({
                "content": intro,
                "metadata": {
                    "doc_type": "catalog",
                    "department": department,
                    "source_file": source_file,
                    "course_code": "",
                    "course_level": "n/a",
                    "section_title": "Department Overview",
                    "faculty_name": "",
                },
            })

    # One chunk per course block
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        code = m.group("code")
        title = m.group("title").strip()
        # Heuristic: course code starting "5xx" or "6xx" → graduate.
        course_num = int(code.split("-")[1])
        level = "graduate" if course_num >= 500 else "undergraduate"
        chunks.append({
            "content": block,
            "metadata": {
                "doc_type": "catalog",
                "department": department,
                "source_file": source_file,
                "course_code": code,
                "course_level": level,
                "section_title": f"{code} {title}",
                "faculty_name": "",
            },
        })

    return chunks


def chunk_policies(text: str, source_file: str) -> list[dict]:
    """Split the policies document at top-level numbered headings."""
    matches = list(POLICY_SECTION_RE.finditer(text))
    chunks: list[dict] = []

    # Header / preamble before the first numbered section
    if matches:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            chunks.append({
                "content": preamble,
                "metadata": {
                    "doc_type": "policy",
                    "department": "university",
                    "source_file": source_file,
                    "course_code": "",
                    "course_level": "n/a",
                    "section_title": "Preamble",
                    "faculty_name": "",
                },
            })

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        title = m.group("title").strip()
        chunks.append({
            "content": block,
            "metadata": {
                "doc_type": "policy",
                "department": "university",
                "source_file": source_file,
                "course_code": "",
                "course_level": "n/a",
                "section_title": title,
                "faculty_name": "",
            },
        })

    return chunks


def chunk_faculty_directory(text: str, source_file: str) -> list[dict]:
    """One chunk per faculty row + a contact-info footer."""
    chunks: list[dict] = []
    # The directory rows are space-aligned lines starting with a Dr/Prof title.
    row_re = re.compile(r"^(Dr\.|Prof\.)\s+\S+.*$", re.MULTILINE)
    for m in row_re.finditer(text):
        line = m.group(0).strip()
        # Department is the second whitespace-delimited field (after the name).
        # Robust parse: try to detect department keywords.
        dept = "university"
        for k, abbr in [
            ("Computer Science", "CS"),
            ("Electrical Eng", "EE"),
            ("Business Admin", "BBA"),
        ]:
            if k in line:
                dept = abbr
                break
        # Faculty name = up to the first occurrence of the department keyword
        name_match = re.match(r"^((?:Dr\.|Prof\.)\s+[\w\s\.]+?)\s{2,}", line)
        name = name_match.group(1).strip() if name_match else line.split("  ")[0].strip()
        chunks.append({
            "content": line,
            "metadata": {
                "doc_type": "faculty",
                "department": dept,
                "source_file": source_file,
                "course_code": "",
                "course_level": "n/a",
                "section_title": "Faculty Row",
                "faculty_name": name,
            },
        })

    # Footer paragraph (office hours, switchboard) — anything after the last row
    last = list(row_re.finditer(text))
    if last:
        footer = text[last[-1].end():].strip()
        if footer:
            chunks.append({
                "content": footer,
                "metadata": {
                    "doc_type": "faculty",
                    "department": "university",
                    "source_file": source_file,
                    "course_code": "",
                    "course_level": "n/a",
                    "section_title": "Faculty Contact & Office Hours",
                    "faculty_name": "",
                },
            })

    return chunks


# ─── Driver ─────────────────────────────────────────────────────────────────

PDF_PLAN = [
    ("CS_Department_Catalog.pdf",      "catalog", "CS"),
    ("EE_Department_Catalog.pdf",      "catalog", "EE"),
    ("BBA_Department_Catalog.pdf",     "catalog", "BBA"),
    ("University_Academic_Policies.pdf", "policy", "university"),
    ("Faculty_Directory.pdf",          "faculty", "university"),
]


def build_chunks() -> list[dict]:
    all_chunks: list[dict] = []
    for filename, kind, dept in PDF_PLAN:
        path = DATA_DIR / filename
        if not path.exists():
            print(f"  [SKIP] {path} not found")
            continue
        text = read_pdf(path)
        if kind == "catalog":
            ch = chunk_department_catalog(text, dept, filename)
        elif kind == "policy":
            ch = chunk_policies(text, filename)
        else:
            ch = chunk_faculty_directory(text, filename)
        print(f"  [OK] {filename}: {len(ch)} chunks")
        all_chunks.extend(ch)
    return all_chunks


def stable_id(metadata: dict, ordinal: int) -> str:
    raw = f"{metadata['source_file']}|{metadata['section_title']}|{ordinal}"
    return hashlib.md5(raw.encode()).hexdigest()


def main() -> int:
    if not DATA_DIR.exists():
        sys.exit(f"[ERROR] Missing data/ directory at {DATA_DIR}")

    print("=" * 60)
    print("Self-RAG Knowledge Base — Ingestion")
    print("=" * 60)

    chunks = build_chunks()
    if not chunks:
        sys.exit("[ERROR] No chunks produced — nothing to index.")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
    )

    # Fresh rebuild
    try:
        client.delete_collection(COLLECTION_NAME)
        print("[INFO] Deleted existing collection.")
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"description": "XYZ National University course catalog + policies + faculty"},
    )

    ids, documents, metadatas = [], [], []
    for i, c in enumerate(chunks):
        ids.append(stable_id(c["metadata"], i))
        documents.append(c["content"])
        metadatas.append(c["metadata"])

    # ChromaDB batches > 5k must be split; we have ~50 so a single call is fine.
    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    print("\nKnowledge base built.")
    print(f"  Total chunks  : {len(chunks)}")
    print(f"  Collection    : {COLLECTION_NAME}")
    print(f"  Persist path  : {CHROMA_DIR}")

    # ── Sanity-check retrievals ──────────────────────────────────────────
    print("\nSanity queries:")
    for q in [
        "What are the prerequisites for CS-301 Artificial Intelligence?",
        "What is the grading scale and what does an A- mean?",
        "Who teaches signal processing in the EE department?",
    ]:
        r = collection.query(query_texts=[q], n_results=2)
        top = r["metadatas"][0][0] if r["metadatas"][0] else {}
        excerpt = (r["documents"][0][0] if r["documents"][0] else "")[:120]
        print(f"  Q: {q}")
        print(f"    -> [{top.get('doc_type','?')}/{top.get('department','?')}] {excerpt}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
