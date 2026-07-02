import fs from "fs-extra";
import Scraper from "../src/scraper.js";
import ScraperSegmented from "../src/scraper-segmented.js";
import getLogger from "../src/logger.js";
import camelcaseKeys from "camelcase-keys";
import path from "path";

let scraperConfig;
let logger;

try {
  scraperConfig = await fs.readJson("./config.json");
  scraperConfig = camelcaseKeys(scraperConfig, {deep: true});
  scraperConfig.generatedFilesRepo = scraperConfig.generatedFilesRepo || "../data.vlaanderen.be2-generated";
  scraperConfig.generatedFilesRepo = path.resolve(scraperConfig.generatedFilesRepo);
  logger = getLogger(scraperConfig.logLevel || "warn");
} catch {
  logger = getLogger("info");
  logger.info("The scraper couldn't find the scraper config file \"./config.json\".");
  logger.info("The scraper will use the default values.");
}

scraperConfig.logger = logger;
if (scraperConfig.segmented){
  const scraper = new ScraperSegmented(scraperConfig);
  scraper.run();
}
else{
  const scraper = new Scraper(scraperConfig);
  scraper.run();
}
