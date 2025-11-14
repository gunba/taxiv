from __future__ import annotations

import json
import logging
import os
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from typing import Any, Dict, Optional

from backend.database import get_db
from backend.models.semantic import bump_graph_version
from backend.services.relatedness_engine import get_graph_version
from ingest.core import llm_extraction
from ingest.core.analysis import GraphAnalyzer, sanitize_for_ltree
from ingest.core.loading import DatabaseLoader
from ingest.core.progress import progress_bar, progress_write
from ingest.core.relatedness_indexer import (
	RelatednessIndexerConfig,
	build_relatedness_index,
	upsert_provision_embeddings,
)
from ingest.core.utils import recursive_finalize_structure


logger = logging.getLogger(__name__)


def finalize_definitions_pass1(definitions_registry: Dict[str, Dict[str, Any]]) -> None:
	for term in list(definitions_registry.keys()):
		entry = definitions_registry.get(term)
		if not entry:
			continue
		entry["content_md"] = entry.get("content_md", "").strip()
		if not entry["content_md"]:
			definitions_registry.pop(term, None)


def process_and_analyze_definitions_concurrent(
	definitions_registry: Dict[str, Dict[str, Any]],
	parser_module,
	config,
	*,
	executor: Optional[ThreadPoolExecutor],
	pbar_llm=None,
) -> None:
	logger.info("Applying precise term identification and analyzing definitions.")
	futures = []
	definition_context = [f"{config.ACT_ID}:Section:{getattr(config, 'DEFINITION_PROGRESS_LABEL', 'Definitions')}"]

	for term, definition in definitions_registry.items():
		current_content = definition.get("content_md", "")
		if parser_module.DEFINITION_MARKER_REGEX:
			precise_terms = parser_module.identify_defined_terms(current_content)
			definition["defined_terms_used"] = precise_terms

		greedy_terms = parser_module.find_defined_terms_in_text(current_content)
		if greedy_terms:
			existing_terms = definition.get("defined_terms_used")
			if isinstance(existing_terms, set):
				existing_terms.update(greedy_terms)
			elif isinstance(existing_terms, list):
				definition["defined_terms_used"] = set(existing_terms).union(greedy_terms)
			else:
				definition["defined_terms_used"] = set(greedy_terms)

		if (
			executor
			and llm_extraction.LLM_CLIENT
			and current_content
		):
			existing_refs = definition.get("references", set())
			if not isinstance(existing_refs, set):
				refs_set = set(tuple(ref) for ref in existing_refs if isinstance(ref, (list, tuple)))
			else:
				refs_set = existing_refs

			temp_section = {
				"content_md": current_content,
				"references": refs_set,
				"title": f"Def:{term}"
			}
			future = executor.submit(
				llm_extraction.process_section_llm_task,
				temp_section,
				definition_context
			)
			futures.append((future, term, temp_section))

	total_tasks = len(futures) if futures else len(definitions_registry)
	pbar_defs = progress_bar(
		desc="Enriching Definitions",
		total=total_tasks,
		unit="def",
		ncols=100,
		position=2,
		leave=False,
	)

	if futures:
		for future, term, temp_section in futures:
			try:
				future.result()
			except Exception as exc:  # pragma: no cover - defensive logging
				progress_write(f"Error processing definition future for '{term}': {exc}")
			pbar_defs.update(1)
			if pbar_llm:
				pbar_llm.update(1)
				current_cost, *_ = llm_extraction.GLOBAL_COST_TRACKER.get_metrics()
				pbar_llm.set_postfix_str(f"Cost: ${current_cost:.4f}")
			definitions_registry[term]["references"] = temp_section["references"]
	else:
		pbar_defs.update(total_tasks)

	for term in definitions_registry:
		recursive_finalize_structure(definitions_registry[term])

	pbar_defs.close()


