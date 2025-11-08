# ingest/core/loading.py
import logging
import traceback
from typing import List

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# We reuse the backend's database setup and models for consistency
# Note: This requires the backend module structure to be in the Python path,
# which is handled by the Docker setup (WORKDIR /app).
try:
	from backend.database import get_db, initialize_engine, Base
	from backend.models.legislation import (
		Act,
		Provision,
		Reference,
		DefinedTermUsage,
		BaselinePagerank,
		RelatednessFingerprint,
	)
except ImportError as e:
	logging.error(
		f"Failed to import backend modules. Ensure the environment is set up correctly (e.g., running inside Docker container). Error: {e}")


	# Define placeholder classes if backend imports fail, allowing script initialization but failing at runtime.
	class Act:
		pass


	class Provision:
		pass


	class Reference:
		pass


	class DefinedTermUsage:
		pass


	class BaselinePagerank:
		pass


	class RelatednessFingerprint:
		pass


	def get_db():
		raise ImportError("Database connection unavailable due to import errors.")


	def initialize_engine():
		raise ImportError("Database engine unavailable due to import errors.")


	Base = None

logger = logging.getLogger(__name__)


class DatabaseLoader:
	"""
	Handles loading processed data into the PostgreSQL database.
	"""

	def __init__(self, act_id: str, act_title: str):
		self.act_id = act_id
		self.act_title = act_title
		# Ensure the database connection and schema are ready
		try:
			# This connects to the DB defined in the .env file via backend.config
			engine = initialize_engine()
			if Base:
				# Ensure tables and extensions (ltree) exist (idempotent)
				Base.metadata.create_all(bind=engine)
				self._ensure_required_schema(engine)
		except Exception as e:
			logger.error(f"Database initialization failed. Cannot proceed with loading. Error: {e}")
			raise

	def _ensure_required_schema(self, engine):
		"""
		Heals expected schema drift (e.g., missing columns) that ingestion depends on.
		Adds any nullable/defaulted Provision columns that are absent.
		"""
		table = Provision.__table__
		try:
			inspector = inspect(engine)
			existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
			candidates: List = []

			for column in table.columns:
				if column.name in existing_columns:
					continue
				if not self._can_auto_add(column):
					logger.warning(
						"Skipping auto-creation of column '%s' on '%s' (requires manual migration).",
						column.name,
						table.name,
					)
					continue
				candidates.append(column)

			if not candidates:
				return

			for column in candidates:
				ddl = self._build_add_column_statement(engine, table, column)
				logger.info("Adding missing column '%s' to '%s'.", column.name, table.name)
				try:
					with engine.begin() as connection:
						connection.execute(text(ddl))
				except SQLAlchemyError as exc:
					message = str(exc).lower()
					if "duplicate column" in message or "already exists" in message:
						logger.info("Column '%s' already exists on '%s'; continuing.", column.name, table.name)
						continue
					logger.error("Failed to add column '%s' to '%s': %s", column.name, table.name, exc)
					raise
		except SQLAlchemyError as exc:
			logger.error("Failed to reconcile schema for '%s': %s", table.name, exc)
			raise

	@staticmethod
	def _can_auto_add(column):
		"""
		We only auto-create columns that are safe to add without additional data backfill.
		"""
		if column.info.get("auto_heal"):
			return True
		if column.foreign_keys:
			return False
		if column.autoincrement:
			return False
		if not column.nullable and column.server_default is None and column.default is None:
			return False
		return True

	@staticmethod
	def _build_add_column_statement(engine, table, column):
		preparer = engine.dialect.identifier_preparer
		table_sql = preparer.format_table(table)
		column_sql = preparer.format_column(column)
		type_sql = column.type.compile(dialect=engine.dialect)
		ddl = f"ALTER TABLE {table_sql} ADD COLUMN {column_sql} {type_sql}"

		default_clause = column.server_default
		if default_clause is not None:
			default_sql = default_clause.arg
			if hasattr(default_sql, "compile"):
				default_sql = default_sql.compile(dialect=engine.dialect)
			ddl += f" DEFAULT {default_sql}"

		if column.nullable is False:
			ddl += " NOT NULL"

		return ddl

	def load_data(self, provisions_payload, references_payload, defined_terms_usage_payload):
		"""
		Loads the payload using SQLAlchemy bulk operations.
		"""
		if not provisions_payload:
			logger.info("Payload is empty. Skipping database load.")
			return

		logger.info(f"\n=== Starting Database Load for {self.act_id} ===")

		# Use the session generator (handles session lifecycle)
		db_session_generator = get_db()
		db = None
		try:
			# Get the session object from the generator
			db = next(db_session_generator)
			self._execute_load(db, provisions_payload, references_payload, defined_terms_usage_payload)
		except StopIteration:
			logger.error("Failed to obtain database session.")
		except Exception as e:
			logger.error(f"An unexpected error occurred during database load: {e}")
			logger.error(traceback.format_exc())
		finally:
			# Ensure the generator's finally block runs (closing the session if opened)
			if db:
				try:
					# Closing the session happens in the generator's finally block
					next(db_session_generator)
				except StopIteration:
					pass

	def _execute_load(self, db: Session, provisions_payload, references_payload, defined_terms_usage_payload):
		try:
			# 1. Ensure Act exists and prepare for reload (Idempotency)
			# We use Session.get() for primary key lookup (SQLAlchemy 2.0 style)
			act = db.get(Act, self.act_id)

			if not act:
				logger.info(f"Creating Act record for {self.act_id}...")
				act = Act(id=self.act_id, title=self.act_title)
				db.add(act)
				db.commit()
			else:
				logger.info(f"Act {self.act_id} exists. Preparing to reload data.")
				# Update title if it changed
				if act.title != self.act_title:
					act.title = self.act_title
					db.commit()

				# Clear existing data for this Act.
				# We perform explicit deletion to ensure related data in Reference and DefinedTermUsage tables are removed.
				logger.info(f"Clearing existing provisions and related data for {self.act_id}...")

				# Identify the internal IDs of the provisions belonging to this act
				provision_ids_subquery = db.query(Provision.internal_id).filter(
					Provision.act_id == self.act_id).subquery()

				# Delete related data first due to foreign key constraints
				# Note: We only delete references originating FROM this act. References pointing TO this act from others remain.

				deleted_refs = db.query(Reference).filter(
					Reference.source_internal_id.in_(provision_ids_subquery)).delete(
					synchronize_session=False)
				deleted_terms = db.query(DefinedTermUsage).filter(
					DefinedTermUsage.source_internal_id.in_(provision_ids_subquery)).delete(synchronize_session=False)

				# Delete provisions themselves
				deleted_count = db.query(Provision).filter(Provision.act_id == self.act_id).delete(
					synchronize_session=False)

				# Commit the deletions
				db.commit()
				logger.info(
					f"Cleanup complete. Deleted {deleted_count} provisions, {deleted_refs} references, {deleted_terms} term usages.")

			# 2. Bulk Insert Provisions
			logger.info("Bulk inserting provisions...")
			# bulk_insert_mappings is efficient for large inserts
			if provisions_payload:
				db.bulk_insert_mappings(Provision, provisions_payload)
				db.commit()
				logger.info(f"Successfully inserted {len(provisions_payload)} provisions.")

			# 3. Bulk Insert References
			if references_payload:
				logger.info("Bulk inserting references...")
				# Remove potential duplicates before bulk insert (although analysis phase should handle this)
				# This is necessary because bulk_insert_mappings doesn't automatically handle duplicates based on content.
				unique_references = [dict(t) for t in {tuple(d.items()) for d in references_payload}]
				db.bulk_insert_mappings(Reference, unique_references)
				db.commit()
				logger.info(f"Successfully inserted {len(unique_references)} references.")

			# 4. Bulk Insert Defined Terms Usage
			if defined_terms_usage_payload:
				logger.info("Bulk inserting defined terms usage...")
				# Remove potential duplicates
				unique_terms = [dict(t) for t in {tuple(d.items()) for d in defined_terms_usage_payload}]
				db.bulk_insert_mappings(DefinedTermUsage, unique_terms)
				db.commit()
				logger.info(f"Successfully inserted {len(unique_terms)} defined term usages.")

			logger.info(f"Database load for {self.act_id} completed successfully.")

		except SQLAlchemyError as e:
			if db:
				db.rollback()
			logger.error(f"Database Error during load (SQLAlchemyError). Rolling back. Error: {e}")
			logger.error(traceback.format_exc())
		except Exception as e:
			# Catch non-SQLAlchemy errors
			if db:
				db.rollback()
			logger.error(f"An unexpected error occurred. Rolling back. Error: {e}")
			logger.error(traceback.format_exc())

	def load_relatedness_data(self, baseline_pi: dict, fingerprints: dict):
		"""
		Bulk insert baseline PageRank and personalized fingerprints for the act's provisions.
		"""
		logger.info("Loading relatedness baseline and fingerprints...")
		db_session_generator = get_db()
		db = None
		try:
			db = next(db_session_generator)
			subquery = db.query(Provision.internal_id).filter(Provision.act_id == self.act_id).subquery()
			db.query(BaselinePagerank).filter(BaselinePagerank.provision_id.in_(subquery)).delete(
				synchronize_session=False)
			db.query(RelatednessFingerprint).filter(RelatednessFingerprint.source_id.in_(subquery)).delete(
				synchronize_session=False)
			db.commit()

			if baseline_pi:
				db.bulk_insert_mappings(BaselinePagerank, [
					{"provision_id": provision_id, "pi": float(value)}
					for provision_id, value in baseline_pi.items()
				])
				db.commit()

			if fingerprints:
				rows = []
				for source_id, (neighbors, captured) in fingerprints.items():
					rows.append({
						"source_kind": "provision",
						"source_id": source_id,
						"neighbors": neighbors,
						"captured_mass_provisions": float(captured),
					})
				if rows:
					db.bulk_insert_mappings(RelatednessFingerprint, rows)
					db.commit()

			logger.info(
				"Relatedness data load complete: %d baseline rows, %d fingerprints.",
				len(baseline_pi or {}),
				len(fingerprints or {}),
			)
		except Exception as exc:
			if db:
				db.rollback()
			logger.error("Error loading relatedness data: %s", exc)
			logger.error(traceback.format_exc())
			raise
		finally:
			if db:
				try:
					next(db_session_generator)
				except StopIteration:
					pass
