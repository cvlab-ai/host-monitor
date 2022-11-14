#!/usr/bin/env python3

import sys

if __package__ is None and not hasattr(sys, 'frozen'):
    import os.path

    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))


def main():
    from host_monitor.gui import run_app
    ret_code = run_app()
    sys.exit(ret_code)


if __name__ == '__main__':
    main()
