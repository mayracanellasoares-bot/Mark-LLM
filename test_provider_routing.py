"""Contrato HTTP das duas rotas de LLM sem fazer chamadas cobradas."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as web


class ProviderRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = mock.patch.object(web, "DATA_DIR", Path(self.temp_dir.name))
        self.data_dir.start()
        self.addCleanup(self.data_dir.stop)
        self.environment = mock.patch.dict(os.environ, {
            "MARK_LLM": "openai",
            "MARK_MODEL": "sabia-4",
            "MARK_BASE_URL": "https://chat.maritaca.ai/api",
            "MARITACA_API_KEY": "test-maritaca",
            "MANDAPI_API_KEY": "test-mandapi",
            "MARK_MODEL2": "deepseek-v4-flash",
            "MARK_BASE_URL2": "https://api.mandapi.com/v1",
            "MARK_WEB_USER": "Mark",
            "MARK_WEB_PASSWORD": "test-password",
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = web.app.test_client()
        response = self.client.post("/login", data={"username": "Mark", "password": "test-password"})
        self.assertEqual(response.status_code, 302)

    def test_login_guards_site_and_api_and_logout_ends_session(self):
        visitor = web.app.test_client()
        self.assertEqual(visitor.get("/").status_code, 302)
        self.assertEqual(visitor.get("/static/index.html").status_code, 302)
        self.assertEqual(visitor.get("/api/status").status_code, 401)
        self.assertEqual(visitor.post("/api/chat", json={"message": "Olá"}).status_code, 401)
        self.assertEqual(visitor.get("/healthz").status_code, 200)
        login_page = visitor.get("/login")
        self.assertEqual(login_page.status_code, 200)
        self.assertNotIn("test-password", login_page.get_data(as_text=True))
        login_page.close()
        self.assertIn("erro=1", visitor.post("/login", data={"username": "Mark", "password": "errada"}).location)
        self.assertEqual(visitor.get("/api/status").status_code, 401)
        visitor.post("/login", data={"username": "Mark", "password": "test-password"})
        self.assertEqual(visitor.get("/api/status").status_code, 200)
        visitor.post("/logout")
        self.assertEqual(visitor.get("/api/status").status_code, 401)

    def test_status_lists_models_without_credentials(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["default_provider"], "primary")
        self.assertEqual([item["id"] for item in data["providers"]], ["primary", "mandapi"])
        self.assertEqual(data["providers"][1]["model"], "deepseek-v4-flash")
        self.assertNotIn("test-mandapi", response.get_data(as_text=True))
        self.assertNotIn("test-maritaca", response.get_data(as_text=True))

    def test_each_model_uses_its_own_endpoint_and_key(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request.full_url, request.get_header("Authorization"), json.loads(request.data)))
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": "Resposta de teste"}}]}).encode())

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            mandapi = self.client.post("/api/chat", json={"message": "Olá", "provider": "mandapi"})
            primary = self.client.post("/api/chat", json={"message": "Olá", "provider": "primary"})

        self.assertEqual(mandapi.status_code, 200)
        self.assertEqual(primary.status_code, 200)
        self.assertEqual(mandapi.get_json()["model"], "deepseek-v4-flash")
        self.assertEqual(calls[0][0:2], ("https://api.mandapi.com/v1/chat/completions", "Bearer test-mandapi"))
        self.assertEqual(calls[0][2]["model"], "deepseek-v4-flash")
        self.assertEqual(calls[1][0:2], ("https://chat.maritaca.ai/api/chat/completions", "Bearer test-maritaca"))
        self.assertEqual(calls[1][2]["model"], "sabia-4")

    def test_unavailable_provider_is_rejected_before_network(self):
        with mock.patch("urllib.request.urlopen") as network:
            response = self.client.post("/api/chat", json={"message": "Olá", "provider": "other"})
        self.assertEqual(response.status_code, 400)
        network.assert_not_called()

    def test_mandapi_alone_uses_documented_defaults(self):
        with mock.patch.dict(os.environ, {"MANDAPI_API_KEY": "test-mandapi", "MARK_WEB_PASSWORD": "test-password"}, clear=True):
            status = self.client.get("/api/status").get_json()
            self.assertEqual(status["default_provider"], "mandapi")
            self.assertEqual(status["model"], "deepseek-v4-flash")
            self.assertEqual([item["id"] for item in status["providers"]], ["mandapi"])

    def test_web_search_uses_maritaca_and_passes_evidence_to_mandapi(self):
        calls = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data)
            calls.append(payload)
            answer = 'Fonte: https://example.org' if payload['model'] == 'sabia-4' else 'Resumo com evidência'
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': answer}}]}).encode())

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            response = self.client.post('/api/chat', json={'message': 'Novidades', 'provider': 'mandapi', 'web': True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['web_used'])
        self.assertTrue(calls[0]['web_search'])
        self.assertNotIn('web_search', calls[1])
        self.assertIn('https://example.org', str(calls[1]['messages']))

    def test_provider_failure_falls_back_and_reports_actual_provider(self):
        from urllib.error import URLError
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request.full_url)
            if 'mandapi' in request.full_url:
                raise URLError('provider unavailable')
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': 'Resposta reserva'}}]}).encode())

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            response = self.client.post('/api/chat', json={'message': 'Olá', 'provider': 'mandapi'})
        self.assertEqual(response.get_json()['provider'], 'primary')
        self.assertEqual(len(calls), 2)

    def test_export_files_are_real_and_login_protected(self):
        import zipfile
        for kind, signature in [('docx', b'PK'), ('xlsx', b'PK'), ('pdf', b'%PDF')]:
            response = self.client.post('/api/export', json={'format': kind, 'content': 'Título\nAção,Valor\nLivro,3'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.startswith(signature))
            if kind != 'pdf':
                with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                    self.assertTrue(archive.namelist())
        self.assertEqual(web.app.test_client().post('/api/export', json={'format': 'pdf', 'content': 'Teste'}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
