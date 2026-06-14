"""Enables ``python -m alphai_news_email``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
