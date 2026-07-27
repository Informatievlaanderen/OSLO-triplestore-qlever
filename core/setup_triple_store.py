import os
import shutil
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import rdflib

from core.clean_data import clean_data
from core.logger import setup_logger
from core.qleverfile import prepare_local_qleverfile
from core.utils import scrape_data, run_command


def _download_codelists(dataset_url: str, target_dir: Path) -> list[Path]:
    """Download all .ttl codelist files referenced in a dataset.json.

    Args:
        dataset_url: URL to the dataset.json file.
        target_dir: Directory to save downloaded .ttl files into.

    Returns:
        List of paths to the downloaded files.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    logging.info("Fetching codelists dataset from %s", dataset_url)
    try:
        with urllib.request.urlopen(dataset_url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        logging.error("Failed to fetch or parse dataset.json: %s", exc)
        raise

    concept_schemes = data.get("conceptSchemes", [])
    if not concept_schemes:
        logging.warning("dataset.json contains no 'conceptSchemes' entries.")
        return downloaded

    logging.info("Found %d concept scheme(s) in dataset.json.", len(concept_schemes))

    for entry in concept_schemes:
        source_url = entry.get("sourceUrl")
        url_ref = entry.get("urlRef", "unknown")
        if not source_url:
            logging.warning("Skipping entry '%s': no sourceUrl.", url_ref)
            continue

        # Derive a filename: use the last path component, fall back to urlRef
        filename = source_url.rstrip("/").split("/")[-1]
        if not filename.endswith(".ttl"):
            filename = f"{url_ref}.ttl"
        nt_filename = filename.replace(".ttl", ".nt")

        nt_dest = target_dir / nt_filename
        if nt_dest.exists():
            logging.info("Codelist '%s' already cached, skipping.", nt_filename)
            downloaded.append(nt_dest)
            continue

        logging.info("Downloading codelist: %s -> %s", source_url, filename)
        try:
            ttl_dest = target_dir / filename
            urllib.request.urlretrieve(source_url, str(ttl_dest))

            # Convert .ttl → .nt (QLever only supports N-Triples/N-Quads, not Turtle)
            g = rdflib.Graph()
            g.parse(str(ttl_dest), format="turtle")
            g.serialize(destination=str(nt_dest), format="nt")
            ttl_dest.unlink()  # Remove the .ttl, keep only .nt
            downloaded.append(nt_dest)
            logging.info("Converted %s -> %s", filename, nt_filename)
        except urllib.error.URLError as exc:
            logging.error("Failed to download '%s': %s", source_url, exc)

    logging.info("Downloaded %d codelist file(s) to %s.", len(downloaded), target_dir)
    return downloaded


def initialize_qlever_endpoint(
    config,
    dumps_dir: Path | None = None,
    single_dump: bool = False,
    codelists_dataset_url: str | None = None,
) -> None:
    """Initialize the QLever endpoint from scratch.

    Args:
        config: The application configuration.
        dumps_dir: Optional path to a directory of ``*.nq`` (N-Quads) dump files.
                   When provided, the scraper is skipped and QLever indexes the
                   ``.nq`` files directly using its native N-Quads parser.
        single_dump: When ``True``, only the first ``.nq`` file is indexed
                     (useful for testing).
        codelists_dataset_url: Optional URL to a ``dataset.json`` file containing
                               a ``conceptSchemes`` list. Each entry's ``sourceUrl``
                               is downloaded as a ``.ttl`` and indexed into its own
                               named graph alongside the main data.
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

        try:
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
        except (SystemExit, Exception) as exc:
            logging.warning("Scraper step failed, proceeding with fallback data: %s", exc)
            # Restore archived data if available, otherwise start with empty dataset
            archived_active = archive_dir / f"{dataset_name}.previous.nt"
            if archived_active.exists():
                logging.info("Restoring previous data from archive.")
                shutil.move(str(archived_active), str(active_file))
            else:
                logging.warning("No previous data available, starting with empty dataset.")
                active_file.touch()

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

    # Download codelists from dataset.json if a URL was provided
    extra_files: list[Path] = []
    if codelists_dataset_url:
        codelists_dir = qlever_dir / "codelists"
        extra_files = _download_codelists(codelists_dataset_url, codelists_dir)

    # Build indexes and start server
    qleverfile_local = prepare_local_qleverfile(
        config, qlever_dir, qlever_data_dir,
        base_dir=qlever_dir,
        rdf_format=rdf_format, input_glob=input_glob,
        extra_files=extra_files,
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

