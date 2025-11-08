# ingest/pipelines/itaa1997/parser.py
import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, Optional, Pattern, List, Tuple, Set

import docx
from PIL import Image, UnidentifiedImageError

# We use tqdm for progress bars during parsing
try:
	from tqdm import tqdm
except ImportError:
	# Fallback if tqdm is not installed
	def tqdm(iterable=None, **kwargs):
		return iterable if iterable is not None else []


	tqdm.write = print

# Standard imports assuming 'ingest' is in the PYTHONPATH (e.g., inside Docker)
from .config import Config
from ingest.core.utils import iter_block_items, get_indentation
# Import LLM tools needed for the finalization callback
# We import these here to ensure they are available when finalize_section is called
# MODIFICATION: Import the module itself
from ingest.core import llm_extraction

# Import pipeline-specific configuration (using relative import)
# We import the config values directly rather than the module object for clarity
config = Config()

# =============================================================================
# Media Handling Helpers
# =============================================================================

CURRENT_MEDIA_CONTEXT: Dict[str, Any] = {}

_RENDERABLE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _convert_blob_to_png(blob: bytes) -> Optional[bytes]:
	try:
		with Image.open(BytesIO(blob)) as image:
			mode = image.mode or ""
			if mode not in ("RGB", "RGBA"):
				if "A" in mode or mode in ("P", "LA"):
					image = image.convert("RGBA")
				else:
					image = image.convert("RGB")
			buffer = BytesIO()
			image.save(buffer, format="PNG")
			return buffer.getvalue()
	except (UnidentifiedImageError, OSError, ValueError) as exc:
		print(f"Warning: Unable to convert image to PNG ({exc}). Storing original bytes.")
	return None


def _record_media_alt_text(digest: str, alt_text: str) -> None:
	if not alt_text or not CURRENT_MEDIA_CONTEXT:
		return
	cache: Dict[str, Any] = CURRENT_MEDIA_CONTEXT.get("cache", {})
	entry = cache.get(digest)
	if not entry:
		return
	alt_texts = entry.setdefault("alt_texts", set())
	alt_texts.add(alt_text)


def _sanitize_media_segment(value: str) -> str:
	value = (value or "").strip()
	sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
	return sanitized or "document"


def _initialize_media_context(filepath: str) -> None:
	global CURRENT_MEDIA_CONTEXT
	doc_basename = _sanitize_media_segment(os.path.splitext(os.path.basename(filepath))[0])
	act_segment = _sanitize_media_segment(config.ACT_ID.lower())
	relative_dir = os.path.join(act_segment, doc_basename)
	absolute_dir = os.path.join(config.MEDIA_ROOT, relative_dir)
	os.makedirs(absolute_dir, exist_ok=True)
	CURRENT_MEDIA_CONTEXT = {
		"relative_dir": relative_dir,
		"absolute_dir": absolute_dir,
		"cache": {},
	}


def _clear_media_context() -> None:
	global CURRENT_MEDIA_CONTEXT
	CURRENT_MEDIA_CONTEXT = {}


def _build_media_url(relative_path: str) -> str:
	base = config.MEDIA_URL_BASE.rstrip('/')
	if not base:
		base = "/media"
	if not base.startswith('/'):
		base = f"/{base}"
	normalized_path = relative_path.replace(os.sep, '/')
	if normalized_path:
		return f"{base}/{normalized_path}"
	return base


