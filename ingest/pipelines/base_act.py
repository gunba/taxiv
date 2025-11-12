from __future__ import annotations

import logging
from abc import ABC, abstractmethod


class BaseActPipeline(ABC):
	"""Shared structure for act ingestion pipelines."""

	def __init__(self, act_id: str):
		self.act_id = act_id
		self.logger = logging.getLogger(self.__class__.__name__)

	def run(self) -> None:
		self.logger.info("Starting ingestion for %s", self.act_id)
		self.run_phase_a()
		self.run_phase_b()
		self.logger.info("Completed ingestion for %s", self.act_id)

	@abstractmethod
	def run_phase_a(self) -> None:  # pragma: no cover - interface
		"""Parse raw sources and emit intermediate artifacts."""

	@abstractmethod
	def run_phase_b(self) -> None:  # pragma: no cover - interface
		"""Analyze parsed output and load it into the database."""
