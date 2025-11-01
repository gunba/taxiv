import os
import re
import json
import docx
import threading
import csv
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# Removed ollama, added google.generativeai
try:
    # We use the standard SDK import pattern
    import google.generativeai as genai
    from google.generativeai import types
except ImportError:
    print("Warning: google-generativeai library not found. Please install it: pip install google-generativeai")
    genai = None
    types = None

# Check if python-docx is installed and import necessary components
try:
    from docx.document import Document as _Document
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import _Cell, Table
    from docx.text.paragraph import Paragraph
except ImportError:
    print("Error: python-docx library not found. It is required for processing. Please install it: pip install python-docx")
    # Define placeholders if docx is not available to allow script initialization (e.g., for configuration checks)
    _Document = object
    CT_Tbl = object
    CT_P = object
    _Cell = object
    Table = object
    Paragraph = object


# Updated typing imports
from typing import Dict, Optional, Pattern, List, Tuple, Set
from tqdm import tqdm

# =============================================================================
# CONFIGURATION
# =============================================================================

# NOTE: Update BASE_DIR if necessary
BASE_DIR = r"C:\Users\jorda\PycharmProjects\taxmcp"
# Fallback for different environments
if not os.path.exists(BASE_DIR):
    BASE_DIR = os.getcwd()

INPUT_DIR = os.path.join(BASE_DIR, "itaa1997")
# Updated output directory
OUTPUT_DIR = os.path.join(BASE_DIR, "itaa1997-processed")
FILE_PATTERN = "C2025C00405VOL{}.docx"

# --- Concurrency Settings ---
# Optimal number for I/O bound tasks like API calls (adjust based on network/API limits)
MAX_WORKERS = 15

# Global variables for definitions and compiled regex pattern
DEFINITIONS_995_1: Dict[str, Dict] = {}
DEFINITION_MARKER_REGEX: Optional[Pattern] = None

# Fallback regex (used during Pass 1 or if compilation fails)
# CHANGE 3: Updated to use non-capturing group for prefix, suitable for identification via finditer.
FALLBACK_ASTERISK_REGEX = re.compile(r'(?:^|[\s\(])\*(?P<term>[a-zA-Z0-9\s\-\(\)]+?)(?=[\s,.;:)]|$)')

# REMOVED: REFERENCE_SALVAGE_REGEX (No longer needed due to robust CSV parsing)

# --- Style Mappings
STYLE_MAP = {
    'ActHead 1': 1, 'ActHead 2': 2, 'ActHead 3': 3, 'ActHead 4': 4, 'ActHead 5': 5,
}
IGNORE_STYLES = ['Header', 'Footer', 'ShortT', 'LongT', 'CompiledActNo']
IGNORE_STYLE_PATTERNS = ['toc ', 'TofSects(']

# =============================================================================
# COST TRACKING (Thread-Safe)
# =============================================================================

class CostTracker:
    """A thread-safe tracker for token usage and cost calculation."""
    # Gemini 2.5 Flash Pricing (per 1 Million tokens)
    INPUT_PRICE_PER_M = 0.05 # $0.30 (text/image/video)
    OUTPUT_PRICE_PER_M = 0.2 # $2.50 (including thinking tokens)

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.lock = threading.Lock()

    def update(self, input_count, output_count):
        """Updates the token counts thread-safely."""
        if input_count == 0 and output_count == 0:
            return
        with self.lock:
            self.input_tokens += input_count
            self.output_tokens += output_count

    def get_metrics(self):
        """Calculates the current total cost and returns metrics thread-safely."""
        with self.lock:
            input_cost = (self.input_tokens / 1_000_000) * self.INPUT_PRICE_PER_M
            output_cost = (self.output_tokens / 1_000_000) * self.OUTPUT_PRICE_PER_M
            total_cost = input_cost + output_cost
            return total_cost, self.input_tokens, self.output_tokens

# Global tracker instance
GLOBAL_COST_TRACKER = CostTracker()

# =============================================================================
# HELPER FUNCTIONS (Formatting, Parsing, Utilities)
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
        
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)

def should_ignore_style(style_name):
    if style_name in IGNORE_STYLES: return True
    for pattern in IGNORE_STYLE_PATTERNS:
        if style_name.startswith(pattern): return True
    return False

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

# CHANGE 3: Replaced process_asterisked_definitions with identify_defined_terms.
def identify_defined_terms(text: str) -> Set[str]:
    """
    Identifies asterisked definitions using the appropriate pattern (Compiled or Fallback).
    Returns a set of the terms found, preserving their original capitalization from the text.
    Does NOT modify the input text.
    """
    regex_to_use = DEFINITION_MARKER_REGEX if DEFINITION_MARKER_REGEX else FALLBACK_ASTERISK_REGEX
    
    found_terms = set()
    # Use finditer to locate all occurrences
    for match in regex_to_use.finditer(text):
        try:
            # Extract the named group 'term'
            term = match.group('term').strip()
            if term:
               found_terms.add(term)
        except IndexError:
            # Handle potential issues if the regex structure is somehow mismatched
            continue
    return found_terms

