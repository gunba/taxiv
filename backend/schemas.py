# backend/schemas.py
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ORMBase(BaseModel):
	class Config:
		from_attributes = True  # Pydantic v2 compatibility with SQLAlchemy


@dataclass(frozen=True)
class ProvisionDetailOptions:
	include_breadcrumbs: bool = True
	include_children: bool = True
	include_definitions: bool = True
	include_references: bool = True


class ActList(ORMBase):
	id: str
	title: str
	description: Optional[str] = None
	is_default: bool = False


class DatasetInfo(BaseModel):
	id: str
	title: str
	type: str
	description: Optional[str] = None


class DocumentSummary(BaseModel):
	id: str
	title: str
	doc_type: str
	snippet: Optional[str] = None


class DocumentSearchResponse(BaseModel):
	results: List[DocumentSummary]
	offset: int
	limit: int
	total: int


# Schemas for related data serialization (structured for frontend consumption)
class ReferenceToDetail(BaseModel):
	target_ref_id: str
	snippet: Optional[str]
	target_title: Optional[str]  # Populated in CRUD
	target_internal_id: Optional[str]  # Populated in CRUD


class ReferencedByDetail(BaseModel):
	source_internal_id: str
	source_ref_id: str
	source_title: str  # Populated in CRUD


class DefinedTermUsageDetail(BaseModel):
	term_text: str
	definition_internal_id: Optional[str]  # Populated in CRUD


class BreadcrumbItem(BaseModel):
	internal_id: str
	title: str


class ChildProvisionSummary(BaseModel):
	internal_id: str
	ref_id: str
	title: str
	type: str


class DefinitionWithReferences(BaseModel):
	definition_internal_id: str
	ref_id: Optional[str]
	title: Optional[str]
	content_md: Optional[str]
	term_texts: List[str] = []
	references_to: List[ReferenceToDetail] = []


class ProvisionDetail(ORMBase):
	internal_id: str
	ref_id: str
	act_id: str
	type: str
	local_id: Optional[str]
	title: str
	content_md: Optional[str]
	level: int
	# LTree paths must be serialized as strings (handled in CRUD)
	hierarchy_path_ltree: str
	parent_internal_id: Optional[str]
	sibling_order: Optional[int]

	# Metrics
	pagerank: float
	in_degree: int
	out_degree: int

	# Related Data (Populated in CRUD)
	references_to: List[ReferenceToDetail] = []
	referenced_by: List[ReferencedByDetail] = []
	defined_terms_used: List[DefinedTermUsageDetail] = []
	definitions_with_references: List[DefinitionWithReferences] = []
	breadcrumbs: List[BreadcrumbItem] = []
	children: List[ChildProvisionSummary] = []
	etag: Optional[str] = None
	last_modified: Optional[datetime] = None
	size_bytes: Optional[int] = None


class ProvisionHierarchy(ORMBase):
	"""A lightweight model just for the navigation hierarchy."""
	internal_id: str
	ref_id: str
	title: str
	type: str
	has_children: bool  # Calculated in CRUD
	sibling_order: Optional[int] = None
	children: Optional[List["ProvisionHierarchy"]] = None


ProvisionHierarchy.model_rebuild()


class ExportMarkdownRequest(BaseModel):
	provision_internal_id: str
	include_descendants: bool = False


class ExportMarkdownResponse(BaseModel):
	markdown: str


class VisibleSubtreeMarkdownRequest(BaseModel):
	root_internal_id: str
	visible_descendant_ids: List[str] = []


class BatchProvisionRequest(BaseModel):
	ids: List[str]
	include_breadcrumbs: bool = False
	include_children: bool = False
	include_definitions: bool = False
	include_references: bool = True
	fields: Optional[List[str]] = None
	act_id: Optional[str] = None


class BatchProvisionResponse(BaseModel):
	results: List[dict]
	parsed: Optional[dict] = None


class UnifiedSearchRequest(BaseModel):
	query: str
	k: int = 10
	offset: int = 0
	act_id: Optional[str] = None


class UnifiedSearchResult(BaseModel):
	id: str
	ref_id: str
	title: str
	type: str
	score_urs: int
	content_snippet: str
	act_id: str


class SearchPagination(BaseModel):
	offset: int
	limit: int
	total: int
	next_offset: Optional[int] = None


class UnifiedSearchResponse(BaseModel):
	query_interpretation: dict
	results: List[UnifiedSearchResult]
	debug: Optional[dict] = None
	pagination: Optional[SearchPagination] = None
	parsed: Optional[dict] = None
