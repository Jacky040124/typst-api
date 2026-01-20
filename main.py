"""
RenderCV API - Full resume generation pipeline.
Accepts YAML content via POST and returns compiled PDF.
"""

import os
import tempfile
from pathlib import Path
from flask import Flask, request, Response, jsonify

import typst

app = Flask(__name__)

# Hardcoded API URL for self-reference (not needed but kept for clarity)
API_URL = "https://typst-api-production.up.railway.app"


@app.route("/", methods=["GET"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "rendercv-api"}


@app.route("/", methods=["POST"])
def generate_resume():
    """
    Generate PDF resume from YAML content.

    Accepts: application/json or text/plain with YAML content
    Returns: application/pdf on success, JSON error on failure
    """
    try:
        # Get YAML content from request
        content_type = request.content_type or ""

        if "application/json" in content_type:
            data = request.get_json()
            yaml_content = data.get("yaml_content", "")
            theme = data.get("theme", "classic")
        else:
            yaml_content = request.get_data(as_text=True)
            theme = request.args.get("theme", "classic")

        if not yaml_content:
            return jsonify({"error": "No YAML content provided"}), 400

        # Clean up markdown code block markers if present
        yaml_content = clean_yaml_content(yaml_content)

        # Import RenderCV components
        try:
            from rendercv.schema.rendercv_model_builder import (
                build_rendercv_dictionary_and_model,
            )
            from rendercv.renderer.typst import generate_typst
            from rendercv.exception import RenderCVUserValidationError
        except ImportError as e:
            return jsonify({"error": f"RenderCV import failed: {str(e)}"}), 500

        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_dir = temp_path / "output"
            output_dir.mkdir(exist_ok=True)

            # Inject theme if not specified
            yaml_content = inject_theme(yaml_content, theme)

            # Step 1: Build RenderCV model
            try:
                _, rendercv_model = build_rendercv_dictionary_and_model(
                    yaml_content,
                    pdf_path=output_dir / "resume.pdf",
                    dont_generate_png=True,
                    dont_generate_html=True,
                    dont_generate_markdown=True,
                )
            except RenderCVUserValidationError as e:
                errors = format_validation_errors(e.validation_errors)
                return jsonify({"error": f"YAML validation failed: {errors}"}), 400
            except Exception as e:
                return jsonify({"error": f"Model build failed: {str(e)}"}), 400

            # Step 2: Generate Typst file
            try:
                typst_path = generate_typst(rendercv_model)
            except Exception as e:
                return jsonify({"error": f"Typst generation failed: {str(e)}"}), 500

            # Step 3: Compile Typst to PDF
            try:
                pdf_bytes = typst.compile(typst_path)
            except Exception as e:
                return jsonify({"error": f"Typst compilation failed: {str(e)}"}), 500

            # Return PDF
            filename = f"{rendercv_model.cv.name}_CV.pdf"
            return Response(
                pdf_bytes,
                mimetype="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def clean_yaml_content(yaml_content: str) -> str:
    """Remove markdown code block markers from YAML content."""
    import re
    content = yaml_content.strip()
    content = re.sub(r'^```(?:yaml|yml)?\s*\n?', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\n?```\s*$', '', content)
    return content.strip()


def inject_theme(yaml_content: str, theme: str) -> str:
    """Inject theme into YAML if not already specified."""
    import yaml
    try:
        data = yaml.safe_load(yaml_content)
        if data is None:
            data = {}
        if "design" not in data:
            data["design"] = {}
        if "theme" not in data["design"]:
            data["design"]["theme"] = theme
        return yaml.dump(data, allow_unicode=True, default_flow_style=False)
    except yaml.YAMLError:
        return yaml_content


def format_validation_errors(errors: list) -> str:
    """Format validation errors into readable string."""
    error_msgs = []
    for i, error in enumerate(errors, 1):
        if isinstance(error, dict):
            loc = ".".join(str(x) for x in error.get("loc", []))
            msg = error.get("msg", "Unknown error")
            error_msgs.append(f"{i}. {loc}: {msg}")
        else:
            error_msgs.append(f"{i}. {str(error)}")
    return "; ".join(error_msgs)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

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
