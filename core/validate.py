import csv
import hashlib
import json
import logging
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import matplotlib.pyplot as plt
import pandas as pd
import requests
from omegaconf import OmegaConf, DictConfig

def setup_logger(config: DictConfig) -> Path:
    """Configures the logging module and returns the daily log directory path."""
    log_base_dir = Path(config.files.logs)
    current_date = datetime.now().date().isoformat()
    log_dir = log_base_dir / current_date

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "validation.log"

    logging.getLogger().handlers.clear()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_dir


def get_directory_size_mb(directory_path: Path) -> float:
    """Calculate the total size of a directory and its subdirectories in megabytes."""
    if not directory_path.exists():
        return 0.0
    total_size = sum(f.stat().st_size for f in directory_path.rglob('*') if f.is_file())
    return total_size / (1024 * 1024)


def generate_deterministic_hash(is_construct: bool, response_text: str, parsed_data: dict = None) -> tuple[str, str]:
    """Generate a stable SHA-256 hash and return the normalized string used for hashing."""
    if is_construct:
        lines = [line.strip() for line in response_text.split('\n') if line.strip()]
        normalized_content = '\n'.join(sorted(lines))
    else:
        bindings = []
        if parsed_data and "results" in parsed_data and "bindings" in parsed_data["results"]:
            bindings = parsed_data["results"]["bindings"]

        stringified_rows = [json.dumps(row, sort_keys=True) for row in bindings]
        normalized_content = '\n'.join(sorted(stringified_rows))

    result_hash = hashlib.sha256(normalized_content.encode('utf-8')).hexdigest()
    return result_hash, normalized_content


def execute_sparql_query(endpoint_url: str, query: str) -> Dict[str, Any]:
    """Execute a single SPARQL query, measure latency, and hash the results."""
    is_construct = "CONSTRUCT" in query.upper()

    if is_construct:
        headers = {"Accept": "application/n-triples"}
    else:
        headers = {"Accept": "application/sparql-results+json"}

    start_time = time.time()
    response = requests.post(endpoint_url, data={"query": query}, headers=headers)
    response.raise_for_status()
    latency = time.time() - start_time

    parsed_data = None
    result_count = 0

    try:
        if is_construct:
            lines = response.text.strip().split('\n')
            result_count = len([line for line in lines if line.strip()])
        else:
            parsed_data = response.json()
            if "results" in parsed_data and "bindings" in parsed_data["results"]:
                result_count = len(parsed_data["results"]["bindings"])

    except ValueError:
        logging.error(f"Failed to parse response. Raw output snippet:\n{response.text[:500]}")

    result_hash, normalized_content = generate_deterministic_hash(is_construct, response.text, parsed_data)

    return {
        "latency_seconds": latency,
        "result_count": result_count,
        "result_hash": result_hash,
        "raw_response": response.text,
        "normalized_response": normalized_content
    }


