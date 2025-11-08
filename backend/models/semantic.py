from __future__ import annotations

from sqlalchemy import (
	Column,
	DateTime,
	Float,
	ForeignKey,
	Index,
	Integer,
	String,
	Text,
	UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from backend.database import Base

EMBED_DIM = 384  # all-MiniLM-L6-v2


class GraphMeta(Base):
	__tablename__ = 'graph_meta'

	id = Column(Integer, primary_key=True, autoincrement=True)
	graph_version = Column(Integer, nullable=False, default=1)
	updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Document(Base):
	__tablename__ = 'documents'

	id = Column(String(64), primary_key=True)
	doc_type = Column(String(32), nullable=False)  # 'case'|'ruling'|'guidance'
	title = Column(Text, nullable=False)
	# SQLAlchemy reserves the attribute name "metadata", so map the column explicitly.
	doc_metadata = Column('metadata', JSONB, default=dict)


class DocumentChunk(Base):
	__tablename__ = 'document_chunks'

	id = Column(String(64), primary_key=True)
	document_id = Column(String(64), ForeignKey('documents.id'), nullable=False, index=True)
	chunk_index = Column(Integer, nullable=False)
	text = Column(Text, nullable=False)
	token_count = Column(Integer)

	__table_args__ = (
		UniqueConstraint('document_id', 'chunk_index', name='uq_doc_chunk_order'),
	)


class DocReference(Base):
	__tablename__ = 'doc_references'

	id = Column(Integer, primary_key=True, autoincrement=True)
	source_chunk_id = Column(String(64), ForeignKey('document_chunks.id'), nullable=False, index=True)
	target_ref_id = Column(String(255), nullable=False, index=True)
	target_internal_id = Column(String(255), ForeignKey('provisions.internal_id'), nullable=True, index=True)
	snippet = Column(Text)


class Embedding(Base):
	__tablename__ = 'embeddings'

	id = Column(Integer, primary_key=True, autoincrement=True)
	entity_kind = Column(String(16), nullable=False)  # 'provision'|'doc_chunk'
	entity_id = Column(String(255), nullable=False, index=True)
	model = Column(String(64), nullable=False)
	dim = Column(Integer, nullable=False, default=EMBED_DIM)
	vector = Column(Vector(EMBED_DIM), nullable=False)
	l2_norm = Column(Float)
	updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	__table_args__ = (
		UniqueConstraint('entity_kind', 'entity_id', 'model', name='uq_embedding_entity_model'),
		Index(
			'ix_embeddings_vector_hnsw',
			vector,
			postgresql_using='hnsw',
			postgresql_ops={'vector': 'vector_l2_ops'},
		),
	)


def ensure_graph_meta_seed(db: Session) -> GraphMeta:
	"""Ensure there is at least one graph_meta row and return it."""
	row = db.query(GraphMeta).order_by(GraphMeta.id.asc()).first()
	if row:
		return row
	seed = GraphMeta(graph_version=1)
	db.add(seed)
	db.commit()
	return seed


def bump_graph_version(db: Session) -> int:
	"""Increment the global graph version and return the new value."""
	row = db.query(GraphMeta).order_by(GraphMeta.id.desc()).first()
	if row:
		row.graph_version += 1
	else:
		row = GraphMeta(graph_version=1)
		db.add(row)
	db.commit()
	return row.graph_version
