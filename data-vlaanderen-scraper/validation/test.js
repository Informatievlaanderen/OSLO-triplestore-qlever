import {QueryEngine} from "@comunica/query-sparql-file";
import assert from "assert";
import path from "path";
import fs from "fs";
import {calculateDiffs} from "../run-scraper.js";

const myEngine = new QueryEngine();

describe('data.vlaanderen.be/standaarden', function () {
  this.timeout(10000);

  it('Should contain certain APs', async () => {
    const bindingsStream = await myEngine.queryBindings(`
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  SELECT ?o WHERE {
    <https://data.vlaanderen.be/standaarden/> rdfs:member ?o
  }`, {
      sources: ['output.ttl'],
    });

    const bindings = await bindingsStream.toArray();
    const objects = bindings.map(binding => binding.get("o").value);

    assert.equal(objects.includes("https://data.vlaanderen.be/doc/applicatieprofiel/erosiepoel/erkendestandaard/2025-07-23"), true);
    assert.equal(objects.includes("https://data.vlaanderen.be/doc/applicatieprofiel/hulp-dienstverlening-gedetineerden/erkendestandaard/2025-07-22"), true);
    assert.equal(objects.includes("https://data.vlaanderen.be/doc/applicatieprofiel/rooilijnplannen/erkendestandaard/2026-02-12"), true);
  })
});

describe('SHACL', function () {
  this.timeout(10000);

  it('Erosiepoel should have NodeShapes', async () => {
    const bindingsStream = await myEngine.queryBindings(`
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  PREFIX shacl: <http://www.w3.org/ns/shacl#>
  SELECT ?o WHERE {
    <https://data.vlaanderen.be/doc/applicatieprofiel/erosiepoel/kandidaatstandaard/2025-05-07> rdfs:member ?o.
    ?o a shacl:NodeShape.
  }`, {
      sources: ['output.ttl'],
    });

    const bindings = await bindingsStream.toArray();
    assert.equal(bindings.length > 20, true);
  })

  it('HDG should have NodeShapes', async () => {
    const bindingsStream = await myEngine.queryBindings(`
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  PREFIX shacl: <http://www.w3.org/ns/shacl#>
  SELECT ?o WHERE {
    <https://data.vlaanderen.be/doc/applicatieprofiel/hulp-dienstverlening-gedetineerden/ontwerpstandaard/2025-05-05> rdfs:member ?o.
    ?o a shacl:NodeShape.
  }`, {
      sources: ['output.ttl'],
    });

    const bindings = await bindingsStream.toArray();
    assert.equal(bindings.length > 50, true);
  })

  it('Rooilijnplannen should have NodeShapes', async () => {
    const bindingsStream = await myEngine.queryBindings(`
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  PREFIX shacl: <http://www.w3.org/ns/shacl#>
  SELECT ?o WHERE {
    <https://data.vlaanderen.be/doc/applicatieprofiel/rooilijnplannen/ontwerpstandaard/2025-06-01> rdfs:member ?o.
    ?o a shacl:NodeShape.
  }`, {
      sources: ['output.ttl'],
    });

    const bindings = await bindingsStream.toArray();
    assert.equal(bindings.length > 55, true);
  })
});


describe('Differential Calculation (comm wrapper)', function () {
    const tempDir = path.join(process.cwd(), 'test-temp');
    const previousOutput = path.join(tempDir, 'output.previous.nt');
    const currentOutput = path.join(tempDir, 'output.unique.nt');
    const additionsFile = path.join(tempDir, 'additions.nt');
    const deletionsFile = path.join(tempDir, 'deletions.nt');

    before(() => {
        if (!fs.existsSync(tempDir)) {
            fs.mkdirSync(tempDir);
        }
    });

    afterEach(() => {
        const files = [previousOutput, currentOutput, additionsFile, deletionsFile];
        files.forEach(file => {
            if (fs.existsSync(file)) {
                fs.unlinkSync(file);
            }
        });
    });

    after(() => {
        if (fs.existsSync(tempDir)) {
            fs.rmdirSync(tempDir);
        }
    });

    it('correctly identifies additions, deletions, and unchanged triples', () => {
        const previousData = [
            '<http://example.org/s1> <http://example.org/p1> "Unchanged" .',
            '<http://example.org/s2> <http://example.org/p2> "To Delete" .'
        ].join('\n') + '\n';

        const currentData = [
            '<http://example.org/s1> <http://example.org/p1> "Unchanged" .',
            '<http://example.org/s3> <http://example.org/p3> "To Add" .'
        ].join('\n') + '\n';

        fs.writeFileSync(previousOutput, previousData);
        fs.writeFileSync(currentOutput, currentData);

        calculateDiffs(previousOutput, currentOutput, additionsFile, deletionsFile, null);

        const additions = fs.readFileSync(additionsFile, 'utf-8');
        const deletions = fs.readFileSync(deletionsFile, 'utf-8');

        assert.strictEqual(additions, '<http://example.org/s3> <http://example.org/p3> "To Add" .\n');
        assert.strictEqual(deletions, '<http://example.org/s2> <http://example.org/p2> "To Delete" .\n');
    });

    it('handles modification of a triple literal as one deletion and one addition', () => {
        const previousData = '<http://example.org/s1> <http://example.org/p1> "Old Value" .\n';
        const currentData = '<http://example.org/s1> <http://example.org/p1> "New Value" .\n';

        fs.writeFileSync(previousOutput, previousData);
        fs.writeFileSync(currentOutput, currentData);

        calculateDiffs(previousOutput, currentOutput, additionsFile, deletionsFile, null);

        const additions = fs.readFileSync(additionsFile, 'utf-8');
        const deletions = fs.readFileSync(deletionsFile, 'utf-8');

        assert.strictEqual(additions, currentData);
        assert.strictEqual(deletions, previousData);
    });
});