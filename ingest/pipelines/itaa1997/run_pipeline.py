# ingest/pipelines/itaa1997/run_pipeline.py
import json
import logging
import os
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

# Import core modules
# MODIFICATION: Import the module itself
from ingest.core import llm_extraction
from ingest.core.analysis import GraphAnalyzer, sanitize_for_ltree
from ingest.core.relatedness_indexer import build_relatedness_index, RelatednessIndexerConfig
from ingest.core.loading import DatabaseLoader
from ingest.core.utils import recursive_finalize_structure
# Import pipeline-specific modules
# We import the functions and global state variables from the parser module as adapted in Phase 1.
from .config import Config
from .parser import (
        process_document, compile_definition_regex, DEFINITIONS_995_1, DEFINITION_MARKER_REGEX,
        identify_defined_terms, find_defined_terms_in_text
)

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

ACT_TITLE = "Income Tax Assessment Act 1997"


# =============================================================================
# PHASE A Helpers (Adapted from process_ita1997.py)
# These functions operate on the global state imported from .parser
# =============================================================================

def finalize_definitions_pass1():
	"""Strips whitespace from definitions collected in Pass 1."""
	# Operates on the global DEFINITIONS_995_1 imported from .parser
	for term in list(DEFINITIONS_995_1.keys()):
		if term in DEFINITIONS_995_1:
			DEFINITIONS_995_1[term]["content_md"] = DEFINITIONS_995_1[term]["content_md"].strip()
			if not DEFINITIONS_995_1[term]["content_md"]:
				del DEFINITIONS_995_1[term]


def process_and_analyze_definitions_concurrent(pbar_llm, executor, config: Config):
	"""
	Applies precise term identification and runs concurrent LLM analysis on definitions.
	(Adapted from process_ita1997.py)
	"""
	logger.info("Applying precise term identification and analyzing definitions concurrently (Gemini)...")
	futures = []
	definition_context = [f"{config.ACT_ID}:Section:995-1"]

	# 1. Re-identify terms using the precise regex and submit LLM tasks
	for term in DEFINITIONS_995_1:
		current_content = DEFINITIONS_995_1[term]["content_md"]

                # If the precise regex is available (compiled in the parser module), use it.
                if DEFINITION_MARKER_REGEX:
                        # identify_defined_terms (from .parser) uses the global DEFINITION_MARKER_REGEX
                        precise_terms = identify_defined_terms(current_content)
                        # Overwrite the terms identified by the fallback regex in Pass 1.
                        DEFINITIONS_995_1[term]["defined_terms_used"] = precise_terms

                greedy_terms = find_defined_terms_in_text(current_content)
                if greedy_terms:
                        existing_terms = DEFINITIONS_995_1[term].get("defined_terms_used")
                        if isinstance(existing_terms, set):
                                existing_terms.update(greedy_terms)
                        elif isinstance(existing_terms, list):
                                DEFINITIONS_995_1[term]["defined_terms_used"] = set(existing_terms).union(greedy_terms)
                        else:
                                DEFINITIONS_995_1[term]["defined_terms_used"] = set(greedy_terms)

                # 2. Submit LLM analysis to the pool
                if llm_extraction.LLM_CLIENT and current_content:
			# Prepare temporary structure for the LLM task
			existing_refs = DEFINITIONS_995_1[term].get("references", set())
			if not isinstance(existing_refs, set):
				refs_set = set(tuple(ref) for ref in existing_refs if isinstance(ref, (list, tuple)))
			else:
				refs_set = existing_refs

			temp_section = {
				"content_md": current_content,
				"references": refs_set,
				"title": f"Def:{term}"
			}
			# Submit the task
			future = executor.submit(
				llm_extraction.process_section_llm_task,  # Use the module path for the task too
				temp_section,
				definition_context
			)
			futures.append((future, term, temp_section))

	# 3. Wait for completion and update results
	total_tasks = len(futures) if futures else len(DEFINITIONS_995_1)
	pbar_defs = tqdm(desc="Enriching Definitions", total=total_tasks, unit="def", ncols=100, position=2, leave=False)

	if futures:
		for future, term, temp_section in futures:
			try:
				future.result()
			except Exception as e:
				tqdm.write(f"Error processing definition future for '{term}': {str(e)}")

			pbar_defs.update(1)
			pbar_llm.update(1)
			current_cost, _, _, _, _ = llm_extraction.GLOBAL_COST_TRACKER.get_metrics()  # Use module path
			pbar_llm.set_postfix_str(f"Cost: ${current_cost:.4f}")

			# Map results back (worker updates temp_section["references"] in place)
			DEFINITIONS_995_1[term]["references"] = temp_section["references"]
	else:
		pbar_defs.update(total_tasks)

	# 4. Finalize the definitions structure (convert Sets to Lists)
	for term in DEFINITIONS_995_1:
		recursive_finalize_structure(DEFINITIONS_995_1[term])

	pbar_defs.close()


