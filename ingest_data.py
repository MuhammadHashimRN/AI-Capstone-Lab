"""
ingest_data.py — RAG ingestion pipeline for the Dynamic Inventory Reorder Agent.

Loads PDF files from Initial_Data/, cleans and chunks them with metadata enrichment,
embeds using OpenAI text-embedding-3-small, and stores in ChromaDB.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "Initial_Data"
CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "inventory_agent_kb"

# Metadata mapping: filename patterns → metadata tags
METADATA_MAP: dict[str, dict[str, str]] = {
    "supplier_catalog": {
        "doc_type": "supplier_catalog",
        "department": "procurement",
        "priority_level": "high",
        "last_updated": "2024-01-15",
    },
    "inventory_policy": {
        "doc_type": "inventory_policy",
        "department": "procurement",
        "priority_level": "high",
        "last_updated": "2024-01-01",
    },
    "market_report": {
        "doc_type": "market_report",
        "department": "finance",
        "priority_level": "medium",
        "last_updated": "2024-03-01",
    },
}


def classify_document(filename: str) -> dict[str, str]:
    """Determine metadata tags based on the source filename.

    Args:
        filename: Name of the source file.

    Returns:
        Dictionary of metadata tags for the document.
    """
    lower = filename.lower()
    for pattern, metadata in METADATA_MAP.items():
        if pattern in lower:
            return {**metadata, "source_file": filename}
    # Default metadata for unclassified documents
    return {
        "doc_type": "general",
        "department": "operations",
        "priority_level": "low",
        "last_updated": "2024-01-01",
        "source_file": filename,
    }


def clean_text(text: str) -> str:
    """Strip noise from extracted PDF text: headers, footers, page numbers, excessive whitespace.

    Args:
        text: Raw text extracted from a PDF page.

    Returns:
        Cleaned text string.
    """
    # Remove page numbers (standalone numbers on their own line)
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    # Remove common header/footer patterns
    text = re.sub(r"(?i)(page \d+ of \d+)", "", text)
    text = re.sub(r"(?i)(confidential|draft|internal use only)", "", text)
    # Remove excessive whitespace while preserving paragraph breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def is_table_content(text: str) -> bool:
    """Detect if text contains a pricing table that should be kept together.

    Args:
        text: Text chunk to check.

    Returns:
        True if the text appears to contain tabular pricing data.
    """
    # Heuristic: multiple lines with dollar signs or SKU patterns indicate a table
    dollar_lines = len(re.findall(r"\$\d+", text))
    sku_lines = len(re.findall(r"SKU-\d+", text))
    return dollar_lines >= 3 or sku_lines >= 3


def load_and_chunk_pdfs() -> list:
    """Load all PDFs from Initial_Data/, clean, enrich with metadata, and chunk.

    Returns:
        List of LangChain Document objects with metadata.
    """
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    all_chunks = []
    pdf_files = list(DATA_DIR.glob("*.pdf"))

    if not pdf_files:
        logger.warning("No PDF files found in %s", DATA_DIR)
        return []

    for pdf_path in pdf_files:
        logger.info("Loading %s", pdf_path.name)
        try:
            loader = PyPDFLoader(str(pdf_path))
            pages = loader.load()
        except Exception as e:
            logger.error("Failed to load %s: %s", pdf_path.name, e)
            continue

        metadata = classify_document(pdf_path.name)

        # Combine all pages, clean text
        full_text = "\n\n".join(clean_text(page.page_content) for page in pages)

        if not full_text.strip():
            logger.warning("No text extracted from %s", pdf_path.name)
            continue

        # Smart chunking: if a chunk contains a table, increase chunk size to keep it together
        if is_table_content(full_text):
            table_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1500,
                chunk_overlap=200,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            chunks = table_splitter.create_documents(
                [full_text],
                metadatas=[metadata],
            )
        else:
            chunks = splitter.create_documents(
                [full_text],
                metadatas=[metadata],
            )

        # Ensure every chunk has all required metadata
        for chunk in chunks:
            chunk.metadata.update(metadata)

        all_chunks.extend(chunks)
        logger.info("  → %d chunks from %s", len(chunks), pdf_path.name)

    logger.info("Total chunks created: %d", len(all_chunks))
    return all_chunks


def build_vector_store(chunks: list, persist_dir: Optional[Path] = None) -> None:
    """Embed chunks and store them in ChromaDB.

    Args:
        chunks: List of LangChain Document objects.
        persist_dir: Directory to persist ChromaDB. Defaults to ./chroma_db.
    """
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import Chroma

    if persist_dir is None:
        persist_dir = CHROMA_DIR

    if not chunks:
        logger.error("No chunks to ingest. Ensure PDFs exist in Initial_Data/.")
        return

    logger.info("Initializing OpenAI embeddings (text-embedding-3-small)...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    logger.info("Building ChromaDB vector store at %s ...", persist_dir)
    try:
        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            persist_directory=str(persist_dir),
        )
        logger.info(
            "ChromaDB collection '%s' created with %d documents.",
            COLLECTION_NAME,
            len(chunks),
        )
    except Exception as e:
        logger.error("Failed to build vector store: %s", e)
        raise


def main() -> None:
    """Run the full RAG ingestion pipeline."""
    logger.info("Starting RAG ingestion pipeline...")

    if not DATA_DIR.exists():
        logger.error("Initial_Data/ directory not found. Run generate_sample_data.py first.")
        return

    chunks = load_and_chunk_pdfs()
    if chunks:
        build_vector_store(chunks)
        logger.info("Ingestion pipeline complete.")
    else:
        logger.error("No chunks were created. Check that PDF files exist in Initial_Data/.")


if __name__ == "__main__":
    main()
