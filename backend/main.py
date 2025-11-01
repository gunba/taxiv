# backend/main.py
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.database import initialize_engine, Base, get_db
from backend.config import get_settings
# Import models to register them
import backend.models.legislation
# Import CRUD and Schemas
from backend import crud, schemas
from typing import List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="Taxiv API", version="0.1.0")

# CORS Middleware
origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    logger.info("Initializing database connection...")
    try:
        engine = initialize_engine()
        logger.info("Ensuring database tables are created...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialization complete.")
    except Exception as e:
        logger.error(f"Error during database initialization: {e}")


@app.get("/")
def read_root():
    return {"message": "Welcome to the Taxiv API", "environment": settings.ENVIRONMENT}

# --- API Endpoints (Using /api prefix) ---

@app.get("/api/acts", response_model=List[schemas.ActList])
def list_acts(db: Session = Depends(get_db)):
    """Lists all available Acts in the database."""
    return crud.get_acts(db)

@app.get("/api/provisions/{internal_id}", response_model=schemas.ProvisionDetail)
def get_provision_detail(internal_id: str, db: Session = Depends(get_db)):
    """
    Returns the detailed information for a specific provision, including relationships.
    """
    provision_detail = crud.get_provision_detail(db, internal_id)
    if not provision_detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provision not found")
    return provision_detail

@app.get("/api/hierarchy", response_model=List[schemas.ProvisionHierarchy])
def get_hierarchy(
    act_id: str = Query(..., description="The ID of the Act (e.g., ITAA1997)"),
    parent_id: Optional[str] = Query(None, description="The internal_id of the parent provision. If None, returns top-level elements."),
    db: Session = Depends(get_db)
):
    """Get the children of a specific provision or the top-level elements of an Act."""
    return crud.get_hierarchy(db, act_id, parent_id)
