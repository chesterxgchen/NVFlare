#!/usr/bin/env python3
"""
Client training script - reuses hello-pt client.py
This is just a symlink/wrapper for convention.
"""

import sys
sys.path.insert(0, '../../hello-world/hello-pt')

# Import and run the hello-pt client
from client import main

if __name__ == "__main__":
    main()