def compile_definition_regex():
    """
    Compiles the DEFINITION_MARKER_REGEX after Pass 1.
    """
    global DEFINITION_MARKER_REGEX
    print("\nCompiling precise definition pattern for Pass 2...")
    
    if not DEFINITIONS_995_1:
        print("Warning: No definitions found. Proceeding with fallback pattern.")
        return

    # Sort terms longest to shortest.
    sorted_terms = sorted(DEFINITIONS_995_1.keys(), key=len, reverse=True)
    
    # Escape terms and create an alternation group
    escaped_terms = [re.escape(term) for term in sorted_terms]
    alternation_group = "|".join(escaped_terms)
    
    # Construct the final pattern
    # CHANGE 3: Updated pattern for finding (using non-capturing group for prefix).
    pattern = r'(?:^|[\s\(])\*(?P<term>' + alternation_group + r')(?=[\s,.;:)]|$)'
    
    try:
        # We use IGNORECASE for matching, but identify_defined_terms extracts the original capitalization.
        DEFINITION_MARKER_REGEX = re.compile(pattern, re.IGNORECASE)
        print(f"Pattern compiled successfully with {len(sorted_terms)} terms.")
    except re.error as e:
        # Use str(e) for robust printing
        print(f"Error compiling definition regex: {str(e)}. Falling back to generic pattern.")

# CHANGE 3: Updated to return markdown string and set of terms.
def get_image_alt_text(paragraph) -> Tuple[str, Set[str]]:
    """Extracts alt text from images and identifies defined terms within it."""
    alt_texts_md = []
    all_defined_terms = set()
    W_URI = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    WP_URI = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
    drawing_qname = f'{{{W_URI}}}drawing'
    docPr_qname = f'{{{WP_URI}}}docPr'

    for drawing in paragraph._element.iter(drawing_qname):
        for docPr in drawing.iter(docPr_qname):
            alt_text = docPr.get('descr')
            if alt_text:
                # Identify terms without modifying the text
                terms = identify_defined_terms(alt_text)
                all_defined_terms.update(terms)
                # Preserve original text
                text_to_add = f"\n[Image Description: {alt_text}]\n\n"
                
                if text_to_add not in alt_texts_md:
                    alt_texts_md.append(text_to_add)
    
    # Return aggregated markdown and terms
    return "".join(alt_texts_md), all_defined_terms

# CHANGE 3: Updated to return markdown string and set of terms.
def process_table(table) -> Tuple[str, Set[str]]:
    """Converts a docx table to Markdown format and identifies defined terms."""
    table_md = "\n"
    all_defined_terms = set()
    try:
        rows_data = []
        max_cols = 0
        for row in table.rows:
               if len(row.cells) > max_cols:
                   max_cols = len(row.cells)
        if max_cols == 0: return "", set()

        for row in table.rows:
            row_data = []
            for cell in row.cells:
               cell_text = cell.text.strip().replace('\n', ' ').replace('\u00A0', ' ')
               # Identify terms without modifying the text
               terms = identify_defined_terms(cell_text)
               all_defined_terms.update(terms)
               # Preserve original text
               row_data.append(cell_text)

            while len(row_data) < max_cols:
               row_data.append("")
            if any(row_data):
               rows_data.append(row_data)

        if not rows_data: return "", set()

        for i, row_data in enumerate(rows_data):
            table_md += "| " + " | ".join(row_data) + " |\n"
            if i == 0:
               # Add header separator (simple heuristic: assume first row is header)
               table_md += "|---" * len(row_data) + "|\n"
               
    except Exception as e:
        # Use str(e) for robust printing
        print(f"Warning: Error processing a table: {str(e)}")
        return "\n[Error processing table. Refer to original document.]\n\n", all_defined_terms
    
    # Return markdown and terms
    return table_md + "\n", all_defined_terms


# =============================================================================
# DEFINITION EXTRACTION LOGIC
# =============================================================================

def identify_definition_start(paragraph):
    """Checks if a paragraph starts a new definition (Bold+Italic at the start)."""
    term = ""
    if not paragraph.text.strip(): return None

    for run in paragraph.runs:
        if not term.strip() and not run.text.strip(): continue
        if run.bold and run.italic:
            term += run.text
        else:
            return term.strip() if term.strip() else None
    return term.strip() if term.strip() else None

# CHANGE 3: Updated to return markdown and terms.
def process_definition_content(block) -> Tuple[str, Set[str]]:
    """Processes a subsequent block (paragraph or table) into Markdown and identifies terms."""
    content_md = ""
    defined_terms = set()

    if isinstance(block, Paragraph):
        text = block.text.strip().replace('\u00A0', ' ')
        
        # Handle images and their terms
        img_md, img_terms = get_image_alt_text(block)
        content_md += img_md
        defined_terms.update(img_terms)

        if text:
            indentation = get_indentation(block)
            # Identify terms without modifying the text
            terms = identify_defined_terms(text)
            defined_terms.update(terms)
            # Preserve original text
            content_md += f"{indentation}{text}\n\n"
            
        return content_md, defined_terms
        
    elif isinstance(block, Table):
        return process_table(block)
        
    return "", set()

# CHANGE 3: Updated to return markdown and terms.
def clean_definition_start(paragraph, term) -> Tuple[str, Set[str]]:
    """Removes the term from the start of the starting paragraph and processes the rest."""
    text = paragraph.text.strip().replace('\u00A0', ' ')
    try:
        pattern = re.compile(r'^' + re.escape(term), re.IGNORECASE)
        text = pattern.sub('', text, count=1).strip()
    except re.error:
        # Fallback if regex fails
        return process_definition_content(paragraph)

    if text.startswith((':', '—', '-')):
          text = text[1:].strip()
    
    if text.lower().startswith('means:'):
        text = text[len('means:'):].strip()

    # Handle images and their terms
    content_md, defined_terms = get_image_alt_text(paragraph)

    if text:
        indentation = get_indentation(paragraph)
        # Identify terms in the remaining text
        terms = identify_defined_terms(text)
        defined_terms.update(terms)
        # Preserve original text
        content_md += f"{indentation}{text}\n\n"
        
    return content_md, defined_terms

