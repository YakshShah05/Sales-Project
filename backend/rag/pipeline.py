import os
import json
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image
import PyPDF2
from pdf2image import convert_from_path

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
# from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain.schema import Document
from langchain_core.documents import Document


VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH", "/app/data/vector_store")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_embeddings = None
_text_store = None
_ocr_store = None


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
        )
    return _embeddings


def get_text_store() -> Chroma:
    global _text_store
    if _text_store is None:
        persist_dir = os.path.join(VECTOR_STORE_PATH, "text")
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _text_store = Chroma(
            collection_name="text_documents",
            embedding_function=get_embeddings(),
            persist_directory=persist_dir,
        )
    return _text_store


def get_ocr_store() -> Chroma:
    global _ocr_store
    if _ocr_store is None:
        persist_dir = os.path.join(VECTOR_STORE_PATH, "ocr")
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _ocr_store = Chroma(
            collection_name="ocr_documents",
            embedding_function=get_embeddings(),
            persist_directory=persist_dir,
        )
    return _ocr_store


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a text-based PDF."""
    text = ""
    try:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
    except Exception:
        pass
    return text.strip()


def extract_text_via_ocr(file_path: str) -> str:
    """Extract text from image or scanned PDF using Tesseract OCR."""
    text = ""
    suffix = Path(file_path).suffix.lower()

    if suffix in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]:
        image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
    elif suffix == ".pdf":
        try:
            images = convert_from_path(file_path, dpi=200)
            for img in images:
                text += pytesseract.image_to_string(img) + "\n"
        except Exception as e:
            text = f"OCR extraction failed: {str(e)}"

    return text.strip()


def detect_modality(file_path: str) -> str:
    """Detect whether document needs text or OCR pipeline."""
    suffix = Path(file_path).suffix.lower()
    if suffix in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]:
        return "ocr"
    elif suffix == ".pdf":
        text = extract_text_from_pdf(file_path)
        if len(text) > 100:
            return "text"
        return "ocr"
    elif suffix in [".txt", ".json", ".csv", ".md"]:
        return "text"
    return "text"


def ingest_document(file_path: str, metadata: dict) -> dict:
    """
    Route document to the correct pipeline based on type.
    Both pipelines can be active simultaneously for mixed content.
    """
    modality = detect_modality(file_path)
    results = {"modality": modality, "chunks_indexed": 0, "pipeline": modality}

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    if modality == "text":
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            raw_text = extract_text_from_pdf(file_path)
        else:
            with open(file_path, "r", errors="ignore") as f:
                raw_text = f.read()

        chunks = splitter.create_documents(
            [raw_text],
            metadatas=[{**metadata, "pipeline": "text", "source": file_path}],
        )
        store = get_text_store()
        store.add_documents(chunks)
        results["chunks_indexed"] = len(chunks)

    elif modality == "ocr":
        raw_text = extract_text_via_ocr(file_path)
        chunks = splitter.create_documents(
            [raw_text],
            metadatas=[{**metadata, "pipeline": "ocr", "source": file_path}],
        )
        store = get_ocr_store()
        store.add_documents(chunks)
        results["chunks_indexed"] = len(chunks)
        results["ocr_text_preview"] = raw_text[:300]

    return results


def ingest_text_directly(text: str, metadata: dict, use_ocr_store: bool = False) -> dict:
    """Ingest raw text directly into the appropriate vector store."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.create_documents(
        [text],
        metadatas=[{**metadata, "pipeline": "ocr" if use_ocr_store else "text"}],
    )
    store = get_ocr_store() if use_ocr_store else get_text_store()
    store.add_documents(chunks)
    return {"chunks_indexed": len(chunks)}


def retrieve_context(query: str, k: int = 4) -> str:
    """
    Query BOTH text and OCR vector stores and merge results.
    Returns combined context string for LLM scoring.
    """
    context_parts = []

    try:
        text_store = get_text_store()
        text_docs = text_store.similarity_search(query, k=k // 2 + 1)
        if text_docs:
            context_parts.append("=== From text documents ===")
            context_parts.extend([d.page_content for d in text_docs])
    except Exception:
        pass

    try:
        ocr_store = get_ocr_store()
        ocr_docs = ocr_store.similarity_search(query, k=k // 2 + 1)
        if ocr_docs:
            context_parts.append("=== From scanned/image documents ===")
            context_parts.extend([d.page_content for d in ocr_docs])
    except Exception:
        pass

    return "\n\n".join(context_parts) if context_parts else "No relevant context found."


def seed_knowledge_base():
    """Seed the knowledge base with example sales intelligence."""
    seed_docs = [
        {
            "text": "Acme Corp closed in Q3 2023 after 3 demos. Key pain point was manual reporting. Deal size $48k ARR. Champion was VP of Ops.",
            "meta": {"type": "won_deal", "industry": "SaaS"},
        },
        {
            "text": "TechFlow lost due to budget freeze. Had strong intent signals — 12 website visits, demo done. Follow up in Q1.",
            "meta": {"type": "lost_deal", "industry": "FinTech"},
        },
        {
            "text": "Companies with 50-200 employees in SaaS or FinTech who recently raised Series A or B are ideal ICP. Avg close rate 34%.",
            "meta": {"type": "icp_profile"},
        },
        {
            "text": "Executive change (new CTO, VP Sales, COO) is the strongest buying signal. Avg 60-day window before budget locked.",
            "meta": {"type": "signal_intelligence"},
        },
        {
            "text": "Demo requests from companies with active hiring in engineering or operations convert at 2.4x vs cold outreach.",
            "meta": {"type": "conversion_data"},
        },
    ]

    for doc in seed_docs:
        ingest_text_directly(doc["text"], doc["meta"])
