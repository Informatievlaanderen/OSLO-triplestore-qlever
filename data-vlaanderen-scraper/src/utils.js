import playwright from "playwright";
import * as cheerio from "cheerio";
import path from "path";
import fs from "fs-extra";

/**
 * This function returns all standards mentioned on https://data.vlaanderen.be/standaarden/ as JSON-LD.
 * @param {Logger} logger - A Winston logger that the function uses for its logging.
 * @returns {object} - A JSON-LD object with all the standards.
 */
export default async function getStandards(logger, generatedFilesRepo) {
  let result = [];
  const browser = await playwright.firefox.launch();
  const page = await browser.newPage();
  await page.goto("https://data.vlaanderen.be/standaarden/");
  const pageRange = await (await page.locator(".vl-pager__element")).first().innerText();
  const totalNumberOfStandaarden = parseInt(pageRange.split(" ")[4]);

  let resultSinglePage = await _getStandardsOnPage(page);
  result = result.concat(resultSinglePage);
  let numberOfStandaarden = resultSinglePage.length;

  while (numberOfStandaarden < totalNumberOfStandaarden) {
    await page.getByText("Volgende").first().click();
    resultSinglePage = await _getStandardsOnPage(page);
    result = result.concat(resultSinglePage);
    numberOfStandaarden += resultSinglePage.length;
  }

  for (const el of result) {
    if (el["@type"] === "fabio:ApplicationProfile") {
      try {
        el["@id"] = await _getCanonicalVersion({url: el["@id"], browser, generatedFilesRepo});
      } catch (e) {
        logger.warn(e.message);
        logger.warn(`Couldn't determine canonical version of ${el["@id"]}.`);
        logger.warn(`Using ${el["@id"]} instead.`);
      }
    }
  }

  browser.close();
  return {
    "@context": {
      "dcterms": "http://purl.org/dc/terms/",
      "fabio": "http://purl.org/spar/fabio/",
      "prism": "http://prismstandard.org/namespaces/basic/2.0/",
      "title": "dcterms:title",
      "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
    },
    "@id": "https://data.vlaanderen.be/standaarden/",
    "rdfs:member": result
  };
}

/**
 * This function returns all the standards currently shown on the page as JSON-LD objects (no context is included).
 * @param {Page} page - A Playwright page.
 * @returns {Array} - An array of standards as JSON-LD objects.
 */
async function _getStandardsOnPage(page) {
  const result = [];
  await page.locator(".standards-table");
  const tr = await page.locator(".standards-table tr");

  await tr.nth(0).innerHTML();
  const count = await tr.count();

  for (let i = 1; i < count; i++) {
    const html = await tr.nth(i).innerHTML();
    const $ = cheerio.load(html);
    const first = $("a:first");
    const el = {
      "@id": first.attr("href"),
      "title": first.text(),
      "prism:publicationDate": $("p:nth(2)").text()
    };

    if (el.title.startsWith("Applicatieprofiel")) {
      el["@type"] = "fabio:ApplicationProfile";
    }

    result.push(el);
  }

  return result;
}

/**
 * This function returns the canonical version of a standard.
 * @param {object} options - An object containing the parameters of the function.
 * @param {string} options.url - The url of the standard.
 * @returns {string} - The url of the canonical version of the standard.
 */
async function _getCanonicalVersion({url, generatedFilesRepo}) {
  const htmlPath = path.join(generatedFilesRepo, url.replace("https://data.vlaanderen.be/", ""), "index.html");
  const htmlStr = await fs.readFile(htmlPath, "utf8");
  const $ = cheerio.load(htmlStr);
  let link = $("#status.head dd:nth-child(6)").text();

  if (!link) {
    link = $("#respecHeader div.head dl dd:nth-child(6)").prop('innerText');

    if (link) {
      link = link.replace("\n", "").trim();
    }
  }

  if (!link) {
    throw new Error("No link found with either CSS selectors.");
  }

  return link;
}
