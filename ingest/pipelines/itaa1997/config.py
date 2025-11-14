import os
import re


class Config:
	# =============================================================================
	# ITAA1997 SPECIFIC CONFIGURATION
	# =============================================================================

	ACT_ID = "ITAA1997"
	ACT_TITLE = "Income Tax Assessment Act 1997"

	# Define paths based on the standardized structure
	try:
		INGEST_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
	except NameError:
		INGEST_ROOT = os.path.abspath(os.path.join(os.getcwd(), 'ingest'))

	# Standardized input/output directories
	INPUT_DATA_DIR = os.path.join(INGEST_ROOT, "data", ACT_ID.lower())
	OUTPUT_INTERMEDIATE_DIR = os.path.join(INGEST_ROOT, "output", "intermediate")
	OUTPUT_FINAL_DIR = os.path.join(INGEST_ROOT, "output", "final")
	CACHE_DIR = os.path.join(INGEST_ROOT, "cache")
	MEDIA_ROOT = os.path.join(INGEST_ROOT, "media")
	MEDIA_URL_BASE = "/media"
	MEDIA_ACT_ROOT = os.path.join(MEDIA_ROOT, ACT_ID.lower())

	# Ensure directories exist
	os.makedirs(INPUT_DATA_DIR, exist_ok=True)
	os.makedirs(OUTPUT_INTERMEDIATE_DIR, exist_ok=True)
	os.makedirs(OUTPUT_FINAL_DIR, exist_ok=True)
	os.makedirs(CACHE_DIR, exist_ok=True)
	os.makedirs(MEDIA_ACT_ROOT, exist_ok=True)

	# Input file pattern
	FILE_PATTERN = "C2025C00405VOL{}.docx"
	INTERMEDIATE_FILE_PATTERN = f"{ACT_ID}_VOL{{}}_intermediate.json"

	# Volume range to process
	START_VOLUME = 1
	END_VOLUME = 10

	# Definitions volume
	DEFINITIONS_VOLUME = 10
	DEFINITION_SECTION_LEVEL = 5
	DEFINITION_SECTION_PREFIXES = ["995-1", "995 1"]
	DEFINITION_PROGRESS_LABEL = "Section 995-1"
	DEFINITION_ANCHOR_REF_ID = f"{ACT_ID}:Section:995-1"
	DEFINITIONS_INTERMEDIATE_FILENAME = "definitions_995_1_intermediate.json"

	# Concurrency
	MAX_WORKERS = 15

	# Style mappings
	STYLE_MAP = {
		'ActHead 1': 1, 'ActHead 2': 2, 'ActHead 3': 3, 'ActHead 4': 4, 'ActHead 5': 5,
	}

	IGNORE_STYLES = ['Header', 'Footer', 'ShortT', 'LongT', 'CompiledActNo']
	IGNORE_STYLE_PATTERNS = ['toc ', 'TofSects(']

	# Regex patterns
	TITLE_PATTERNS = {
		"Structure": re.compile(r'^(Chapter|Part|Division|Subdivision)\s+([0-9A-Z\-]+)(?:\s*(?:—|-|--)\s*(.*))?$',
								re.IGNORECASE),
		"Section": re.compile(r'^([0-9\-A-Z]+)\s+(.*)$', re.IGNORECASE),
	}

	FALLBACK_ASTERISK_REGEX = re.compile(r'(?:^|[\s\(])\*(?P<term>[a-zA-Z0-9\s\-\(\)]+?)(?=[\s,.;:)]|$)')