def run_parsing_and_enrichment(config, parser_module, *, enable_llm: bool = True) -> None:
	logger.info(f"\n=== PHASE A: PARSING AND ENRICHMENT ({config.ACT_ID}) ===")

	os.makedirs(config.OUTPUT_INTERMEDIATE_DIR, exist_ok=True)
	os.makedirs(config.CACHE_DIR, exist_ok=True)

	definitions_registry = parser_module.DEFINITION_REGISTRY
	definitions_registry.clear()

	llm_requested = enable_llm
	if llm_requested:
		llm_extraction.initialize_gemini_client()
	llm_active = llm_requested and llm_extraction.LLM_CLIENT is not None

	if not llm_active and llm_requested:
		logger.warning("Proceeding without LLM reference extraction for %s.", config.ACT_ID)
	elif not llm_requested:
		logger.info("LLM enrichment disabled for %s.", config.ACT_ID)

	pbar_llm = None
	if llm_active:
		pbar_llm = progress_bar(
			desc="Gemini Processing Status",
			unit="item",
			ncols=100,
			position=1,
			leave=True,
		)
		pbar_llm.set_postfix_str("Cost: $0.0000")

	executor_manager = ThreadPoolExecutor(max_workers=config.MAX_WORKERS) if llm_active else nullcontext(None)

	with executor_manager as executor:
		logger.info("\n--- Pass 1: Extracting Definitions ---")
		def_volume_num = f"{int(config.DEFINITIONS_VOLUME):02d}"
		def_filepath = os.path.join(config.INPUT_DATA_DIR, config.FILE_PATTERN.format(def_volume_num))
		if os.path.exists(def_filepath):
			logger.info("Processing VOL%s (Pass 1)...", def_volume_num)
			parser_module.process_document(def_filepath, pass_num=1)
		else:
			logger.warning("Definition volume (%s) not found at %s.", def_volume_num, def_filepath)

		finalize_definitions_pass1(definitions_registry)
		logger.info("Pass 1 Complete. Extracted %d definitions.", len(definitions_registry))

		parser_module.compile_definition_regex()
		if definitions_registry:
			process_and_analyze_definitions_concurrent(
				definitions_registry,
				parser_module,
				config,
				executor=executor,
				pbar_llm=pbar_llm,
			)

		logger.info("\n--- Pass 2: Full Structure Extraction and Enrichment ---")
		pbar_volumes = progress_bar(
			range(config.START_VOLUME, config.END_VOLUME + 1),
			desc="Overall Volume Processing",
			unit="vol",
			ncols=100,
			position=0,
		)

		for i in pbar_volumes:
			volume_num = f"{i:02d}"
			filename = config.FILE_PATTERN.format(volume_num)
			filepath = os.path.join(config.INPUT_DATA_DIR, filename)
			pbar_volumes.set_description(f"Processing Volume {volume_num}", refresh=True)

			if not os.path.exists(filepath):
				progress_write(f"File not found: {filepath}")
				continue

			volume_futures = [] if executor else None
			structured_data = parser_module.process_document(
				filepath,
				pass_num=2,
				executor=executor,
				futures=volume_futures,
			)

			if volume_futures:
				pbar_volumes.set_description(f"Volume {volume_num}: Waiting for LLM...", refresh=True)
				for future in as_completed(volume_futures):
					try:
						future.result()
					except Exception as exc:  # pragma: no cover - defensive logging
						progress_write(f"Error in completed future for Volume {volume_num}: {exc}")
					if pbar_llm:
						pbar_llm.update(1)
						current_cost, *_ = llm_extraction.GLOBAL_COST_TRACKER.get_metrics()
						pbar_llm.set_postfix_str(f"Cost: ${current_cost:.4f}")

			pbar_volumes.set_description(f"Volume {volume_num}: Finalizing...", refresh=True)
			recursive_finalize_structure(structured_data)

			if not structured_data:
				progress_write(f"\nWarning: No structure extracted from {filename}.")

			output_filename = config.INTERMEDIATE_FILE_PATTERN.format(volume_num)
			output_filepath = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, output_filename)
			try:
				with open(output_filepath, "w", encoding="utf-8") as handle:
					json.dump(structured_data, handle, indent=2, ensure_ascii=False)
				progress_write(f"Successfully saved intermediate file: {output_filename}")
			except Exception as exc:  # pragma: no cover - defensive logging
				progress_write(f"Error saving {output_filename}: {exc}")

		pbar_volumes.close()

	if pbar_llm:
		pbar_llm.close()

	definitions_filename = getattr(config, "DEFINITIONS_INTERMEDIATE_FILENAME", "definitions_intermediate.json")
	if definitions_registry:
		definitions_filepath = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, definitions_filename)
		try:
			sorted_definitions = dict(sorted(definitions_registry.items()))
			with open(definitions_filepath, "w", encoding="utf-8") as handle:
				json.dump(sorted_definitions, handle, indent=2, ensure_ascii=False)
			logger.info("Saved %d definitions to %s", len(definitions_registry), definitions_filename)
		except Exception as exc:  # pragma: no cover - defensive logging
			logger.error("Error saving definitions: %s", exc)

	if llm_active:
		final_cost, total_in, total_out, *_ = llm_extraction.GLOBAL_COST_TRACKER.get_metrics()
		print("\n--- Gemini Usage Summary ---")
		print(f"Model: {llm_extraction.LLM_MODEL_NAME}")
		print(f"Total Input Tokens:  {total_in:,}")
		print(f"Total Output Tokens: {total_out:,}")
		print(f"Estimated Total Cost: ${final_cost:.4f}")


