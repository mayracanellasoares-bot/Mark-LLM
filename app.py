"""Web interface for Mark Shaney BR."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, send_from_directory, session, url_for

from export_files import create_export
from mark_shaney_br import MarkVShaneyBR, provedores_llm


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("MARK_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=32 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)


@app.before_request
def require_login():
    if request.endpoint in {"login", "healthz"}:
        return None
    if not os.environ.get("MARK_WEB_PASSWORD"):
        return jsonify({"error": "Acesso em configuração."}), 503
    if session.get("authenticated") is not True:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Faça login para usar o chat."}), 401
        return redirect(url_for("login"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("authenticated") is True:
            return redirect(url_for("home"))
        return send_from_directory(BASE_DIR / "static", "login.html")

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    configured_user = os.environ.get("MARK_WEB_USER", "Mark")
    configured_password = os.environ.get("MARK_WEB_PASSWORD", "")
    if (configured_password
            and secrets.compare_digest(username, configured_user)
            and secrets.compare_digest(password, configured_password)):
        session.clear()
        session["authenticated"] = True
        session.permanent = True
        return redirect(url_for("home"))
    return redirect(url_for("login", erro=1))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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
        documents = bot.memoria.db.execute(
            "SELECT COUNT(*) FROM documentos"
        ).fetchone()[0]
        corrections = bot.memoria.db.execute(
            "SELECT COUNT(*) FROM correcoes"
        ).fetchone()[0]
        return jsonify({
            "llm_enabled": bool(providers),
            "knowledge_areas": ["literatura", "gramática", "ciências humanas", "ciências exatas", "direito brasileiro"],
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
    web = body.get("web", False)
    if not isinstance(web, bool):
        return jsonify({"error": "Opção de pesquisa inválida."}), 400
    mode = body.get('mode', 'balanced')
    if mode not in ('fast', 'balanced', 'thinking'):
        return jsonify({'error': 'Modo de resposta inválido.'}), 400

    bot, _ = _new_bot()
    try:
        reply = bot.executar(message, provider=selected, web=web, mode=mode)
        if message == "/nova":
            session["conversation_id"] = bot.sessao
        return jsonify({
            "reply": reply,
            "llm_enabled": bool(providers),
            "mode": mode,
            "web_used": bot.web_used,
            "provider_issues": bot.provider_issues,
        })
    finally:
        bot.memoria.fechar()


@app.post('/api/export')
def export():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or body.get('format') not in ('docx', 'xlsx', 'pdf'):
        return jsonify({'error': 'Escolha DOCX, XLSX ou PDF.'}), 400
    content = body.get('content')
    if not isinstance(content, str) or not content.strip() or len(content) > 25000:
        return jsonify({'error': 'O texto deve ter entre 1 e 25.000 caracteres.'}), 400
    output, mime, name = create_export(content, body['format'])
    return send_file(output, mimetype=mime, as_attachment=True, download_name=name)


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "A mensagem enviada é grande demais."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
