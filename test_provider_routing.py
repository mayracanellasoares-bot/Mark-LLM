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

    def test_status_hides_model_names_and_reports_domains(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['llm_enabled'])
        self.assertIn('direito brasileiro', data['knowledge_areas'])
        self.assertNotIn('model', data)
        self.assertNotIn('providers', data)
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
        self.assertNotIn('model', mandapi.get_json())
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
            self.assertTrue(status['llm_enabled'])
            self.assertNotIn('model', status)

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
        self.assertEqual(response.get_json()['reply'], 'Resposta reserva')
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

    def test_response_modes_set_limits_and_report_real_model(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(json.loads(request.data))
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': 'Tudo certo'}}]}).encode())

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            for mode in ('fast', 'balanced', 'thinking'):
                response = self.client.post('/api/chat', json={'message': 'Explique', 'provider': 'primary', 'mode': mode})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()['mode'], mode)
        self.assertEqual([call['max_tokens'] for call in calls], [700, 2048, 4096])
        self.assertEqual([call['model'] for call in calls], ['sabia-4', 'sabia-4', 'sabia-4-thinking'])
        self.assertNotIn('model', response.get_json())
        self.assertIn('sem expor raciocínio interno', calls[-1]['messages'][0]['content'])

    def test_mandapi_thinking_keeps_its_model_and_mode_validation(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(json.loads(request.data))
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': 'OK'}}]}).encode())

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            result = self.client.post('/api/chat', json={'message': 'Calcule', 'provider': 'mandapi', 'mode': 'thinking'})
        self.assertNotIn('model', result.get_json())
        self.assertEqual(calls[0]['max_tokens'], 4096)
        self.assertEqual(calls[0]['model'], 'deepseek-v4-flash')
        self.assertEqual(self.client.post('/api/chat', json={'message': 'Olá', 'mode': 'desconhecido'}).status_code, 400)

    def test_thinking_fallback_reports_actual_provider_and_model(self):
        from urllib.error import HTTPError

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data)
            if payload['model'] == 'sabia-4-thinking':
                raise HTTPError(request.full_url, 429, 'rate limit', {}, io.BytesIO())
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': 'Reserva'}}]}).encode())

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            result = self.client.post('/api/chat', json={'message': 'Pense', 'provider': 'primary', 'mode': 'thinking'})
        self.assertEqual(result.get_json()['reply'], 'Reserva')
        self.assertNotIn('provider', result.get_json())
        self.assertEqual(result.get_json()['provider_issues'], ['Serviço de resposta: HTTP 429'])

    def test_topic_source_guides_and_legal_freshness_warning(self):
        from knowledge_sources import assunto, guia
        self.assertEqual(assunto('Qual a interpretação da CLT no TST?'), 'juridico')
        self.assertEqual(assunto('Dúvida de crase'), 'gramatica')
        self.assertEqual(assunto('Romance de Machado de Assis'), 'literatura')
        self.assertEqual(assunto('Geografia e população'), 'humanas')
        self.assertEqual(assunto('Cálculo de uma equação'), 'exatas')
        self.assertIn('planalto.gov.br', guia('Lei 13.467')[1])
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(json.loads(request.data))
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': 'Resposta'}}]}).encode())

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            no_web = self.client.post('/api/chat', json={'message': 'A lei 13.467 continua vigente?', 'web': False})
            with_web = self.client.post('/api/chat', json={'message': 'A lei 13.467 continua vigente?', 'web': True})
            help_reply = self.client.post('/api/chat', json={'message': '/ajuda'})
            status_reply = self.client.post('/api/chat', json={'message': '/status'})
        self.assertIn('não foram verificados', no_web.get_json()['reply'])
        self.assertNotIn('não foram verificados', with_web.get_json()['reply'])
        self.assertIn('planalto.gov.br', calls[0]['messages'][0]['content'])
        self.assertTrue(calls[1]['web_search'])
        self.assertIn('Brittech Inc', calls[0]['messages'][0]['content'])
        self.assertIn('Brittech Inc', help_reply.get_json()['reply'])
        for response in (help_reply, status_reply):
            self.assertNotIn('sabia-4', response.get_json()['reply'])

    def test_visible_pages_credit_brittech_without_model_selector(self):
        response = self.client.get('/')
        page = response.get_data(as_text=True)
        self.assertIn('Brittech Inc', page)
        self.assertNotIn('modelSwitcher', page)
        self.assertNotIn('Modelo:', page)
        response.close()
        visitor = web.app.test_client()
        login = visitor.get('/login')
        self.assertIn('Brittech Inc', login.get_data(as_text=True))
        login.close()

    def test_spreadsheet_export_does_not_execute_untrusted_formulas(self):
        from openpyxl import load_workbook
        data = self.client.post('/api/export', json={'format': 'xlsx', 'content': 'Campo,Valor\nInseguro,=2+2'}).data
        sheet = load_workbook(io.BytesIO(data)).active
        self.assertEqual(sheet['B2'].data_type, 's')
        self.assertEqual(sheet['B2'].value, "'=2+2")

    def test_bad_payload_and_file_size_are_rejected(self):
        self.assertEqual(self.client.post('/api/chat', json={'message': 'Olá', 'web': 'yes'}).status_code, 400)
        self.assertEqual(self.client.post('/api/chat', json={'message': 'Olá', 'mode': {}}).status_code, 400)
        self.assertEqual(self.client.post('/api/export', json={'format': 'zip', 'content': 'ok'}).status_code, 400)
        self.assertEqual(self.client.post('/api/export', json={'format': 'pdf', 'content': 'x' * 25001}).status_code, 400)

    def test_generic_request_to_rephrase_gets_a_real_retry(self):
        calls = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data)
            calls.append(payload)
            content = 'Pode reformular a pergunta?' if len(calls) == 1 else '**Resposta útil:** a regência depende do sentido.'
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': content}}]}).encode())

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            result = self.client.post('/api/chat', json={'message': 'Explique a regência de assistir', 'web': False})
        self.assertEqual(len(calls), 2)
        self.assertIn('resposta anterior ficou', calls[1]['messages'][0]['content'].lower())
        self.assertEqual(result.get_json()['reply'], 'Resposta útil: a regência depende do sentido.')

    def test_formatting_preserves_code_operators_and_history_skips_bad_reply(self):
        from mark_shaney_br import limpar_formatacao, resposta_insuficiente
        self.assertTrue(resposta_insuficiente('Poderia reformular a pergunta?'))
        self.assertFalse(resposta_insuficiente('A resposta é 42. Se quiser, pode reformular a pergunta com outra condição.'))
        self.assertEqual(limpar_formatacao('**Título** e *ênfase* `f(**kwargs)`\n```python\nf(**kwargs)\n```'),
                         'Título e ênfase `f(**kwargs)`\n```python\nf(**kwargs)\n```')

    def test_both_provider_errors_are_reported_as_service_error(self):
        from urllib.error import HTTPError

        def fail(request, timeout):
            raise HTTPError(request.full_url, 503, 'offline', {}, io.BytesIO())

        with mock.patch('urllib.request.urlopen', side_effect=fail):
            result = self.client.post('/api/chat', json={'message': 'Pergunta', 'web': False})
        self.assertEqual(result.status_code, 503)
        self.assertNotIn('reply', result.get_json())
        self.assertIn('indisponíveis', result.get_json()['error'])

    def test_pwa_manifest_icons_install_button_and_no_private_cache(self):
        from PIL import Image
        manifest = web.app.test_client().get('/manifest.webmanifest')
        self.assertEqual(manifest.status_code, 200)
        config = json.loads(manifest.data)
        self.assertEqual(config['display'], 'standalone')
        self.assertEqual(config['start_url'], '/')
        manifest.close()
        for size in (192, 512):
            icon = web.app.test_client().get(f'/icons/icon-{size}.png')
            self.assertEqual(icon.status_code, 200)
            self.assertEqual(Image.open(io.BytesIO(icon.data)).size, (size, size))
            icon.close()
        worker = web.app.test_client().get('/sw.js')
        self.assertEqual(worker.status_code, 200)
        self.assertNotIn('caches.open', worker.get_data(as_text=True))
        worker.close()
        self.assertEqual(web.app.test_client().get('/icons/../../app.py').status_code, 404)
        page = self.client.get('/')
        html = page.get_data(as_text=True)
        self.assertIn('id="install"', html)
        self.assertIn('beforeinstallprompt', html)
        self.assertIn('/manifest.webmanifest', html)
        page.close()


if __name__ == "__main__":
    unittest.main()
