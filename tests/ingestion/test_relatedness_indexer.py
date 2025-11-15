from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from ingest.core import relatedness_indexer as ri


def test_split_into_chunks_handles_overlap():
	text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
	chunks = ri._split_into_chunks(text, chunk_chars=12, overlap=4)
	assert len(chunks) >= 2
	for chunk in chunks:
		assert len(chunk) <= 12
	assert chunks[0].startswith("Lorem ipsum")
	assert chunks[1][0].isalpha()


def test_upsert_provision_embeddings_invokes_backend(monkeypatch):
	provisions = [
		{"internal_id": "A", "title": "First", "content_md": "alpha beta gamma delta epsilon"},
		{"internal_id": "B", "title": "Second", "content_md": "zeta eta theta iota kappa lambda mu"},
	]

	backend_calls = []

	class StubBackend:
		def encode(self, texts, batch_size=32, instruction=None):
			backend_calls.append({"texts": texts, "batch_size": batch_size, "instruction": instruction})
			length = len(texts)
			data = np.arange(length * 4, dtype=np.float32).reshape(length, 4)
			return data

	monkeypatch.setattr(ri, "get_embedding_backend", lambda *args, **kwargs: StubBackend())

	fake_query = MagicMock()
	fake_query.filter.return_value = fake_query
	fake_query.delete.return_value = 0

	fake_session = MagicMock()
	fake_session.query.return_value = fake_query

	def fake_get_db():
		yield fake_session

	monkeypatch.setattr(ri, "get_db", fake_get_db)

	cfg = SimpleNamespace(
		embedding_model_name="test-model",
		embedding_device=None,
		embedding_batch_size=2,
		embedding_max_length=512,
		embedding_instruction=None,
		chunk_chars=10,
		chunk_overlap=2,
	)
	monkeypatch.setattr(ri, "RelatednessIndexerConfig", lambda: cfg)

	ri.upsert_provision_embeddings(provisions, model_name="test-model", batch_size=2)

	assert backend_calls, "Embedding backend was not invoked"
	assert backend_calls[0]["batch_size"] == 2
	assert fake_session.merge.call_count == len(provisions)
	for call in fake_session.merge.call_args_list:
		embedding_obj = call.args[0]
		assert embedding_obj.model == "test-model"
		assert embedding_obj.dim == len(embedding_obj.vector)
		np.testing.assert_allclose(np.linalg.norm(embedding_obj.vector), 1.0, atol=1e-5)