# =============================================================================
# STRUCTURAL IDENTIFICATION (Semantic Labeling)
# =============================================================================

TITLE_PATTERNS = {
    "Structure": re.compile(r'^(Chapter|Part|Division|Subdivision)\s+([0-9A-Z\-]+)(?:\s*(?:—|-|--)\s*(.*))?$', re.IGNORECASE),
    "Section": re.compile(r'^([0-9\-A-Z]+)\s+(.*)$', re.IGNORECASE),
}

def parse_title(title, level):
    """
    Parses the title string to extract the type, id, name, and generate the ref_id.
    """
    
    parsed_data = {
        "type": f"Level{level}Element", # Default type
        "id": None,
        "name": title,
        "ref_id": None
    }

    # 1. Handle Guides and Operative Provisions
    if title.lower().startswith("guide to"):
        parsed_data["type"] = "Guide"
        return parsed_data
    if title.lower().startswith("operative provision"):
        parsed_data["type"] = "OperativeProvision"
        return parsed_data

    # 2. Handle Sections (Typically Level 5)
    if level == 5:
        match = TITLE_PATTERNS["Section"].match(title)
        if match:
            parsed_data["type"] = "Section"
            parsed_data["id"] = match.group(1).strip()
            parsed_data["name"] = match.group(2).strip()

    # 3. Handle Standard Structures (Chapter, Part, Division, Subdivision)
    if parsed_data["type"] == f"Level{level}Element":
        match = TITLE_PATTERNS["Structure"].match(title)
        if match:
            parsed_data["type"] = match.group(1).capitalize()
            parsed_data["id"] = match.group(2).strip()
            if match.group(3):
               parsed_data["name"] = match.group(3).strip()
            else:
               parsed_data["name"] = "" 

    # 4. Generate ref_id (Canonical ID)
    if parsed_data["id"]:
        ref_type = parsed_data["type"]
        parsed_data["ref_id"] = f"ITAA1997:{ref_type}:{parsed_data['id']}"

    return parsed_data

# CHANGE 1 & 3: Renamed and updated to finalize the new structures (Sets to Lists).
def recursive_finalize_structure(structure):
    """Recursively finalizes data structures (sorts references, sorts terms) after processing."""
    if isinstance(structure, list):
        for item in structure:
            recursive_finalize_structure(item)
    elif isinstance(structure, dict):
        
        # 1. Finalize References (Set of Tuples -> List of Tuples)
        # Convert the set (used during concurrent updates) to a sorted list
        if "references" in structure and isinstance(structure["references"], set):
            # Sort by Normalized Reference (index 0)
            try:
                structure["references"] = sorted(
                    list(structure["references"]), 
                    # Robust key handling
                    key=lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) > 0 else str(x)
                )
            except TypeError as e:
                tqdm.write(f"Warning: Error sorting references for {structure.get('title', 'Unknown')}: {e}. Proceeding unsorted.")
                structure["references"] = list(structure["references"])

        # 2. Finalize Defined Terms (Set of Strings -> List of Strings)
        if "defined_terms_used" in structure and isinstance(structure["defined_terms_used"], set):
            # Sort the set
            structure["defined_terms_used"] = sorted(list(structure["defined_terms_used"]))

        if "children" in structure:
            recursive_finalize_structure(structure["children"])

# =============================================================================
# LLM REFERENCE EXTRACTION (GEMINI INTEGRATION & CONCURRENCY)
# =============================================================================

SYSTEM_PROMPT = """
You are an expert Australian tax paralegal. Identify explicit legislative references and the exact text snippets that mention them.

RULES:
1. Normalize ONLY to Act, Schedule, Part, Division, or Section level. Omit Subsection/Paragraph identifiers.
2. Use `ACRONYM:Element:Identifier` (e.g., `ITAA1997:Section:10-1`). Schedules: `TAA1953:Schedule:1:Section:12-5`.
3. Only extract if a specific identifier (number/ID) is present.
4. Use standard acronyms (ITAA1997, ITAA1936, TAA1953, GSTA1999). Generate others concisely.
5. Output separate entries for lists/ranges (e.g., "sections 10 and 11" should create two identifier entries, both pointing to the text "sections 10 and 11").
6. If a an identifier is referenced in multiple places, return a **separate entry** for each (with the identifier duplicated for each related text that references it).
7. The `ref_id` value must be clean and contain *only* the `ACRONYM:Element:Identifier` string.

EXAMPLE INPUT:
`Covered by section 355-100 and paragraph 355-105(1)(a). See also Part VA of the ITAA 1936. For further information, see sections 355-101 to 103.`

EXAMPLE OUTPUT (JSON):
[
  {"ref_id": "ITAA1997:Section:355-100", "snippet": "section 355-100"},
  {"ref_id": "ITAA1997:Section:355-101", "snippet": "sections 355-101 to 103"},
  {"ref_id": "ITAA1997:Section:355-102", "snippet": "sections 355-101 to 103"},
  {"ref_id": "ITAA1997:Section:355-103", "snippet": "sections 355-101 to 103"},
  {"ref_id": "ITAA1997:Section:355-105", "snippet": "paragraph 355-105(1)(a)"},
  {"ref_id": "ITAA1936:Part:VA", "snippet": "Part VA of the ITAA 1936"}
]

OUTPUT FORMAT:
Strictly JSON. Output a valid JSON array of objects, where each object has a "ref_id" (string) and "snippet" (string) key.
If no references are found, return an empty JSON array [].
"""

