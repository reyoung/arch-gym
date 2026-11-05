#!/usr/bin/env python3
"""Validate a generated case; does not verify online evidence."""
import sys
from gym import main

if __name__ == '__main__':
    sys.exit(main(['validate', *sys.argv[1:]]))
