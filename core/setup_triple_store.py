import os
import shutil
import logging
from datetime import datetime
from pathlib import Path

from core.clean_data import clean_data
from core.logger import setup_logger
from core.qleverfile import prepare_local_qleverfile
from core.utils import scrape_data, run_command


def initialize_qlever_endpoint(config, dumps_dir: Path | None = None, single_dump: bool = False) -> None:
    """Initialize the QLever endpoint from scratch.

    Args:
        config: The application configuration.
        dumps_dir: Optional path to a directory of ``*.nq`` (N-Quads) dump files.
                   When provided, the scraper is skipped and QLever indexes the
                   ``.nq`` files directly using its native N-Quads parser.
        single_dump: When ``True``, only the first ``.nq`` file is indexed
                     (useful for testing).
    """
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

    if dumps_dir is None:
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

        # Scraper produces .nt files in data/
        qlever_data_dir = active_data_dir
        rdf_format = "nt"
        input_glob = "data/*.nt"
    else:
        dumps_dir = dumps_dir.resolve()
        if not dumps_dir.exists() or not dumps_dir.is_dir():
            raise FileNotFoundError(f"Dumps directory not found: {dumps_dir}")

        nq_files = sorted(dumps_dir.glob("*.nq"))
        if not nq_files:
            raise FileNotFoundError(f"No .nq files found in: {dumps_dir}")

        logging.info(
            "--with-dumps: skipping scraper, using %d N-Quads dump file(s) from %s.",
            len(nq_files), dumps_dir,
        )

        if single_dump:
            nq_files = nq_files[:1]
            logging.info("--single-dump: using only %s", nq_files[0].name)

        # Point QLever directly at the .nq dump files — no conversion needed.
        # QLever natively supports N-Quads (.nq) format.
        qlever_data_dir = dumps_dir
        rdf_format = "nq"

        # Compute the INPUT_FILES glob relative to qlever_dir (where the index
        # command runs).  qlever-control requires a relative glob pattern.
        try:
            rel_dumps = dumps_dir.relative_to(qlever_dir)
        except ValueError:
            rel_dumps = Path(os.path.relpath(dumps_dir, qlever_dir))
        input_glob = str(rel_dumps / "*.nq")

    # Build indexes and start server
    qleverfile_local = prepare_local_qleverfile(
        config, qlever_dir, qlever_data_dir,
        base_dir=qlever_dir,
        rdf_format=rdf_format, input_glob=input_glob,
    )
    index_cmd = f"qlever --qleverfile {qleverfile_local} index --overwrite-existing --parser-buffer-size=100MB"

    logging.info("Building QLever indexes.")
    run_command(index_cmd, cwd=qlever_dir)

    logging.info("Starting QLever endpoint.")
    run_command(f"qlever --qleverfile {qleverfile_local} start", cwd=qlever_dir)

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

    run_command(f"qlever --qleverfile {qleverfile_local} stop", cwd=qlever_dir)
    run_command(f"qlever --qleverfile {qleverfile_local} start", cwd=qlever_dir)
    logging.info("QLever endpoint restarted successfully.")