def run_analysis_and_loading(config) -> None:
	logger.info(f"\n=== PHASE B: ANALYSIS AND LOADING ({config.ACT_ID}) ===")
	analyzer = GraphAnalyzer(default_act_id=config.ACT_ID)

	logger.info("\n--- Pass 1: Loading Intermediate Data and Calculating LTree Paths ---")
	processed_files = 0

	file_pattern = config.INTERMEDIATE_FILE_PATTERN
	definitions_file = getattr(config, "DEFINITIONS_INTERMEDIATE_FILENAME", "definitions_intermediate.json")
	act_ltree_root = sanitize_for_ltree(config.ACT_ID)

	volume_indices = range(config.START_VOLUME, config.END_VOLUME + 1)
	pbar_pass1_volumes = progress_bar(
		volume_indices,
		desc="Pass 1: Loading Volumes",
		unit="vol",
		ncols=100,
	)

	for i in pbar_pass1_volumes:
		volume_num = f"{i:02d}"
		filepath = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, file_pattern.format(volume_num))
		if not os.path.exists(filepath):
			progress_write(f"Intermediate file missing for Volume {volume_num}: {filepath}")
			continue
		pbar_pass1_volumes.set_description(f"Pass 1: Volume {volume_num}", refresh=True)
		logger.info("Processing VOL%s (Pass 1)...", volume_num)
		processed_files += 1
		with open(filepath, "r", encoding="utf-8") as handle:
			data = json.load(handle)
		for index, item in enumerate(data):
			analyzer.process_node_pass1(item, ltree_path=act_ltree_root, sibling_index=index)

	pbar_pass1_volumes.close()

	definitions_path = os.path.join(config.OUTPUT_INTERMEDIATE_DIR, definitions_file)
	if os.path.exists(definitions_path):
		logger.info("Attaching definitions from %s", definitions_file)
		with open(definitions_path, "r", encoding="utf-8") as handle:
			definitions_data = json.load(handle)

		parent_ref_id = getattr(
			config,
			"DEFINITION_ANCHOR_REF_ID",
			f"{config.ACT_ID}:Section:{getattr(config, 'DEFINITION_PROGRESS_LABEL', 'Definitions')}",
		)
		parent_internal_id = analyzer.generate_internal_id(ref_id_override=parent_ref_id) if parent_ref_id else None

		if parent_internal_id and parent_internal_id in analyzer.node_registry:
			parent_ltree_obj = analyzer.node_registry[parent_internal_id].get("hierarchy_path_ltree", act_ltree_root)
			parent_ltree_path = str(parent_ltree_obj)
		else:
			if parent_ref_id:
				logger.warning("Definition anchor %s not found. Definitions will be top-level.", parent_ref_id)
			parent_internal_id = None
			parent_ltree_path = act_ltree_root

		definition_items = list(definitions_data.items())
		pbar_definitions = progress_bar(
			definition_items,
			desc="Pass 1: Integrating Definitions",
			unit="def",
			ncols=100,
		)
		for index, (term, data) in enumerate(pbar_definitions):
			sanitized_term_for_id = re.sub(r"[^\w\-]+", "_", term)
			if not sanitized_term_for_id:
				sanitized_term_for_id = f"UnnamedTerm_{time.time_ns()}"

			ref_id = f"{config.ACT_ID}:Definition:{sanitized_term_for_id}"
			synthetic_node = {
				"ref_id": ref_id,
				"type": "Definition",
				"id": sanitized_term_for_id,
				"raw_term": term,
				"name": term,
				"title": term,
				"level": getattr(config, "DEFINITION_SECTION_LEVEL", 5) + 1,
				"content_md": data.get("content_md", ""),
				"references": data.get("references", []),
				"defined_terms_used": data.get("defined_terms_used", []),
				"children": [],
			}
			analyzer.process_node_pass1(
				synthetic_node,
				parent_internal_id,
				parent_ltree_path,
				sibling_index=index,
			)
		pbar_definitions.close()
		processed_files += 1
	else:
		logger.info("Definitions file %s not found; skipping definition ingestion.", definitions_file)

	if processed_files == 0:
		logger.warning("Note: No intermediate input files were processed. Ensure Phase A completed successfully.")
		return

	logger.info("Pass 1 Complete. Structure built with %d nodes.", analyzer.G.number_of_nodes())

	analyzer.add_references_and_validate()
	metrics = analyzer.analyze_graph_metrics()
	provisions_payload, references_payload, defined_terms_usage_payload = analyzer.prepare_database_payload(metrics)

	try:
		loader = DatabaseLoader(act_id=config.ACT_ID, act_title=getattr(config, "ACT_TITLE", config.ACT_ID))
		loader.load_data(provisions_payload, references_payload, defined_terms_usage_payload)
		cfg = RelatednessIndexerConfig()
		cfg.act_id = config.ACT_ID
		try:
			logger.info("Upserting provision embeddings into pgvector...")
			upsert_provision_embeddings(
				provisions_payload,
				model_name=cfg.embedding_model_name,
				batch_size=cfg.embedding_batch_size,
			)
		except Exception as embed_error:  # pragma: no cover - best-effort logging
			logger.error("Embedding upsert failed: %s", embed_error)
		try:
			logger.info("Computing relatedness baseline and fingerprints...")
			baseline_pi, fingerprints = build_relatedness_index(
				provisions_payload,
				references_payload,
				defined_terms_usage_payload,
				cfg,
			)
			target_graph_version = None
			db_gen = None
			try:
				db_gen = get_db()
				db = next(db_gen)
				current_version = get_graph_version(db)
				target_graph_version = (current_version or 0) + 1
				logger.info("Preparing relatedness data for graph version %d.", target_graph_version)
			except Exception as version_error:  # pragma: no cover
				logger.error("Failed to read current graph version: %s", version_error)
			finally:
				if db_gen:
					try:
						next(db_gen)
					except StopIteration:
						pass

			loader.load_relatedness_data(baseline_pi, fingerprints, graph_version=target_graph_version)

			db_gen = None
			try:
				db_gen = get_db()
				db = next(db_gen)
				new_version = bump_graph_version(db)
				if target_graph_version and new_version != target_graph_version:
					logger.warning(
						"Graph version bumped to %d but expected %d.",
						new_version,
						target_graph_version,
					)
				else:
					logger.info("Graph version bumped to %d.", new_version)
			except Exception as version_error:  # pragma: no cover
				logger.error("Failed to bump graph version: %s", version_error)
			finally:
				if db_gen:
					try:
						next(db_gen)
					except StopIteration:
						pass
		except Exception as relatedness_error:  # pragma: no cover
			logger.error("Relatedness indexing failed: %s", relatedness_error)
			logger.error(traceback.format_exc())
	except Exception as exc:  # pragma: no cover
		logger.error("Database loading failed: %s", exc)
		logger.error(traceback.format_exc())

	analyzer.write_unresolved_log(config.OUTPUT_FINAL_DIR)
	logger.info("\nPhase B: Analysis and Loading Complete.")


def ensure_env_loaded() -> None:
	if os.getenv("DB_HOST"):
		return
	try:
		from dotenv import load_dotenv

		dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
		dotenv_path = os.path.abspath(dotenv_path)
		if os.path.exists(dotenv_path):
			load_dotenv(dotenv_path)
			logger.info("Loaded local .env file for environment variables.")
		else:
			logger.warning("Local .env file not found. Relying on system environment variables.")
	except ImportError:
		logger.warning("python-dotenv not installed. Relying on system environment variables.")
