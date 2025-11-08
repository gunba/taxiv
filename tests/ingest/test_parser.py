import copy
import re
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from ingest.pipelines.itaa1997 import parser


@pytest.fixture
def definition_state_cleanup():
	original_definitions = copy.deepcopy(parser.DEFINITIONS_995_1)
	original_variant_map = copy.deepcopy(parser.DEFINITION_VARIANT_MAP)
	original_greedy_regex = parser.DEFINITION_GREEDY_REGEX
	original_marker_regex = parser.DEFINITION_MARKER_REGEX

	try:
		parser.DEFINITIONS_995_1.clear()
		parser.DEFINITION_VARIANT_MAP.clear()
		parser.DEFINITION_GREEDY_REGEX = None
		yield
	finally:
		parser.DEFINITIONS_995_1.clear()
		parser.DEFINITIONS_995_1.update(original_definitions)
		parser.DEFINITION_VARIANT_MAP.clear()
		parser.DEFINITION_VARIANT_MAP.update(original_variant_map)
		parser.DEFINITION_GREEDY_REGEX = original_greedy_regex
		parser.DEFINITION_MARKER_REGEX = original_marker_regex


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


def _prime_media_context(tmp_path, monkeypatch):
	monkeypatch.setattr(parser.config, 'MEDIA_ROOT', str(tmp_path))
	monkeypatch.setattr(parser.config, 'MEDIA_URL_BASE', '/media')
	parser._initialize_media_context('sample.docx')


def _build_paragraph_with_image(blob, content_type, partname, alt_text, relationship_id='rId1'):
	embed_key = parser.qn('r:embed')
	link_key = parser.qn('r:link')

	class _DocPr:
		def __init__(self, text):
			self._text = text

		def get(self, key: str) -> str:
			if key == 'descr':
				return self._text
			if key == 'title':
				return ''
			return ''

	class _Blip:
		def __init__(self, rid):
			self._map = {embed_key: rid, link_key: None}

		def get(self, key: str):
			return self._map.get(key)

	class _Drawing:
		def __init__(self):
			self._doc_pr = _DocPr(alt_text)
			self._blip = _Blip(relationship_id)

		def iter(self, qname: str):
			if 'docPr' in qname:
				yield self._doc_pr
			elif 'blip' in qname:
				yield self._blip

	class _Element:
		def __init__(self):
			self._drawing = _Drawing()

		def iter(self, qname: str):
			if 'drawing' in qname:
				yield self._drawing

	image_part = type('ImagePart', (), {
		'blob': blob,
		'content_type': content_type,
		'partname': partname,
	})()

	paragraph = type('Paragraph', (), {})()
	paragraph._element = _Element()
	paragraph.part = type('Part', (), {'related_parts': {relationship_id: image_part}})()
	paragraph.text = ''
	return paragraph


def test_persist_image_blob_converts_to_png(tmp_path, monkeypatch):
	_prime_media_context(tmp_path, monkeypatch)

	image = Image.new('RGB', (2, 2), color=(255, 0, 0))
	buffer = BytesIO()
	image.save(buffer, format='JPEG')
	blob = buffer.getvalue()

	record = parser._persist_image_blob(blob, 'word/media/image1.jpeg', 'image/jpeg')

	assert record is not None
	assert record['stored_extension'] == '.png'
	assert record['converted_to_png'] is True
	assert record['renderable'] is True
	assert record['public_url']
	saved_path = Path(record['absolute_path'])
	assert saved_path.exists()
	assert saved_path.suffix == '.png'

	# Ensure cached reuse returns the same metadata object
	cached = parser._persist_image_blob(blob, 'word/media/image1.jpeg', 'image/jpeg')
	assert cached is record

	parser._clear_media_context()


def test_get_image_alt_text_returns_markdown_without_description(tmp_path, monkeypatch):
	_prime_media_context(tmp_path, monkeypatch)

	image = Image.new('RGB', (1, 1), color=(0, 128, 0))
	buffer = BytesIO()
	image.save(buffer, format='PNG')
	paragraph = _build_paragraph_with_image(
		buffer.getvalue(),
		'image/png',
		'word/media/image2.png',
		'An illustrative graph',
	)

	markdown, terms = parser.get_image_alt_text(paragraph)

	assert markdown.strip().startswith('![')
	assert '[Image Description:' not in markdown
	assert not terms

	cache = parser.CURRENT_MEDIA_CONTEXT['cache']
	assert len(cache) == 1
	record = next(iter(cache.values()))
	assert 'An illustrative graph' in record['alt_texts']

	parser._clear_media_context()


def test_get_image_alt_text_falls_back_to_description_when_not_renderable(tmp_path, monkeypatch):
	_prime_media_context(tmp_path, monkeypatch)

	paragraph = _build_paragraph_with_image(
		b'not-an-image',
		'image/x-emf',
		'word/media/vector.emf',
		'Diagram of tax flow',
	)

	markdown, _ = parser.get_image_alt_text(paragraph)

	assert '![' not in markdown
	assert '[Image Description: Diagram of tax flow]' in markdown

	cache = parser.CURRENT_MEDIA_CONTEXT['cache']
	record = next(iter(cache.values()))
	assert record['renderable'] is False
	assert not record['public_url']
	assert 'Diagram of tax flow' in record['alt_texts']

	parser._clear_media_context()


def _configure_definitions(terms):
	parser.DEFINITION_VARIANT_MAP.clear()
	parser.DEFINITION_GREEDY_REGEX = None
	parser.DEFINITIONS_995_1.clear()
	for term in terms:
		parser.DEFINITIONS_995_1[term] = {}
	parser.build_definition_greedy_matcher()


def test_greedy_definition_matching_prefers_longest(definition_state_cleanup):
	_configure_definitions(['income tax', 'tax'])

	text = 'Income tax applies alongside fringe benefits legislation.'
	result = parser.find_defined_terms_in_text(text)

	assert 'income tax' in result
	assert 'tax' not in result


def test_greedy_definition_matching_handles_plurals_and_case(definition_state_cleanup):
	_configure_definitions(['tax offset'])

	text = 'Eligible Tax Offsets can reduce liability.'
	result = parser.find_defined_terms_in_text(text)

	assert result == {'tax offset'}


def test_greedy_definition_matching_ignores_markdown_links(definition_state_cleanup):
	_configure_definitions(['tax offset'])

	text = 'Refer to [tax offset](#link) and note that the tax offset applies.'
	result = parser.find_defined_terms_in_text(text)

	assert result == {'tax offset'}
