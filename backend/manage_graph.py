import argparse
import logging

from sqlalchemy.orm import Session

from backend.database import Base, get_session_local, initialize_engine
from backend.models.semantic import bump_graph_version, ensure_graph_meta_seed, GraphMeta

logger = logging.getLogger(__name__)


def _get_session() -> Session:
	SessionLocal = get_session_local()
	return SessionLocal()


def _show_version(db: Session) -> int:
	row = db.query(GraphMeta).order_by(GraphMeta.id.desc()).first()
	if not row:
		row = ensure_graph_meta_seed(db)
	return row.graph_version


def main() -> int:
	parser = argparse.ArgumentParser(description="Graph metadata management commands.")
	subparsers = parser.add_subparsers(dest="command")

	subparsers.add_parser("show-version", help="Display the current graph version.")
	subparsers.add_parser("bump-version", help="Increment the graph version.")

	args = parser.parse_args()
	if not args.command:
		parser.print_help()
		return 1

	engine = initialize_engine()
	Base.metadata.create_all(bind=engine)

	session = _get_session()
	try:
		if args.command == "show-version":
			version = _show_version(session)
			print(f"Current graph_version: {version}")
		elif args.command == "bump-version":
			version = bump_graph_version(session)
			print(f"Bumped graph_version to: {version}")
		else:
			parser.print_help()
			return 1
	finally:
		session.close()

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
