import re

import pytest

from ingest.pipelines.itaa1997 import parser


class _FakeValue:
	def __init__(self, value: str):
		self._value = value

	def get(self, _key: str) -> str:
		return self._value


class _FakeNumberingElement:
	def __init__(self, formats):
		self._formats = formats

	def xpath(self, query: str, namespaces=None):
		if 'abstractNumId' in query and '@w:numId' in query:
			num_id_match = re.search(r"@w:numId='([^']+)'", query)
			if not num_id_match:
				return []
			num_id = num_id_match.group(1)
			return [_FakeValue(num_id)]
		if 'numFmt' in query:
			abstract_match = re.search(r"@w:abstractNumId='([^']+)'", query)
			level_match = re.search(r"@w:ilvl='([^']+)'", query)
			if not abstract_match or not level_match:
				return []
			abstract_id = abstract_match.group(1)
			level = int(level_match.group(1))
			fmt = self._formats.get((abstract_id, level))
			return [_FakeValue(fmt)] if fmt else []
		return []


class _FakeNumberingPart:
	def __init__(self, formats):
		self.element = _FakeNumberingElement(formats)


class FakeParagraph:
	def __init__(self, text: str, num_id: str | None = None, level: int | None = None,
			formats=None):
		self.text = text
		self._element = None
		self.paragraph_format = type('PF', (), {'left_indent': None})()
		if num_id is None or level is None:
			self._p = type('P', (), {'pPr': None})()
			self.part = type('Part', (), {'numbering_part': None})()
		else:
			num_pr = type('NumPr', (), {})()
			num_pr.numId = type('Val', (), {'val': str(num_id)})()
			num_pr.ilvl = type('Val', (), {'val': str(level)})()
			p_pr = type('PPr', (), {'numPr': num_pr})()
			self._p = type('P', (), {'pPr': p_pr})()
			self.part = type('Part', (), {'numbering_part': _FakeNumberingPart(formats or {})})()


def _build_paragraphs_for_lists():
	formats = {
		('1', 0): 'bullet',
		('1', 1): 'bullet',
		('2', 0): 'decimal',
		('2', 1): 'decimal',
	}
	return (
		formats,
		[
			FakeParagraph('Intro text'),
			FakeParagraph('Bullet 1', '1', 0, formats),
			FakeParagraph('Bullet nested', '1', 1, formats),
			FakeParagraph('Bullet 2', '1', 0, formats),
			FakeParagraph('Number 1', '2', 0, formats),
			FakeParagraph('Number nested', '2', 1, formats),
			FakeParagraph('Outro text'),
		],
	)


def test_format_paragraph_markdown_handles_nested_lists():
	formats, paragraphs = _build_paragraphs_for_lists()
	tracker = parser.ListStateTracker()
	content = ''
	for para in paragraphs:
		content += parser.format_paragraph_markdown(
			para,
			para.text,
			tracker,
			bool(content),
			'',
		)

	expected = (
		'Intro text\n\n'
		'- Bullet 1\n'
		'    - Bullet nested\n'
		'- Bullet 2\n\n'
		'1. Number 1\n'
		'    1. Number nested\n\n'
		'Outro text\n\n'
	)
	assert content == expected


def test_process_definition_content_preserves_list_markdown(monkeypatch):
	formats, paragraphs = _build_paragraphs_for_lists()
	monkeypatch.setattr(parser, 'Paragraph', FakeParagraph)
	definition_tracker = parser.ListStateTracker()
	definition_md = ''
	for para in paragraphs[1:]:
		content, _ = parser.process_definition_content(para, definition_tracker, definition_md)
		definition_md += content

	expected = (
		'- Bullet 1\n'
		'    - Bullet nested\n'
		'- Bullet 2\n\n'
		'1. Number 1\n'
		'    1. Number nested\n\n'
		'Outro text\n\n'
	)
	assert definition_md == expected
