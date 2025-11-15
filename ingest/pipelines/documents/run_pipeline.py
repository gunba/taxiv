"""Generic document/ruling ingestion pipeline."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.act_metadata import resolve_datasets_config_path
from backend.database import get_db
from backend.models.semantic import Document, DocumentChunk

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

DEFAULT_DATASET_ID = "TAX_CASES"
CHUNK_SIZE = 1800
CHUNK_OVERLAP = 200
SUPPORTED_EXTENSIONS = {".json", ".txt", ".md"}


@dataclass
class ParsedDocument:
    identifier: str
    title: str
    doc_type: str
    body: str


def _resolve_input_dir(dataset_id: str) -> Path:
    config_path = resolve_datasets_config_path()
    meta = json.loads(config_path.read_text(encoding="utf-8"))
    for entry in meta.get("datasets", []):
        if entry.get("id") == dataset_id:
            ingestion = entry.get("ingestion", {})
            path = ingestion.get("input_dir")
            if path:
                return Path(path).expanduser().resolve()
    raise ValueError(f"Dataset '{dataset_id}' is missing ingestion.input_dir in config/datasets.json")


def _read_documents(input_dir: Path) -> List[ParsedDocument]:
    documents: List[ParsedDocument] = []
    for path in sorted(input_dir.glob("**/*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            identifier = payload.get("id") or path.stem
            title = payload.get("title") or path.stem.replace("_", " ")
            doc_type = payload.get("doc_type") or "case"
            body = payload.get("body") or ""
        else:
            text = path.read_text(encoding="utf-8")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                continue
            title = lines[0]
            body = "\n".join(lines[1:])
            identifier = path.stem
            doc_type = "case"
        body = body.strip()
        if not body:
            continue
        documents.append(ParsedDocument(identifier=identifier, title=title, doc_type=doc_type, body=body))
    logger.info("Discovered %s documents under %s", len(documents), input_dir)
    return documents


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    if not text:
        return []
    tokens = list(text)
    chunks: List[str] = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + size)
        chunk = "".join(tokens[start:end])
        chunks.append(chunk)
        if end == len(tokens):
            break
        start = end - overlap
        if start < 0:
            start = 0
    return chunks


def _slugify(dataset_id: str, identifier: str) -> str:
    cleaned = "".join(ch for ch in identifier if ch.isalnum() or ch in {"-", "_"})
    cleaned = cleaned.strip("-_") or "doc"
    return f"{dataset_id}_{cleaned}"[:60]


def _purge_dataset(db: Session, dataset_id: str) -> None:
    pattern = f"{dataset_id}_%"
    logger.info("Clearing existing documents for dataset %s", dataset_id)
    chunk_stmt = delete(DocumentChunk).where(DocumentChunk.document_id.like(pattern))
    doc_stmt = delete(Document).where(Document.id.like(pattern))
    db.execute(chunk_stmt)
    db.execute(doc_stmt)
    db.commit()


def _store_documents(db: Session, dataset_id: str, docs: Sequence[ParsedDocument]) -> None:
    for doc in docs:
        document_id = _slugify(dataset_id, doc.identifier)
        record = Document(id=document_id, doc_type=doc.doc_type, title=doc.title, doc_metadata={"dataset": dataset_id})
        db.add(record)
        chunk_texts = _chunk_text(doc.body)
        for idx, chunk_text in enumerate(chunk_texts):
            db.add(DocumentChunk(
                id=f"{document_id}_chunk_{idx}",
                document_id=document_id,
                chunk_index=idx,
                text=chunk_text,
                token_count=len(chunk_text.split()),
            ))
    db.commit()
    logger.info("Inserted %s documents for dataset %s", len(docs), dataset_id)


def run(dataset_id: str | None = None) -> None:
    dataset = dataset_id or os.environ.get("DATASET_ID") or DEFAULT_DATASET_ID
    input_dir = _resolve_input_dir(dataset)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory {input_dir} does not exist")
    documents = _read_documents(input_dir)
    if not documents:
        logger.warning("No documents found for dataset %s", dataset)
        return
    session_gen = get_db()
    db = next(session_gen)
    try:
        _purge_dataset(db, dataset)
        _store_documents(db, dataset, documents)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    run()
