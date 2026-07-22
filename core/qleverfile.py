"""QLeverfile template rendering and preparation."""

import logging
import subprocess
import sys
from pathlib import Path


def prepare_local_qleverfile(config, qlever_dir: Path, data_dir: Path | None = None) -> Path:
    """Create a local Qleverfile with a concrete ACCESS_TOKEN value."""
    project_root = Path(__file__).resolve().parents[1]
    source_template = qlever_dir / "Qleverfile.template"
    fallback_template = project_root / "templates" / "Qleverfile.template"
    source_qleverfile = qlever_dir / "Qleverfile"
    target = project_root / "Qleverfile.local"

    if source_template.exists():
        source = source_template
    elif source_qleverfile.exists():
        source = source_qleverfile
    elif fallback_template.exists():
        source = fallback_template
    else:
        source = None

    if source is None:
        raise FileNotFoundError(
            f"Neither {source_template} nor {source_qleverfile} nor {fallback_template} exists. "
            "At least one source Qleverfile is required."
        )

    token = str(config.qlever.access_token)
    if not token or token.startswith("${"):
        raise ValueError(
            "qlever.access_token is not resolved. Load your environment (for example from .env) before running commands."
        )

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
    if data_dir is not None:
        cmd.extend(["--data-dir", str(data_dir)])
    try:
        subprocess.run(cmd, cwd=project_root, check=True)
    except subprocess.CalledProcessError as e:
        logging.error("Failed to render local Qleverfile from template.")
        raise RuntimeError("Unable to generate Qleverfile.local") from e

    return target