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
