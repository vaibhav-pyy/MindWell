"""Entry point: `flask --app wsgi run` (development) or a WSGI server such as waitress/gunicorn."""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
