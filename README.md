# Mark Shaney BR

Assistente de pesquisa em português desenvolvido pela Brittech Inc, empresa de tecnologia brasileira.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abra `http://localhost:10000`.

Defina `MARK_WEB_USER` e `MARK_WEB_PASSWORD` no ambiente antes de abrir o site. Sem senha configurada, as páginas e a API ficam indisponíveis. Configure também `FLASK_SECRET_KEY` com um valor aleatório persistente para manter as sessões entre reinicializações.

## Publicar no Render

O `render.yaml` define um serviço web Python no plano gratuito. Também é possível criar o serviço diretamente com os comandos de build `pip install -r requirements.txt` e de inicialização `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`.

### LLM opcional

Sem configurar uma LLM, a pesquisa e a recuperação de trechos continuam disponíveis; a escrita retorna um roteiro. Para respostas geradas por um servidor compatível com a API de chat completions, configure no Render:

- `MARK_LLM=openai`
- `MARK_MODEL` com o identificador do modelo escolhido
- `MARK_BASE_URL` com a URL base terminada em `/v1`
- `MARK_API_KEY` como segredo, quando o provedor exigir chave; para Maritaca, a variável `MARITACA_API_KEY` também é aceita
- `FLASK_SECRET_KEY` com um segredo aleatório para assinar a sessão

Para adicionar a MandAPI como alternativa interna:

- `MANDAPI_API_KEY` com a chave da MandAPI (segredo)
- `MARK_BASE_URL2=https://api.mandapi.com/v1`
- `MARK_MODEL2=deepseek-v4-flash`

Se apenas a MandAPI estiver configurada, ela vira o provedor padrão. As chaves ficam no servidor; `/api/status` e `/api/chat` não mostram nomes de modelos. O campo opcional `provider` de `/api/chat` continua aceitando `primary` ou `mandapi` para compatibilidade de clientes existentes; a interface não apresenta esse seletor.

Não coloque chaves no repositório. O serviço mantém uma base SQLite separada por navegador. No plano gratuito do Render, o disco é efêmero; a memória pode ser perdida quando a instância reiniciar ou for redeployada.
O login protege o site, `/api/status` e `/api/chat`; apenas `/healthz` permanece público para o monitoramento do Render. Use o botão **Sair** para encerrar a sessão.

## Comandos

Use `/ajuda` para ver os comandos. Entre eles: `/wiki tema`, `/wikisource título`, `/gutenberg autor ou título`, `/openlibrary tema`, `/aprender informação` e `/escrever conto | tema | orientação`.
### Acesso, pesquisa e arquivos no site

Configure `MARK_WEB_USER` e `MARK_WEB_PASSWORD` no Render, além de `FLASK_SECRET_KEY` com um valor aleatório persistente. A página inicial, os arquivos estáticos e as APIs de conversa e exportação exigem login; `/healthz` permanece público para monitoramento.

No chat, **Pesquisar na internet nesta resposta** começa marcado. A pesquisa usa o provedor principal; quando a alternativa está em uso, as evidências pesquisadas são passadas para a resposta. A pesquisa pode ter custo e mostra aviso quando não fica disponível. Se uma API de resposta falhar, o app tenta a outra configurada.

O arquivo `knowledge_sources.py` traz um índice versionado de portais para literatura, gramática, ciências humanas e exatas e direito brasileiro. Isso orienta pesquisas em tempo de uso; os links não são um corpus completo nem prova de leitura. Para perguntas jurídicas, as instruções pedem norma vigente, decisões com órgão/data e distinção entre texto legal, interpretação e aplicação. Sem pesquisa atual, a resposta traz aviso de que leis e precedentes não foram verificados. A memória SQLite por navegador permite guardar informações aprovadas, mas é efêmera no plano gratuito do Render; para conhecimento próprio durável, conecte armazenamento persistente.

Após uma resposta, use **Baixar DOCX**, **Baixar XLSX** ou **Baixar PDF**. A planilha converte tabelas Markdown ou linhas CSV em células; outros textos ficam em uma coluna. Os arquivos são gerados na hora, sem armazenamento no servidor.

**Modos de resposta:** Rápido usa respostas mais curtas (até 700 tokens); Equilibrado usa até 2048; Pensamento usa até 4096 e instruções de verificação. Internamente, o modo Pensamento usa `sabia-4-thinking` no provedor principal (configurável por `MARK_THINKING_MODEL`). Na alternativa, continua `deepseek-v4-flash` com instruções mais cuidadosas. A pesquisa na internet é independente do modo e aumenta o tempo de resposta e o uso da API.

