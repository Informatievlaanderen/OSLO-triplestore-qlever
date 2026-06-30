# Data.Vlaanderen Turtle scraper

## Install

1. Clone [data.vlaanderen.be2-generated](https://github.com/Informatievlaanderen/data.vlaanderen.be2-generated)
   in the parent directory and use the branch `production` via

   ```shell
   git clone -b production https://github.com/Informatievlaanderen/data.vlaanderen.be2-generated ../data.vlaanderen.be-generated
   ```

2. Install the dependencies via

    ```shell
    npm i
    ```

## Usage

1. Run the scraper with its default config via

   ```shell
   node bin/cli.js
   ```  

2. Remove duplicate lines and sort them via

   ```shell
   sort -u output.nt > output.unique.nt
   ```

3. Create a [config file](#config-file) called `config.json` to overwrite the default config of the scraper.

## Config file

- `shacl-files`: This object configures how the scraper should handle SHACL files.
  - `enabled`: If true the scraper includes SHACL false. The default is false.
- `log-level`: The level used by the scraper's logger.
  The default is `warn`.
- `generated-files-repo`: The path to the clone of 
  [this repo](https://github.com/Informatievlaanderen/data.vlaanderen.be2-generated/).
  The default is `../data.vlaanderen.be2-generated`.

## Generate subsets

The generated Turtle file is large.
You can generate subsets of this file via

```shell
npm run subsets
```

This generates two Turtle files:

- `classes-ap.ttl` contains the triples that connects classes to the application profiles that uses them.
- `predicates-ap.ttl` contains the triples that connects predicates to the application profiles that uses them.

## Deployment

We run the scrapper every day via the
[Gitlab CI](https://gitlab.ilabt.imec.be/KNoWS/data-vlaanderen-scraper/-/pipeline_schedules).
You find the output in [this repo](https://github.com/KNowledgeOnWebScale/data-vlaanderen-bundled-rdf).
We use a personal GitHub authentication token to push to this repo.
We use Pieter Heyvaert's name and email when doing the commit.
You can change this at `deploy.before_script` in `.gitlab-ci.yml`.

## Example queries

You find examples SPARQL queries in the directory `queries`.

- `all-aps-that-use-dcterms-title.rq` returns all application profiles that use `dcterms:title`.
- `properties-used-by-ap-vrachtwagenparkeren.rq` returns all properties used by the application profile "Vrachtwagenparkeren".

## Validation

We do a basic validation of the scraped output in `validation/test.js`.
It checks whether specific APs and NodeShapes are present.
