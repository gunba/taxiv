import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.services.provision_tokens import parse_flexible_token


def test_parse_section_with_prefix_and_terms():
        token = parse_flexible_token("s 6-5 ordinary income", default_act="ITAA1997")
        assert token is not None
        assert token.act == "ITAA1997"
        assert token.section == "6-5"
        assert token.terms == ["ordinary income"]


def test_parse_section_with_dotted_identifier():
        token = parse_flexible_token("sec 6.5", default_act="ITAA1997")
        assert token is not None
        assert token.section == "6-5"
        assert token.terms == []


def test_parse_section_with_space_delimiter():
        token = parse_flexible_token("6 5", default_act="ITAA1997")
        assert token is not None
        assert token.section == "6-5"


def test_parse_returns_none_for_unrecognized_pattern():
        assert parse_flexible_token("chapter foo", default_act="ITAA1997") is None
        assert parse_flexible_token("", default_act="ITAA1997") is None


def test_parse_allows_explicit_act_prefix():
        token = parse_flexible_token("DEMOACT: s 10-1 custom", default_act="ITAA1997")
        assert token is not None
        assert token.act == "DEMOACT"
        assert token.section == "10-1"
