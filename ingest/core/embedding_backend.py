from __future__ import annotations

import logging
import threading
from typing import List, Optional

try:
	import numpy as np
except ImportError:  # pragma: no cover - numpy is a hard dependency elsewhere
	np = None

try:
	import torch
	import torch.nn.functional as F
	from transformers import AutoModel, AutoTokenizer
except Exception:  # pragma: no cover - handled gracefully for environments without torch/transformers
	torch = None
	F = None
	AutoModel = None
	AutoTokenizer = None

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, "HFEmbeddingBackend"] = {}
_CACHE_LOCK = threading.Lock()


class EmbeddingBackendUnavailable(RuntimeError):
	"""Raised when the embedding backend cannot be initialized."""


def _resolve_device(preferred: Optional[str] = None) -> str:
	if torch is None:
		return "cpu"
	if preferred:
		return preferred
	if torch.cuda.is_available():
		return "cuda"
	if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
		return "mps"
	return "cpu"


def _resolve_dtype(device: str):
	if torch is None:
		return None
	if device == "cuda":
		return torch.float16
	return torch.float32


class HFEmbeddingBackend:
	"""
	Thin wrapper around Hugging Face Qwen embedding models with chunk/batch helpers.
	Caches tokenizer/model instances per (model_name, device, max_length).
	"""

	def __init__(self, model_name: str, *, device: Optional[str] = None, max_length: int = 8192):
		if torch is None or AutoModel is None or AutoTokenizer is None or np is None:
			raise EmbeddingBackendUnavailable(
				"transformers/torch/numpy stack missing; install dependencies before embedding."
			)
		self.device = _resolve_device(device)
		self.model_name = model_name
		self.max_length = max_length
		dtype = _resolve_dtype(self.device)

		logger.info("Loading embedding model %s on %s (dtype=%s)", model_name, self.device, dtype)
		self.tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="right")
		if self.tokenizer.pad_token_id is None:
			# Qwen tokenizers typically use eos as pad when not defined.
			self.tokenizer.pad_token = self.tokenizer.eos_token

		self.model = AutoModel.from_pretrained(
			model_name,
			torch_dtype=dtype,
			trust_remote_code=False,
		)
		self.model.to(self.device)
		self.model.eval()

	def encode(
			self,
			texts: List[str],
			*,
			batch_size: int = 32,
			instruction: Optional[str] = None,
	) -> np.ndarray:
		"""
		Encode a batch of texts (optionally prepending an instruction to each).
		Returns L2-normalized numpy vectors.
		"""
		if not texts:
			return np.zeros((0, self.model.config.hidden_size), dtype=np.float32)

		def _format(text: str) -> str:
			if instruction:
				return f"Instruct: {instruction}\nQuery:{text}"
			return text

		formatted = [_format(t or "") for t in texts]
		chunks: List[np.ndarray] = []
		for start in range(0, len(formatted), batch_size):
			batch_texts = formatted[start:start + batch_size]
			enc = self.tokenizer(
				batch_texts,
				padding=True,
				truncation=True,
				max_length=self.max_length,
				return_tensors="pt",
			).to(self.device)

			with torch.inference_mode():
				outputs = self.model(**enc)
				pooled = self._last_token_pool(outputs.last_hidden_state, enc["attention_mask"])
				pooled = F.normalize(pooled, p=2, dim=1)
			chunks.append(pooled.cpu().numpy().astype(np.float32))
		return np.vstack(chunks)

	@staticmethod
	def _last_token_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
		sequence_lengths = attention_mask.sum(dim=1) - 1
		sequence_lengths = torch.clamp(sequence_lengths, min=0)
		batch_indices = torch.arange(last_hidden_state.shape[0], device=last_hidden_state.device)
		return last_hidden_state[batch_indices, sequence_lengths]


def get_embedding_backend(model_name: str, *, device: Optional[str] = None, max_length: int = 8192) -> HFEmbeddingBackend:
	cache_key = f"{model_name}:{device or 'auto'}:{max_length}"
	with _CACHE_LOCK:
		if cache_key in _MODEL_CACHE:
			return _MODEL_CACHE[cache_key]
		backend = HFEmbeddingBackend(model_name, device=device, max_length=max_length)
		_MODEL_CACHE[cache_key] = backend
		return backend