def _persist_image_blob(blob: bytes, partname: str, content_type: str) -> Optional[Dict[str, Any]]:
	if not CURRENT_MEDIA_CONTEXT:
		return None
	cache: Dict[str, Any] = CURRENT_MEDIA_CONTEXT.setdefault("cache", {})
	original_extension = os.path.splitext(partname)[1].lower()
	if not original_extension and content_type:
		subtype = content_type.split('/')[-1].lower()
		if subtype:
			original_extension = f".{subtype}"
	converted_blob = _convert_blob_to_png(blob)
	stored_blob = converted_blob if converted_blob is not None else blob
	stored_extension = ".png" if converted_blob is not None else (original_extension or ".bin")
	digest = hashlib.sha1(stored_blob).hexdigest()
	if digest in cache:
		return cache[digest]
	filename = f"{digest[:16]}{stored_extension}"
	relative_path = os.path.join(CURRENT_MEDIA_CONTEXT["relative_dir"], filename)
	absolute_path = os.path.join(config.MEDIA_ROOT, relative_path)
	os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
	if not os.path.exists(absolute_path):
		with open(absolute_path, "wb") as media_file:
			media_file.write(stored_blob)
	renderable = converted_blob is not None or stored_extension.lower() in _RENDERABLE_EXTENSIONS
	public_url = _build_media_url(relative_path) if renderable else None
	record: Dict[str, Any] = {
		"digest": digest,
		"public_url": public_url,
		"relative_path": relative_path,
		"absolute_path": absolute_path,
		"stored_extension": stored_extension,
		"source_extension": original_extension or stored_extension,
		"converted_to_png": converted_blob is not None,
		"renderable": renderable,
		"alt_texts": set(),
	}
	cache[digest] = record
	return record


# Import docx components
try:
	from docx.document import Document as _Document
	from docx.oxml.ns import qn
	from docx.oxml.table import CT_Tbl
	from docx.oxml.text.paragraph import CT_P
	from docx.table import _Cell, Table
	from docx.text.paragraph import Paragraph
except ImportError:
	print("Error: python-docx library not found. Please install it: pip install python-docx")
	_Document = object;
	Table = object;
	Paragraph = object;
	_Cell = object;
	CT_P = object;
	CT_Tbl = object


	def qn(value):
		return value

# =============================================================================
# Global State for Definitions (Managed during the parsing process)
# =============================================================================

# This state is specific to the execution of this pipeline run.
DEFINITIONS_995_1: Dict[str, Dict] = {}
DEFINITION_MARKER_REGEX: Optional[Pattern] = None
DEFINITION_VARIANT_MAP: Dict[str, str] = {}
DEFINITION_GREEDY_REGEX: Optional[Pattern] = None
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\([^\)]+\)")

# =============================================================================
# List Handling Helpers
# =============================================================================

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


@dataclass
class ListInfo:
	num_id: str
	level: int
	ordered: bool


class ListStateTracker:
	def __init__(self):
		self._stack: List[ListInfo] = []

	def start_item(self, info: ListInfo, has_prior_content: bool) -> Tuple[str, str]:
		leading = ""
		changed = False
		popped_same_list = False
		was_empty = not self._stack
		while self._stack and (
				self._stack[-1].level > info.level
				or (self._stack[-1].level == info.level and self._stack[-1].num_id != info.num_id)
		):
			popped = self._stack.pop()
			changed = True
			if popped.num_id == info.num_id and popped.ordered == info.ordered:
				popped_same_list = True
		if not self._stack or self._stack[-1].level < info.level:
			self._stack.append(ListInfo(info.num_id, info.level, info.ordered))
			changed = True
		else:
			top = self._stack[-1]
			if top.num_id != info.num_id or top.ordered != info.ordered:
				self._stack[-1] = ListInfo(info.num_id, info.level, info.ordered)
				changed = True
		if (
				changed
				and has_prior_content
				and len(self._stack) == 1
				and not popped_same_list
				and not was_empty
		):
			leading = "\n"
		prefix = "    " * info.level + ("1. " if info.ordered else "- ")
		return leading, prefix

	def close_lists(self, has_prior_content: bool) -> str:
		if self._stack:
			self._stack.clear()
			return "\n" if has_prior_content else ""
		return ""


def _resolve_numbering_format(paragraph, num_id: str, level: int) -> Optional[str]:
	numbering_part = getattr(paragraph.part, 'numbering_part', None)
	if numbering_part is None:
		return None
	numbering_element = getattr(numbering_part, 'element', None)
	if numbering_element is None:
		return None
	try:
		abstract_refs = numbering_element.xpath(
			f"./w:num[@w:numId='{num_id}']/w:abstractNumId",
			namespaces={'w': W_NS}
		)
		if not abstract_refs:
			return None
		abstract_num_id = abstract_refs[0].get(f'{{{W_NS}}}val')
		if abstract_num_id is None:
			return None
		lvl_nodes = numbering_element.xpath(
			f"./w:abstractNum[@w:abstractNumId='{abstract_num_id}']/w:lvl[@w:ilvl='{level}']/w:numFmt",
			namespaces={'w': W_NS}
		)
		if not lvl_nodes:
			return None
		return lvl_nodes[0].get(f'{{{W_NS}}}val')
	except Exception:
		return None


