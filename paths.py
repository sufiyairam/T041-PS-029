"""
paths.py  -  where the input files are and where the results go.

By default: the `data` and `output` folders next to the code, so the program works
from ANY folder you start it in. To use other folders:
    python main.py  path/to/data  path/to/output
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def data_folder():
    return os.environ.get("EXPENSE_DATA_DIR") or os.path.join(HERE, "data")


def output_folder():
    return os.environ.get("EXPENSE_OUTPUT_DIR") or os.path.join(HERE, "output")
