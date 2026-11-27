"""Explicit, local model download. Never processes patient documents."""
import argparse
from app.config import settings
from app.ai.providers.hybrid_ocr import _paddle, _trocr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--languages", nargs="+", choices=["en", "hi", "te"], default=["en"])
    args = parser.parse_args()
    settings.ocr_allow_model_downloads = True
    for language in args.languages:
        _paddle(language)
        print(f"PaddleOCR {language} ready", flush=True)
    _trocr()
    print("English TrOCR ready. Model scores do not establish medical accuracy.", flush=True)


if __name__ == "__main__":
    main()
