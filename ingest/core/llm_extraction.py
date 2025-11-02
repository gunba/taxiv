import hashlib
import json
import os
import re
import sqlite3
import threading
from typing import Dict, List, Tuple

# We import tqdm for thread-safe printing during concurrent operations
try:
	from tqdm import tqdm
except ImportError:
	# Fallback if tqdm is not installed
	class tqdm:
		@staticmethod
		def write(msg):
			print(msg)

		# Define a dummy call signature for the progress bar usage in the runner
		def __call__(self, *args, **kwargs):
			return self

		def update(self, n=1):
			pass

		def close(self):
			pass

		def set_description(self, desc, refresh=True):
			pass

		def set_postfix_str(self, s, refresh=True):
			pass

# Import necessary libraries.
try:
	import google.generativeai as genai
	from google.generativeai import types
except ImportError:
	print("Warning: google-generativeai library not found. Install it: pip install google-generativeai")
	genai = None
	types = None

# =============================================================================
# CONFIGURATION
# =============================================================================

# --- Gemini Configuration ---
LLM_MODEL_NAME = 'gemini-2.5-flash-lite-preview-09-2025'
API_KEY_ENV_VAR = "GOOGLE_CLOUD_API_KEY"
LLM_CLIENT = None

# --- Caching Configuration ---
# Determine the base directory for the cache relative to this core module
# Use a robust method to find the ingest directory, handling environments where __file__ might not be defined
try:
	BASE_INGEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
except NameError:
	# Fallback for interactive environments or specific execution contexts
	BASE_INGEST_DIR = os.path.abspath(os.path.join(os.getcwd(), 'ingest'))

CACHE_DB_PATH = os.path.join(BASE_INGEST_DIR, 'cache', 'llm_cache.db')


# =============================================================================
# COST TRACKING (Thread-Safe)
# =============================================================================

class CostTracker:
	"""A thread-safe tracker for token usage and cost calculation."""
	# Gemini 2.5 Flash Pricing (as provided in the original script)
	INPUT_PRICE_PER_M = 0.05
	OUTPUT_PRICE_PER_M = 0.2

	def __init__(self):
		self.input_tokens = 0
		self.output_tokens = 0
		self.cache_hits = 0
		self.api_calls = 0
		self.lock = threading.Lock()

	def update(self, input_count, output_count, is_cache_hit=False):
		"""Updates the token counts and metrics thread-safely."""
		# Ensure counts are integers
		input_count = int(input_count or 0)
		output_count = int(output_count or 0)

		with self.lock:
			# We track the tokens associated with the original API call, even if retrieved from cache
			self.input_tokens += input_count
			self.output_tokens += output_count
			if is_cache_hit:
				self.cache_hits += 1
			# Only count as an API call if it wasn't a cache hit and actual tokens were processed
			elif input_count > 0 or output_count > 0:
				self.api_calls += 1

	def get_metrics(self):
		"""Calculates the current total cost and returns metrics thread-safely."""
		with self.lock:
			input_cost = (self.input_tokens / 1_000_000) * self.INPUT_PRICE_PER_M
			output_cost = (self.output_tokens / 1_000_000) * self.OUTPUT_PRICE_PER_M
			total_cost = input_cost + output_cost
			return total_cost, self.input_tokens, self.output_tokens, self.cache_hits, self.api_calls


# Global tracker instance
GLOBAL_COST_TRACKER = CostTracker()


# =============================================================================
# CACHING MECHANISM (SQLite)
# =============================================================================

