"""Convert N-Quads dump files to individual N-Triples files.

Each .nq file in data/dumps/ is converted to its own .nt file in the data/
directory.  This keeps files small and individual instead of producing one
giant merged file — QLever's `data/*.nt` glob handles multiple input files
natively.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path


# Regex validating a line as a well-formed N-Triples line:
#   <IRI> <IRI> (<IRI>|"literal"...) <IRI_or_literal> .\n
# Must start with <, have 3 or 4 whitespace-delimited tokens (the 3rd token
# may be a literal containing spaces, so we match `"<...>"` or `<...>`),
# and end with ` .`.  IRIs must have matching angle brackets and no embedded
# newlines.
_NT_LINE_RE = re.compile(
    r"^"
    r"<[^>\n]+>"                         # subject IRI
    r"\s+"
    r"<[^>\n]+>"                         # predicate IRI
    r"\s+"
    r"(?:"
    r'"[^"\\]*(?:\\.[^"\\]*)*"(?:@\w+)?(?:'  # literal with optional lang/datatype
    r"\^\^<[^>\n]+>)?"
    r"|<[^>\n]+>"
    r"|_\:[A-Za-z][A-Za-z0-9]*"
    r")"
    r"\s+"
    r"\.\s*$"
)

# Regex to detect unterminated IRIs (starts with < but has no matching >)
_BROKEN_IRI_RE = re.compile(r"<[^>\n]*$")


def _is_valid_nt_line(line: str) -> bool:
    """Return True if *line* is a syntactically valid N-Triples statement."""
    return bool(_NT_LINE_RE.match(line))


def _has_broken_iri(line: str) -> bool:
    """Return True if the line contains an unterminated IRI."""
    # After stripping trailing whitespace, check if the line ends in an unclosed <
    stripped = line.rstrip()
    if stripped.endswith("."):
        return False  # ends properly
    return bool(_BROKEN_IRI_RE.search(stripped))


def convert_nq_dumps_to_individual_nt(active_data_dir: Path, single: bool = False) -> None:
    """Convert each .nq file in data/dumps/ to its own deduplicated .nt file.

    N-Quads format:  <s> <p> <o> <graph> .
    N-Triples format: <s> <p> <o> .

    The graph component (typically a file-import UUID) is stripped so that
    identical triples across files collapse during deduplication.

    Args:
        active_data_dir: Path to the data/ directory (dumps/ must be inside it).
        single: If True, only convert the first .nq file (useful for testing).
    """
    # Ensure logging is configured even when run standalone
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler()],
            force=True,
        )

    dumps_dir = active_data_dir / "dumps"
    if not dumps_dir.exists() or not dumps_dir.is_dir():
        logging.info("No dumps directory found, skipping N-Quads conversion.")
        return

    nq_files = sorted(dumps_dir.glob("*.nq"))
    if not nq_files:
        logging.info("No .nq files found in dumps directory, skipping N-Quads conversion.")
        return

    if single:
        logging.info("--single-dump: converting only the first .nq file")
        nq_files = nq_files[:1]

    logging.info(f"Found {len(nq_files)} N-Quads dump file(s). Converting to individual .nt files…")

    for i, nq_file in enumerate(nq_files, 1):
        nt_file = active_data_dir / f"{nq_file.stem}.nt"
        tmp_file = active_data_dir / f"{nq_file.stem}_tmp.nt"
        valid_file = active_data_dir / f"{nq_file.stem}_valid.nt"

        logging.info(f"  [{i}/{len(nq_files)}] Converting {nq_file.name} → {nt_file.name}")

        # awk: print the first 3 whitespace-separated tokens, append " ."
        # Uses LC_ALL=C for speed (no Unicode locale overhead)
        cmd = (
            f"awk '{{print $1, $2, $3, \".\"}}' '{nq_file}' > '{tmp_file}'"
        )
        try:
            subprocess.run(
                cmd, shell=True, check=True,
                env={**dict(subprocess.os.environ), "LC_ALL": "C"},
            )
        except subprocess.CalledProcessError as exc:
            logging.error(f"  ERROR converting {nq_file.name}: {exc}")
            tmp_file.unlink(missing_ok=True)
            continue

        # Count before dedup
        result = subprocess.run(
            f"wc -l < '{tmp_file}'",
            shell=True, capture_output=True, text=True, check=True,
        )
        before_count = int(result.stdout.strip())

        # Validate and filter malformed lines before dedup
        broken_count = 0
        with open(tmp_file, "r", encoding="utf-8", errors="replace") as inf, \
             open(valid_file, "w", encoding="utf-8") as outf:
            for line in inf:
                line = line.rstrip("\n")
                if _is_valid_nt_line(line):
                    outf.write(line + "\n")
                else:
                    broken_count += 1
                    if _has_broken_iri(line):
                        snippet = line[:200] + ("…" if len(line) > 200 else "")
                        logging.warning(
                            f"    Skipping malformed triple (unterminated IRI): {snippet}"
                        )
                    elif line.strip():
                        snippet = line[:200] + ("…" if len(line) > 200 else "")
                        logging.warning(f"    Skipping malformed triple: {snippet}")

        if broken_count > 0:
            logging.warning(f"    {broken_count} malformed triples filtered out from {nq_file.name}")

        # Deduplicate the validated file
        subprocess.run(
            f"sort -u '{valid_file}' > '{nt_file}'",
            shell=True, check=True,
            env={**dict(subprocess.os.environ), "LC_ALL": "C"},
        )
        tmp_file.unlink(missing_ok=True)
        valid_file.unlink(missing_ok=True)

        result = subprocess.run(
            f"wc -l < '{nt_file}'",
            shell=True, capture_output=True, text=True, check=True,
        )
        after_count = int(result.stdout.strip())
        logging.info(f"    {before_count} → {after_count} triples ({before_count - after_count} removed: duplicates + malformed)")

    # Count total across all .nt files
    result = subprocess.run(
        f"cat '{active_data_dir}'/*.nt 2>/dev/null | wc -l",
        shell=True, capture_output=True, text=True,
    )
    total = int(result.stdout.strip()) if result.stdout.strip() else 0
    logging.info(f"N-Quads conversion complete: {total} total triples across all .nt files in {active_data_dir}")