# --- Gemini Configuration ---
LLM_MODEL_NAME = 'gemini-2.5-flash-lite-preview-09-2025'
API_KEY_ENV_VAR = "GOOGLE_CLOUD_API_KEY" 
LLM_CLIENT = None

def initialize_gemini_client():
    """Initializes the Gemini client using the standard Google AI SDK."""
    global LLM_CLIENT
    if genai is None or types is None:
        return

    api_key = os.environ.get(API_KEY_ENV_VAR)

    if not api_key:
        print(f"Warning: Gemini API Key not found in environment variable '{API_KEY_ENV_VAR}'. Proceeding without LLM features.")
        return

    try:
        genai.configure(api_key=api_key)

        # Configuration for deterministic output, FORCING JSON
        generation_config = types.GenerationConfig(
            temperature=0.0,
            # CHANGE: Re-added response_mime_type to force JSON output
            response_mime_type="application/json",
            max_output_tokens=16384
        )
        # Safety settings (Set to BLOCK_NONE)
        safety_settings = {
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
        }

        # Initialize the model once with the system instruction and configuration
        LLM_CLIENT = genai.GenerativeModel(
            LLM_MODEL_NAME,
            system_instruction=SYSTEM_PROMPT,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        print(f"Successfully initialized Gemini model: {LLM_MODEL_NAME} (JSON Mode)")

    except Exception as e:
        # FIX: Use str(e) for robust printing
        print(f"Warning: Error initializing Gemini Client ({str(e)}). Check API key and network connection. Proceeding without LLM features.")
        LLM_CLIENT = None

# Initialize the client when the script loads
initialize_gemini_client()


# CHANGE 1: Updated return type and parsing logic for CSV.
def extract_references_with_llm(text_chunk: str) -> tuple[List[Tuple[str, str]], int, int]:
    """
    Uses the Gemini API to extract references from JSON output. 
    Returns references (list of tuples (NormalizedRef, Snippet)) and token usage.
    """
    if not LLM_CLIENT or not text_chunk or not text_chunk.strip():
        return [], 0, 0
        
    # Optimization 1: Length check
    if len(text_chunk) < 10:
        return [], 0, 0
        
    # Optimization 2: Keyword Pre-filter
    if not re.search(r'\b(section|division|part|schedule|act|\d{4})\b', text_chunk, re.IGNORECASE):
        return [], 0, 0
        
    try:
        # Call the Gemini API
        response = LLM_CLIENT.generate_content(text_chunk)
        
        input_tokens = 0
        output_tokens = 0
        references = []

        # Extract token usage from metadata
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)

        # --- GRACEFUL HANDLING OF EMPTY RESPONSE ---
        response_text = ""
        if (response.candidates and
            response.candidates[0].content and
            response.candidates[0].content.parts):
            response_text = response.candidates[0].content.parts[0].text.strip()
        else:
            # No content returned (e.g., safety block or empty generation)
            pass
        # --- END: GRACEFUL HANDLING ---

        # Process the response text (only if we successfully got text)
        if response_text:
            
            # --- JSON Parsing Logic ---
            try:
                # The API is forced to return valid JSON, so we just load it.
                data = json.loads(response_text)
                
                # We expect a list of objects (dictionaries)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            normalized_ref = item.get("ref_id")
                            text_extract = item.get("snippet")
                            
                            if normalized_ref and text_extract:
                                # Store as a tuple (as expected by the rest of the code)
                                references.append((str(normalized_ref).strip(), str(text_extract).strip()))
                        else:
                            # Log unexpected item in the list
                            tqdm.write(f"Warning: Gemini returned non-dict item in JSON list. Item: {str(item)[:100]}")
                elif data:
                    # Log unexpected JSON structure (e.g., a single dict instead of a list)
                     tqdm.write(f"Warning: Gemini returned unexpected JSON type (expected list). Type: {type(data)}")

            except json.JSONDecodeError as e:
                # --- FIX: Implement regex salvage as requested ---
                # This logic runs *only if* the primary json.loads(response_text) fails.
                tqdm.write(f"Warning: Error parsing Gemini JSON ({str(e)}). Attempting regex salvage...")
                salvaged_references = []
                
                try:
                    # Find all substrings that look like JSON objects ({...})
                    # re.DOTALL makes '.' match newlines, handling multi-line snippets.
                    potential_objects = re.finditer(r'\{.*?\}', response_text, re.DOTALL)
                    
                    for match in potential_objects:
                        object_text = match.group(0)
                        try:
                            # Try to parse *this specific object*
                            item = json.loads(object_text)
                            
                            if isinstance(item, dict):
                                normalized_ref = item.get("ref_id")
                                text_extract = item.get("snippet")
                                
                                if normalized_ref and text_extract:
                                    salvaged_references.append((str(normalized_ref).strip(), str(text_extract).strip()))
                        except json.JSONDecodeError:
                            # This specific chunk was malformed (e.g., contains the
                            # invalid control char or is the truncated part). Skip it.
                            continue
                            
                    if salvaged_references:
                        tqdm.write(f"Successfully salvaged {len(salvaged_references)} entries from broken JSON.")
                        references = salvaged_references
                    else:
                        tqdm.write(f"Salvage failed to find any valid objects. Snippet: {response_text[:100]}...")
                        return [], input_tokens, output_tokens # Still return tokens used

                except Exception as salvage_error:
                    # Catch errors during the regex salvage itself
                    tqdm.write(f"Error during salvage attempt: {str(salvage_error)}. Snippet: {response_text[:100]}...")
                    return [], input_tokens, output_tokens
                # --- END: FIX ---

            except (TypeError, AttributeError) as e:
                # Handle cases where 'data' isn't iterable or 'item' isn't a dict
                 tqdm.write(f"Warning: Error processing Gemini JSON structure ({str(e)}). Snippet: {response_text[:100]}...")


            # Deduplication and sorting (Set handles uniqueness, then sort by reference ID)
            unique_sorted_references = sorted(list(set(references)), key=lambda x: x[0])
            return unique_sorted_references, input_tokens, output_tokens

    except Exception as e:
        # FIX: Catch API errors and safely print the exception using str(e) and include type
        tqdm.write(f"Error calling Gemini API during reference extraction: {type(e).__name__}: {str(e)}")
        
    return [], 0, 0 # Return 0 tokens on failure if usage metadata wasn't captured

