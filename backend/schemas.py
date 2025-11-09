# backend/schemas.py
from typing import List, Optional

from pydantic import BaseModel


class ORMBase(BaseModel):
	class Config:
		from_attributes = True  # Pydantic v2 compatibility with SQLAlchemy


class ActList(ORMBase):
	id: str
	title: str


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


class UnifiedSearchRequest(BaseModel):
	query: str
	k: int = 25


class UnifiedSearchResult(BaseModel):
	id: str
	ref_id: str
	title: str
	type: str
	score_urs: int


class UnifiedSearchResponse(BaseModel):
	query_interpretation: dict
	results: List[UnifiedSearchResult]
	debug: Optional[dict] = None