def _is_ordered_list(paragraph, num_id: str, level: int) -> bool:
	num_format = _resolve_numbering_format(paragraph, num_id, level)
	if not num_format:
		return True
	num_format = str(num_format).lower()
	return num_format not in {'bullet', 'none'}


def get_paragraph_list_info(paragraph) -> Optional[ListInfo]:
	if not hasattr(paragraph, '_p') or paragraph._p is None:
		return None
	p_props = getattr(paragraph._p, 'pPr', None)
	if p_props is None:
		return None
	num_pr = getattr(p_props, 'numPr', None)
	if num_pr is None:
		return None
	try:
		num_id = getattr(num_pr, 'numId', None)
		ilvl = getattr(num_pr, 'ilvl', None)
		num_val = num_id.val if num_id is not None else None
		level_val = int(ilvl.val) if ilvl is not None and ilvl.val is not None else 0
	except AttributeError:
		return None
	if num_val is None:
		return None
	ordered = _is_ordered_list(paragraph, str(num_val), level_val)
	return ListInfo(str(num_val), level_val, ordered)


def format_paragraph_markdown(paragraph, text: str, list_tracker: ListStateTracker,
							  has_prior_content: bool, indentation: str) -> str:
	list_info = get_paragraph_list_info(paragraph)
	if list_info:
		leading, prefix = list_tracker.start_item(list_info, has_prior_content)
		return f"{leading}{prefix}{text}\n"
	leading = list_tracker.close_lists(has_prior_content)
	return f"{leading}{indentation}{text}\n\n"


# =============================================================================
# Parsing Helper Functions (Specific to ITAA1997 structure/formatting)
# =============================================================================

def should_ignore_style(style_name):
	"""Checks if a style should be ignored based on config."""
	if style_name in config.IGNORE_STYLES: return True
	for pattern in config.IGNORE_STYLE_PATTERNS:
		if style_name.startswith(pattern): return True
	return False


def identify_defined_terms(text: str) -> Set[str]:
	"""Identifies asterisked definitions using the appropriate pattern (Compiled or Fallback)."""
	# Use the precise regex if available (Pass 2), otherwise use the fallback (Pass 1).
	regex_to_use = DEFINITION_MARKER_REGEX if DEFINITION_MARKER_REGEX else config.FALLBACK_ASTERISK_REGEX

	found_terms = set()
	# Ensure text is a string
	text = str(text)
	for match in regex_to_use.finditer(text):
		try:
			term = match.group('term').strip()
			if term:
				found_terms.add(term)
		except IndexError:
			continue
	return found_terms


def compile_definition_regex():
	"""Compiles the DEFINITION_MARKER_REGEX after Pass 1."""
	global DEFINITION_MARKER_REGEX
	print("\nCompiling precise definition pattern for Pass 2...")

	if not DEFINITIONS_995_1:
		print("Warning: No definitions found. Proceeding with fallback pattern.")
		DEFINITION_VARIANT_MAP.clear()
		DEFINITION_GREEDY_REGEX = None
		return

	sorted_terms = sorted(DEFINITIONS_995_1.keys(), key=len, reverse=True)
	escaped_terms = [re.escape(term) for term in sorted_terms]
	alternation_group = "|".join(escaped_terms)

	# Ensure the pattern matches the structure used in the config regex (raw string)
	pattern = r'(?:^|[\s\(])\*(?P<term>' + alternation_group + r')(?=[\s,.;:)]|$)'

	try:
		DEFINITION_MARKER_REGEX = re.compile(pattern, re.IGNORECASE)
		print(f"Pattern compiled successfully with {len(sorted_terms)} terms.")
	except re.error as e:
		print(f"Error compiling definition regex: {str(e)}. Falling back to generic pattern.")

	build_definition_greedy_matcher(sorted_terms)