# CHANGE 1: Updated to handle Set of Tuples.
def process_section_llm_task(section: Dict, hierarchy_context: List[str]):
    """The task executed by the ThreadPoolExecutor for LLM processing."""
    # Check if the required keys exist and if content is present
    if not section or not section.get("content_md"):
        return

    try:
        # --- NEW: Build context header ---
        context_header = ""
        if hierarchy_context:
            context_header = "CONTEXT: You are processing text within the following hierarchy:\n"
            context_header += "\n".join(hierarchy_context)
            context_header += "\n\n---\n\n"
        
        full_text_chunk = context_header + section["content_md"]
        # --- END NEW ---

        # Perform the LLM call (returns list of (ref, snippet) tuples)
        # Pass the full text chunk with the context header
        refs, in_tok, out_tok = extract_references_with_llm(full_text_chunk)
        
        if refs:
            # Update the section dictionary. 
            # Ensure 'references' key exists and is a set before updating
            if "references" not in section or not isinstance(section["references"], set):
                section["references"] = set()
            
            # Extend the set. Tuples are hashable.
            # Since each worker operates on a unique section object, this is safe.
            section["references"].update(refs)
        
        # Update global costs (thread-safe)
        GLOBAL_COST_TRACKER.update(in_tok, out_tok)

    except Exception as e:
        # FIX: Use tqdm.write for thread-safe printing and safely print the exception using str(e)
        tqdm.write(f"\nWarning: LLM task failed for section {section.get('title', 'Unknown')}: {type(e).__name__}: {str(e)}")

# =============================================================================
# MAIN DOCUMENT PROCESSING (BATCHED & CONCURRENT)
# =============================================================================

def finalize_section(section, hierarchy_context: List[str], executor=None, futures=None):
    """
    Processes the aggregated content of a section. Submits LLM processing to the thread pool.
    """
    if isinstance(section, dict):
        # Clean the markdown content first
        section["content_md"] = section["content_md"].strip()
        
        # If an executor is provided and LLM is active, submit the task concurrently
        if executor and futures is not None and LLM_CLIENT and section["content_md"]:
            # Submit the task to the thread pool, NOW WITH CONTEXT
            future = executor.submit(process_section_llm_task, section, hierarchy_context)
            futures.append(future)

