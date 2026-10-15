"""Frontend + pré-processamento real, com eventos de progresso e resultado parcial."""

from io import BytesIO
from pathlib import Path
import warnings
import json

import cv2
from flask import Flask, Request, Response, jsonify, request, send_from_directory, stream_with_context
import numpy as np
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from backend.src.mock_analysis import generate_analysis
from backend.src.preprocessing import detectar_e_isolar_rosto
from backend.src.segmentation.pipeline import PipelineError, analysis_events

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000


class MemoryUploadRequest(Request):
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        # Evita que Werkzeug transfira uploads maiores para arquivos temporários.
        return BytesIO()


def decode_photo(data):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Use uma foto JPG, PNG ou WebP.")
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("A foto deve ter no máximo 24 megapixels.")
            oriented = ImageOps.exif_transpose(source)
            profile = source.info.get("icc_profile")
            if profile:
                oriented = ImageCms.profileToProfile(
                    oriented, ImageCms.ImageCmsProfile(BytesIO(profile)),
                    ImageCms.createProfile("sRGB"), outputMode="RGB")
            else:
                oriented = oriented.convert("RGB")
            oriented.thumbnail((1600, 1600))
            return cv2.cvtColor(np.array(oriented), cv2.COLOR_RGB2BGR)


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    app.request_class = MemoryUploadRequest
    app.config.update(MAX_CONTENT_LENGTH=MAX_FILE_BYTES + 1024 * 1024, MAX_FORM_PARTS=5)
    if test_config:
        app.config.update(test_config)
    app.json.ensure_ascii = False

    def error(code, message, status):
        return jsonify(codigo=code, mensagem=message), status

    @app.get("/")
    def index():
        return send_from_directory(ROOT / "frontend", "index.html")

    @app.get("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(ROOT / "frontend" / "assets", filename)

    @app.get("/css/<path:filename>")
    def styles(filename):
        return send_from_directory(ROOT / "frontend" / "css", filename)

    @app.get("/js/<path:filename>")
    def scripts(filename):
        return send_from_directory(ROOT / "frontend" / "js", filename)

    @app.get("/api/exemplo")
    def example():
        return jsonify(generate_analysis(example=True))

    @app.post("/api/analises")
    def analyze():
        photo = request.files.get("foto")
        if photo is None or not photo.filename:
            return error("FOTO_OBRIGATORIA", "Selecione uma foto para continuar.", 400)
        data = photo.stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            return error("FOTO_MUITO_GRANDE", "A foto deve ter no máximo 10 MB.", 413)
        try:
            image = decode_photo(data)
        except (ValueError, OSError, UnidentifiedImageError, ImageCms.PyCMSError,
                Image.DecompressionBombError, Image.DecompressionBombWarning):
            return error("FOTO_INVALIDA", "Não foi possível ler a foto. Use JPG, PNG ou WebP com até 24 megapixels.", 400)

        # O mesmo pipeline atende JSON e progresso em tempo real, sem guardar jobs.
        events = analysis_events(image, detectar_e_isolar_rosto, generate_analysis)
        if request.accept_mimetypes.best == "application/x-ndjson":
            def stream():
                try:
                    for event in events:
                        yield json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
                except PipelineError as exc:
                    yield json.dumps({"tipo": "erro", "codigo": exc.code,
                                      "mensagem": str(exc), "status": exc.status}, ensure_ascii=False) + "\n"
                except Exception:
                    app.logger.exception("Falha no pipeline durante streaming")
                    yield json.dumps({"tipo": "erro", "codigo": "ERRO_INTERNO",
                                      "mensagem": "Não foi possível processar agora. Tente novamente.", "status": 500}) + "\n"
                finally:
                    events.close()
            response = Response(stream_with_context(stream()), mimetype="application/x-ndjson")
            response.headers["X-Accel-Buffering"] = "no"
            return response
        try:
            for event in events:
                if event["tipo"] == "resultado":
                    return jsonify(event["dados"])
        except PipelineError as exc:
            return error(exc.code, str(exc), exc.status)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_exc):
        return error("FOTO_MUITO_GRANDE", "A foto deve ter no máximo 10 MB.", 413)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return error("REQUISICAO_INVALIDA", "Não foi possível atender esta solicitação.", exc.code)

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        app.logger.exception("Falha no processamento da solicitação")
        return error("ERRO_INTERNO", "Não foi possível processar agora. Tente novamente.", 500)

    @app.after_request
    def headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000)
