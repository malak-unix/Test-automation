"""Root Flask launcher for the dashboard MVP."""

from __future__ import annotations

import os

from test_auto.interface.flask_app import create_app


app = create_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    app.run(host="127.0.0.1", port=5000, debug=debug)