def process_document(filepath, pass_num=1, executor=None, futures=None):
    """
    Processes a single .docx file.
    Pass 1: Extracts definitions (Sequential).
    Pass 2: Extracts structure and submits LLM tasks concurrently.
    """
    try:
        doc = docx.Document(filepath)
    except Exception as e:
        # Use str(e) for robust printing
        print(f"Error opening document {filepath}: {str(e)}")
        return []

    structure = []
    hierarchy_stack = [structure]
    current_section = None
    
    in_definitions_section = False
    current_definition_term = None

    # --- TQDM SETUP (Document Parsing) ---
    try:
        total_blocks = len(doc.element.body.getchildren())
    except Exception:
        total_blocks = None 
    
    block_iterator = iter_block_items(doc)
    
    # Progress bar for parsing the document structure (Position 2)
    progress_bar_doc = tqdm(
        block_iterator, 
        total=total_blocks, 
        desc=f"  Parsing {os.path.basename(filepath)} (Pass {pass_num})",
        unit="block",
        leave=False, 
        ncols=100,
        position=2 
    )
    # --- END TQDM SETUP ---

    for block in progress_bar_doc:
        
        is_paragraph = isinstance(block, Paragraph)
        is_table = isinstance(block, Table)
        style_name = None
        text = ""

        if is_paragraph:
            if block.style and hasattr(block.style, 'name'):
                style_name = block.style.name
                if should_ignore_style(style_name):
                    continue
            
            text = block.text.strip().replace('\u00A0', ' ')

        # 2. Handle Headings (Hierarchy)
        if is_paragraph and style_name in STYLE_MAP:
            level = STYLE_MAP[style_name]
            if not text: continue

            title_data = {"name": text}
            if pass_num == 2:
                title_data = parse_title(text, level)

            # CHANGE 1 & 3: Update initialization (Sets for concurrent accumulation)
            new_section = {
                "level": level,
                "title": text,
                "type": title_data.get("type"),
                "id": title_data.get("id"),
                "name": title_data.get("name"),
                "ref_id": title_data.get("ref_id"),
                "content_md": "",
                "references": set(), # Stores tuples (NormalizedRef, Snippet)
                "defined_terms_used": set(), # Stores strings
                "children": []
            }

            # Finalize sections higher in the hierarchy before moving on
            while len(hierarchy_stack) > level:
                popped_section = hierarchy_stack.pop()
                if pass_num == 2:
                    # Create context from the *remaining* stack (which are the parents)
                    hierarchy_context = [item.get("ref_id") for item in hierarchy_stack[1:] if item.get("ref_id")]
                    
                    # Finalize (and submit LLM task) when the section is popped
                    finalize_section(popped_section, hierarchy_context, executor, futures)
                    
            if pass_num == 2:
                parent_container = hierarchy_stack[-1]
                if isinstance(parent_container, list):
                    parent_container.append(new_section)
                elif isinstance(parent_container, dict) and "children" in parent_container:
                        parent_container["children"].append(new_section)
                
                hierarchy_stack.append(new_section)
                current_section = new_section
            else:
                current_section = True # Flag for Pass 1

            # Definition section tracking (for Pass 1)
            if level == 5 and (text.startswith("995-1") or text.startswith("995 1")):
                in_definitions_section = True
                current_definition_term = None
                if pass_num == 1: 
                    progress_bar_doc.set_description(f"  Extracting Definitions (995-1)...", refresh=True)
            elif level < 5 and in_definitions_section:
                if pass_num == 1: 
                    progress_bar_doc.set_description(f"  Exiting Definitions (995-1)...", refresh=True)
                in_definitions_section = False
                current_definition_term = None
            
            continue

        # 3. Handle Content (Paragraphs and Tables)
        if current_section:

            # --- Definition Extraction Logic (Runs only in Pass 1) ---
            if pass_num == 1 and in_definitions_section:
                new_term = None
                if is_paragraph:
                    new_term = identify_definition_start(block)

                if new_term:
                    current_definition_term = new_term
                    # Initialize definition structure (Dict)
                    # CHANGE 1 & 3: Update initialization
                    if current_definition_term not in DEFINITIONS_995_1:
                        DEFINITIONS_995_1[current_definition_term] = {
                            "content_md": "",
                            "references": set(),
                            "defined_terms_used": set()
                        }
                    # CHANGE 3: Handle new return signature
                    content, terms = clean_definition_start(block, new_term)
                    DEFINITIONS_995_1[current_definition_term]["content_md"] += content
                    # In Pass 1, this uses the fallback regex.
                    DEFINITIONS_995_1[current_definition_term]["defined_terms_used"].update(terms)

                elif current_definition_term:
                    # CHANGE 3: Handle new return signature
                    content, terms = process_definition_content(block)
                    if current_definition_term in DEFINITIONS_995_1:
                        DEFINITIONS_995_1[current_definition_term]["content_md"] += content
                        DEFINITIONS_995_1[current_definition_term]["defined_terms_used"].update(terms)
            
            # Standard content processing (Only needed in Pass 2)
            if pass_num == 2:
                if is_paragraph:
                    # CHANGE 3: Handle new return signature
                    alt_text_md, alt_terms = get_image_alt_text(block)
                    if alt_text_md:
                        current_section["content_md"] += alt_text_md
                        current_section["defined_terms_used"].update(alt_terms)

                    if text:
                        indentation = get_indentation(block)
                        
                        # CHANGE 3: Identify terms without modifying the text (Uses precise regex in Pass 2)
                        terms = identify_defined_terms(text)
                        current_section["defined_terms_used"].update(terms)
                        
                        processed_text = text # Use the original text
                        
                        # Apply specific formatting styles
                        if style_name == 'SubsectionHead':
                            processed_text = f"*{processed_text}*"
                        elif (style_name and (style_name.startswith('note(') or style_name.startswith('Note('))):
                            processed_text = f"_{processed_text}_"

                        # Aggregate content
                        current_section["content_md"] += f"{indentation}{processed_text}\n\n"

                elif is_table:
                    # CHANGE 3: Handle new return signature
                    table_md, table_terms = process_table(block)
                    # Aggregate content
                    current_section["content_md"] += table_md
                    current_section["defined_terms_used"].update(table_terms)

    # Close the inner document progress bar
    progress_bar_doc.close()

    # Finalize remaining sections on the stack after the document ends
    if pass_num == 2:
        while len(hierarchy_stack) > 1:
            popped_section = hierarchy_stack.pop()
            
            # Create context from the *remaining* stack
            hierarchy_context = [item.get("ref_id") for item in hierarchy_stack[1:] if item.get("ref_id")]
            
            # Finalize (and submit LLM task) remaining items
            finalize_section(popped_section, hierarchy_context, executor, futures)

    return structure

# =============================================================================
# EXECUTION BLOCK (Two-Pass Implementation)
# =============================================================================

