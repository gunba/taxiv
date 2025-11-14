import os
import re


class Config:
	ACT_ID = "ITAA1936"
	ACT_TITLE = "Income Tax Assessment Act 1936"

	try:
		INGEST_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
	except NameError:
		INGEST_ROOT = os.path.abspath(os.path.join(os.getcwd(), 'ingest'))

	RAW_INPUT_DIR = os.path.join(INGEST_ROOT, "data", ACT_ID.lower())
	INPUT_DATA_DIR = os.path.join(INGEST_ROOT, "output", "converted", ACT_ID.lower())
	OUTPUT_INTERMEDIATE_DIR = os.path.join(INGEST_ROOT, "output", "intermediate")
	OUTPUT_FINAL_DIR = os.path.join(INGEST_ROOT, "output", "final")
	CACHE_DIR = os.path.join(INGEST_ROOT, "cache")
	MEDIA_ROOT = os.path.join(INGEST_ROOT, "media")
	MEDIA_URL_BASE = "/media"
	MEDIA_ACT_ROOT = os.path.join(MEDIA_ROOT, ACT_ID.lower())

	for path in (
		RAW_INPUT_DIR,
		INPUT_DATA_DIR,
		OUTPUT_INTERMEDIATE_DIR,
		OUTPUT_FINAL_DIR,
		CACHE_DIR,
		MEDIA_ACT_ROOT,
	):
		os.makedirs(path, exist_ok=True)

	FILE_PATTERN = f"{ACT_ID}_VOL{{}}.docx"
	INTERMEDIATE_FILE_PATTERN = f"{ACT_ID}_VOL{{}}_intermediate.json"

	START_VOLUME = 1
	END_VOLUME = 7

	DEFINITIONS_VOLUME = 1
	DEFINITION_SECTION_LEVEL = 5
	DEFINITION_SECTION_PREFIXES = ["6", "Section 6"]
	DEFINITION_PROGRESS_LABEL = "Section 6"
	DEFINITION_ANCHOR_REF_ID = f"{ACT_ID}:Section:6"
	DEFINITIONS_INTERMEDIATE_FILENAME = "definitions_section6_intermediate.json"
	DEFINITION_SECTION_EXIT_STYLES = ["subsection"]
	DEFINITION_SECTION_EXIT_REQUIRES_CONTENT = True

	MAX_WORKERS = 10

	STYLE_MAP = {
		'ActHead 1': 1, 'ActHead 2': 2, 'ActHead 3': 3, 'ActHead 4': 4, 'ActHead 5': 5,
	}

	IGNORE_STYLES = ['Header', 'Footer', 'ShortT', 'LongT', 'CompiledActNo']
	IGNORE_STYLE_PATTERNS = ['toc ', 'TofSects(']

	TITLE_PATTERNS = {
		"Structure": re.compile(
			r'^(Chapter|Part|Division|Subdivision)\s+([0-9A-Z\-]+)(?:\s*(?:—|-|--)\s*(.*))?$',
			re.IGNORECASE,
		),
		"Section": re.compile(r'^([0-9\-A-Z]+)\s+(.*)$', re.IGNORECASE),
	}

	FALLBACK_ASTERISK_REGEX = re.compile(r'(?:^|[\s\(])\*(?P<term>[a-zA-Z0-9\s\-\(\)]+?)(?=[\s,.;:)]|$)')
