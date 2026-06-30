import winston from "winston";

let logger;

/**
 * This function returns an instance of Winston logger.
 * @param {string} logLevel - The log level as defined by Winston.
 * @returns {Logger} A Winston logger.
 */
export default function getLogger(logLevel) {
  if (!logger) {
    logger = winston.createLogger({
      transports: [
        new winston.transports.Console()
      ],
      format: winston.format.simple(),
      level: logLevel
    });
  } else if (logLevel) {
    logger.warn(`Already created a logger. Log level "${logLevel}" is ignored.`);
  }

  return logger;
}
