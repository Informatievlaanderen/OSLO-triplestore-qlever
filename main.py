import argparse
from pathlib import Path
from omegaconf import OmegaConf

from core.env_loader import load_dotenv_if_present
from core.setup_triple_store import initialize_qlever_endpoint, restart_qlever_endpoint
from core.update_pipeline import execute_update_pipeline
from core.validate import validate_endpoint


def load_config(config_path: Path):
    load_dotenv_if_present()
    if not config_path.exists():
        raise FileNotFoundError(
            f"{config_path} not found. Please ensure the file exists at the specified path."
        )
    return OmegaConf.load(config_path)


def main():
    parser = argparse.ArgumentParser(description="Data Vlaanderen Pipeline Manager")

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("triple_store_config.yaml"),
        help="Path to the configuration YAML file (default: triple_store_config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_init = subparsers.add_parser(
        "init",
        help="Start the endpoint from a clean slate and obtain all current data.",
    )

    parser_init.add_argument(
        "--with-dumps",
        action="store_true",
        default=False,
        help="Also include all quads from qlever/data/dumps/*.nq files during initialization.",
    )

    parser_init.add_argument(
        "--single-dump",
        action="store_true",
        default=False,
        help="When used with --with-dumps, only convert the first .nq file (useful for testing).",
    )

    parser_restart = subparsers.add_parser(
        "restart", help="Restart the endpoint from a previous state."
    )

    parser_update = subparsers.add_parser(
        "update",
        help="Manually obtain the latest data and rebuild the index/calculate diffs.",
    )

    parser_validate = subparsers.add_parser(
        "validate",
        help="Run validation queries against the endpoint and log performance metrics.",
    )

    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "init":
        initialize_qlever_endpoint(config, with_dumps=args.with_dumps, single_dump=args.single_dump)
    elif args.command == "restart":
        restart_qlever_endpoint(config)
    elif args.command == "update":
        execute_update_pipeline(config)
    elif args.command == "validate":
        validate_endpoint(config)


if __name__ == "__main__":
    main()