def finalize_definitions_pass1():
    """Strips whitespace and performs initial cleanup of definitions collected in Pass 1."""
    for term in list(DEFINITIONS_995_1.keys()):
        if term in DEFINITIONS_995_1:
            # Access the content_md key due to updated structure
            DEFINITIONS_995_1[term]["content_md"] = DEFINITIONS_995_1[term]["content_md"].strip()
            
            # Note: defined_terms_used contains potentially imprecise findings from the fallback regex at this stage.

            if not DEFINITIONS_995_1[term]["content_md"]:
                del DEFINITIONS_995_1[term]

# CHANGE 3: Updated logic to correctly utilize the precise regex after Pass 1.
def process_and_analyze_definitions_concurrent(pbar_llm, executor):
    """
    Applies precise term identification (Pass 2 logic) and runs concurrent LLM analysis on definitions.
    """
    print("Applying precise term identification and analyzing definitions concurrently (Gemini)...")
    futures = []

    definition_context = ["ITAA1997:Section:995-1"]

    # 1. Re-identify terms using the precise regex and submit LLM tasks
    for term in DEFINITIONS_995_1:
        current_content = DEFINITIONS_995_1[term]["content_md"]
        
        # If the precise regex is available, use it to replace the fallback results from Pass 1.
        if DEFINITION_MARKER_REGEX:
            # Since DEFINITION_MARKER_REGEX is now global, identify_defined_terms will use it.
            precise_terms = identify_defined_terms(current_content)
            # Overwrite the terms identified by the fallback regex in Pass 1.
            DEFINITIONS_995_1[term]["defined_terms_used"] = precise_terms
        
        # 2. Submit LLM analysis to the pool (using the original content, as LLM analyzes raw text)
        if LLM_CLIENT and current_content:
            # Create a temporary structure compatible with process_section_llm_task
            
            # Ensure existing references (if any) are correctly formatted as a set of tuples.
            existing_refs = DEFINITIONS_995_1[term].get("references", set())
            if not isinstance(existing_refs, set):
                # Handle potential initialization issues if it's a list from a previous failed run/version
                refs_set = set(tuple(ref) for ref in existing_refs if isinstance(ref, (list, tuple)))
            else:
                refs_set = existing_refs

            temp_section = {
                "content_md": current_content,
                "references": refs_set, 
                "title": f"Def:{term}"
            }
            # Submit the task, NOW WITH CONTEXT
            future = executor.submit(process_section_llm_task, temp_section, definition_context)
            # We need to map the result back later
            futures.append((future, term, temp_section))
            
    # 3. Wait for completion and update results
    # Initialize progress bar based on LLM tasks or just term identification if LLM is off.
    total_tasks = len(futures) if futures else len(DEFINITIONS_995_1)
    pbar_defs = tqdm(desc="Enriching Definitions", total=total_tasks, unit="def", ncols=100, position=2, leave=False)
    
    # Process results (this blocks until definitions are done)
    if futures:
        for future, term, temp_section in futures:
            try:
                future.result() # Wait for the specific future to complete
            except Exception as e:
                # FIX: Use str(e) for robust printing
                tqdm.write(f"Error processing definition future for '{term}': {str(e)}")

            pbar_defs.update(1)
            pbar_llm.update(1)

            # Update cost display (main thread)
            current_cost, _, _ = GLOBAL_COST_TRACKER.get_metrics()
            pbar_llm.set_postfix_str(f"Cost: ${current_cost:.4f}")

            # Map results back from the temporary structure
            # The worker updates temp_section["references"] (a set) in place.
            DEFINITIONS_995_1[term]["references"] = temp_section["references"]
    else:
        # If LLM was inactive, update the progress bar for the term identification step
        for _ in DEFINITIONS_995_1:
            pbar_defs.update(1)


    # 4. Finalize the definitions structure (convert Sets to Lists)
    # We do this after all concurrent tasks are finished.
    for term in DEFINITIONS_995_1:
        # Use the finalization logic to convert Sets to sorted Lists
        recursive_finalize_structure(DEFINITIONS_995_1[term])

    pbar_defs.close()

