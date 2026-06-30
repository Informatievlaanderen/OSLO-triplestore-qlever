import os
import re
import shutil
import logging

from rdflib import Dataset, Graph


def clean_data(database_path: str, database_file_name: str):
    data_file_path = os.path.join(database_path, database_file_name)
    temp_trig_path = os.path.join(database_path, "temp_" + database_file_name)
    final_turtle_path = os.path.join(database_path, "cleaned_" + database_file_name)

    if not os.path.exists(final_turtle_path):
        logging.info("Sanitizing integer data types")

        def validate_integer(match):
            literal_value = match.group(1)
            try:
                int(literal_value)
                return match.group(0)
            except ValueError:
                return f'"{literal_value}"'

        xsd_int_pattern = r'"([^"]*)"\^\^<http://www.w3.org/2001/XMLSchema#(?:integer|int)>'

        with open(data_file_path, 'r', encoding='utf-8') as infile, \
                open(temp_trig_path, 'w', encoding='utf-8') as outfile:
            for line in infile:
                line = re.sub(xsd_int_pattern, validate_integer, line)
                outfile.write(line)

        logging.info(f"Moving temporary file to {final_turtle_path}...")
        shutil.move(temp_trig_path, final_turtle_path)

if __name__ == "__main__":
    clean_data("qlever/data/", "data-vlaanderen.nt")