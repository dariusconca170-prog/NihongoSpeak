#!/usr/bin/env python3
"""
Entry point for 日本語 Sensei.
Loads everything from /src and runs the app.
"""

import sys
import os

# Add src to Python path for easy imports
src_path = os.path.join(os.path.dirname(__file__), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

if __name__ == "__main__":
    from main import main
    main()