def _generate_plural_variants(term: str) -> Set[str]:
	"""Generate plural variants for the final word in a term."""
	stripped = term.strip()
	if not stripped:
		return set()

	match = re.search(r'([A-Za-z]+)([^A-Za-z]*)$', stripped)
	if not match:
		return set()

	last_word = match.group(1)
	trailing = match.group(2)
	prefix = stripped[:match.start(1)]

	lower_last = last_word.lower()
	plural_forms = set()

	if not last_word:
		return set()

	if lower_last.endswith('s'):
		# Already plural-like; avoid producing awkward duplicates.
		return set()

	if re.search(r'(s|x|z|ch|sh)$', lower_last):
		plural_forms.add(last_word + 'es')
	elif re.search(r'[bcdfghjklmnpqrstvwxyz]y$', lower_last):
		plural_forms.add(last_word[:-1] + 'ies')
	elif lower_last.endswith('fe'):
		plural_forms.add(last_word[:-2] + 'ves')
	elif lower_last.endswith('f') and len(last_word) > 1:
		plural_forms.add(last_word[:-1] + 'ves')
	else:
		plural_forms.add(last_word + 's')

	variants = set()
	for plural_word in plural_forms:
		variants.add(prefix + plural_word + trailing)
	return variants


def _generate_definition_variants(term: str) -> List[str]:
	"""Return ordered variants (base + plural) for a definition term."""
	base = term.strip()
	variants: List[str] = []
	seen: Set[str] = set()

	for candidate in [base, *sorted(_generate_plural_variants(base), key=len, reverse=True)]:
		normalized = candidate.strip()
		if not normalized:
			continue
		lowered = normalized.lower()
		if lowered in seen:
			continue
		seen.add(lowered)
		variants.append(normalized)

	return variants


def build_definition_greedy_matcher(sorted_terms: Optional[List[str]] = None) -> None:
	"""Compile a greedy regex and variant map for definition matching."""
	global DEFINITION_VARIANT_MAP, DEFINITION_GREEDY_REGEX

	if sorted_terms is None:
		sorted_terms = sorted(DEFINITIONS_995_1.keys(), key=len, reverse=True)

	DEFINITION_VARIANT_MAP = {}
	pattern_parts: List[str] = []

	for term in sorted_terms:
		for variant in _generate_definition_variants(term):
			lowered = variant.lower()
			if lowered in DEFINITION_VARIANT_MAP:
				continue
			DEFINITION_VARIANT_MAP[lowered] = term
			pattern_parts.append(re.escape(variant))

	if not pattern_parts:
		DEFINITION_GREEDY_REGEX = None
		return

	alternation_group = "|".join(pattern_parts)
	boundary_pattern = r'(?<![A-Za-z0-9])(' + alternation_group + r')(?![A-Za-z0-9])'

	try:
		DEFINITION_GREEDY_REGEX = re.compile(boundary_pattern, re.IGNORECASE)
	except re.error as exc:
		print(f"Error compiling greedy definition regex: {exc}")
		DEFINITION_GREEDY_REGEX = None


def find_defined_terms_in_text(text: str) -> Set[str]:
	"""Return canonical definition terms found in content outside markdown links."""
	if not text or not DEFINITION_GREEDY_REGEX or not DEFINITION_VARIANT_MAP:
		return set()

	segments: List[str] = []
	last_end = 0
	for match in MARKDOWN_LINK_PATTERN.finditer(text):
		if match.start() > last_end:
			segments.append(text[last_end:match.start()])
		last_end = match.end()
	if last_end < len(text):
		segments.append(text[last_end:])

	found: Set[str] = set()
	for segment in segments:
		for match in DEFINITION_GREEDY_REGEX.finditer(segment):
			variant_text = match.group(1).strip().lower()
			canonical = DEFINITION_VARIANT_MAP.get(variant_text)
			if canonical:
				found.add(canonical)
	return found


# =============================================================================
# Content Processing (Text, Tables, Images)
# =============================================================================

