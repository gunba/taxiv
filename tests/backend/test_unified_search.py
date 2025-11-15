import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.append(str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")

import pytest

from backend.services import unified_search as search


class DummyResult:
	def __init__(self, rows: List[Tuple[str, str, float, float]]):
		self._rows = rows

	def fetchall(self) -> List[Tuple[str, str, float, float]]:
		return self._rows


class DummySession:
	def __init__(self, rows: List[Tuple[str, str, float, float]]):
		self.rows = rows
		self.calls: List[Tuple[str, Dict[str, object]]] = []

	def execute(self, sql, params):
		self.calls.append((str(sql), dict(params)))
		return DummyResult(self.rows)


def test_extract_tsquery_terms_caps_length_and_respects_order():
	normalized = "alpha betafoxtrot charlie delta epsilon foxtrot golf hotel india juliet kilo lima"
	terms = search._extract_tsquery_terms(normalized)
	assert len(terms) <= search.TSQUERY_OR_MAX_TERMS
	# foxtrot appears twice; ensure dedupe keeps first occurrence only
	assert terms.count("foxtrot") == 1
	# Selected terms should maintain original order among the chosen subset
	indices = [normalized.split().index(term) for term in terms]
	assert indices == sorted(indices)


def test_lexical_candidates_includes_relaxed_tsquery_and_trigram_floor():
	rows = [("ITAA1997_Section_6-5", "Section", 0.0, 0.42)]
	session = DummySession(rows)

	results = search._lexical_candidates(
		session,
		original="Ordinary income termination payment",
		normalized="ordinary income termination payment",
		act_id="ITAA1997",
		limit=5,
	)

	assert "ITAA1997_Section_6-5" in results
	assert math.isclose(results["ITAA1997_Section_6-5"], 0.42 * 0.3, rel_tol=1e-6)

	assert session.calls, "expected SQL execution"
	_sql, params = session.calls[0]
	expected_or = "'ordinary':* | 'income':* | 'termination':* | 'payment':*"
	assert params["q_or_en"] == expected_or
	assert params["q_or_simple"] == expected_or
	assert params["tri_floor"] == pytest.approx(search.TRIGRAM_MATCH_FLOOR)


def test_extract_tsquery_terms_and_tsquery_or_support_ampersand_terms():
	normalized = "R&D feedstock"
	terms = search._extract_tsquery_terms(normalized)
	# & should be allowed inside a token so that \"R&D\" is preserved
	assert "r&d" in terms
	assert "feedstock" in terms

	q_or = search._build_tsquery_or(terms)
	# Ensure ampersand is escaped for tsquery syntax while still present
	assert "'r\\&d':*" in q_or
	assert "'feedstock':*" in q_or


def test_filter_lexical_candidates_for_terms_keeps_only_matching_rows():
	# Arrange: two lexical candidates, only one contains the query term.

	class Row:
		def __init__(self, internal_id: str, title: str, content_md: str):
			self.internal_id = internal_id
			self.title = title
			self.content_md = content_md

	class DummyQuery:
		def __init__(self, rows):
			self._rows = rows

		def filter(self, *args, **kwargs):
			# Ignore SQLAlchemy filters in this dummy implementation.
			return self

		def all(self):
			return self._rows

	class DummyDB:
		def __init__(self, rows):
			self._rows = rows

		def query(self, *cols):
			return DummyQuery(self._rows)

	rows = [
		Row("A", "R&D adjustments", "Some R&D related content."),
		Row("B", "Generic admin", "No relevant terms here."),
	]
	db = DummyDB(rows)

	lex_candidates = {"A": 1.0, "B": 0.5}
	terms = ["r&d", "feedstock"]

	filtered = search._filter_lexical_candidates_for_terms(
		db,
		lex_candidates,
		act_id="ITAA1936",
		terms=terms,
	)

	assert "A" in filtered
	assert "B" not in filtered


def test_unified_search_multi_act_aggregates_and_preserves_act_ids(monkeypatch):
	"""Ensure act_id=\"*\" triggers multi-act aggregation and returns per-Act results."""

	class StubActMeta:
		def __init__(self, act_id: str):
			self.id = act_id

	def fake_list_acts():
		return [StubActMeta("ITAA1997"), StubActMeta("ITAA1936")]

	# Track calls into the single-act helper
	calls = []

	def fake_single_act(db, query, k, offset, act_id):
		calls.append((query, k, offset, act_id))
		# Return a single result per act with different URS scores
		return {
			"query_interpretation": {
				"provisions": [],
				"definitions": [],
				"keywords": query,
				"parsed": None,
				"pseudo_seeds": [],
			},
			"results": [
				{
					"id": f"{act_id}_Section_6-5",
					"act_id": act_id,
					"ref_id": f"{act_id}:Section:6-5",
					"title": "Ordinary income",
					"type": "Section",
					"score_urs": 90 if act_id == "ITAA1997" else 80,
					"content_snippet": "Assessable income includes ordinary income…",
				},
			],
			"debug": {
				"mass_captured": 1.0,
				"num_seeds": 1,
			},
		}

	monkeypatch.setattr(search, "list_metadata_acts", fake_list_acts)
	monkeypatch.setattr(search, "_unified_search_single_act", fake_single_act)

	class DummyDB:
		pass

	payload = search.unified_search(
		db=DummyDB(),
		query="ordinary income",
		k=2,
		offset=0,
		act_id="*",
	)

	# Both acts should have been queried
	assert {call[3] for call in calls} == {"ITAA1997", "ITAA1936"}

	# Results should be merged and carry act_id per row
	assert len(payload["results"]) == 2
	act_ids = {row["act_id"] for row in payload["results"]}
	assert act_ids == {"ITAA1997", "ITAA1936"}

	# ITAA1997 has higher URS, so should appear first
	assert payload["results"][0]["act_id"] == "ITAA1997"


def test_unified_search_multi_act_skips_failed_acts(monkeypatch):
	"""Multi-act unified search should tolerate per-Act failures."""

	class StubActMeta:
		def __init__(self, act_id: str):
			self.id = act_id

	def fake_list_acts():
		# Include one healthy and one failing act.
		return [StubActMeta("ITAA1997"), StubActMeta("BROKEN_ACT")]

	def fake_single_act(db, query, k, offset, act_id):
		if act_id == "BROKEN_ACT":
			raise RuntimeError("boom")
		return {
			"query_interpretation": {
				"provisions": [],
				"definitions": [],
				"keywords": query,
				"parsed": None,
				"pseudo_seeds": [],
			},
			"results": [
				{
					"id": f"{act_id}_Section_6-5",
					"act_id": act_id,
					"ref_id": f"{act_id}:Section:6-5",
					"title": "Ordinary income",
					"type": "Section",
					"score_urs": 90,
					"content_snippet": "Assessable income includes ordinary income…",
				},
			],
			"debug": {
				"mass_captured": 1.0,
				"num_seeds": 1,
			},
		}

	monkeypatch.setattr(search, "list_metadata_acts", fake_list_acts)
	monkeypatch.setattr(search, "_unified_search_single_act", fake_single_act)

	class DummyDB:
		pass

	payload = search.unified_search(
		db=DummyDB(),
		query="ordinary income",
		k=5,
		offset=0,
		act_id="*",
	)

	# Only the healthy act's results should be present.
	assert len(payload["results"]) == 1
	assert payload["results"][0]["act_id"] == "ITAA1997"

	# Debug metadata should include a per-act entry for the failure.
	debug = payload.get("debug") or {}
	per_act = debug.get("per_act") or []
	failed_entries = [entry for entry in per_act if entry.get("act_id") == "BROKEN_ACT"]
	assert failed_entries, "Expected a debug entry for the failed act"
