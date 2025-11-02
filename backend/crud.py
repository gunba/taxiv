# backend/crud.py
import logging
from typing import List, Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session, aliased
from sqlalchemy_utils import Ltree

from backend.models import legislation as models
from backend.schemas import ProvisionDetail, ProvisionHierarchy, ReferenceToDetail, ReferencedByDetail, \
	DefinedTermUsageDetail, BreadcrumbItem

logger = logging.getLogger(__name__)


def get_acts(db: Session) -> List[models.Act]:
	return db.query(models.Act).all()


def get_provision_by_ref_id(db: Session, ref_id: str, act_id: str) -> List[ProvisionDetail]:
	"""
	Finds a provision by its ref_id and act_id.
	Returns a list as multiple provisions could potentially match, though it's often a single item.
	"""
	query = db.query(models.Provision).filter(
		models.Provision.ref_id == ref_id,
		models.Provision.act_id == act_id
	)
	provisions = query.all()

	# Use the detailed constructor for each provision found
	return [get_provision_detail(db, p.internal_id) for p in provisions if p]


def get_breadcrumbs(db: Session, internal_id: str) -> List[BreadcrumbItem]:
	"""
	Constructs the breadcrumb trail for a given provision using its LTree path.
	"""
	logger.info(f"Fetching breadcrumbs for internal_id: {internal_id}")
	target_provision = db.get(models.Provision, internal_id)
	if not target_provision or not target_provision.hierarchy_path_ltree:
		logger.warning(f"Provision or hierarchy path not found for {internal_id}")
		return []

	ancestor_path_str = str(target_provision.hierarchy_path_ltree)
	ancestor_path = Ltree(ancestor_path_str)
	logger.info(f"Ancestor path string: {ancestor_path_str}")

	query = db.query(
		models.Provision.internal_id,
		models.Provision.title,
		models.Provision.hierarchy_path_ltree
	).filter(
		models.Provision.hierarchy_path_ltree.op('@>')(ancestor_path)
	).order_by(models.Provision.hierarchy_path_ltree)

	# Log the actual query being sent. Some dialect-specific types such as Ltree do not
	# support literal compilation, so we gracefully fall back to parameterised logging.
	try:
		from sqlalchemy.dialects import postgresql

		compiled_query = query.statement.compile(dialect=postgresql.dialect())
		logger.info("Executing breadcrumb query: %s", compiled_query)
		if compiled_query.params:
			logger.info("Query parameters: %s", compiled_query.params)
	except Exception as e:
		logger.warning("Could not prepare breadcrumb query for logging: %s", e)

	ancestors = query.all()
	logger.info(f"Found {len(ancestors)} breadcrumb ancestors.")

	return [BreadcrumbItem(internal_id=a.internal_id, title=a.title) for a in ancestors]


def search_hierarchy(db: Session, act_id: str, query: str) -> List[ProvisionHierarchy]:
	"""
	Performs a full-text search on provision titles and returns the results in a hierarchical format.
	It includes all ancestors of the matched nodes to provide context.
	"""
	if not query:
		return []

	# 1. Find provisions that match the search query using full-text search
	# We use to_tsvector for the content and to_tsquery for the query string.
	matched_provisions_subq = db.query(models.Provision.internal_id).filter(
		models.Provision.act_id == act_id,
		func.to_tsvector('english', models.Provision.title).op('@@')(
			func.plainto_tsquery('english', query)
		)
	).subquery()

	# 2. Get the LTree paths of all matched provisions
	matched_paths_subq = db.query(
		models.Provision.hierarchy_path_ltree.label("hierarchy_path_ltree")
	).join(
		matched_provisions_subq, models.Provision.internal_id == matched_provisions_subq.c.internal_id
	).subquery()

	# 3. Find all provisions that are either a match OR an ancestor of a match.
	# We use the LTree ancestor operator '@>' to find all parents.
	# We also need to include the matched nodes themselves.
	union_subq = db.query(
		matched_paths_subq.c.hierarchy_path_ltree.label("hierarchy_path_ltree")
	).union(
		db.query(
			models.Provision.hierarchy_path_ltree.label("hierarchy_path_ltree")
		).join(
			matched_paths_subq,
			models.Provision.hierarchy_path_ltree.op('@>')(matched_paths_subq.c.hierarchy_path_ltree)
		)
	).subquery()

	# 4. Fetch the final hierarchy data for the combined set of nodes.
	ChildProvision = aliased(models.Provision)
	children_exists_subq = db.query(ChildProvision.internal_id) \
		.filter(ChildProvision.parent_internal_id == models.Provision.internal_id) \
		.exists().label("has_children")

	results = db.query(
		models.Provision.internal_id,
		models.Provision.ref_id,
		models.Provision.title,
		models.Provision.type,
		models.Provision.sibling_order,
		models.Provision.parent_internal_id,
		children_exists_subq
	).join(
		union_subq, models.Provision.hierarchy_path_ltree == union_subq.c.hierarchy_path_ltree
	).filter(
		models.Provision.act_id == act_id
	).order_by(
		case((models.Provision.sibling_order.is_(None), 1), else_=0),
		models.Provision.sibling_order,
		models.Provision.hierarchy_path_ltree
	).all()

	if not results:
		return []

	ordered_ids: List[str] = []
	node_map = {}
	parent_lookup = {}

	for row in results:
		ordered_ids.append(row.internal_id)
		node_map[row.internal_id] = {
			"internal_id": row.internal_id,
			"ref_id": row.ref_id,
			"title": row.title,
			"type": row.type,
			"has_children": row.has_children,
			"sibling_order": row.sibling_order,
			"children": None,
		}
		parent_lookup[row.internal_id] = row.parent_internal_id

	for node_id in ordered_ids:
		parent_id = parent_lookup.get(node_id)
		if parent_id and parent_id in node_map:
			parent_node = node_map[parent_id]
			if parent_node["children"] is None:
				parent_node["children"] = []
			parent_node["children"].append(node_map[node_id])

	roots = [
		node_map[node_id]
		for node_id in ordered_ids
		if not parent_lookup.get(node_id) or parent_lookup[node_id] not in node_map
	]

	return [ProvisionHierarchy.model_validate(node) for node in roots]