def get_image_alt_text(paragraph) -> Tuple[str, Set[str]]:
	alt_texts_md: List[str] = []
	all_defined_terms: Set[str] = set()
	W_URI = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
	WP_URI = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
	A_URI = 'http://schemas.openxmlformats.org/drawingml/2006/main'
	R_EMBED = qn('r:embed')
	R_LINK = qn('r:link')
	drawing_qname = f'{{{W_URI}}}drawing'
	docPr_qname = f'{{{WP_URI}}}docPr'
	blip_qname = f'{{{A_URI}}}blip'

	if not hasattr(paragraph, '_element') or paragraph._element is None:
		return "", set()

	related_parts = getattr(getattr(paragraph, 'part', None), 'related_parts', {})

	for drawing in paragraph._element.iter(drawing_qname):
		alt_text = ""
		for docPr in drawing.iter(docPr_qname):
			alt_text = (docPr.get('descr') or docPr.get('title') or "").strip()
			if alt_text:
				break

		for blip in drawing.iter(blip_qname):
			relationship_id = blip.get(R_EMBED) or blip.get(R_LINK)
			if not relationship_id:
				continue
			image_part = related_parts.get(relationship_id) if related_parts else None
			if image_part is None:
				continue
			blob = getattr(image_part, 'blob', None)
			if blob is None:
				continue
			content_type = getattr(image_part, 'content_type', '')
			partname = getattr(image_part, 'partname', '')
			record = _persist_image_blob(blob, partname, content_type)
			if not record:
				continue
			digest = record.get("digest", "")
			if alt_text:
				_record_media_alt_text(digest, alt_text)
			public_url = record.get("public_url") if record.get("renderable") else None
			if public_url:
				alt_for_md = alt_text or "Embedded image"
				text_to_add = f"\n![{alt_for_md}]({public_url})\n\n"
			elif alt_text:
				text_to_add = f"\n[Image Description: {alt_text}]\n\n"
			else:
				continue

			if text_to_add not in alt_texts_md:
				alt_texts_md.append(text_to_add)

			if alt_text:
				terms = identify_defined_terms(alt_text)
				all_defined_terms.update(terms)

	return "".join(alt_texts_md), all_defined_terms


def process_table(table) -> Tuple[str, Set[str]]:
	table_md = "\n"
	all_defined_terms = set()
	try:
		rows_data = []
		max_cols = 0

		# Handle potential missing rows attribute
		if not hasattr(table, 'rows'):
			return "\n[Table structure unreadable]\n\n", set()

		for row in table.rows:
			if len(row.cells) > max_cols:
				max_cols = len(row.cells)
		if max_cols == 0: return "", set()

		for row in table.rows:
			row_data = []
			for cell in row.cells:
				# Clean cell text and normalize whitespace
				cell_text = cell.text.strip().replace('\n', ' ').replace('\u00A0', ' ')
				terms = identify_defined_terms(cell_text)
				all_defined_terms.update(terms)
				row_data.append(cell_text)

			while len(row_data) < max_cols:
				row_data.append("")
			if any(row_data):
				rows_data.append(row_data)

		if not rows_data: return "", set()

		for i, row_data in enumerate(rows_data):
			table_md += "| " + " | ".join(row_data) + " |\n"
			if i == 0:
				table_md += "|---" * len(row_data) + "|\n"

	except Exception as e:
		print(f"Warning: Error processing a table: {str(e)}")
		return "\n[Error processing table. Refer to original document.]\n\n", all_defined_terms

	return table_md + "\n", all_defined_terms


# =============================================================================
# Definition Extraction Logic (Specific to Section 995-1 formatting)
# =============================================================================

def identify_definition_start(paragraph):
	term = ""
	if not paragraph.text.strip(): return None

	# Handle potential missing runs attribute
	if not hasattr(paragraph, 'runs'):
		return None

	for run in paragraph.runs:
		if not term.strip() and not run.text.strip(): continue
		if run.bold and run.italic:
			term += run.text
		else:
			return term.strip() if term.strip() else None
	return term.strip() if term.strip() else None


