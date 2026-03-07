import sys
import os

# Add the 'src' directory to the search path
src_path = os.path.join(os.path.dirname(__file__), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Import the main function from src/main.py
from src.main import main

if __name__ == "__main__":
    main()