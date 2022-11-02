import os
import shutil
from argparse import ArgumentParser

import yaml


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('-t', '--time', help='Time between checks in seconds', default=1, type=float)
    return parser.parse_args()


def read_config():
    config_path = os.path.expanduser("~/.host-monitor")
    if not os.path.exists(config_path):
        default_path = os.path.normpath(f"{__file__}/../config_default.yaml")
        shutil.copy(default_path, config_path)
    return yaml.safe_load(open(config_path))


args = parse_args()
config = read_config()
