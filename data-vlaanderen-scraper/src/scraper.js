import N3 from "n3";
import fs from "fs-extra";
import fsp from "fs/promises";
import path from "path";
import getStandards from "./utils.js";
import {JsonLdParser} from "jsonld-streaming-parser";
import {DataFactory} from "n3";
const { namedNode, literal, defaultGraph, quad } = DataFactory;

const prefixes = await fs.readJson(path.join(import.meta.dirname, "prefixes.json"));

export default class Scraper {

  /**
   * The constructor of the class Scraper.
   * @param {object} options - An object containing the parameters of the constructor.
   * @param {object} options.shaclFiles - This object configures how the Scraper should handle SHACL files.
   *   - {boolean} enabled: if true, then SHACL files are in included. The default is false.
   * @param {Logger} options.logger - A Winston logger that the Scraper uses for its logging.
   * @param {string} options.outputFilePath - The path of the output file where the Scraper stores the Turtle.
   */
  constructor({shaclFiles, logger, outputFilePath, generatedFilesRepo}) {
    // this._inputs = [path.resolve(import.meta.dirname, "../../data.vlaanderen.be2-generated/")];
    this._inputs = [(generatedFilesRepo)];
    this._skip = [];
    this._logger = logger;
    this._outputFilePath = outputFilePath || "output.nt";
    this._shaclFiles = {...{enabled: false}, ...shaclFiles};
    this._nodeShapes = [];
    this._generatedFilesRepo = generatedFilesRepo;
  }

  /**
   * This method runs the Scraper.
   */
  async run() {
    const writer = new N3.Writer(fs.createWriteStream(this._outputFilePath), {
      format: "N-Triples",
      end: false,
      prefixes
    });
    const writerPromises = [];

    for (const source of this._inputs) {
      if (fs.lstatSync(source).isDirectory()) {
        await this._processDirectory(source, this._skip, writer, writerPromises);
      } else {
        writerPromises.push(this._writeData(source, writer));
      }
    }

    writerPromises.push(this._addStandards(writer));

    this._logger.debug(`Doing ${writerPromises.length} writerPromises`);
    for (const writerPromise of writerPromises) {
      await writerPromise();
    }

    this._parseNodeShapes(writer);
    writer.end();
  }

  /**
   * This method reads all Turtle files in a directory and writes the corresponding Quads to a Writer.
   * @param {string} dirPath - The path of the directory that should be processed.
   * @param {Array} skip - An array of file path that should be skipped.
   * @param {N3Writer} writer - The Writer to which the Quads are written.
   * @param {Array} writerPromises - An array of promises that add Quads to the Writer.
   */
  async _processDirectory(dirPath, skip, writer, writerPromises) {
    const slashedSource = dirPath.endsWith("/") ? dirPath : dirPath + "/";
    for (const foundPath of (await fsp.readdir(slashedSource))) {
      if (fs.lstatSync(slashedSource + foundPath).isDirectory()) {
        await this._processDirectory(slashedSource + foundPath, skip, writer, writerPromises);
      } else if (!skip.includes(path.resolve(slashedSource + foundPath).replaceAll("\\", "/"))) {
        if ((path.extname(foundPath) === ".ttl")) {
          if (!this._shaclFiles.enabled && ((slashedSource + foundPath).replaceAll("\\", "/").indexOf("/shacl/") !== -1)) {
            return;
          }

          writerPromises.push(this._writeData(slashedSource + foundPath, writer));
        }
      }
    }
  }

  /**
   * This method reads Turtle from a file and writes the corresponding Quads to a Writer.
   * @param {string} filePath - The path to the file from which to read the Turtle.
   * @param {N3Writer} writer - The Writer to which the Quads are written.
   * @returns {Function} - A new function that returns a Promise which resolves once all Quads are written to the Writer.
   */
  _writeData(filePath, writer) {
    return () => {
      return new Promise((resolve) => {
        this._logger.info(`Parsing ${filePath}`);
        fs.createReadStream(filePath, "utf8")
          .pipe(new N3.StreamParser({baseIRI: filePath}))
          .on("data", q => {
            writer.addQuad(q);

            if (q.object.value === "http://www.w3.org/ns/shacl#NodeShape") {
              this._nodeShapes.push(q.subject.value);
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
   * This method adds the standards found at Flemish standard registry to a Writer.
   * @param {N3Writer} writer - The Writer to which the Quads of the standards are written.
   * @returns {Promise} - This promise resolves when the standards are written to the Writer.
   */
  _addStandards(writer) {
    return async () => {
      const standards = await getStandards(this._logger, this._generatedFilesRepo);
      return await this._parseJsonld(writer, standards);
    };
  }

  /**
   * This function parses a JSON-LD object and writes the corresponding Quads to a Writer.
   * @param {N3Writer} writer - The Writer to which the Quads of the standards are written.
   * @param {object} standards - A JSON-LD object with standards.
   * @returns {Promise} - The promise that resolves once all Quads are written to the Writer.
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
   * This method adds Quads that connect an AP with its NodeShapes to a writer.
   * @param {N3Writer} writer - The Writer to which the Quads are written.
   * @private
   */
  _parseNodeShapes(writer) {
    const aps = []
    this._nodeShapes.forEach(shape => {
      if (shape.includes("doc/applicatieprofiel")) {
        let ap;

        if (shape.includes("#")) {
          ap = shape.split("#")[0];
        } else {
          const parts = shape.split("/");
          parts.pop();
          ap = parts.join("/");
        }

        writer.addQuad(quad(namedNode(ap), namedNode("http://www.w3.org/2000/01/rdf-schema#member"), namedNode(shape)));
      }
    });
  }
}