def process_definition_content(block, list_tracker: Optional[ListStateTracker] = None,
							   existing_content: str = "") -> Tuple[str, Set[str]]:
	content_md = ""
	defined_terms = set()
	tracker = list_tracker or ListStateTracker()
	prior_content = bool(existing_content)

	if isinstance(block, Paragraph):
		text = block.text.strip().replace('\u00A0', ' ')

		img_md, img_terms = get_image_alt_text(block)
		if img_md:
			defined_terms.update(img_terms)
			content_md += tracker.close_lists(prior_content)
			content_md += img_md
			prior_content = True

		if text:
			indentation = get_indentation(block)
			terms = identify_defined_terms(text)
			defined_terms.update(terms)
			content_md += format_paragraph_markdown(
				block, text, tracker, prior_content, indentation
			)

		return content_md, defined_terms

	elif isinstance(block, Table):
		content_md += tracker.close_lists(prior_content)
		table_md, table_terms = process_table(block)
		content_md += table_md
		defined_terms.update(table_terms)
		return content_md, defined_terms

	return "", set()


def clean_definition_start(paragraph, term, list_tracker: Optional[ListStateTracker] = None,
						   existing_content: str = "") -> Tuple[str, Set[str]]:
	text = paragraph.text.strip().replace('\u00A0', ' ')
	try:
		pattern = re.compile(r'^' + re.escape(term), re.IGNORECASE)
		text = pattern.sub('', text, count=1).strip()
	except re.error:
		return process_definition_content(paragraph, list_tracker, existing_content)

	if text.startswith((':', '—', '-')):
		text = text[1:].strip()

	if text.lower().startswith('means:'):
		text = text[len('means:'):].strip()

	tracker = list_tracker or ListStateTracker()
	prior_content = bool(existing_content)
	content_md = ""
	defined_terms = set()

	img_md, img_terms = get_image_alt_text(paragraph)
	if img_md:
		content_md += tracker.close_lists(prior_content)
		content_md += img_md
		defined_terms.update(img_terms)
		prior_content = True

	if text:
		indentation = get_indentation(paragraph)
		terms = identify_defined_terms(text)
		defined_terms.update(terms)
		content_md += format_paragraph_markdown(
			paragraph, text, tracker, prior_content, indentation
		)

	return content_md, defined_terms


# =============================================================================
# Structural Identification (Semantic Labeling)
# =============================================================================

def parse_title(title, level):
	"""Parses the title string using patterns defined in config.py."""
	parsed_data = {
		"type": f"Level{level}Element",
		"id": None,
		"name": title,
		"ref_id": None
	}

	if title.lower().startswith("guide to"):
		parsed_data["type"] = "Guide"
		return parsed_data
	if title.lower().startswith("operative provision"):
		parsed_data["type"] = "OperativeProvision"
		return parsed_data

	if level == 5:
		match = config.TITLE_PATTERNS["Section"].match(title)
		if match:
			parsed_data["type"] = "Section"
			parsed_data["id"] = match.group(1).strip()
			parsed_data["name"] = match.group(2).strip()

	if parsed_data["type"] == f"Level{level}Element":
		match = config.TITLE_PATTERNS["Structure"].match(title)
		if match:
			parsed_data["type"] = match.group(1).capitalize()
			parsed_data["id"] = match.group(2).strip()
			if match.group(3):
				parsed_data["name"] = match.group(3).strip()
			else:
				parsed_data["name"] = ""

	# Generate standardized ref_id: ACT:Element:Identifier
	if parsed_data["id"]:
		ref_type = parsed_data["type"]
		parsed_data["ref_id"] = f"{config.ACT_ID}:{ref_type}:{parsed_data['id']}"

	return parsed_data


# =============================================================================
# Finalization Callback (Integration Point for LLM)
# =============================================================================

def finalize_section(section: Dict, hierarchy_context: List[str], executor: Optional[ThreadPoolExecutor] = None,
					 futures: Optional[List] = None):
	"""
	Processes the aggregated content of a section. Submits LLM processing to the thread pool.
	(This function is called by process_document when a section is complete)
	"""
	if isinstance(section, dict):
		# Clean the markdown content first
		section["content_md"] = section["content_md"].strip()

		if section["content_md"]:
			greedy_terms = find_defined_terms_in_text(section["content_md"])
			existing_terms = section.get("defined_terms_used")
			if isinstance(existing_terms, set):
				existing_terms.update(greedy_terms)
			elif isinstance(existing_terms, list):
				section["defined_terms_used"] = set(existing_terms).union(greedy_terms)
			else:
				section["defined_terms_used"] = set(greedy_terms)

		# If an executor is provided and LLM is active, submit the task concurrently
		# MODIFICATION: Access LLM_CLIENT via its module
		if executor and futures is not None and llm_extraction.LLM_CLIENT and section["content_md"]:
			# Submit the task to the thread pool
			future = executor.submit(
				llm_extraction.process_section_llm_task,  # Use the module path for the task
				section,
				hierarchy_context
			)
			futures.append(future)


