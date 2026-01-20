"""
Minimal Typst compilation API.
Accepts Typst markup via POST and returns compiled PDF.
"""

import os
import tempfile
from pathlib import Path
from flask import Flask, request, Response

import typst

app = Flask(__name__)


@app.route("/", methods=["GET"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "typst-api"}


@app.route("/", methods=["POST"])
def compile_typst():
    """
    Compile Typst markup to PDF.

    Accepts: text/plain body with Typst content
    Returns: application/pdf on success, JSON error on failure
    """
    try:
        # Get Typst content from request body
        typst_content = request.get_data(as_text=True)

        if not typst_content:
            return {"error": "No content provided"}, 400

        # Write to temporary file (typst.compile expects a file path)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            typst_file = temp_path / "input.typ"
            typst_file.write_text(typst_content, encoding="utf-8")

            # Compile to PDF using typst-py
            pdf_bytes = typst.compile(typst_file)

            return Response(
                pdf_bytes,
                mimetype="application/pdf",
                headers={"Content-Disposition": "inline; filename=output.pdf"}
            )

    except Exception as e:
        error_msg = str(e)
        return {"error": error_msg}, 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    # Use gunicorn in production, Flask dev server for local testing
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        import gunicorn.app.base

        class StandaloneApplication(gunicorn.app.base.BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        options = {
            "bind": f"0.0.0.0:{port}",
            "workers": 2,
            "timeout": 120,
        }
        StandaloneApplication(app, options).run()
    else:
        app.run(host="0.0.0.0", port=port, debug=True)
