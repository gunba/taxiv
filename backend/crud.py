# backend/crud.py
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, case
from backend.models import legislation as models
from backend.schemas import ProvisionDetail, ProvisionHierarchy, ActList, ReferenceToDetail, ReferencedByDetail, DefinedTermUsageDetail
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

def get_acts(db: Session) -> List[models.Act]:
    return db.query(models.Act).all()

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

    references_to = [ReferenceToDetail.model_validate(r) for r in references_to_query]

    # 2. Referenced By (Incoming)
    SourceProvision = aliased(models.Provision)
    referenced_by_query = db.query(
        SourceProvision.internal_id.label("source_internal_id"),
        SourceProvision.ref_id.label("source_ref_id"),
        SourceProvision.title.label("source_title")
    ).join(models.Reference, models.Reference.source_internal_id == SourceProvision.internal_id
    ).filter(models.Reference.target_internal_id == internal_id).distinct().all()

    referenced_by = [ReferencedByDetail.model_validate(r) for r in referenced_by_query]

    # 3. Defined Terms Used
    DefinitionProvision = aliased(models.Provision)
    terms_used_query = db.query(
        models.DefinedTermUsage.term_text,
        DefinitionProvision.internal_id.label("definition_internal_id")
    ).outerjoin(DefinitionProvision, DefinitionProvision.internal_id == models.DefinedTermUsage.definition_internal_id
    ).filter(models.DefinedTermUsage.source_internal_id == internal_id).all()

    defined_terms_used = [DefinedTermUsageDetail.model_validate(t) for t in terms_used_query]

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

    # Define a subquery to check for the existence of children efficiently.
    children_exists_subq = db.query(models.Provision.internal_id)\
        .filter(models.Provision.parent_internal_id == models.Provision.internal_id)\
        .exists().label("has_children")

    # Base query for the hierarchy nodes
    query = db.query(
        models.Provision.internal_id,
        models.Provision.ref_id,
        models.Provision.title,
        models.Provision.type,
        # Use the subquery to determine has_children
        children_exists_subq
    ).filter(models.Provision.act_id == act_id)

    if parent_id:
        query = query.filter(models.Provision.parent_internal_id == parent_id)
    else:
        # Top-level elements have no parent
        query = query.filter(models.Provision.parent_internal_id == None)

    # Order by LTree path for natural structural ordering
    results = query.order_by(models.Provision.hierarchy_path_ltree).all()

    # Convert results to Pydantic models
    return [ProvisionHierarchy.model_validate(r) for r in results]