def get_provision_detail(db: Session, internal_id: str) -> Optional[ProvisionDetail]:
	"""
	Fetches a provision and manually constructs the detailed view including relationships.
	"""
	provision = db.get(models.Provision, internal_id)
	if not provision:
		return None

	# 1. References To (Outgoing)
	# We join Reference with Provision (aliased as TargetProvision) to get the target title.
	TargetProvision = aliased(models.Provision)
	references_to_query = db.query(
		models.Reference.target_ref_id,
		models.Reference.snippet,
		TargetProvision.title.label("target_title")
	).outerjoin(TargetProvision, TargetProvision.internal_id == models.Reference.target_internal_id
				).filter(models.Reference.source_internal_id == internal_id).all()

	references_to = [ReferenceToDetail.model_validate(r._asdict()) for r in references_to_query]

	# 2. Referenced By (Incoming)
	SourceProvision = aliased(models.Provision)
	referenced_by_query = db.query(
		SourceProvision.internal_id.label("source_internal_id"),
		SourceProvision.ref_id.label("source_ref_id"),
		SourceProvision.title.label("source_title")
	).join(models.Reference, models.Reference.source_internal_id == SourceProvision.internal_id
		   ).filter(models.Reference.target_internal_id == internal_id).distinct().all()

	referenced_by = [ReferencedByDetail.model_validate(r._asdict()) for r in referenced_by_query]

	# 3. Defined Terms Used
	DefinitionProvision = aliased(models.Provision)
	terms_used_query = db.query(
		models.DefinedTermUsage.term_text,
		DefinitionProvision.internal_id.label("definition_internal_id")
	).outerjoin(DefinitionProvision, DefinitionProvision.internal_id == models.DefinedTermUsage.definition_internal_id
				).filter(models.DefinedTermUsage.source_internal_id == internal_id).all()

	defined_terms_used = [DefinedTermUsageDetail.model_validate(t._asdict()) for t in terms_used_query]

	# 4. Construct the final response model
	# Convert the SQLAlchemy model to a dict
	provision_data = provision.__dict__

	# Handle LTree conversion (must be string for JSON)
	if 'hierarchy_path_ltree' in provision_data and provision_data['hierarchy_path_ltree'] is not None:
		provision_data['hierarchy_path_ltree'] = str(provision_data['hierarchy_path_ltree'])
	else:
		provision_data['hierarchy_path_ltree'] = ""

	return ProvisionDetail(
		**provision_data,
		references_to=references_to,
		referenced_by=referenced_by,
		defined_terms_used=defined_terms_used
	)


def get_hierarchy(db: Session, act_id: str, parent_id: Optional[str]) -> List[ProvisionHierarchy]:
	"""
	Fetches the hierarchy nodes (children) for a given parent or the top level of an act.
	"""

	# Alias for the child provision in the subquery
	ChildProvision = aliased(models.Provision)

	# Define a subquery to check for the existence of children efficiently.
	# This subquery is correlated with the outer query on models.Provision.internal_id
	children_exists_subq = db.query(ChildProvision.internal_id) \
		.filter(ChildProvision.parent_internal_id == models.Provision.internal_id) \
		.exists().label("has_children")

	# Base query for the hierarchy nodes
	query = db.query(
		models.Provision.internal_id,
		models.Provision.ref_id,
		models.Provision.title,
		models.Provision.type,
		models.Provision.sibling_order,
		# Use the correlated subquery to determine has_children for each row
		children_exists_subq
	).filter(models.Provision.act_id == act_id)

	if parent_id:
		query = query.filter(models.Provision.parent_internal_id == parent_id)
	else:
		# Top-level elements have no parent
		query = query.filter(models.Provision.parent_internal_id == None)

	# Order by sibling order when available, falling back to hierarchy path
	results = query.order_by(
		case((models.Provision.sibling_order.is_(None), 1), else_=0),
		models.Provision.sibling_order,
		models.Provision.hierarchy_path_ltree
	).all()

	# Convert results to Pydantic models
	return [ProvisionHierarchy.model_validate(r._asdict()) for r in results]