class LLMCache:
	def __init__(self, db_path=CACHE_DB_PATH):
		self.db_path = db_path
		# Ensure the cache directory exists
		os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
		self._initialize_db()
		# Use a lock for thread safety when accessing the SQLite connection
		self.lock = threading.Lock()

	def _initialize_db(self):
		conn = None
		try:
			# Use a slightly longer timeout for initialization
			conn = sqlite3.connect(self.db_path, timeout=10.0)
			cursor = conn.cursor()
			# Create the cache table if it doesn't exist
			cursor.execute('''
                           CREATE TABLE IF NOT EXISTS cache
                           (
                               hash
                               TEXT
                               PRIMARY
                               KEY,
                               model_name
                               TEXT,
                               input_text
                               TEXT,
                               response_json
                               TEXT,
                               input_tokens
                               INTEGER,
                               output_tokens
                               INTEGER
                           )
						   ''')
			cursor.execute('CREATE INDEX IF NOT EXISTS idx_model_name ON cache (model_name)')
			conn.commit()
		except sqlite3.Error as e:
			tqdm.write(f"Database error during initialization: {e}")
		finally:
			if conn:
				conn.close()

	def _get_hash(self, text):
		# Use SHA256 for robust hashing
		return hashlib.sha256(text.encode('utf-8')).hexdigest()

	def get(self, text_chunk, model_name):
		hash_key = self._get_hash(text_chunk)
		conn = None
		# Use lock for thread-safe read access
		with self.lock:
			try:
				# Set a timeout to prevent indefinite waiting if the DB is busy
				conn = sqlite3.connect(self.db_path, timeout=5.0)
				cursor = conn.cursor()
				cursor.execute(
					"SELECT response_json, input_tokens, output_tokens FROM cache WHERE hash = ? AND model_name = ?",
					(hash_key, model_name))
				result = cursor.fetchone()
				if result:
					# Return response JSON and the token counts
					return result[0], result[1], result[2]
			except sqlite3.OperationalError as e:
				tqdm.write(f"Database operational error (e.g., locked) during cache retrieval: {e}")
			except sqlite3.Error as e:
				tqdm.write(f"Database error during cache retrieval: {e}")
			finally:
				if conn:
					conn.close()
		return None, None, None

	def set(self, text_chunk, model_name, response_json, input_tokens, output_tokens):
		hash_key = self._get_hash(text_chunk)
		conn = None
		# Use lock for thread-safe write access
		with self.lock:
			try:
				conn = sqlite3.connect(self.db_path, timeout=5.0)
				cursor = conn.cursor()
				cursor.execute('''
                    INSERT OR REPLACE INTO cache (hash, model_name, input_text, response_json, input_tokens, output_tokens)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (hash_key, model_name, text_chunk, response_json, input_tokens, output_tokens))
				conn.commit()
			except sqlite3.OperationalError as e:
				tqdm.write(f"Database operational error (e.g., locked) during cache insertion: {e}")
			except sqlite3.Error as e:
				tqdm.write(f"Database error during cache insertion: {e}")
			finally:
				if conn:
					conn.close()


# Global cache instance
# We initialize it here so it's ready when the module is imported
try:
	GLOBAL_LLM_CACHE = LLMCache()
except Exception as e:
	print(f"Failed to initialize LLM Cache: {e}")
	GLOBAL_LLM_CACHE = None

# =============================================================================
# GEMINI INTEGRATION
# =============================================================================

# (SYSTEM_PROMPT remains the same as in the original process_ita1997.py)
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

import traceback


def initialize_gemini_client():
	"""Initializes the Gemini client."""
	global LLM_CLIENT
	# Prevent re-initialization
	if genai is None or types is None or LLM_CLIENT is not None:
		return

	api_key = os.environ.get(API_KEY_ENV_VAR)

	if not api_key:
		tqdm.write(
			f"Warning: Gemini API Key not found in environment variable '{API_KEY_ENV_VAR}'. Proceeding without LLM features.")
		return

	try:
		genai.configure(api_key=api_key)

		# Configuration for deterministic output, FORCING JSON
		generation_config = types.GenerationConfig(
			temperature=0.0,
			response_mime_type="application/json",
			max_output_tokens=16384
		)
		safety_settings = {
			"HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
			"HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
			"HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
			"HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
		}

		LLM_CLIENT = genai.GenerativeModel(
			LLM_MODEL_NAME,
			system_instruction=SYSTEM_PROMPT,
			generation_config=generation_config,
			safety_settings=safety_settings
		)

		tqdm.write(f"Successfully initialized Gemini model: {LLM_MODEL_NAME} (JSON Mode)")

	except Exception as e:
		tqdm.write(f"Warning: Error initializing Gemini Client ({str(e)}). Proceeding without LLM features.")
		traceback.print_exc()
		LLM_CLIENT = None


# =============================================================================
# EXTRACTION LOGIC
# =============================================================================

def _parse_llm_response(response_text: str) -> List[Tuple[str, str]]:
	"""Parses the JSON response from the LLM, including salvage logic."""
	# (Implementation remains the same as in the original process_ita1997.py)
	references = []
	if not response_text:
		return references

	try:
		data = json.loads(response_text)

		if isinstance(data, list):
			for item in data:
				if isinstance(item, dict):
					normalized_ref = item.get("ref_id")
					text_extract = item.get("snippet")

					if normalized_ref and text_extract:
						references.append((str(normalized_ref).strip(), str(text_extract).strip()))
				else:
					tqdm.write(f"Warning: Gemini returned non-dict item in JSON list. Item: {str(item)[:100]}")
		elif data:
			tqdm.write(f"Warning: Gemini returned unexpected JSON type (expected list). Type: {type(data)}")

	except json.JSONDecodeError as e:
		# Regex Salvage Logic
		tqdm.write(f"Warning: Error parsing Gemini JSON ({str(e)}). Attempting regex salvage...")
		salvaged_references = []

		try:
			potential_objects = re.finditer(r'\{.*?\}', response_text, re.DOTALL)

			for match in potential_objects:
				object_text = match.group(0)
				try:
					item = json.loads(object_text)
					if isinstance(item, dict):
						normalized_ref = item.get("ref_id")
						text_extract = item.get("snippet")
						if normalized_ref and text_extract:
							salvaged_references.append((str(normalized_ref).strip(), str(text_extract).strip()))
				except json.JSONDecodeError:
					continue

			if salvaged_references:
				tqdm.write(f"Successfully salvaged {len(salvaged_references)} entries.")
				references = salvaged_references
			else:
				tqdm.write(f"Salvage failed. Snippet: {response_text[:100]}...")

		except Exception as salvage_error:
			tqdm.write(f"Error during salvage attempt: {str(salvage_error)}. Snippet: {response_text[:100]}...")

	except (TypeError, AttributeError) as e:
		tqdm.write(f"Warning: Error processing Gemini JSON structure ({str(e)}). Snippet: {response_text[:100]}...")

	unique_sorted_references = sorted(list(set(references)), key=lambda x: x[0])
	return unique_sorted_references


def extract_references_with_llm(text_chunk: str) -> tuple[List[Tuple[str, str]], int, int]:
	"""
	Uses the Gemini API (with caching) to extract references.
	"""
	# Ensure client is initialized (lazy initialization)
	if LLM_CLIENT is None:
		initialize_gemini_client()
		if LLM_CLIENT is None:
			return [], 0, 0

	# Optimization 1: Pre-filters (Length check)
	if not text_chunk or not text_chunk.strip() or len(text_chunk) < 10:
		return [], 0, 0

	# Optimization 2: Keyword Pre-filter (Using raw string for regex)
	if not re.search(r'\b(section|division|part|schedule|act|\d{4})\b', text_chunk, re.IGNORECASE):
		return [], 0, 0

	# --- Caching Logic ---
	if GLOBAL_LLM_CACHE:
		cached_response, cached_in_tok, cached_out_tok = GLOBAL_LLM_CACHE.get(text_chunk, LLM_MODEL_NAME)

		if cached_response:
			references = _parse_llm_response(cached_response)
			# Update metrics (counting tokens as they were used originally)
			GLOBAL_COST_TRACKER.update(cached_in_tok, cached_out_tok, is_cache_hit=True)
			return references, int(cached_in_tok or 0), int(cached_out_tok or 0)
	# --- End Caching Logic ---

	# --- API Call (Cache Miss) ---
	try:
		response = LLM_CLIENT.generate_content(text_chunk)

		input_tokens = 0
		output_tokens = 0
		response_text = ""

		# Extract token usage
		if hasattr(response, 'usage_metadata') and response.usage_metadata:
			input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
			output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)

		# Graceful handling of response content
		if (response.candidates and
				response.candidates[0].content and
				response.candidates[0].content.parts):
			response_text = response.candidates[0].content.parts[0].text.strip()

		# Parse the response
		references = _parse_llm_response(response_text)

		# Update cache if successful response was received
		if response_text and GLOBAL_LLM_CACHE:
			GLOBAL_LLM_CACHE.set(text_chunk, LLM_MODEL_NAME, response_text, input_tokens, output_tokens)

		# Update metrics
		GLOBAL_COST_TRACKER.update(input_tokens, output_tokens, is_cache_hit=False)

		return references, input_tokens, output_tokens

	except Exception as e:
		tqdm.write(f"Error calling Gemini API: {type(e).__name__}: {str(e)}")
		return [], 0, 0


# =============================================================================
# CONCURRENT PROCESSING TASK (Used by the Pipeline Runner)
# =============================================================================

def process_section_llm_task(section: Dict, hierarchy_context: List[str]):
	"""
	The task executed by the ThreadPoolExecutor for LLM processing.
	"""
	if not section or not section.get("content_md"):
		return

	try:
		# Build context header (Using standard newlines for the prompt input)
		context_header = ""
		if hierarchy_context:
			# Note: We use double backslashes for newlines as this code is often written into a file by the LLM
			context_header = "CONTEXT: You are processing text within the following hierarchy:\n"
			context_header += "\n".join(hierarchy_context)
			context_header += "\n\n---\n\n"

		full_text_chunk = context_header + section["content_md"]

		# Perform the LLM call (handles caching internally)
		refs, _, _ = extract_references_with_llm(full_text_chunk)

		if refs:
			# Update the section dictionary.
			if "references" not in section or not isinstance(section["references"], set):
				section["references"] = set()

			# Extend the set. (Thread-safe as each worker operates on a unique 'section' dict)
			section["references"].update(refs)

		# Costs are updated within extract_references_with_llm

	except Exception as e:
		tqdm.write(
			f"\nWarning: LLM task failed for section {section.get('title', 'Unknown')}: {type(e).__name__}: {str(e)}")