# =============================================================================
# Main Document Processing Loop
# =============================================================================

def process_document(filepath, pass_num=1, executor: Optional[ThreadPoolExecutor] = None,
					 futures: Optional[List] = None):
	"""
	Processes a single .docx file.
	(Adapted signature to accept executor and futures for concurrent processing)
	"""
	try:
		doc = docx.Document(filepath)
	except Exception as e:
		print(f"Error opening document {filepath}: {str(e)}")
		return []

	_initialize_media_context(filepath)

	try:
		# Setup for hierarchy tracking
		structure = []
		hierarchy_stack = [structure]  # Stack starts with the root list
		current_section = None

		# Setup for definition tracking
		in_definitions_section = False
		current_definition_term = None
		definition_list_trackers: Dict[str, ListStateTracker] = {}
		current_list_tracker: Optional[ListStateTracker] = None

		# Progress bar setup
		try:
			# Estimate total blocks based on body children
			total_blocks = len(doc.element.body.getchildren())
		except Exception:
			total_blocks = None

		block_iterator = iter_block_items(doc)

		progress_bar_doc = tqdm(
			block_iterator, total=total_blocks,
			desc=f"  Parsing {os.path.basename(filepath)} (Pass {pass_num})",
			unit="block", leave=False, ncols=100, position=2
		)

		# Main processing loop
		for block in progress_bar_doc:

			is_paragraph = isinstance(block, Paragraph)
			is_table = isinstance(block, Table)
			style_name = None
			text = ""

			# Extract basic info from paragraphs
			if is_paragraph:
				if block.style and hasattr(block.style, 'name'):
					style_name = block.style.name
					if should_ignore_style(style_name):
						continue
				# Clean text and normalize whitespace
				text = block.text.strip().replace('\u00A0', ' ')

			# 1. Handle Headings (Hierarchy Management)
			if is_paragraph and style_name in config.STYLE_MAP:
				level = config.STYLE_MAP[style_name]
				if not text: continue

				# Parse title data (only in Pass 2)
				title_data = {"name": text}
				if pass_num == 2:
					title_data = parse_title(text, level)

				# Initialize new section structure (using sets for accumulation)
				new_section = {
					"level": level, "title": text,
					"type": title_data.get("type"), "id": title_data.get("id"),
					"name": title_data.get("name"), "ref_id": title_data.get("ref_id"),
					"content_md": "", "references": set(), "defined_terms_used": set(),
					"children": []
				}

				# Manage hierarchy stack: pop until the correct parent level is reached
				while len(hierarchy_stack) > level:
					popped_section = hierarchy_stack.pop()
					# CRITICAL CHANGE: Call finalize_section with executor and futures
					if pass_num == 2:
						# Generate hierarchy context (list of parent ref_ids)
						hierarchy_context = [item.get("ref_id") for item in hierarchy_stack[1:] if
											 isinstance(item, dict) and item.get("ref_id")]
						# Pass the executor and futures list to the finalizer
						finalize_section(popped_section, hierarchy_context, executor, futures)

				# Add the new section to the hierarchy
				if pass_num == 2:
					parent_container = hierarchy_stack[-1]
					if isinstance(parent_container, list):
						parent_container.append(new_section)
					elif isinstance(parent_container, dict) and "children" in parent_container:
						parent_container["children"].append(new_section)

					hierarchy_stack.append(new_section)
					current_section = new_section
					current_list_tracker = ListStateTracker()
				else:
					# In Pass 1, we just need a flag that we are inside a section
					current_section = True

				# --- Definition section tracking (Pass 1 specific logic) ---
				# Check if entering or exiting the definitions section (Section 995-1)
				if level == 5 and (text.startswith("995-1") or text.startswith("995 1")):
					in_definitions_section = True
					current_definition_term = None
					if pass_num == 1:
						progress_bar_doc.set_description(f"  Extracting Definitions (995-1)...", refresh=True)
				elif level < 5 and in_definitions_section:
					# If a higher-level heading appears, we have left the definitions section
					in_definitions_section = False
					current_definition_term = None
					if pass_num == 1:
						# Reset progress bar description
						progress_bar_doc.set_description(f"  Parsing {os.path.basename(filepath)} (Pass {pass_num})",
														 refresh=True)

				continue  # Proceed to the next block after handling a heading

			# 2. Handle Content
			if current_section:

				# --- Definition Extraction Logic (Pass 1) ---
				if pass_num == 1 and in_definitions_section:
					new_term = None
					if is_paragraph:
						new_term = identify_definition_start(block)

					if new_term:
						# Start a new definition
						current_definition_term = new_term
						if current_definition_term not in DEFINITIONS_995_1:
							DEFINITIONS_995_1[current_definition_term] = {
								"content_md": "", "references": set(), "defined_terms_used": set()
							}
						definition_tracker = definition_list_trackers.get(current_definition_term)
						if definition_tracker is None:
							definition_tracker = ListStateTracker()
							definition_list_trackers[current_definition_term] = definition_tracker
						existing_content = DEFINITIONS_995_1[current_definition_term]["content_md"]
						# Process the starting line of the definition
						content, terms = clean_definition_start(
							block, new_term, definition_tracker, existing_content
						)
						DEFINITIONS_995_1[current_definition_term]["content_md"] += content
						DEFINITIONS_995_1[current_definition_term]["defined_terms_used"].update(terms)

					elif current_definition_term:
						# Continue processing subsequent blocks of the current definition
						definition_tracker = definition_list_trackers.setdefault(
							current_definition_term, ListStateTracker()
						)
						existing_content = DEFINITIONS_995_1[current_definition_term]["content_md"]
						content, terms = process_definition_content(
							block, definition_tracker, existing_content
						)
						if current_definition_term in DEFINITIONS_995_1:
							DEFINITIONS_995_1[current_definition_term]["content_md"] += content
							DEFINITIONS_995_1[current_definition_term]["defined_terms_used"].update(terms)

			# --- Standard Content Processing (Pass 2) ---
			if pass_num == 2 and current_section:
				if is_paragraph:
					if current_list_tracker is None:
						current_list_tracker = ListStateTracker()
					alt_text_md, alt_terms = get_image_alt_text(block)
					if alt_text_md:
						current_section["content_md"] += current_list_tracker.close_lists(
							bool(current_section["content_md"])
						)
						current_section["content_md"] += alt_text_md
						current_section["defined_terms_used"].update(alt_terms)

					if text:
						indentation = get_indentation(block)
						# Identify terms (using precise regex in Pass 2)
						terms = identify_defined_terms(text)
						current_section["defined_terms_used"].update(terms)

						processed_text = text

						# Apply formatting based on known styles (Simplified logic matching original script intent)
						if style_name == 'SubsectionHead':
							processed_text = f"*{processed_text}*"
						elif (style_name and (style_name.startswith('note(') or style_name.startswith('Note('))):
							processed_text = f"_{processed_text}_"

						# Append content to the current section with list handling
						current_section["content_md"] += format_paragraph_markdown(
							block,
							processed_text,
							current_list_tracker,
							bool(current_section["content_md"]),
							indentation
						)

				elif is_table:
					# Handle tables
					if current_list_tracker is not None:
						current_section["content_md"] += current_list_tracker.close_lists(
							bool(current_section["content_md"])
						)
					table_md, table_terms = process_table(block)
					current_section["content_md"] += table_md
					current_section["defined_terms_used"].update(table_terms)

		# Close the progress bar for this document
		progress_bar_doc.close()

		# Finalize remaining sections on the stack after the document ends
		if pass_num == 2:
			while len(hierarchy_stack) > 1:
				popped_section = hierarchy_stack.pop()
				hierarchy_context = [item.get("ref_id") for item in hierarchy_stack[1:] if
									 isinstance(item, dict) and item.get("ref_id")]
				# Pass the executor and futures list to the finalizer
				finalize_section(popped_section, hierarchy_context, executor, futures)

		return structure
	finally:
		_clear_media_context()
