# Qlever Triple Store for Digitaal Vlaanderen

Code repository for starting, automatically updating, and maintaining the Qlever endpoint for OSLO standards.

## Getting Started

Below is a list of available commands to manage the endpoint.

### Initialize the Endpoint

To start the endpoint from a clean slate and obtain all current data, run:

```bash
python main.py init
```

By default, this command deletes any existing data in the `qlever/data_bak` and `qlever/data_raw` directories, and moves any existing data in the `qlever/data` directory to `qlever/data_bak`. 

This command will download and scrape the latest data in `data.vlaanderen.be2-generated` and overwrite existing indexes (in `qlever/data_vlaanderen_endpoint.*`) with this data.  **Warning:** This is a destructive operation! Existing indexes may contain the results of update queries issued to the endpoint that are not stored in the `.nt` file in `qlever/data`.

To reinitialize an already running endpoint, you must first stop it:

```bash
cd qlever
qlever stop
```

### Restarting the Endpoint from a Previous State

To restart the endpoint from a previous state, run:

```bash
python main.py restart
```

This command stops any existing Qlever Docker containers on the port specified in the `Qleverfile` and restarts the endpoint.

### Manually Trigger the Update Pipeline

To manually run the update pipeline, obtain the latest data, and rebuild the index, execute the following command in the repository root:

```bash
python main.py update
```

This command executes the following sequence:
1. Runs the scraper over the repository specified in `triple_store_config.yaml`.
2. Calculates the differences between the newly obtained data (default: `data-vlaanderen-scraper-output/output.unique.nt`) and the previously obtained data. When the update command runs the previously obtained data is stored in `data-vlaanderen-scraper-output/output.unique.nt`, only after the update command is finished it is moved to a `previous` location (default: `data-vlaanderen-scraper-output/output.previous.nt`).
3. Creates `additions.nt` and `deletions.nt` and logs them in the logging directory (default: `logs`).
4. If there are any additions or deletions, sends them as update queries to Qlever and executes a `rebuild-index` command to integrate the changes into the main index.

If the endpoint fails to start after rebuilding the index, the script rolls back to the previous index, logs the failure in the `.log` file, and restarts the endpoint.

This command can also be triggered via HTTP. Start the server using:

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

Then, issue the command via an HTTP POST request:

```bash
curl -X POST http://localhost:8000/update -H "Authorization: Bearer <TOKEN FROM CONFIG>"
```

### Validate the Endpoint

To validate the endpoint, run:

```bash
python main.py validate
```

This command runs several test queries against the endpoint and records their latency (including standard deviation) and result sets. The validator then compares the current result hash to the baseline result hash from previous validation runs. If a mismatch occurs, it records the output differences in the `logs` directory.

The validation output is appended to `validation_data/validation_history.csv` and plotted against previous runs in `validation_data/performance_evolution.pdf`.

This process includes a simple text-search query that finds 100 literals starting with 'adres'.

## Docker Deployment

This repository includes a multi-stage Docker setup to containerize the endpoint and automate updates via cron.

### Deployment Steps

Build the base image (installs system requirements including Python, Node.js, and Playwright dependencies):

```bash
make build-base
```

Build the runtime image (sets up the virtual environment, configures the FastAPI server, and registers the cronjob):

```bash
make build
```

Run the container with the required volumes:

```bash
make run
```

> **Note:** Running the Docker image requires the `qlever` directory to be completely free of existing indexes. The Dockerfile initializes the environment from scratch and will not overwrite existing indexes.

**Important:** Currently, the cronjob is scheduled to run every 8 minutes. This should be adjusted to a more appropriate interval for production in
`Dockerfile.build`.

## Considerations

* **Log Management:** The pipeline currently logs additions, deletions, and previous indexes whenever `rebuild-index` is executed. A retention strategy is required to clean up these logs and prevent disk exhaustion.
* **Validation File:** This disk space consideration also applies to the validation script, which continuously appends data to a `.csv` file.
* **Data Cleaning:** The initialization of the endpoint does minor data cleaning. Specifically there is a triple where a string literal has the integer datatype. We remove this to allow qlever to parse the data. If this triple is ever fixed in a different way than our data cleaning approach this will be registered as a triple addition.
