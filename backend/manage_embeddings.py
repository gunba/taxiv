import argparse
import logging

from sqlalchemy import text

from backend.database import Base, initialize_engine

logger = logging.getLogger(__name__)


def resize_vector_column(dim: int, truncate: bool) -> None:
	engine = initialize_engine()
	Base.metadata.create_all(bind=engine)
	with engine.connect() as conn:
		if truncate:
			logger.info("Truncating embeddings table before resizing vector dimension...")
			conn.execute(text("TRUNCATE TABLE embeddings;"))
		logger.info("Dropping existing HNSW index if present...")
		conn.execute(text("DROP INDEX IF EXISTS ix_embeddings_vector_hnsw;"))
		logger.info("Altering embeddings.vector to dimension %d...", dim)
		conn.execute(text("ALTER TABLE embeddings ALTER COLUMN vector TYPE vector(:dim);"), {"dim": dim})
		conn.execute(text("ALTER TABLE embeddings ALTER COLUMN dim SET DEFAULT :dim;"), {"dim": dim})
		conn.execute(text("UPDATE embeddings SET dim = :dim;"), {"dim": dim})
		logger.info("Recreating HNSW index for the resized vector column...")
		conn.execute(
			text("CREATE INDEX IF NOT EXISTS ix_embeddings_vector_hnsw ON embeddings USING hnsw (vector vector_l2_ops);")
		)
		conn.commit()
		logger.info("Embedding dimension resize complete.")


def main() -> int:
	parser = argparse.ArgumentParser(description="Embedding maintenance utilities.")
	subparsers = parser.add_subparsers(dest="command")

	resize_parser = subparsers.add_parser(
		"resize-vector",
		help="Resize the pgvector embeddings column and rebuild the HNSW index.",
	)
	resize_parser.add_argument("--dim", type=int, default=1024, help="Target vector dimension (default: 1024).")
	resize_parser.add_argument(
		"--skip-truncate",
		action="store_true",
		help="Skip truncating the embeddings table before resizing (only safe if the table is empty).",
	)

	args = parser.parse_args()
	if args.command == "resize-vector":
		if args.skip_truncate:
			logger.warning("Skipping truncate; ensure the embeddings table is empty before resizing.")
		resize_vector_column(dim=args.dim, truncate=not args.skip_truncate)
		return 0
	parser.print_help()
	return 1


if __name__ == "__main__":
	raise SystemExit(main())
