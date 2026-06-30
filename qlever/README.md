From project root:
```bash
source .venv/bin/activate
pip install qlever
```
Then navigate to qlever directory
```bash
cd triples_stores/qlever
```

if a Qleverfile doesn't exist yet:
```bash
qlever setup-config default
```
Index data:
```bash
qlever --qleverfile Qleverfile index
```
Starts dockerfile running QLever:
```bash
qlever --qleverfile Qleverfile start
```

Rebuilds index when updates happen:
```bash
qlever --qleverfile Qleverfile rebuild-index 
```

## Considerations
QLever was initially designed to be a read-only database. Recently support has been added
to integrate any update queries into the main index quickly (<1 min for millions of triples).
This requires a periodic run of rebuild-index commands to integrate 
update queries into the main index to maintain performance.
We should sync periodically run rebuild-index to ensure we don't lose performance when updates happen.
This should also run manually if it is required.

QLever is fully opensource and easy to configure, in addition it supports premium support 
options that allow you to access domain experts to fix problems.

## Additional Capabilities
Text search of literals. We can instruct QLever to add text-based indexes, which allows us
to use text search on external corpuses or literal values. 

