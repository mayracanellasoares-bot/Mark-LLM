"""Web interface for Mark Shaney BR."""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session

from mark_shaney_br import MarkVShaneyBR, provedores_llm


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("MARK_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=32 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)


def _session_ids() -> tuple[str, str]:
    if "visitor_id" not in session:
        session["visitor_id"] = secrets.token_urlsafe(24)
    if "conversation_id" not in session:
        session["conversation_id"] = secrets.token_urlsafe(18)
    return session["visitor_id"], session["conversation_id"]


def _new_bot() -> tuple[MarkVShaneyBR, str]:
    visitor_id, conversation_id = _session_ids()
    safe_id = hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()[:32]
    bot = MarkVShaneyBR(DATA_DIR / f"{safe_id}.sqlite3")
    bot.sessao = conversation_id
    previous = bot.memoria.db.execute(
        "SELECT id, pedido FROM conversas WHERE sessao=? ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    ).fetchone()
    if previous:
        bot.ultima = previous["id"]
        bot.fontes = bot.memoria.recuperar(previous["pedido"])
    return bot, conversation_id


@app.get("/")
def home():
    return send_from_directory(BASE_DIR / "static", "index.html")


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "app": "Mark Shaney BR"})


@app.get("/api/status")
def status():
    bot, _ = _new_bot()
    try:
        providers = provedores_llm()
        default_provider = next(iter(providers), None)
        documents = bot.memoria.db.execute(
            "SELECT COUNT(*) FROM documentos"
        ).fetchone()[0]
        corrections = bot.memoria.db.execute(
            "SELECT COUNT(*) FROM correcoes"
        ).fetchone()[0]
        return jsonify({
            "llm_enabled": bool(providers),
            "model": providers[default_provider]["model"] if default_provider else None,
            "default_provider": default_provider,
            "providers": [
                {"id": provider_id, "label": config["label"], "model": config["model"]}
                for provider_id, config in providers.items()
            ],
            "documents": documents,
            "corrections": corrections,
        })
    finally:
        bot.memoria.fechar()


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Envie uma mensagem em JSON."}), 400
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Digite uma mensagem."}), 400
    message = message.strip()
    if len(message) > 12_000:
        return jsonify({"error": "A mensagem passou do limite de 12.000 caracteres."}), 413

    providers = provedores_llm()
    requested_provider = body.get("provider")
    if requested_provider is not None and not isinstance(requested_provider, str):
        return jsonify({"error": "Selecione um modelo válido."}), 400
    selected = requested_provider or next(iter(providers), None)
    if selected is not None and selected not in providers:
        return jsonify({"error": "O modelo selecionado não está disponível."}), 400

    bot, _ = _new_bot()
    try:
        reply = bot.executar(message, provider=selected)
        if message == "/nova":
            session["conversation_id"] = bot.sessao
        return jsonify({
            "reply": reply,
            "llm_enabled": bool(providers),
            "model": providers[selected]["model"] if selected else None,
            "provider": selected,
        })
    finally:
        bot.memoria.fechar()


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "A mensagem enviada é grande demais."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
