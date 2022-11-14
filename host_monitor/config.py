import os
import shutil
from argparse import ArgumentParser

import yaml


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('-v', '--verbose', help='Show debug messages', action="store_true")
    return parser.parse_args()


def read_config():
    config_path = os.path.expanduser("~/.host-monitor")
    if not os.path.exists(config_path):
        default_path = os.path.normpath(f"{__file__}/../config_default.yaml")
        shutil.copy(default_path, config_path)
    return yaml.safe_load(open(config_path))


args = parse_args()
config = read_config()