# =============================================================================
# PHASE A: PARSING AND ENRICHMENT
# =============================================================================

def run_parsing_and_enrichment(config: Config):
	"""
	PHASE A: Executes the two-pass DOCX parsing and concurrent LLM enrichment.
	(Adapted from process_ita1997.py main())
	"""
	logger.info(f"\n=== PHASE A: PARSING AND ENRICHMENT ({config.ACT_ID}) ===")

	# Setup directories
	os.makedirs(config.OUTPUT_INTERMEDIATE_DIR, exist_ok=True)
	os.makedirs(config.CACHE_DIR, exist_ok=True)

	# Initialize Gemini Client (uses GOOGLE_CLOUD_API_KEY from env)

	# MODIFICATION: Access LLM_CLIENT via its module
	print(f"LLM_CLIENT before initialization: {llm_extraction.LLM_CLIENT}")
	llm_extraction.initialize_gemini_client()
	print(f"LLM_CLIENT after initialization: {llm_extraction.LLM_CLIENT}")

	logger.info(f"Starting Processing (Concurrent Workers: {config.MAX_WORKERS})...")
	# MODIFICATION: Access LLM_CLIENT via its module
	if not llm_extraction.LLM_CLIENT:
		logger.warning("CRITICAL WARNING: Proceeding without LLM reference extraction.")

	# Initialize the LLM progress bar (Position 1)
	pbar_llm = tqdm(desc="Gemini Processing Status", unit="item", ncols=100, position=1, leave=True)
	pbar_llm.set_postfix_str("Cost: $0.0000")

	# Initialize Thread Pool Executor
	with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:

		# --- PASS 1: Extract Definitions (Volume 10 ONLY for ITAA1997) ---
		logger.info("\n--- Pass 1: Extracting Definitions ---")
		volume_num_pass1 = "10"
		filepath_pass1 = os.path.join(config.INPUT_DATA_DIR, config.FILE_PATTERN.format(volume_num_pass1))

		if os.path.exists(filepath_pass1):
			logger.info(f"Processing VOL{volume_num_pass1} (Pass 1)...")
			# Pass 1 is sequential. process_document updates the global DEFINITIONS_995_1
			process_document(filepath_pass1, pass_num=1)
		else:
			logger.warning(f"Definition Volume (10) not found at {filepath_pass1}.")

		finalize_definitions_pass1()
		logger.info(f"Pass 1 Complete. Extracted {len(DEFINITIONS_995_1)} definitions.")

		# --- INTERMEDIATE STEP: Compile Regex and Analyze Definitions ---
		compile_definition_regex()  # Updates the global DEFINITION_MARKER_REGEX in .parser

		if DEFINITIONS_995_1:
			process_and_analyze_definitions_concurrent(pbar_llm, executor, config)

		# --- PASS 2: Full Structure Extraction and Enrichment ---
		logger.info("\n--- Pass 2: Full Structure Extraction and Enrichment ---")

		pbar_volumes = tqdm(range(1, 11), desc="Overall Volume Processing", unit="vol", ncols=100, position=0)

		for i in pbar_volumes:
			volume_num = f"{i:02d}"
			filename = config.FILE_PATTERN.format(volume_num)
			filepath = os.path.join(config.INPUT_DATA_DIR, filename)

			pbar_volumes.set_description(f"Processing Volume {volume_num}", refresh=True)

			if os.path.exists(filepath):
				# Track futures for this specific volume
				volume_futures = []

				# Process the document, submitting tasks to the executor via the callback
				structured_data = process_document(
					filepath,
					pass_num=2,
					executor=executor,
					futures=volume_futures
				)

				# Wait for this volume's LLM tasks to complete
				if volume_futures:
					pbar_volumes.set_description(f"Volume {volume_num}: Waiting for LLM...", refresh=True)

					# Process futures as they complete (this blocks until the volume is done)
					for future in as_completed(volume_futures):
						try:
							future.result()  # Wait and check for exceptions
						except Exception as e:
							tqdm.write(f"Error in completed future for Volume {volume_num}: {str(e)}")

						pbar_llm.update(1)

						# Update cost display (main thread)
						current_cost, _, _, _, _ = llm_extraction.GLOBAL_COST_TRACKER.get_metrics()
						pbar_llm.set_postfix_str(f"Cost: ${current_cost:.4f}")

				pbar_volumes.set_description(f"Volume {volume_num}: Finalizing...", refresh=True)

				# Finalize the structure (convert Sets to Lists)
				recursive_finalize_structure(structured_data)

				if not structured_data and i <= 10:
					tqdm.write(f"\nWarning: No structure extracted from {filename}.")

				# Save the volume JSON (Intermediate Output)
				output_filename = f"ITAA1997_VOL{volume_num}_intermediate.json"
				output_filepath = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, output_filename)

				try:
					with open(output_filepath, 'w', encoding='utf-8') as f:
						json.dump(structured_data, f, indent=2, ensure_ascii=False)
					tqdm.write(f"Successfully saved intermediate file: {output_filename}")
				except Exception as e:
					tqdm.write(f"Error saving {output_filename}: {str(e)}")
			else:
				if i <= 10:
					tqdm.write(f"File not found: {filepath}")

	# Close the progress bars
	pbar_llm.close()
	pbar_volumes.close()

	# Save the finalized definitions file
	if DEFINITIONS_995_1:
		definitions_filename = "definitions_995_1_intermediate.json"
		definitions_filepath = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, definitions_filename)
		try:
			# Sort by the term (key)
			sorted_definitions = dict(sorted(DEFINITIONS_995_1.items()))
			with open(definitions_filepath, 'w', encoding='utf-8') as f:
				json.dump(sorted_definitions, f, indent=2, ensure_ascii=False)
			logger.info(f"\nSuccessfully saved {len(DEFINITIONS_995_1)} definitions to {definitions_filename}")
		except Exception as e:
			logger.error(f"Error saving definitions: {str(e)}")

	logger.info("\nPhase A: Parsing and Enrichment complete.")
	if llm_extraction.LLM_CLIENT:
		final_cost, total_in, total_out, _, _ = llm_extraction.GLOBAL_COST_TRACKER.get_metrics()
		print(f"\n--- Gemini Usage Summary ---")
		print(f"Model: {llm_extraction.LLM_MODEL_NAME}")
		print(f"Total Input Tokens:  {total_in:,}")
		print(f"Total Output Tokens: {total_out:,}")
		print(f"Estimated Total Cost: ${final_cost:.4f}")


