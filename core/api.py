import secrets
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from omegaconf import OmegaConf

from core.env_loader import load_dotenv_if_present
from core.update_pipeline import execute_update_pipeline

# Initialize application and security schema
app = FastAPI(title="Data Vlaanderen Pipeline API")
security = HTTPBearer()


def load_config():
    load_dotenv_if_present()
    config_path = Path("triple_store_config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    return OmegaConf.load(config_path)


# Load configuration globally for the API instance
config = load_config()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verifies the bearer token against the configured access token in constant time."""
    expected_token = config.server.access_token

    if not secrets.compare_digest(credentials.credentials, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@app.post("/update", status_code=status.HTTP_202_ACCEPTED)
def trigger_update(background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    """
    Triggers the update pipeline.
    Requires a valid bearer token matching the QLever access token.
    """
    background_tasks.add_task(execute_update_pipeline, config)
    return {"message": "Update pipeline initiated in the background."}