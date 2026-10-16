# Mark Shaney BR

Oficina literária e pesquisa em português, construída sobre o projeto Mark Shaney BR 2.0.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abra `http://localhost:10000`.

## Publicar no Render

O `render.yaml` define um serviço web Python no plano gratuito. Também é possível criar o serviço diretamente com os comandos de build `pip install -r requirements.txt` e de inicialização `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`.

### LLM opcional

Sem configurar uma LLM, a pesquisa e a recuperação de trechos continuam disponíveis; a escrita retorna um roteiro. Para respostas geradas por um servidor compatível com a API de chat completions, configure no Render:

- `MARK_LLM=openai`
- `MARK_MODEL` com o identificador do modelo escolhido
- `MARK_BASE_URL` com a URL base terminada em `/v1`
- `MARK_API_KEY` como segredo, quando o provedor exigir chave; para Maritaca, a variável `MARITACA_API_KEY` também é aceita
- `FLASK_SECRET_KEY` com um segredo aleatório para assinar a sessão

Para adicionar a MandAPI com DeepSeek V4 Flash como segunda opção no seletor do chat:

- `MANDAPI_API_KEY` com a chave da MandAPI (segredo)
- `MARK_BASE_URL2=https://api.mandapi.com/v1`
- `MARK_MODEL2=deepseek-v4-flash`

Se apenas a MandAPI estiver configurada, ela vira o modelo padrão. As chaves ficam no servidor; `/api/status` expõe apenas os nomes e IDs dos modelos. O campo `provider` de `/api/chat` aceita `primary` ou `mandapi` quando disponíveis.

Não coloque chaves no repositório. O serviço mantém uma base SQLite separada por navegador. No plano gratuito do Render, o disco é efêmero; a memória pode ser perdida quando a instância reiniciar ou for redeployada.

## Comandos

Use `/ajuda` para ver os comandos. Entre eles: `/wiki tema`, `/wikisource título`, `/gutenberg autor ou título`, `/openlibrary tema`, `/aprender informação` e `/escrever conto | tema | orientação`.
