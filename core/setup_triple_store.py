import shutil
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core.clean_data import clean_data
from core.utils import scrape_data, run_command


def prepare_local_qleverfile(config, qlever_dir: Path) -> Path:
    """Create a local Qleverfile with a concrete ACCESS_TOKEN value."""
    source_template = qlever_dir / "Qleverfile.template"
    source_qleverfile = qlever_dir / "Qleverfile"
    target = qlever_dir / "Qleverfile.local"

    source = source_template if source_template.exists() else source_qleverfile
    if not source.exists():
        raise FileNotFoundError(
            f"Neither {source_template} nor {source_qleverfile} exists. "
            "At least one source Qleverfile is required."
        )

    token = str(config.qlever.access_token)
    if not token or token.startswith("${"):
        raise ValueError(
            "qlever.access_token is not resolved. Load your environment (for example from .env) before running commands."
        )

    project_root = Path(__file__).resolve().parents[1]
    render_script = project_root / "scripts" / "render_qleverfile.py"
    if not render_script.exists():
        raise FileNotFoundError(f"Render script not found at {render_script}")

    cmd = [
        sys.executable,
        str(render_script),
        "--template",
        str(source),
        "--output",
        str(target),
        "--token",
        token,
    ]
    try:
        subprocess.run(cmd, cwd=project_root, check=True)
    except subprocess.CalledProcessError as e:
        logging.error("Failed to render local Qleverfile from template.")
        raise RuntimeError("Unable to generate Qleverfile.local") from e

    return target


def setup_logger(log_dir: Path):
    """Configures logging to output to both console and a file in the log directory."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "qlever_initialization.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ],
        force=True
    )


def initialize_qlever_endpoint(config) -> None:
    cwd = Path.cwd()
    date_str = datetime.now().date().isoformat()

    log_dir = cwd / config.files.logs / date_str
    setup_logger(log_dir)
    logging.info("Initializing QLever endpoint.")

    # Define streamlined paths
    qlever_dir = cwd / config.qlever.store_dir
    active_data_dir = qlever_dir / "data"
    archive_dir = qlever_dir / "archive"
    output_dir = cwd / config.scraper.scraper_output_dir

    dataset_name = config.qlever.dataset_name
    active_file = active_data_dir / f"{dataset_name}.nt"

    # Ensure directories exist
    active_data_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Archive the previous active dataset (overwrites existing file)
    if active_file.exists():
        logging.info("Archiving previous active data.")
        archived_active = archive_dir / f"{dataset_name}.previous.nt"
        shutil.move(str(active_file), str(archived_active))

    # Scrape new data
    raw_scraped_file = scrape_data(config, output_dir)

    # Archive the raw scrape (overwrites existing file)
    logging.info("Archiving raw scraped data.")
    archived_raw = archive_dir / f"{dataset_name}.raw.nt"
    shutil.copy2(raw_scraped_file, archived_raw)

    # Clean data in the output directory (specifically ensure integers/strings have correct rdf datatype)
    logging.info("Executing data cleaning routine.")
    cleaned_output = output_dir / f"cleaned_{raw_scraped_file.name}"

    clean_data(database_path=str(output_dir), database_file_name=raw_scraped_file.name)

    # Move final cleaned data to the active QLever directory
    if cleaned_output.exists():
        logging.info("Transferring cleaned data to active datastore.")
        shutil.move(str(cleaned_output), str(active_file))
    else:
        raise FileNotFoundError("Data cleaning failed to produce the expected output file.")

    # Build indexes and start server
    qleverfile_local = prepare_local_qleverfile(config, qlever_dir)
    index_cmd = f"qlever --qleverfile {qleverfile_local.name} index --overwrite-existing"

    logging.info("Building QLever indexes.")
    run_command(index_cmd, cwd=qlever_dir)

    logging.info("Starting QLever endpoint.")
    run_command(f"qlever --qleverfile {qleverfile_local.name} start", cwd=qlever_dir)

def restart_qlever_endpoint(config):
    cwd = Path.cwd()
    date_str = datetime.now().date().isoformat()
    log_dir = cwd / config.files.logs / date_str

    setup_logger(log_dir)
    logging.info("Restarting QLever endpoint.")

    qlever_dir = cwd / config.qlever.store_dir
    qleverfile_local = prepare_local_qleverfile(config, qlever_dir)

    if not qlever_dir.exists():
        logging.error("QLever directory missing. Initialization required.")
        raise FileNotFoundError("QLever directory does not exist. Run initialization first.")

    run_command(f"qlever --qleverfile {qleverfile_local.name} stop", cwd=qlever_dir)
    run_command(f"qlever --qleverfile {qleverfile_local.name} start", cwd=qlever_dir)
    logging.info("QLever endpoint restarted successfully.")