def main():
    # Setup directories
    if not os.path.exists(INPUT_DIR):
        print(f"Warning: Input directory not found at {INPUT_DIR}. Script may fail if input files are required.")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print(f"Created output directory: {OUTPUT_DIR}")

    print(f"\nStarting ITAA 1997 Processing (Gemini {LLM_MODEL_NAME} Accelerated, Concurrent Workers: {MAX_WORKERS})...")
    if not LLM_CLIENT:
        print("CRITICAL WARNING: Proceeding without LLM reference extraction due to initialization failure.")

    # Initialize the LLM progress bar (Position 1)
    pbar_llm = tqdm(desc="Gemini Processing Status", unit="item", ncols=100, position=1, leave=True)
    # Initialize cost display
    pbar_llm.set_postfix_str("Cost: $0.0000")
        
    # Initialize Thread Pool Executor
    # Using a 'with' statement ensures the executor is shut down properly
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        # --- PASS 1: Extract Definitions (Volume 10 ONLY) ---
        print("\n=== PASS 1: Extracting Definitions (Volume 10) ===")
        volume_num_pass1 = "10"
        filepath_pass1 = os.path.join(INPUT_DIR, FILE_PATTERN.format(volume_num_pass1))
        
        if os.path.exists(filepath_pass1):
            print(f"Processing VOL{volume_num_pass1} (Pass 1)...")
            # Pass 1 is sequential (no executor needed)
            process_document(filepath_pass1, pass_num=1)
        else:
            print(f"Note: Definition Volume (10) not found at {filepath_pass1}. Proceeding without pre-defined terms.")

        finalize_definitions_pass1()
        print(f"Pass 1 Complete. Extracted {len(DEFINITIONS_995_1)} definitions.")
        
        # --- INTERMEDIATE STEP ---
        compile_definition_regex()

        # We always run this step to finalize definitions (identify terms precisely and run LLM if active)
        if DEFINITIONS_995_1:
            process_and_analyze_definitions_concurrent(pbar_llm, executor)


        # --- PASS 2: Full Structure Extraction and Enrichment ---
        print("\n=== PASS 2: Full Structure Extraction and Enrichment (All Volumes) ===")
        
        # Initialize Overall Volume Processing (Position 0)
        # NOTE: The original script had range(1, 2). Assuming the intent is to process all standard volumes (1-10).
        # Adjust range(1, 11) if needed.
        pbar_volumes = tqdm(range(1, 11), desc="Overall Volume Processing", unit="vol", ncols=100, position=0)
        
        for i in pbar_volumes:
            volume_num = f"{i:02d}"
            filename = FILE_PATTERN.format(volume_num)
            filepath = os.path.join(INPUT_DIR, filename)
            
            pbar_volumes.set_description(f"Processing Volume {volume_num}", refresh=True)

            if os.path.exists(filepath):
                # Track futures for this specific volume
                volume_futures = []
                
                # Process the document, submitting tasks to the executor via finalize_section
                structured_data = process_document(
                    filepath, 
                    pass_num=2, 
                    executor=executor, 
                    futures=volume_futures
                )
                
                # Wait for this volume's LLM tasks to complete before proceeding
                if volume_futures:
                    pbar_volumes.set_description(f"Volume {volume_num}: Waiting for LLM...", refresh=True)
                
                    # Process futures as they complete (this blocks until the volume is done)
                    for future in as_completed(volume_futures):
                        try:
                            future.result() # Wait and check for exceptions
                        except Exception as e:
                            # FIX: Use str(e) for robust printing
                            tqdm.write(f"Error in completed future for Volume {volume_num}: {str(e)}")

                        pbar_llm.update(1)
                        
                        # Update cost display frequently (main thread)
                        current_cost, _, _ = GLOBAL_COST_TRACKER.get_metrics()
                        pbar_llm.set_postfix_str(f"Cost: ${current_cost:.4f}")

                pbar_volumes.set_description(f"Volume {volume_num}: Finalizing...", refresh=True)

                # Finalize the structure (convert Sets to Lists)
                recursive_finalize_structure(structured_data)

                if not structured_data and i <= 10:
                    tqdm.write(f"\nWarning: No structure extracted from {filename}.")

                # Save the volume JSON
                output_filename = f"ITAA1997_VOL{volume_num}_gemini_concurrent.json"
                output_filepath = os.path.join(OUTPUT_DIR, output_filename)
                
                try:
                    with open(output_filepath, 'w', encoding='utf-8') as f:
                        json.dump(structured_data, f, indent=2, ensure_ascii=False)
                    tqdm.write(f"Successfully saved {output_filename}")
                except Exception as e:
                    # Use str(e) for robust printing
                    tqdm.write(f"Error saving {output_filename}: {str(e)}")
            else:
                # Only warn if the file is expected (e.g., Vol 1-10)
                if i <= 10:
                    tqdm.write(f"File not found: {filepath}")

    # Executor shuts down automatically due to 'with' statement

    # Close the progress bars
    pbar_llm.close()
    pbar_volumes.close()

    # Save the finalized definitions file
    # Definitions are already finalized during the intermediate step.
    if DEFINITIONS_995_1:
        definitions_filepath = os.path.join(OUTPUT_DIR, "definitions_995_1_gemini_concurrent.json")
        try:
            # Sort by the term (key)
            sorted_definitions = dict(sorted(DEFINITIONS_995_1.items()))
            with open(definitions_filepath, 'w', encoding='utf-8') as f:
                json.dump(sorted_definitions, f, indent=2, ensure_ascii=False)
            print(f"\nSuccessfully saved {len(DEFINITIONS_995_1)} definitions to {definitions_filepath}")
        except Exception as e:
            # Use str(e) for robust printing
            print(f"Error saving definitions: {str(e)}")

    print("\nProcessing complete.")
    if LLM_CLIENT:
        final_cost, total_in, total_out = GLOBAL_COST_TRACKER.get_metrics()
        print(f"\n--- Gemini Usage Summary ---")
        print(f"Model: {LLM_MODEL_NAME}")
        print(f"Total Input Tokens:  {total_in:,}")
        print(f"Total Output Tokens: {total_out:,}")
        print(f"Estimated Total Cost: ${final_cost:.4f}")
    
if __name__ == '__main__':
    # Ensure you have the required libraries installed: 
    # pip install python-docx tqdm google-generativeai
    
    # --- IMPORTANT ---
    # Before running:
    # 1. Ensure the environment variable GOOGLE_CLOUD_API_KEY is set with your Gemini API key.
    #    (e.g., export GOOGLE_CLOUD_API_KEY='your_api_key')
    # 2. Ensure python-docx is installed.
    # 3. Review the volume range in main() (pbar_volumes initialization).
    
    # To run the script, uncomment the following line:
    main()
    pass