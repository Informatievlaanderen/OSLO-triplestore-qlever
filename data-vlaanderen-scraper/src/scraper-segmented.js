import N3 from "n3";
import fs from "fs-extra";
import fsp from "fs/promises";
import path from "path";
import getStandards from "./utils.js";
import { JsonLdParser } from "jsonld-streaming-parser";
import { DataFactory } from "n3";
const { namedNode, quad } = DataFactory;

const prefixes = await fs.readJson(path.join(import.meta.dirname, "prefixes.json"));

export default class ScraperSegmented {
  /**
   * The constructor of the class Scraper.
   */
  constructor({ shaclFiles, logger, outputFilePath, generatedFilesRepo }) {
    this._inputs = [generatedFilesRepo];
    this._skip = [];
    this._logger = logger;
    // Treat outputFilePath as the root directory for your segmented outputs
    this._outputOutputDir = outputFilePath || "output_segmented";
    this._shaclFiles = { ...{ enabled: false }, ...shaclFiles };
    this._nodeShapes = []; // Stores objects: { value: string, relativeDir: string }
    this._generatedFilesRepo = generatedFilesRepo;
    this._writers = new Map(); // Tracks N3.Writer instances per directory path
  }

  /**
   * Helper to fetch or create an active N3.Writer for a specific directory sub-path.
   */
  _getWriter(relativeDir) {
    if (!this._writers.has(relativeDir)) {
      const targetFolder = path.join(this._outputOutputDir, relativeDir);
      fs.ensureDirSync(targetFolder);

      const targetFilePath = path.join(targetFolder, "output.nt");
      const writeStream = fs.createWriteStream(targetFilePath);

      const writer = new N3.Writer(writeStream, {
        format: "N-Triples",
        end: false,
        prefixes
      });
      this._writers.set(relativeDir, writer);
    }
    return this._writers.get(relativeDir);
  }

  /**
   * This method runs the Scraper.
   */
  async run() {
    const writerPromises = [];

    for (const source of this._inputs) {
      if (fs.lstatSync(source).isDirectory()) {
        await this._processDirectory(source, source, this._skip, writerPromises);
      } else {
        writerPromises.push(this._writeData(source, "root"));
      }
    }

    // Directs external JSON-LD registry standards into their own subdirectory
    writerPromises.push(this._addStandards("external-registry"));

    this._logger.debug(`Doing ${writerPromises.length} writerPromises`);
    for (const writerPromise of writerPromises) {
      await writerPromise();
    }

    // Maps member relationships to the correct directory writer instances
    this._parseNodeShapes();

    // Close all open directory writers safely
    for (const writer of this._writers.values()) {
      writer.end();
    }
  }

  /**
   * This method reads all Turtle files in a directory and registers write operations.
   */
  async _processDirectory(dirPath, rootSource, skip, writerPromises) {
    const slashedSource = dirPath.endsWith("/") ? dirPath : dirPath + "/";
    for (const foundPath of (await fsp.readdir(slashedSource))) {
      const fullPath = slashedSource + foundPath;

      if (fs.lstatSync(fullPath).isDirectory()) {
        await this._processDirectory(fullPath, rootSource, skip, writerPromises);
      } else if (!skip.includes(path.resolve(fullPath).replaceAll("\\", "/"))) {
        if (path.extname(foundPath) === ".ttl") {
          if (!this._shaclFiles.enabled && (fullPath.replaceAll("\\", "/").indexOf("/shacl/") !== -1)) {
            return;
          }

          // Compute relative directory context from repo root
          const relativeDir = path.relative(rootSource, dirPath) || "root";
          writerPromises.push(this._writeData(fullPath, relativeDir));
        }
      }
    }
  }

  /**
   * This method reads Turtle from a file and writes to the correct directory-scoped writer.
   */
  _writeData(filePath, relativeDir) {
    return () => {
      return new Promise((resolve) => {
        this._logger.info(`Parsing ${filePath}`);
        const writer = this._getWriter(relativeDir);

        fs.createReadStream(filePath, "utf8")
          .pipe(new N3.StreamParser({ baseIRI: filePath }))
          .on("data", q => {
            writer.addQuad(q);

            if (q.object.value === "http://www.w3.org/ns/shacl#NodeShape") {
              // Attach relativeDir metadata to the shape reference
              this._nodeShapes.push({ value: q.subject.value, relativeDir });
            }
          })
          .on("error", () => {
            this._logger.error(`${filePath.replaceAll("\\", "/")} is not valid Turtle, did best effort but skipping now...`);
            resolve();
          })
          .on("finish", resolve);
      });
    };
  }

  /**
   * This method adds the standards found at Flemish standard registry to a specific writer.
   */
  _addStandards(relativeDir) {
    return async () => {
      const writer = this._getWriter(relativeDir);
      const standards = await getStandards(this._logger, this._generatedFilesRepo);
      return await this._parseJsonld(writer, standards);
    };
  }

  /**
   * This function parses a JSON-LD object and writes the corresponding Quads to a Writer.
   */
  _parseJsonld(writer, standards) {
    return new Promise((resolve, reject) => {
      const myParser = new JsonLdParser();

      myParser
        .on("data", q => {
          writer.addQuad(q);
        })
        .on("error", reject)
        .on("end", resolve);

      myParser.write(JSON.stringify(standards));
      myParser.end();
    });
  }

  /**
   * This method adds Quads that connect an AP with its NodeShapes to the matching writer.
   * @private
   */
  _parseNodeShapes() {
    this._nodeShapes.forEach(({ value: shape, relativeDir }) => {
      if (shape.includes("doc/applicatieprofiel")) {
        let ap;

        if (shape.includes("#")) {
          ap = shape.split("#")[0];
        } else {
          const parts = shape.split("/");
          parts.pop();
          ap = parts.join("/");
        }

        const writer = this._getWriter(relativeDir);
        writer.addQuad(quad(namedNode(ap), namedNode("http://www.w3.org/2000/01/rdf-schema#member"), namedNode(shape)));
      }
    });
  }
}