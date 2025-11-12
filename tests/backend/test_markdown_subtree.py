import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")

import backend.main as backend_main
from backend import schemas
from backend.services import export_markdown as export_service


def _make_detail(
		internal_id: str,
		hierarchy_path: str,
		sibling_order: int,
		title: str,
		*,
		content: str = "Body",
		references=None,
		definitions=None,
		parent_internal_id: str | None = None,
) -> schemas.ProvisionDetail:
	references = references or []
	definitions = definitions or []
	return schemas.ProvisionDetail(
		internal_id=internal_id,
		ref_id=f"REF-{internal_id}",
		act_id="ACT",
		type="Section",
		local_id=None,
		title=title,
		content_md=content,
		level=1,
		hierarchy_path_ltree=hierarchy_path,
		parent_internal_id=parent_internal_id,
		sibling_order=sibling_order,
		pagerank=0.0,
		in_degree=0,
		out_degree=0,
		references_to=[schemas.ReferenceToDetail(**ref) for ref in references],
		referenced_by=[],
		defined_terms_used=[schemas.DefinedTermUsageDetail(**definition) for definition in definitions],
		definitions_with_references=[],
		breadcrumbs=[],
		children=[],
	)


def test_markdown_subtree_endpoint_returns_content_and_definitions(monkeypatch):
	call_order = []

	def fake_ordered_ids(db, ids):
		assert set(ids) == {"root", "chapter", "section"}
		return ["root", "chapter", "section"]

	detail_map = {
		"root": _make_detail(
			"root",
			"ACT.Root",
			1,
			"Root Title",
			content="Root body text",
			definitions=[{"term_text": "Defined Term", "definition_internal_id": "def-1"}],
		),
		"chapter": _make_detail(
			"chapter",
			"ACT.Root.Chapter",
			2,
			"Chapter Title",
			content="Chapter body text",
		),
		"section": _make_detail(
			"section",
			"ACT.Root.Chapter.Section",
			3,
			"Section Title",
			content="Section body text",
			definitions=[{"term_text": "Defined Term", "definition_internal_id": "def-1"}],
			parent_internal_id="chapter",
		),
		"def-1": _make_detail(
			"def-1",
			"ACT.Definition.One",
			4,
			"Definition One",
			content="Definition body text",
		),
	}

	def fake_get_detail(db, internal_id):
		call_order.append(internal_id)
		return detail_map[internal_id]

	monkeypatch.setattr(backend_main.crud, "get_ordered_internal_ids", fake_ordered_ids)
	monkeypatch.setattr(backend_main.crud, "get_provision_detail", fake_get_detail)
	monkeypatch.setattr(export_service.crud, "get_provision_detail", fake_get_detail)

	request = schemas.VisibleSubtreeMarkdownRequest(
		root_internal_id="root",
		visible_descendant_ids=["chapter", "section", "section"],
	)

	response = backend_main.get_visible_subtree_markdown(request, db=None)

	body = response.body.decode()
	assert "### Root Title" in body
	assert "Root body text" in body
	assert "### Chapter Title" in body
	assert "### Section Title" in body
	assert "## Definitions" in body
	assert body.count("Definition One") == 1
	assert "Definition body text" in body
	assert call_order == ["root", "chapter", "section", "def-1"]
