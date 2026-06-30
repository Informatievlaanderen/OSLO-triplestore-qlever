import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Reconstruct __dirname for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Executes a shell command synchronously and pipes output to the console.
 */
function runCommand(command, cwd = process.cwd()) {
    console.log(`\n> Executing: ${command}`);
    try {
        execSync(command, { stdio: 'inherit', cwd: cwd });
    } catch (error) {
        console.error(`\nProcess failed during: ${command}`);
        process.exit(1);
    }
}

function executePipeline() {
    console.log("Starting scraper pipeline...");

    const parentDir = path.resolve(__dirname, '..');
    const generatedRepoPath = path.join(parentDir, 'data.vlaanderen.be2-generated');

    // Remove previous scrapes
    if (fs.existsSync(generatedRepoPath)) {
        console.log(`Removing existing repository at ${generatedRepoPath}...`);
        fs.rmSync(generatedRepoPath, { recursive: true, force: true });
    }

    // Clone the data-vlaanderen production generated artifacts
    runCommand(`git clone -b production --depth 1 https://github.com/Informatievlaanderen/data.vlaanderen.be2-generated ${generatedRepoPath}`);

    // Install scraper
    runCommand('npm i');

    // Start scraper
    runCommand('npm start');

    // Generate the subset files
    runCommand('sort -u output.nt > output.unique.nt');

    console.log("\nPipeline complete. Expected artifacts:");
}

export function scrapeData(repoPath, unsortedFile, sortedFile) {
    console.log("Starting scraper pipeline...");
    if (fs.existsSync(repoPath)) {
        fs.rmSync(repoPath, { recursive: true, force: true });
    }

    runCommand(`git clone -b production --depth 1 https://github.com/Informatievlaanderen/data.vlaanderen.be2-generated ${repoPath}`);
    runCommand('npm i');
    runCommand('npm start');
    runCommand(`sort -u ${unsortedFile} > ${sortedFile}`);
}

export function calculateDiffs(previousFile, currentFile, additionsFile, deletionsFile, logDirectory) {
    console.log("\nCalculating differentials...");

    // comm -13 outputs lines unique to file 2 (Current) -> Additions
    runCommand(`comm -13 ${previousFile} ${currentFile} > ${additionsFile}`);

    // comm -23 outputs lines unique to file 1 (Previous) -> Deletions
    runCommand(`comm -23 ${previousFile} ${currentFile} > ${deletionsFile}`);

    if (logDirectory) {
        if (!fs.existsSync(logDirectory)) {
            fs.mkdirSync(logDirectory, { recursive: true });
        }
        fs.copyFileSync(additionsFile, path.join(logDirectory, 'additions.nt'));
        fs.copyFileSync(deletionsFile, path.join(logDirectory, 'deletions.nt'));
    }
}

export function executeUpdatePipeline() {
    const parentDir = path.resolve(__dirname, '..');
    const generatedRepoPath = path.join(parentDir, 'data.vlaanderen.be2-generated');

    const previousOutput = path.join(process.cwd(), 'output.previous.nt');
    const currentOutputUnsorted = path.join(process.cwd(), 'output.nt');
    const currentOutputSorted = path.join(process.cwd(), 'output.unique.nt');
    const additionsFile = path.join(process.cwd(), 'additions.nt');
    const deletionsFile = path.join(process.cwd(), 'deletions.nt');

    if (fs.existsSync(currentOutputSorted)) {
        console.log("Archiving previous run...");
        fs.renameSync(currentOutputSorted, previousOutput);
    } else {
        fs.writeFileSync(previousOutput, '');
    }

    scrapeData(generatedRepoPath, currentOutputUnsorted, currentOutputSorted);

    const date = new Date().toISOString().split('T')[0];
    const logDir = path.join(process.cwd(), 'logs', date);

    calculateDiffs(previousOutput, currentOutputSorted, additionsFile, deletionsFile, logDir);

    console.log("\nUpdate pipeline complete. Ready for ingestion.");
}

export function initializeQLeverEndpoint() {
    console.log("Initializing endpoint...");

    const parentDir = path.resolve(__dirname, '..');
    const generatedRepoPath = path.join(parentDir, 'data.vlaanderen.be2-generated');
    const currentOutputUnsorted = path.join(process.cwd(), 'output.nt');

    // QLever directory structure
    const qleverDir = path.join(process.cwd(), 'qlever-store');
    const qleverDataDir = path.join(qleverDir, 'data');
    const qleverBackupDataDir = path.join(qleverDir, 'data-bak');
    const qleverDataFile = path.join(qleverDataDir, 'data-vlaanderen-bak.nt');

    // Clean Execution Environment
    if (fs.existsSync(qleverDir)) {
        console.log("Wiping existing QLever backup data directory, moving previous data to a back-up directory");
        fs.rmSync(qleverBackupDataDir, { recursive: true, force: true });
        fs.cpSync(qleverDataDir, qleverBackupDataDir, { recursive: true } )
        fs.rmSync(qleverDataDir, { recursive: true, force: true });
    }

    fs.mkdirSync(qleverDataDir, { recursive: true });

    if (fs.existsSync(generatedRepoPath)) {
        fs.rmSync(generatedRepoPath, { recursive: true, force: true });
    }

    // Scrape Data
    runCommand(`git clone -b production --depth 1 https://github.com/Informatievlaanderen/data.vlaanderen.be2-generated ${generatedRepoPath}`);
    runCommand('npm i');
    runCommand('npm start');

    // QLever requires the target file to match the NAME parameter in the Qleverfile
    runCommand(`sort -u ${currentOutputUnsorted} > ${qleverDataFile}`);

    runCommand('qlever --qleverfile Qleverfile index', qleverDir);

    console.log("\nStarting QLever endpoint...");
    runCommand('qlever --qleverfile Qleverfile start', qleverDir);
}
// executePipeline();