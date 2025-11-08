import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
import pytest
from types import SimpleNamespace

from backend import schemas
from backend.services import export_markdown as export_service
import backend.main as backend_main
from fastapi import HTTPException


class FakeQuery:
	def __init__(self, internal_ids):
		self._internal_ids = internal_ids

	def filter(self, *args, **kwargs):
		return self

	def order_by(self, *args, **kwargs):
		return self

	def all(self):
		return [SimpleNamespace(internal_id=internal_id) for internal_id in self._internal_ids]


class FakeDB:
	def __init__(self, root_id: str, hierarchy_path: str, subtree_ids):
		self._root = SimpleNamespace(internal_id=root_id, hierarchy_path_ltree=hierarchy_path)
		self._subtree_ids = subtree_ids

	def get(self, model, internal_id):
		if internal_id == self._root.internal_id:
			return self._root
		return None

	def query(self, *args, **kwargs):
		return FakeQuery(self._subtree_ids)


def _make_detail(*, internal_id: str, ref_id: str, title: str, hierarchy_path: str, sibling_order: int, content: str,
				 references=None, definitions=None, parent_internal_id=None):
	references = references or []
	definitions = definitions or []
	return schemas.ProvisionDetail(
		internal_id=internal_id,
		ref_id=ref_id,
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
	)


def test_export_markdown_service_collects_related_data(monkeypatch):
	details = {
		"root": _make_detail(
			internal_id="root",
			ref_id="ACT-1",
			title="Root Node",
			hierarchy_path="ACT.Root",
			sibling_order=1,
			content="Intro with image ![Diagram](diagram.png)",
			references=[
				{
					"target_ref_id": "ACT-99",
					"snippet": "see ACT-99",
					"target_title": "Referenced Node",
					"target_internal_id": "ref",
				},
				{
					"target_ref_id": "EXT-1",
					"snippet": "external context",
					"target_title": None,
					"target_internal_id": None,
				},
				{
					"target_ref_id": "EXT-1",
					"snippet": "external context",
					"target_title": None,
					"target_internal_id": None,
				},
			],
			definitions=[
				{
					"term_text": "Defined Term",
					"definition_internal_id": "def1",
				},
			],
		),
		"child": _make_detail(
			internal_id="child",
			ref_id="ACT-1.1",
			title="Child Node",
			hierarchy_path="ACT.Root.Child",
			sibling_order=2,
			content="Child content",
			references=[],
			definitions=[],
			parent_internal_id="root",
		),
		"ref": _make_detail(
			internal_id="ref",
			ref_id="ACT-99",
			title="Referenced Node",
			hierarchy_path="ACT.Ref",
			sibling_order=3,
			content="Referenced content",
			references=[],
			definitions=[
				{
					"term_text": "Nested Term",
					"definition_internal_id": "def2",
				},
			],
		),
		"def1": _make_detail(
			internal_id="def1",
			ref_id="DEF-1",
			title="Definition One",
			hierarchy_path="ACT.Def1",
			sibling_order=4,
			content="Definition text with ![Symbol](symbol.png)",
			references=[
				{
					"target_ref_id": "ACT-200",
					"snippet": "see ACT-200",
					"target_title": "Definition Reference",
					"target_internal_id": "def_ref",
				},
				{
					"target_ref_id": "ACT-99",
					"snippet": "already seen",
					"target_title": "Referenced Node",
					"target_internal_id": "ref",
				},
				{
					"target_ref_id": "ACT-200",
					"snippet": "duplicate",
					"target_title": "Definition Reference",
					"target_internal_id": "def_ref",
				},
			],
			definitions=[
				{
					"term_text": "Secondary Term",
					"definition_internal_id": "def2",
				},
			],
		),
		"def2": _make_detail(
			internal_id="def2",
			ref_id="DEF-2",
			title="Definition Two",
			hierarchy_path="ACT.Def2",
			sibling_order=5,
			content="Terminal definition",
			references=[],
			definitions=[],
		),
		"def_ref": _make_detail(
			internal_id="def_ref",
			ref_id="ACT-200",
			title="Definition Reference",
			hierarchy_path="ACT.DefRef",
			sibling_order=6,
			content="Definition reference content",
			references=[],
			definitions=[],
		),
	}

	def fake_get_provision_detail(db, internal_id):
		return details[internal_id]

	monkeypatch.setattr(export_service.crud, "get_provision_detail", fake_get_provision_detail)
	fake_db = FakeDB("root", "ACT.Root", ["root", "child"])
	markdown = export_service.export_markdown_for_provision(fake_db, "root", include_descendants=True)

	assert "## Copied nodes" in markdown
	assert "### Root Node" in markdown
	assert "### Child Node" in markdown
	assert "## Referenced nodes" in markdown
	assert "### Referenced Node" in markdown
	assert "## Definitions used" in markdown
	assert "### Definition One" in markdown
	assert "### Definition Two" in markdown
	assert markdown.count("### Definition Reference") == 1
	assert "```" in markdown
	assert "### Definition Reference" not in markdown.split("## Referenced nodes")[1].split("## Definitions used")[0]
	assert "```\n### Definition Reference\n\nDefinition reference content\n```" in markdown
	assert "## Unresolved external references" in markdown
	assert "- EXT-1 (from ACT-1) — external context" in markdown
	assert "![Diagram]" not in markdown
	assert "Diagram" in markdown
	assert "Symbol" in markdown
	assert markdown.count("EXT-1 (from ACT-1)") == 1


def test_export_markdown_endpoint_success(monkeypatch):
	monkeypatch.setattr(
		backend_main,
		"export_markdown_for_provision",
		lambda db, pid, include: "Rendered",
	)
	request = schemas.ExportMarkdownRequest(
		provision_internal_id="root",
		include_descendants=True,
	)
	response = backend_main.export_markdown(request, db=None)
	assert response.markdown == "Rendered"


def test_export_markdown_endpoint_not_found(monkeypatch):
	def failing_service(db, pid, include):
		raise ValueError("Provision missing")

	monkeypatch.setattr(backend_main, "export_markdown_for_provision", failing_service)
	request = schemas.ExportMarkdownRequest(
		provision_internal_id="absent",
		include_descendants=False,
	)
	with pytest.raises(HTTPException) as excinfo:
		backend_main.export_markdown(request, db=None)

	assert excinfo.value.status_code == 404
	assert excinfo.value.detail == "Provision missing"
