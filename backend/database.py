import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Define the Base for models
Base = declarative_base()

# Global engine initialization
engine = None


def initialize_engine(max_retries=5, delay=5):
	"""Initializes the database engine and ensures extensions are enabled."""
	global engine
	if engine:
		return engine

	logger.info(f"Attempting to connect to database at {settings.DB_HOST}:{settings.DB_PORT}...")

	# Retry mechanism for Docker environments
	for attempt in range(max_retries):
		try:
			engine = create_engine(
				settings.DATABASE_URL,
				echo=settings.ENVIRONMENT == "development"
			)

			# Test connection and enable extensions
			with engine.connect() as connection:
				connection.execute(text("CREATE EXTENSION IF NOT EXISTS ltree;"))
				connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
				connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
				connection.commit()

			logger.info("Database connection successful and 'ltree', 'vector', 'pg_trgm' extensions ensured.")
			return engine

		except SQLAlchemyError as e:
			logger.warning(f"Database connection failed (Attempt {attempt + 1}/{max_retries}): {e}")
			if attempt < max_retries - 1:
				time.sleep(delay)
			else:
				logger.error("Maximum retries reached. Could not initialize the database.")
				raise


# Initialize SessionLocal using the potentially delayed engine initialization
def get_session_local():
	engine = initialize_engine()
	return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency injection utility for FastAPI
def get_db():
	SessionLocal = get_session_local()
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()