def validate_endpoint(config: DictConfig, num_runs: int = 20) -> None:
    """Execute validation queries multiple times and compare result hashes."""
    log_dir = setup_logger(config)
    mismatch_dir = log_dir / "mismatches"

    endpoint_url = f"http://localhost:{config.qlever.port}/sparql"

    store_dir = Path(config.qlever.store_dir)
    queries_dir = Path(config.validation.queries_dir)
    log_file = Path(config.validation.log_file)
    plot_file = Path(config.validation.plot_file)

    hash_file = Path(config.validation.get("hash_file", "./validation_data/result_hashes.json"))

    timestamp = datetime.now(timezone.utc).isoformat()
    file_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    log_exists = log_file.exists()

    index_size_mb = get_directory_size_mb(store_dir)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.parent.mkdir(parents=True, exist_ok=True)

    if hash_file.exists():
        with open(hash_file, 'r', encoding='utf-8') as f:
            baseline_hashes = json.load(f)
    else:
        baseline_hashes = {}

    with open(log_file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not log_exists:
            writer.writerow([
                "timestamp",
                "query_name",
                "latency_seconds",
                "latency_std_dev",
                "result_count",
                "index_size_mb",
                "hash_status"
            ])

        for query_file in queries_dir.glob("*.rq"):
            query_text = query_file.read_text(encoding="utf-8")
            query_name = query_file.name
            logging.info(f"Executing {query_name} ({num_runs} runs)...")

            latencies = []
            result_count = 0
            current_hash = ""
            raw_response = ""
            normalized_response = ""

            try:
                for i in range(num_runs):
                    stats = execute_sparql_query(endpoint_url, query_text)
                    latencies.append(stats['latency_seconds'])
                    if i == 0:
                        result_count = stats['result_count']
                        current_hash = stats['result_hash']
                        raw_response = stats['raw_response']
                        normalized_response = stats['normalized_response']

                mean_latency = statistics.mean(latencies)
                std_dev = statistics.stdev(latencies) if num_runs > 1 else 0.0

                baselines_dir = hash_file.parent / "baselines"
                baselines_dir.mkdir(parents=True, exist_ok=True)
                baseline_text_file = baselines_dir / f"{query_name}.txt"

                if query_name in baseline_hashes:
                    if baseline_hashes[query_name] != current_hash:
                        hash_status = "MISMATCH"

                        mismatch_dir.mkdir(parents=True, exist_ok=True)
                        mismatch_file = mismatch_dir / f"{query_name}_{file_timestamp}_mismatch.txt"

                        with open(mismatch_file, "w", encoding="utf-8") as mf:
                            mf.write(f"Query: {query_name}\n")
                            mf.write(f"Expected Hash: {baseline_hashes[query_name]}\n")
                            mf.write(f"Received Hash: {current_hash}\n")
                            mf.write(f"Compare against: {baseline_text_file}\n")
                            mf.write("-" * 50 + "\n")
                            mf.write("NORMALIZED RESPONSE (Used for hashing):\n")
                            mf.write("-" * 50 + "\n")
                            mf.write(normalized_response)

                        logging.warning(
                            f"Hash mismatch for {query_name}! Detailed output saved to {mismatch_file}"
                        )
                    else:
                        hash_status = "MATCH"
                else:
                    logging.info(f"New baseline hash recorded for {query_name}.")
                    baseline_hashes[query_name] = current_hash
                    hash_status = "NEW"

                    with open(baseline_text_file, "w", encoding="utf-8") as bf:
                        bf.write(normalized_response)

                writer.writerow([
                    timestamp,
                    query_name,
                    f"{mean_latency:.4f}",
                    f"{std_dev:.4f}",
                    result_count,
                    f"{index_size_mb:.2f}",
                    hash_status
                ])
            except Exception as e:
                logging.error(f"Failed to execute {query_name}: {e}")

    with open(hash_file, 'w', encoding='utf-8') as f:
        json.dump(baseline_hashes, f, indent=4)

    logging.info("Validation complete. Generating performance plot.")
    generate_performance_plot(log_file, plot_file)


def generate_performance_plot(log_file: Path, output_plot: Path) -> None:
    """Generate a line plot showing mean latency evolution with error bars for standard deviation."""
    if not log_file.exists():
        logging.warning("No historical data found to plot.")
        return

    df = pd.read_csv(log_file, parse_dates=["timestamp"])
    has_std = "latency_std_dev" in df.columns

    plt.figure(figsize=(12, 6))
    for query_name, group in df.groupby("query_name"):
        if has_std:
            yerr = group["latency_std_dev"].fillna(0)
            plt.errorbar(
                group["timestamp"],
                group["latency_seconds"],
                yerr=yerr,
                marker="o",
                capsize=5,
                label=query_name
            )
        else:
            plt.plot(
                group["timestamp"],
                group["latency_seconds"],
                marker="o",
                label=query_name
            )

    plt.title("SPARQL Endpoint Query Latency Evolution")
    plt.xlabel("Execution Date")
    plt.ylabel("Latency (Seconds)")
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()

    output_plot.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_plot)
    plt.close()


if __name__ == "__main__":
    config_path = Path("triple_store_config.yaml")

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")

    cfg = OmegaConf.load(config_path)
    validate_endpoint(cfg)