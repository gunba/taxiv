import logging

from ingest.pipelines.base_act import BaseActPipeline
from ingest.pipelines.docx_pipeline import (
	ensure_env_loaded,
	run_analysis_and_loading,
	run_parsing_and_enrichment,
)

from .config import Config
from . import parser


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


class Itaa1997Pipeline(BaseActPipeline):
	def __init__(self):
		self.config = Config()
		super().__init__(self.config.ACT_ID)

	def run_phase_a(self) -> None:
		run_parsing_and_enrichment(self.config, parser, enable_llm=True)

	def run_phase_b(self) -> None:
		run_analysis_and_loading(self.config)


def main():
	ensure_env_loaded()
	Itaa1997Pipeline().run()


if __name__ == "__main__":
	main()
