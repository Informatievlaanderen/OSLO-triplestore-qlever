from pathlib import Path
import os


def load_dotenv_if_present(env_path: Path | str = ".env", override: bool = False) -> bool:
    """Load key=value pairs from a local .env file into os.environ.

    Returns True when the file exists and is processed, False otherwise.
    """
    path = Path(env_path)
    if not path.exists():
        return False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]

        if override or key not in os.environ:
            os.environ[key] = value

    return True
