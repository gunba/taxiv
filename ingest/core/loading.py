# ingest/core/loading.py
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import traceback

# We reuse the backend's database setup and models for consistency
# Note: This requires the backend module structure to be in the Python path,
# which is handled by the Docker setup (WORKDIR /app).
try:
    from backend.database import get_db, initialize_engine, Base
    from backend.models.legislation import Act, Provision, Reference, DefinedTermUsage
except ImportError as e:
    logging.error(f"Failed to import backend modules. Ensure the environment is set up correctly (e.g., running inside Docker container). Error: {e}")
    # Define placeholder classes if backend imports fail, allowing script initialization but failing at runtime.
    class Act: pass
    class Provision: pass
    class Reference: pass
    class DefinedTermUsage: pass
    def get_db(): raise ImportError("Database connection unavailable due to import errors.")
    def initialize_engine(): raise ImportError("Database engine unavailable due to import errors.")
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
        except Exception as e:
            logger.error(f"Database initialization failed. Cannot proceed with loading. Error: {e}")
            raise

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
                provision_ids_subquery = db.query(Provision.internal_id).filter(Provision.act_id == self.act_id).subquery()

                # Delete related data first due to foreign key constraints
                # Note: We only delete references originating FROM this act. References pointing TO this act from others remain.

                deleted_refs = db.query(Reference).filter(Reference.source_internal_id.in_(provision_ids_subquery)).delete(synchronize_session=False)
                deleted_terms = db.query(DefinedTermUsage).filter(DefinedTermUsage.source_internal_id.in_(provision_ids_subquery)).delete(synchronize_session=False)

                # Delete provisions themselves
                deleted_count = db.query(Provision).filter(Provision.act_id == self.act_id).delete(synchronize_session=False)

                # Commit the deletions
                db.commit()
                logger.info(f"Cleanup complete. Deleted {deleted_count} provisions, {deleted_refs} references, {deleted_terms} term usages.")


            # 2. Bulk Insert Provisions
            logger.info("Bulk inserting provisions...")
            # bulk_insert_mappings is efficient for large inserts
            if provisions_payload:
                # Ensure LTree path is explicitly a string before bulk insert
                for provision in provisions_payload:
                    if 'hierarchy_path_ltree' in provision and not isinstance(provision['hierarchy_path_ltree'], str):
                         provision['hierarchy_path_ltree'] = str(provision['hierarchy_path_ltree'])

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
