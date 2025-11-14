import hashlib
import json
import logging
from pathlib import Path

from ingest.core.conversion import convert_rtf_to_docx
from ingest.pipelines.base_act import BaseActPipeline
from ingest.pipelines.docx_pipeline import (
	ensure_env_loaded,
	run_analysis_and_loading,
	run_parsing_and_enrichment,
)
from ingest.pipelines.itaa1997 import parser as shared_parser

from .config import Config


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def _conversion_manifest_path(config: Config) -> Path:
	return Path(config.INPUT_DATA_DIR) / "conversion_manifest.json"


def _load_conversion_manifest(config: Config) -> dict:
	path = _conversion_manifest_path(config)
	if not path.exists():
		return {}
	try:
		with path.open("r", encoding="utf-8") as handle:
			data = json.load(handle)
		if isinstance(data, dict):
			return data
	except (OSError, json.JSONDecodeError):
		logger.warning("Failed to parse %s; rebuilding conversion manifest.", path)
	return {}


def _save_conversion_manifest(config: Config, manifest: dict) -> None:
	path = _conversion_manifest_path(config)
	try:
		with path.open("w", encoding="utf-8") as handle:
			json.dump(manifest, handle, indent=2, ensure_ascii=False)
	except OSError as exc:  # pragma: no cover - filesystem failure guard
		logger.error("Unable to persist conversion manifest %s: %s", path, exc)


def _hash_file(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def prepare_converted_inputs(config: Config) -> None:
	raw_dir = Path(config.RAW_INPUT_DIR)
	if not raw_dir.exists():
		raise FileNotFoundError(f"RTF input directory {raw_dir} does not exist")

	rtf_files = sorted(raw_dir.glob("*.rtf"))
	if not rtf_files:
		raise FileNotFoundError(f"No RTF files found under {raw_dir}")

	expected = config.END_VOLUME - config.START_VOLUME + 1
	if len(rtf_files) != expected:
		logger.warning(
			"Expected %s RTF files for %s but found %s",
			expected,
			config.ACT_ID,
			len(rtf_files),
		)

	manifest = _load_conversion_manifest(config)
	updated_manifest = {}

	logger.info("Converting %s RTF volumes for %s", len(rtf_files), config.ACT_ID)
	for offset, source in enumerate(rtf_files, start=config.START_VOLUME):
		if offset > config.END_VOLUME:
			logger.warning("Skipping extra RTF file %s; volume range exhausted.", source.name)
			break
		volume_token = f"{offset:02d}"
		dest_name = config.FILE_PATTERN.format(volume_token)
		dest_path = Path(config.INPUT_DATA_DIR) / dest_name
		source_hash = _hash_file(source)
		entry = manifest.get(source.name)
		if (
			dest_path.exists()
			and entry
			and entry.get("sha256") == source_hash
		):
			logger.info("Skipping conversion for %s (unchanged).", source.name)
			updated_manifest[source.name] = entry
			continue

		logger.info("Converting %s -> %s", source.name, dest_name)
		convert_rtf_to_docx(source, dest_path)
		updated_manifest[source.name] = {
			"sha256": source_hash,
			"docx": dest_name,
		}

	_save_conversion_manifest(config, updated_manifest)


class Itaa1936Pipeline(BaseActPipeline):
	def __init__(self):
		self.config = Config()
		super().__init__(self.config.ACT_ID)

	def run_phase_a(self) -> None:
		prepare_converted_inputs(self.config)
		with shared_parser.use_config(self.config):
			run_parsing_and_enrichment(self.config, shared_parser, enable_llm=False)

	def run_phase_b(self) -> None:
		run_analysis_and_loading(self.config)


def main():
	ensure_env_loaded()
	Itaa1936Pipeline().run()


if __name__ == "__main__":
	main()
