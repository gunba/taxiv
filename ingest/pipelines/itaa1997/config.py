import os
import re

# =============================================================================
# ITAA1997 SPECIFIC CONFIGURATION
# =============================================================================

ACT_ID = "ITAA1997"

# Define paths based on the standardized structure
# We determine the root 'ingest' directory dynamically.
try:
    INGEST_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
except NameError:
    # Fallback for environments where __file__ is not defined
    INGEST_ROOT = os.path.abspath(os.path.join(os.getcwd(), 'ingest'))


# Standardized input/output directories
INPUT_DIR = os.path.join(INGEST_ROOT, "data", ACT_ID.lower())
OUTPUT_DIR = os.path.join(INGEST_ROOT, "output", "intermediate")

# Ensure input and output directories exist (useful for first run)
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Input file pattern (e.g., C2025C00405VOL01.docx)
# This pattern is specific to the files provided for ITAA1997
INPUT_FILE_PATTERN = "C2025C00405VOL{}.docx"

# Output file patterns
OUTPUT_FILE_PATTERN = f"{ACT_ID}_VOL{{}}_gemini_concurrent.json"
DEFINITIONS_FILE_NAME = f"definitions_995_1_gemini_concurrent.json"

# Volume range to process (inclusive)
START_VOLUME = 1
END_VOLUME = 10

# Volume containing the primary definitions (Section 995-1)
DEFINITIONS_VOLUME = 10

# --- Concurrency Settings ---
MAX_WORKERS = 15

# --- Style Mappings for Hierarchy Detection ---
# These are specific to the formatting of the ITAA1997 DOCX files
STYLE_MAP = {
    'ActHead 1': 1, 'ActHead 2': 2, 'ActHead 3': 3, 'ActHead 4': 4, 'ActHead 5': 5,
}

# Styles or style patterns to completely ignore
IGNORE_STYLES = ['Header', 'Footer', 'ShortT', 'LongT', 'CompiledActNo']
IGNORE_STYLE_PATTERNS = ['toc ', 'TofSects(']

# Styles requiring special formatting in Markdown
FORMATTING_STYLES = {
    'SubsectionHead': 'emphasis', # *text*
    'note(': 'note',              # _text_ (prefix match)
    'Note(': 'note',              # _text_ (prefix match)
}

# --- Structural Identification Patterns (Regex) ---
# Used to parse the title text of a heading. (Using raw strings for regex definitions)
TITLE_PATTERNS = {
    "Structure": re.compile(r'^(Chapter|Part|Division|Subdivision)\s+([0-9A-Z\-]+)(?:\s*(?:—|-|--)\s*(.*))?$', re.IGNORECASE),
    "Section": re.compile(r'^([0-9\-A-Z]+)\s+(.*)$', re.IGNORECASE),
}

# Fallback regex for identifying asterisked definitions (used during Pass 1).
FALLBACK_ASTERISK_REGEX = re.compile(r'(?:^|[\s\(])\*(?P<term>[a-zA-Z0-9\s\-\(\)]+?)(?=[\s,.;:)]|$)')
