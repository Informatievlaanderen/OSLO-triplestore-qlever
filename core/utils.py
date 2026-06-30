import shutil
import sys
import subprocess
from pathlib import Path
import logging

def run_command(command: str, cwd: Path = None, lenient: bool = False,
                 fail_patterns: tuple[str, ...] | None = None):
    """Executes a shell command synchronously and pipes output to the console.

    If fail_patterns is provided, output is streamed line-by-line and the process
    is killed as soon as a matching line appears, raising as a failure. This is
    useful for commands that hang instead of exiting non-zero on a known failure mode.
    """
    working_dir = cwd or Path.cwd()
    logging.info(f"\n> Executing: {command}")

    if fail_patterns is None:
        # For commands that actually exit. Optionally allow commands to not exit
        # the program
        try:
            subprocess.run(command, shell=True, check=True, cwd=working_dir)
        except subprocess.CalledProcessError as e:
            logging.error(f"\nProcess failed during: {command}")
            logging.error(e)
            if lenient:
                raise e
            sys.exit(1)
        except Exception as eGeneral:
            logging.error(f"\nProcess failed during: {command} \n Error: {eGeneral}")
            if lenient:
                raise eGeneral
            sys.exit(1)
        return

    # Pattern-matching path: stream output, bail out early on a known failure signature.
    # This is used for rebuild-index, which shows an error and then hangs. We
    # parse the output to look for an error and exit early as the error is expected and
    # can be worked around.
    process = subprocess.Popen(
        command, shell=True, cwd=working_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    output_lines = []
    triggered_pattern = None

    for line in process.stdout:
        print(line, end="")
        output_lines.append(line)

        if any(pat in line for pat in fail_patterns):
            triggered_pattern = line.strip()
            break

    if triggered_pattern:
        process.kill()
        process.wait()
        logging.error(f"Detected failure pattern '{triggered_pattern}' during: {command}")
        if lenient:
            raise subprocess.CalledProcessError(returncode=-1, cmd=command, output="".join(output_lines))
        sys.exit(1)

    process.wait()
    if process.returncode != 0:
        logging.error(f"\nProcess failed during: {command}")
        if lenient:
            raise subprocess.CalledProcessError(process.returncode, command, output="".join(output_lines))
        sys.exit(1)

def scrape_data(config, output_dir: Path) -> Path:
    logging.info("Executing data scrape...")
    cwd = Path.cwd()
    repo_path = cwd / config.repository.dir_name
    scraper_dir = cwd / config.scraper.scraper_dir

    if repo_path.exists():
        shutil.rmtree(repo_path, ignore_errors=True)

    run_command(
        f"git clone -b {config.repository.branch} --depth 1 {config.repository.url} {repo_path}"
    )
    run_command("npm i", cwd=scraper_dir)
    run_command("npm start", cwd=scraper_dir)

    source_unsorted = scraper_dir / config.files.unsorted
    target_unsorted = output_dir / config.files.unsorted
    sorted_file = output_dir / config.files.sorted

    if source_unsorted.exists() and source_unsorted.resolve() != target_unsorted.resolve():
        print("Moving")
        shutil.move(str(source_unsorted), str(target_unsorted))

    run_command(f"sort -u {target_unsorted} > {sorted_file}")

    return sorted_file
