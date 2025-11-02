# Import necessary components from python-docx
try:
	from docx.document import Document as _Document
	from docx.oxml.table import CT_Tbl
	from docx.oxml.text.paragraph import CT_P
	from docx.table import _Cell, Table
	from docx.text.paragraph import Paragraph
except ImportError:
	print("Error: python-docx library not found. Please install it: pip install python-docx")
	# Define placeholders if docx is not available
	_Document = object
	CT_Tbl = object
	CT_P = object
	_Cell = object
	Table = object
	Paragraph = object


# =============================================================================
# DOCX Iteration and Formatting Helpers
# =============================================================================

def iter_block_items(parent):
	"""Yields consecutive block-level objects (paragraphs and tables)."""
	if isinstance(parent, _Document):
		parent_elm = parent.element.body
	elif isinstance(parent, _Cell):
		parent_elm = parent._tc
	else:
		return

	if parent_elm is None:
		return

	# Handle potential missing iterchildren method if docx import failed partially
	if not hasattr(parent_elm, 'iterchildren'):
		return

	for child in parent_elm.iterchildren():
		if isinstance(child, CT_P):
			yield Paragraph(child, parent)
		elif isinstance(child, CT_Tbl):
			yield Table(child, parent)


def get_indentation(paragraph):
	"""Calculates the indentation level (36pt standard)."""
	pf = paragraph.paragraph_format
	if not pf or not pf.left_indent:
		return ""
	try:
		if hasattr(pf.left_indent, 'pt') and pf.left_indent.pt > 0:
			level = int(round(pf.left_indent.pt / 36.0))
			return "    " * max(0, min(level, 8))
	except Exception:
		pass
	return ""


# =============================================================================
# Data Structure Finalization
# =============================================================================

def recursive_finalize_structure(structure):
	"""Recursively finalizes data structures (sorts references, sorts terms) after processing."""
	# This converts Sets (used during concurrent processing) to sorted Lists (for final JSON output).

	# Import tqdm only if needed for printing warnings, to avoid hard dependency in utils
	try:
		from tqdm import tqdm
		write_fn = tqdm.write
	except ImportError:
		write_fn = print

	if isinstance(structure, list):
		for item in structure:
			recursive_finalize_structure(item)
	elif isinstance(structure, dict):

		# 1. Finalize References (Set of Tuples -> List of Tuples)
		if "references" in structure and isinstance(structure["references"], set):
			# Sort by Normalized Reference (index 0)
			try:
				structure["references"] = sorted(
					list(structure["references"]),
					# Robust key handling
					key=lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) > 0 else str(x)
				)
			except TypeError as e:
				write_fn(
					f"Warning: Error sorting references for {structure.get('title', 'Unknown')}: {e}. Proceeding unsorted.")
				structure["references"] = list(structure["references"])

		# 2. Finalize Defined Terms (Set of Strings -> List of Strings)
		if "defined_terms_used" in structure and isinstance(structure["defined_terms_used"], set):
			# Sort the set
			structure["defined_terms_used"] = sorted(list(structure["defined_terms_used"]))

		if "children" in structure:
			recursive_finalize_structure(structure["children"])