# =============================================================================
# PHASE B: ANALYSIS AND LOADING
# =============================================================================

def run_analysis_and_loading(config: Config):
	"""
	PHASE B: Reads intermediate files, analyzes, and loads into PostgreSQL.
	(Adapted from analyze_and_ingest.py main())
	"""
	logger.info(f"\n=== PHASE B: ANALYSIS AND LOADING (PostgreSQL) ===")

	# Initialize Analyzer
	analyzer = GraphAnalyzer(default_act_id=config.ACT_ID)

	# --- PASS 1: Load Data and Build Structure (LTree Calculation) ---
	logger.info("\n--- Pass 1: Loading Intermediate Data and Calculating LTree Paths ---")

	processed_files = 0

	# Define patterns for intermediate files
	FILE_PATTERN = "ITAA1997_VOL{}_intermediate.json"
	DEFINITIONS_FILE = "definitions_995_1_intermediate.json"

	# Sanitize Act ID for LTree root path
	ACT_LTREE_ROOT = sanitize_for_ltree(config.ACT_ID)

	# --- Load Volume Files First ---
	# This establishes the main structure and LTree paths.
	for i in range(1, 11):
		volume_num = f"{i:02d}"
		filepath = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, FILE_PATTERN.format(volume_num))

		if os.path.exists(filepath):
			logger.info(f"Processing VOL{volume_num} (Pass 1)...")
			processed_files += 1
			try:
				with open(filepath, 'r', encoding='utf-8') as f:
					data = json.load(f)
				for index, item in enumerate(data):
					# ADAPTED: Start LTree path calculation with the sanitized Act ID
					analyzer.process_node_pass1(item, ltree_path=ACT_LTREE_ROOT, sibling_index=index)
			except Exception as e:
				logger.error(f"Error (Pass 1) processing {filepath}: {e}")
				logger.error(traceback.format_exc())

	# --- Load Definitions File (After main structure) ---
	# This allows definitions to link to their parent (e.g., 995-1) if it was processed above.
	def_filepath = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, DEFINITIONS_FILE)
	if os.path.exists(def_filepath):
		logger.info(f"Processing Definitions File (Pass 1)...")
		processed_files += 1
		try:
			with open(def_filepath, 'r', encoding='utf-8') as f:
				definitions_data = json.load(f)

			# Attempt to find the parent (Section 995-1)
			parent_ref_id = f"{config.ACT_ID}:Section:995-1"
			parent_internal_id = analyzer.generate_internal_id(ref_id_override=parent_ref_id)

			if parent_internal_id in analyzer.node_registry:
				# Parent exists, use its LTree path
				parent_ltree_obj = analyzer.node_registry[parent_internal_id].get("hierarchy_path_ltree",
																				  ACT_LTREE_ROOT)
				parent_ltree_path = str(parent_ltree_obj)
			else:
				logger.warning("Parent section 995-1 not found in registry. Definitions will be top-level.")
				parent_internal_id = None
				parent_ltree_path = ACT_LTREE_ROOT

			for index, (term, data) in enumerate(definitions_data.items()):
				# Reconstruct the synthetic node structure (Logic from original script)
				sanitized_term_for_id = re.sub(r'[^\w\-]+', '_', term)
				if not sanitized_term_for_id:
					sanitized_term_for_id = f"UnnamedTerm_{time.time_ns()}"

				ref_id = f"{config.ACT_ID}:Definition:{sanitized_term_for_id}"

				synthetic_node = {
					"ref_id": ref_id, "type": "Definition",
					"id": sanitized_term_for_id,  # local_id
					"raw_term": term,
					"name": term,
					"title": term, "level": 6, "content_md": data.get("content_md", ""),
					"references": data.get("references", []),
					"defined_terms_used": data.get("defined_terms_used", []), "children": []
				}
				# Process the definition node, passing the parent context
				analyzer.process_node_pass1(synthetic_node, parent_internal_id, parent_ltree_path, sibling_index=index)

		except Exception as e:
			logger.error(f"Error (Pass 1) loading definitions file {def_filepath}: {e}")
			logger.error(traceback.format_exc())

	if processed_files == 0:
		logger.warning("Note: No intermediate input files were processed. Ensure Phase A completed successfully.")
		return

	logger.info(f"Pass 1 Complete. Structure built with {analyzer.G.number_of_nodes()} nodes.")

	# --- PASS 2: Add References & Validate ---
	analyzer.add_references_and_validate()

	# --- Analysis and Loading ---
	metrics = analyzer.analyze_graph_metrics()
	provisions_payload, references_payload, defined_terms_usage_payload = analyzer.prepare_database_payload(metrics)

	try:
		# Initialize the loader (connects to the DB defined in .env)
		loader = DatabaseLoader(act_id=config.ACT_ID, act_title=ACT_TITLE)
		# Load the data (Bulk insert)
		loader.load_data(provisions_payload, references_payload, defined_terms_usage_payload)
		try:
			logger.info("Computing relatedness index (baseline + fingerprints)...")
			cfg = RelatednessIndexerConfig()
			baseline_pi, fingerprints = build_relatedness_index(
				provisions_payload,
				references_payload,
				defined_terms_usage_payload,
				cfg
			)
			loader.load_relatedness_data(baseline_pi, fingerprints)
		except Exception as relatedness_error:
			logger.error(f"Relatedness indexing failed: {relatedness_error}")
			logger.error(traceback.format_exc())
	except Exception as e:
		logger.error(f"Database loading failed: {e}")
		logger.error(traceback.format_exc())

	# Write Log
	analyzer.write_unresolved_log(config.OUTPUT_FINAL_DIR)

	logger.info("\nPhase B: Analysis and Loading Complete.")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
	config = Config()

	# Set environment variable context for database connection (Required if running locally outside Docker)
	# If running inside Docker, these are already set by docker-compose.
	if not os.getenv("DB_HOST"):
		# Attempt to load .env from the project root
		try:
			from dotenv import load_dotenv
			# Calculate path relative to this script: ingest/pipelines/itaa1997/run_pipeline.py -> project_root/.env
			dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
			if os.path.exists(dotenv_path):
				load_dotenv(dotenv_path)
				logger.info("Loaded local .env file for environment variables.")
			else:
				logger.warning("Local .env file not found. Relying on system environment variables.")
		except ImportError:
			logger.warning("python-dotenv not installed. Relying on system environment variables.")

	# === PHASE A: PARSING AND ENRICHMENT ===
	# Comment this out if you only want to run Phase B on existing intermediate files.
	run_parsing_and_enrichment(config)

	# === PHASE B: ANALYSIS AND LOADING ===
	run_analysis_and_loading(config)


if __name__ == '__main__':
	# To run this pipeline:
	# 1. Ensure Docker Compose is running (docker-compose up -d)
	# 2. Execute this script within the 'backend' container:
	#    docker-compose exec backend python -m ingest.pipelines.itaa1997.run_pipeline
	main()
