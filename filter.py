import fiona
import json
import os
import logging
import argparse
import textwrap
from config import LOG_LEVEL, LOG_FORMAT, LOG_DIR

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logfile = "filter-log.txt"

def main():
    description_str=textwrap.dedent('''\
            Script is designed to filter vector data based on feature properties using the fiona library. 
            Driver is chosen based on file suffix. Filter is specified in a sepparate json file. 
            For instance filtering all objects with the fature FOO is 3 and BAR is "EGGS" will look like
            --------------------------------
            {
                "and" :
                [
                    {"==": [ {"var" : "FOO"}, 3]},
                    {"==": [ {"var" : "BAR"}, "EGGS"]}
                ]
            }
            ''')

    parser = argparse.ArgumentParser(
        prog='filter.py',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=description_str
    )
    parser.add_argument('input_file', type=str,
                        help='Input vector file.')
    parser.add_argument('out_file', type=str,
                        help='Output vector file (filtered).')
    parser.add_argument('-c','--counter', action='store', type=str,
                        help='Optional integer counter added to feature properties')
    parser.add_argument('-f','--filter', action='store', type=str,
                        help='json file containing filter expression.')
    args = parser.parse_args()

    for arg in vars(args):
        logging.info("{}: {}".format(arg, getattr(args, arg)))

    # Add new file handler to logger.
    file_handler = logging.FileHandler(filename=os.path.join(LOG_DIR, logfile))
    log_formatter = logging.Formatter(fmt=LOG_FORMAT)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOG_LEVEL)
    logging.getLogger().addHandler(file_handler)

    if args.filter:
        with open(args.filter) as file:
            filter_expression = json.load(file)

    logging.info("applying filter: {}".format(filter_expression))

    with fiona.open(args.input_file) as source:
        sink_schema = source.schema
        if args.counter:
            sink_schema["properties"][args.counter] = 'int'
        with fiona.open(args.out_file, "w", crs=source.crs, driver=source.driver, schema=sink_schema) as sink:
            counter = 1
            for f in source:
                if args.filter and eval_expression(filter_expression, f["properties"]):
                    if args.counter:
                        f["properties"][args.counter] = counter
                    sink.write(f)
                    counter += 1
            logging.info("Wrote {} features to file: {}".format(counter, args.out_file))

def eval_expression(expr, properties):
    for key, exp in expr.items():
        #print("eval: key:{}, exp:{}".format(key, exp))
        if key in {"and", "or"}:
            bool_value = []
            for ex in exp:
                bool_value.append(eval_expression(ex, properties))
            if key == "and":
                return all(bool_value)
            else:
                return any(bool_value)
        if key in {"==", "<", ">"}:
            return eval_basic_expression(expr, properties)

def eval_basic_expression(expr, properties):
    for key, val in expr.items():
        #print("basic: key:{}, exp:{}".format(key, val))
        if key == "==":
            return properties[val[0]['var']] == val[1]
        elif key == "<":
            return properties[val[0]['var']] < val[1]
        elif key == ">":
            return properties[val[0]['var']] > val[1]
        else:
            raise Exception("Logical operator not implemented") 


if __name__ == "__main__":
    main()

