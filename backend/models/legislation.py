from sqlalchemy import Column, String, Integer, Text, Float, Index, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import LtreeType as LTREE
from sqlalchemy.orm import relationship, backref
from backend.database import Base

class Act(Base):
    __tablename__ = 'acts'

    id = Column(String(50), primary_key=True) # e.g., 'ITAA1997'
    title = Column(String(255), nullable=False)
    description = Column(Text)

    provisions = relationship("Provision", back_populates="act", cascade="all, delete-orphan")

class Provision(Base):
    __tablename__ = 'provisions'

    internal_id = Column(String(255), primary_key=True)
    act_id = Column(String(50), ForeignKey('acts.id'), nullable=False, index=True)
    ref_id = Column(String(255), nullable=False, unique=True, index=True)
    type = Column(String(50), nullable=False, index=True)

    # The specific identifier (e.g., '10-5' or sanitized term)
    local_id = Column(String(100), index=True)
    title = Column(Text, nullable=False)
    content_md = Column(Text)
    level = Column(Integer)

    # Hierarchy Management using LTree (e.g., ActID.Chapter_1.Section_10_5)
    hierarchy_path_ltree = Column(LTREE, nullable=False)
    parent_internal_id = Column(String(255), ForeignKey('provisions.internal_id'), index=True)

    # Metrics
    pagerank = Column(Float, default=0.0)
    in_degree = Column(Integer, default=0)
    out_degree = Column(Integer, default=0)

    # Relationships
    act = relationship("Act", back_populates="provisions")
    children = relationship("Provision", backref=backref("parent", remote_side=[internal_id]))

    references_to = relationship("Reference", foreign_keys="[Reference.source_internal_id]", back_populates="source_provision", cascade="all, delete-orphan")
    referenced_by = relationship("Reference", foreign_keys="[Reference.target_internal_id]", back_populates="target_provision")
    terms_used = relationship("DefinedTermUsage", foreign_keys="[DefinedTermUsage.source_internal_id]", back_populates="source_provision", cascade="all, delete-orphan")

    # Index for LTree path (Crucial for performance)
    __table_args__ = (
        Index('ix_provisions_hierarchy_path_ltree_gist', hierarchy_path_ltree, postgresql_using='gist'),
    )

class Reference(Base):
    """Represents a citation (Graph Edge)."""
    __tablename__ = 'references'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_internal_id = Column(String(255), ForeignKey('provisions.internal_id'), nullable=False, index=True)
    target_ref_id = Column(String(255), nullable=False, index=True)

    # target_internal_id is NULL if the target is external/missing
    target_internal_id = Column(String(255), ForeignKey('provisions.internal_id'), nullable=True, index=True)

    # Metadata
    original_ref_text = Column(Text)
    snippet = Column(Text)

    # Relationships
    source_provision = relationship("Provision", foreign_keys=[source_internal_id], back_populates="references_to")
    target_provision = relationship("Provision", foreign_keys=[target_internal_id], back_populates="referenced_by")

class DefinedTermUsage(Base):
    """Tracks the usage of defined terms."""
    __tablename__ = 'defined_term_usage'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_internal_id = Column(String(255), ForeignKey('provisions.internal_id'), nullable=False, index=True)

    # The term as it appeared in the text
    term_text = Column(String(255), nullable=False, index=True)

    # Link to the definition provision itself, if found.
    definition_internal_id = Column(String(255), ForeignKey('provisions.internal_id'), nullable=True, index=True)

    # Relationships
    source_provision = relationship("Provision", foreign_keys=[source_internal_id], back_populates="terms_used")
    definition_provision = relationship("Provision", foreign_keys=[definition_internal_id])

    __table_args__ = (
        UniqueConstraint('source_internal_id', 'term_text', name='uq_term_usage_source_term'),
    )
