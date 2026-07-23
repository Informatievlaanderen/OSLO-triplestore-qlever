- 1.0.0
  Change runtime from every 8 minutes to every 2 hours

- 1.0.2
  Don't expose access_token and use a startup script to generate the `Qleverfile.local` file from the template and the token in `.env`.

- 1.0.3
  Stream the http logs to the docker container

  1.1.0
  Add support for bedrijventerreinen so that the triplestore can be given information through a set of dumps

- 1.2.0
  **Breaking change:** `--with-dumps` now expects a _path_ to a directory of
  `.nq` files instead of being a boolean flag. The old hardcoded
  `qlever/data/dumps/` location is no longer assumed.

  Usage: `python main.py init --with-dumps /path/to/nq/files`

  Also removed the regex-based N-Quads→N-Triples conversion step. QLever
  natively supports `.nq` (N-Quads) files, so the `.nq` files are now indexed
  directly without any intermediate conversion or deduplication.
