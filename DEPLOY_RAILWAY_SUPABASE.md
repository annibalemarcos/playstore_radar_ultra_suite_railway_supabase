# Deploy no Railway com banco Supabase

O projeto agora escolhe o banco automaticamente:

- sem `DATABASE_URL`: usa o SQLite local existente em `data/playstore_radar.db`;
- com `DATABASE_URL` ou `SUPABASE_DB_URL`: usa PostgreSQL no Supabase.

Não é necessário editar o código para alternar entre local e online.

## 1. Criar o projeto no Supabase

1. Crie um projeto no Supabase.
2. No painel do projeto, clique em **Connect**.
3. Copie a connection string do **Session pooler**, porta `5432`.
4. Troque o marcador da senha pela senha real do banco.

Formato aproximado:

```text
postgresql://postgres.PROJECT_REF:SENHA@aws-0-REGIAO.pooler.supabase.com:5432/postgres
```

O Session pooler é a opção mais previsível para um backend persistente em redes IPv4. A aplicação também desativa prepared statements, então aceita o pooler transacional da porta `6543`, embora o Session pooler seja o recomendado aqui.

## 2. Publicar no Railway

### Via GitHub

1. Extraia este ZIP.
2. Suba os arquivos para um repositório privado no GitHub.
3. No Railway, crie um projeto e escolha **Deploy from GitHub repo**.
4. Selecione o repositório.

### Via Railway CLI

Na pasta do projeto:

```bash
railway login
railway init
railway up
```

O Railway detectará o `Dockerfile` e o `railway.json`. O servidor inicia com Gunicorn em `0.0.0.0:$PORT`, e o healthcheck usa `/health`.

## 3. Variáveis obrigatórias no Railway

Abra o serviço no Railway e adicione:

```env
DATABASE_URL=postgresql://postgres.PROJECT_REF:SENHA@aws-0-REGIAO.pooler.supabase.com:5432/postgres
PLAYSTORE_RADAR_SECRET_KEY=gere-uma-chave-longa-e-aleatoria
PLAYSTORE_RADAR_LOGIN_USER=admin
PLAYSTORE_RADAR_LOGIN_PASSWORD=troque-esta-senha
DB_SSLMODE=require
```

Gere a chave de sessão localmente com:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

As credenciais antigas `admin` / `000000` continuam como padrão local. Em produção, troque a senha usando as variáveis acima.

Adicione também no Railway as chaves das APIs que deseja usar, por exemplo `SERPAPI_KEY`, `FIRECRAWL_KEY`, `SCRAPERAPI_KEY` etc. Variáveis do Railway são preferíveis ao painel de Configurações porque o disco do container é temporário.

## 4. Inicialização do banco

Não é necessário criar tabelas manualmente. O app cria e atualiza o schema na primeira inicialização.

Para validar a conexão antes do deploy:

### Windows PowerShell

```powershell
$env:DATABASE_URL="postgresql://..."
python scripts/init_database.py
```

### Linux/macOS

```bash
DATABASE_URL='postgresql://...' python scripts/init_database.py
```

## 5. Migrar o histórico SQLite existente

Para copiar as runs, apps, logs e testes de API do banco local atual para o Supabase:

### Windows PowerShell

```powershell
$env:DATABASE_URL="postgresql://..."
python scripts/migrate_sqlite_to_supabase.py
```

### Linux/macOS

```bash
DATABASE_URL='postgresql://...' python scripts/migrate_sqlite_to_supabase.py
```

O script recusa um destino que já contenha dados. Para mesclar/atualizar registros por ID:

```bash
python scripts/migrate_sqlite_to_supabase.py --merge
```

Faça essa migração uma vez, antes de começar a usar o app online.

## 6. Domínio público

No Railway, abra **Settings → Networking → Generate Domain**. Depois acesse o domínio gerado e faça login.

## 7. Observações importantes

- Mantenha **uma réplica** e **um worker Gunicorn**. O scraper atual usa threads internas e controles em memória; múltiplos workers poderiam iniciar ou controlar tarefas de forma desencontrada.
- O histórico e os apps ficam persistentes no Supabase.
- Relatórios HTML/JSON/CSV são gerados a partir do banco quando solicitados. Os arquivos temporários no container podem desaparecer após um redeploy, sem perda dos dados do Supabase.
- O endpoint `/health` testa também a conexão com o banco e retorna `503` quando o PostgreSQL está indisponível.
- Nunca envie `.env` ou senhas para um repositório público. O `.dockerignore` e o `.gitignore` já excluem esses arquivos.

## Documentação oficial consultada

- Railway Flask: https://docs.railway.com/guides/flask
- Railway healthchecks: https://docs.railway.com/deployments/healthchecks
- Railway Config as Code: https://docs.railway.com/config-as-code
- Supabase — conectar ao Postgres: https://supabase.com/docs/guides/database/connecting-to-postgres
