# backend/main.py
import logging
from pathlib import Path as PathLib
from typing import Dict, List, Optional, Literal, Set

from fastapi import FastAPI, Depends, HTTPException, status, Query, Path as FastAPIPath
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

# Import models to register them
# Import CRUD and Schemas
from backend import crud, schemas
from backend.config import get_settings
from backend.database import initialize_engine, Base, get_db
from backend.schemas import UnifiedSearchRequest, UnifiedSearchResponse
from backend.services.export_markdown import export_markdown_for_provision, assemble_visible_subtree_markdown
from backend.services.unified_search import unified_search as unified_search_service
from backend.services.mcp_formatter import format_provision_detail_md
from backend.services.provision_tokens import parse_flexible_token

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="Taxiv API", version="0.1.0")
media_url = (settings.MEDIA_URL_BASE.rstrip('/') if settings.MEDIA_URL_BASE else '')
if not media_url:
        media_url = '/media'
if not media_url.startswith('/'):
        media_url = f'/{media_url}'
PathLib(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
app.mount(media_url, StaticFiles(directory=settings.MEDIA_ROOT), name='media')


def _normalize_field_list(raw_fields: Optional[List[str]]) -> Optional[Set[str]]:
        if not raw_fields:
                return None
        collected: Set[str] = set()
        for item in raw_fields:
                if not item:
                        continue
                parts = [segment.strip() for segment in item.split(',')]
                for part in parts:
                        if part:
                                collected.add(part)
        return collected or None


def _serialize_detail(
        detail: schemas.ProvisionDetail,
        include_fields: Optional[Set[str]],
        parsed: Optional[dict],
        requested_id: Optional[str] = None,
) -> dict:
        payload = detail.model_dump()
        if parsed:
                payload["parsed"] = parsed
        if requested_id:
                payload["requested_id"] = requested_id
        if include_fields is not None:
                keys = set(include_fields)
                keys.update({"etag", "last_modified", "size_bytes"})
                if parsed:
                        keys.add("parsed")
                if requested_id:
                        keys.add("requested_id")
                payload = {key: payload[key] for key in keys if key in payload}
        return payload

# CORS Middleware
origins = [
	"http://localhost:3000",
]

app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
	logger.info("Initializing database connection...")
	try:
		engine = initialize_engine()
		logger.info("Ensuring database tables are created...")
		Base.metadata.create_all(bind=engine)
		logger.info("Database initialization complete.")
	except Exception as e:
		logger.error(f"Error during database initialization: {e}")


@app.get("/")
def read_root():
        return {"message": "Welcome to the Taxiv API", "environment": settings.ENVIRONMENT}


@app.get("/capabilities")
def get_capabilities(db: Session = Depends(get_db)):
        acts = crud.get_acts(db)
        act_ids = [act.id for act in acts]
        default_act = act_ids[0] if act_ids else None
        return {
                "acts": act_ids,
                "default_act": default_act,
        }


# --- API Endpoints (Using /api prefix) ---

@app.get("/api/acts", response_model=List[schemas.ActList])
def list_acts(db: Session = Depends(get_db)):
	"""Lists all available Acts in the database."""
	return crud.get_acts(db)


@app.get("/api/provisions/detail/{internal_id}")
def get_provision_detail(
        internal_id: str,
        response_format: Literal["json", "markdown"] = Query(
                "json",
                alias="format",
                description="Set to 'markdown' to receive a formatted MCP-style payload.",
        ),
        include_breadcrumbs: bool = Query(False, description="Include breadcrumb hierarchy."),
        include_children: bool = Query(False, description="Include immediate children."),
        include_definitions: bool = Query(False, description="Include definitions and defined terms."),
        include_references: bool = Query(True, description="Include references and inbound citations."),
        fields: Optional[List[str]] = Query(None, description="Subset of fields to include in the response."),
        db: Session = Depends(get_db),
):
        """
        Returns the detailed information for a specific provision with controllable expansions.
        """
        options = schemas.ProvisionDetailOptions(
                include_breadcrumbs=include_breadcrumbs,
                include_children=include_children,
                include_definitions=include_definitions,
                include_references=include_references,
        )
        include_fields = _normalize_field_list(fields)
        parsed_info: Optional[dict] = None
        target_id = internal_id.strip()

        provision_detail = crud.get_provision_detail(db, target_id, options=options)
        if not provision_detail:
                token = parse_flexible_token(internal_id)
                if token:
                        resolved_id = crud.find_internal_id_by_section(db, token.act, token.section)
                        if resolved_id:
                                provision_detail = crud.get_provision_detail(db, resolved_id, options=options)
                                if provision_detail:
                                        parsed_info = {
                                                "act": token.act,
                                                "section": token.section,
                                                "terms": token.terms,
                                                "internal_id": resolved_id,
                                        }
        if not provision_detail:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provision not found")

        if response_format.lower() == "markdown":
                detail_payload = provision_detail.model_dump()
                if parsed_info:
                        detail_payload["parsed"] = parsed_info
                markdown = format_provision_detail_md(detail_payload)
                return PlainTextResponse(markdown)

        serialized = _serialize_detail(provision_detail, include_fields, parsed_info)
        encoded = jsonable_encoder(serialized)
        return JSONResponse(content=encoded)


@app.post("/api/batch_provisions", response_model=schemas.BatchProvisionResponse)
def batch_provision_details(
        request: schemas.BatchProvisionRequest,
        db: Session = Depends(get_db),
):
        options = schemas.ProvisionDetailOptions(
                include_breadcrumbs=request.include_breadcrumbs,
                include_children=request.include_children,
                include_definitions=request.include_definitions,
                include_references=request.include_references,
        )
        include_fields = _normalize_field_list(request.fields)
        parsed_map: Dict[str, dict] = {}
        results: List[dict] = []

        for identifier in request.ids:
                parsed_info: Optional[dict] = None
                detail = crud.get_provision_detail(db, identifier, options=options)
                if not detail:
                        token = parse_flexible_token(identifier)
                        if token:
                                resolved_id = crud.find_internal_id_by_section(db, token.act, token.section)
                                if resolved_id:
                                        detail = crud.get_provision_detail(db, resolved_id, options=options)
                                        if detail:
                                                parsed_info = {
                                                        "act": token.act,
                                                        "section": token.section,
                                                        "terms": token.terms,
                                                        "internal_id": resolved_id,
                                                }
                                                parsed_map[identifier] = parsed_info
                if not detail:
                        results.append({
                                "requested_id": identifier,
                                "error": "Provision not found",
                        })
                        continue
                if parsed_info and identifier not in parsed_map:
                        parsed_map[identifier] = parsed_info
                serialized = _serialize_detail(detail, include_fields, parsed_info, requested_id=identifier)
                results.append(serialized)

        return schemas.BatchProvisionResponse(
                results=results,
                parsed=parsed_map or None,
        )


@app.get("/api/provisions/hierarchy/{act_id}", response_model=List[schemas.ProvisionHierarchy])
def get_hierarchy(
                act_id: str = FastAPIPath(..., description="The ID of the Act (e.g., ITAA1997)"),
                parent_id: Optional[str] = Query(None,
										 description="The internal_id of the parent provision. If None, returns top-level elements."),
		db: Session = Depends(get_db)
):
	"""Get the children of a specific provision or the top-level elements of an Act."""
	return crud.get_hierarchy(db, act_id, parent_id)


@app.get("/api/provisions/search_hierarchy/{act_id}", response_model=List[schemas.ProvisionHierarchy])
def search_hierarchy(
		act_id: str = FastAPIPath(..., description="The ID of the Act."),
		query: str = Query(..., description="The search query string."),
		db: Session = Depends(get_db)
):
	"""Search the hierarchy for a given query."""
	return crud.search_hierarchy(db, act_id, query)


@app.get("/api/provisions/lookup", response_model=List[schemas.ProvisionDetail])
def get_provision_by_ref_id(
		ref_id: str = Query(..., description="The reference ID of the provision."),
		act_id: str = Query(..., description="The ID of the act."),
		db: Session = Depends(get_db)
):
	"""Lookup a provision by its reference ID and act ID."""
	provisions = crud.get_provision_by_ref_id(db, ref_id, act_id)
	if not provisions:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provision not found")
	return provisions


@app.post("/api/provisions/export_markdown", response_model=schemas.ExportMarkdownResponse)
def export_markdown(request: schemas.ExportMarkdownRequest, db: Session = Depends(get_db)):
	try:
		markdown = export_markdown_for_provision(
			db,
			request.provision_internal_id,
			request.include_descendants,
		)
	except ValueError as exc:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
	return schemas.ExportMarkdownResponse(markdown=markdown)


@app.post("/api/search/unified", response_model=UnifiedSearchResponse)
def unified_search_endpoint(request: UnifiedSearchRequest, db: Session = Depends(get_db)):
        try:
                payload = unified_search_service(db, request.query, request.k, request.offset)
                return payload
        except Exception as exc:
                logger.exception("Unified search failed")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/provisions/markdown_subtree", response_class=PlainTextResponse)
def get_visible_subtree_markdown(
		request: schemas.VisibleSubtreeMarkdownRequest,
		db: Session = Depends(get_db),
):
	unique_ids = set(request.visible_descendant_ids or [])
	unique_ids.add(request.root_internal_id)
	ordered_ids = crud.get_ordered_internal_ids(db, list(unique_ids))
	if not ordered_ids:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provision not found")

	markdown = assemble_visible_subtree_markdown(db, ordered_ids)
	if not markdown:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provision not found")

	return PlainTextResponse(markdown)
