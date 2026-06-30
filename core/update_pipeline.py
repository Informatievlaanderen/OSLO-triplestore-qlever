import shutil
import time
import urllib.request
import urllib.parse
import urllib.error
import logging
from datetime import datetime, timezone
from pathlib import Path
import rdflib
import subprocess

from core.utils import run_command, scrape_data

BASE_DIR = Path(__file__).resolve().parent


def setup_logger(log_dir: Path) -> None:
    """Configures logging to output to both console and a file in the log directory."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pipeline_execution.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ],
        force=True
    )


def count_lines(file_path: Path) -> int:
    """Counts the number of lines in a given text file."""
    with file_path.open('r', encoding='utf-8') as f:
        return sum(1 for _ in f)


def validate_rdf_syntax(file_path: Path, rdf_format: str = "nt") -> bool:
    """Validates RDF syntax using rdflib. Defaults to N-Triples format."""
    logging.info(f"Validating syntax for: {file_path.name}")
    graph = rdflib.Graph()
    try:
        graph.parse(file_path, format=rdf_format)
        return True
    except Exception as error:
        logging.error(f"Validation failed. Syntax error in {file_path.name}: {error}")
        return False


def send_sparql_update(
        port: int,
        query: str,
        access_token: str,
        max_retries: int = 3,
        backoff_factor: float = 2.0
):
    """Transmits a SPARQL update query to the QLever endpoint with exponential backoff."""
    url = f"http://localhost:{port}/"
    data = query.encode('utf-8')

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/sparql-update',
        'Authorization': f'Bearer {access_token}'
    }

    req = urllib.request.Request(url, data=data, headers=headers)

    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()
        except urllib.error.URLError as error:
            logging.warning(f"Network error on attempt {attempt}/{max_retries}: {error}")
            if attempt == max_retries:
                logging.error("Maximum retry attempts reached.")
                raise ConnectionError(f"Failed to update QLever after {max_retries} attempts.") from error
            time.sleep(backoff_factor ** attempt)
    return None


def update_qlever(config, additions_file: Path, deletions_file: Path) -> None:
    """Applies calculated additions and deletions to the active QLever endpoint."""
    logging.info("Applying updates to QLever...")

    with deletions_file.open('r', encoding='utf-8') as f:
        deletions = f.read().strip()
    if deletions:
        logging.info("Sending DELETE DATA query.")
        send_sparql_update(config.qlever.port, f"DELETE DATA {{ {deletions} }}", config.qlever.access_token)

    if additions_file.exists() and additions_file.stat().st_size > 0:
        if not validate_rdf_syntax(additions_file):
            raise ValueError("Pipeline halted: Invalid RDF syntax detected in additions file.")

        with additions_file.open('r', encoding='utf-8') as f:
            additions = f.read().strip()
        if additions:
            logging.info("Sending INSERT DATA query.")
            send_sparql_update(config.qlever.port, f"INSERT DATA {{ {additions} }}", config.qlever.access_token)


def calculate_diffs(config, output_dir: Path, log_directory: Path) -> tuple[int, int]:
    """Generates differential files between previous and current datasets."""
    logging.info("Calculating differentials...")

    previous_file = output_dir / config.files.previous
    current_file = output_dir / config.files.sorted
    additions_file = output_dir / config.files.additions
    deletions_file = output_dir / config.files.deletions

    run_command(f"comm -13 {previous_file} {current_file} > {additions_file}")
    run_command(f"comm -23 {previous_file} {current_file} > {deletions_file}")

    additions_count = count_lines(additions_file)
    deletions_count = count_lines(deletions_file)

    shutil.copy2(additions_file, log_directory / config.files.additions)
    shutil.copy2(deletions_file, log_directory / config.files.deletions)

    return additions_count, deletions_count


def rebuild_qlever_index_cli(config: dict) -> None:
    """
    Rebuilds the base index, generates a text index, and attempts an endpoint restart.
    If the restart fails, it initiates a rollback to the previous indexes to prevent downtime.
    """
    qlever_config = config["qlever"]
    store_dir = Path(qlever_config["store_dir"])
    previous_indexes_dir = Path(qlever_config["previous_indexes_dir"])
    base_name = qlever_config.get("name", "data_vlaanderen_endpoint")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = store_dir / previous_indexes_dir / f"previous.{timestamp}.ORIGINAL"

    # Absorb accumulated .update-triples delta and build the base index.
    try:
        run_command("qlever rebuild-index", cwd=store_dir, lenient=True, fail_patterns = ("ERROR", "FATAL"))
    except subprocess.CalledProcessError as e:
        logging.info(f"Captured expected error: {e}")

    tmp_files = list(store_dir.glob("rebuild.*.tmp"))
    if not tmp_files:
        logging.error("No temporary rebuild directories found.")
        raise FileNotFoundError("No temporary rebuild directories found.")

    tmp_dir = max(tmp_files)
    if not tmp_dir.is_dir():
        logging.error(f"Expected temporary directory not found: {tmp_dir}")
        raise RuntimeError(f"Expected temporary directory not found: {tmp_dir}")

    # Build the text index inside the temporary directory.
    run_command("qlever add-text-index", cwd=tmp_dir)

    # Stop the active endpoint prior to migrating files.
    run_command("qlever stop", cwd=store_dir)

    # Archive the active index files.
    backup_dir.mkdir(parents=True, exist_ok=True)
    for file_path in store_dir.glob(f"{base_name}.*"):
        if file_path.is_file() and file_path.name not in ("README.md", "Qleverfile"):
            shutil.move(str(file_path), str(backup_dir / file_path.name))

    # Deploy the newly built files to the live store directory.
    for file_path in tmp_dir.iterdir():
        shutil.move(str(file_path), str(store_dir / file_path.name))

    # Attempt to start the server and validate the deployment.
    try:
        logging.info("Initiating endpoint restart with new indexes.")
        run_command("qlever start --kill-existing-with-same-port", cwd=store_dir, lenient=True)
        logging.info("Endpoint restart successful.")

        # Execute cleanup on success.
        if any(tmp_dir.iterdir()):
            logging.warning(f"Temporary directory {tmp_dir} retains residual files.")
        else:
            tmp_dir.rmdir()

    except Exception as error:
        logging.error("Endpoint initialization failed. Initiating rollback sequence.")

        # Move the faulty indexes back to the temporary directory for debugging.
        for file_path in store_dir.glob(f"{base_name}.*"):
            if file_path.is_file() and file_path.name not in ("README.md", "Qleverfile"):
                shutil.move(str(file_path), str(tmp_dir / file_path.name))

        # Restore the archived indexes.
        for file_path in backup_dir.iterdir():
            shutil.move(str(file_path), str(store_dir / file_path.name))

        logging.info("Archived indexes restored. Restarting primary endpoint.")
        run_command("qlever start --kill-existing-with-same-port", cwd=store_dir)

        raise RuntimeError("Deployment aborted due to startup failure. Rollback executed.") from error

def execute_update_pipeline(config) -> None:
    """Executes the complete data scraping and QLever update sequence."""
    cwd = Path.cwd()
    date_str = datetime.now().date().isoformat()
    log_dir = cwd / config.files.logs / date_str
    output_dir = cwd / config.scraper.scraper_output_dir

    output_dir.mkdir(parents=True, exist_ok=True)
    setup_logger(log_dir)
    logging.info("Initializing update pipeline.")

    previous_output = output_dir / config.files.previous
    current_output_sorted = output_dir / config.files.sorted

    if current_output_sorted.exists():
        logging.info("Archiving previous run...")
        current_output_sorted.rename(previous_output)
    else:
        previous_output.touch()

    scrape_data(config, output_dir)

    additions_count, deletions_count = calculate_diffs(config, output_dir, log_dir)
    logging.info(f"Differentials calculated: {additions_count} additions, {deletions_count} deletions.")

    update_qlever(config, output_dir / config.files.additions, output_dir / config.files.deletions)

    if additions_count > 0 or deletions_count > 0:
        rebuild_qlever_index_cli(config)

    logging.info("Update pipeline complete.")