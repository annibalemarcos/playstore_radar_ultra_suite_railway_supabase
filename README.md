# PlayStore Radar Ultra

Duas versões usando o mesmo motor:

- **Terminal Rich**: `python cli.py` ou `rodar_terminal.bat`
- **Dashboard Web Flask**: `python webapp.py` ou `rodar_web.bat`
- Porta web: **5892**
- Banco: **SQLite local** ou **PostgreSQL/Supabase** por variável de ambiente
- Exports: HTML, JSON e CSV em `playstore_radar_outputs/`

## O que foi turbinado

- Coleta base com `google-play-scraper`.
- Categorias de apps + jogos.
- Modos:
  - **Simples**: parecido com o atual, rápido.
  - **Profundo**: detalhes completos + reviews recentes.
  - **Financeiro**: estima receita/lucro mensal, com faixa baixa/base/alta.
  - **Full**: financeiro + APIs externas disponíveis.
  - **Ultra Full**: tudo ligado, mais reviews, tentativa de developer site e fontes extras.
- Filtros de perfil:
  - Todos.
  - Pequenos/indie.
  - Crescendo.
  - Oportunidade.
  - Sem gigantes.
- Score indie, score crescimento, score oportunidade.
- Estimativa financeira aproximada:
  - MAU estimado.
  - Receita mensal USD baixa/base/alta.
  - Lucro mensal USD/BRL base.
  - Confiança: baixa/média/alta.
- SQLite local ou PostgreSQL/Supabase para histórico e exploração posterior.
- Dashboard web com formulário, runs, logs, tabela de apps, detalhes e export.
- Terminal com painel Rich, progresso e ENTER como padrão.

## Instalação rápida no Windows

```bat
instalar.bat
rodar_terminal.bat
```

Ou dashboard web:

```bat
rodar_web.bat
```

Depois abra:

```text
http://127.0.0.1:5892
```

## Login do dashboard

O acesso web é protegido por sessão. Use:

```text
Usuário: admin
Senha: 000000
```

O login protege o dashboard, APIs internas, configurações e downloads de exportação. A sessão expira após 12 horas e pode ser encerrada pelo botão **Sair**. A chave de assinatura dos cookies é criada localmente em `data/.session_secret` na primeira execução.

## Uso no terminal

```bat
python cli.py
```

ENTER sempre usa padrão.

Padrões principais:

- Escopo: Apps + Jogos
- Modo: Simples
- Perfil: Todos
- Apps por categoria: 25
- Categorias: todas

Também dá para rodar sem perguntas:

```bat
python cli.py --no-interactive --scope JOGOS --level FINANCEIRO --profile PEQUENOS_INDIE --quantity 25 --max-categories 3
```

## APIs externas

As chaves ficam no `.env`, não no código. O zip já vem com `.env` preenchido com as chaves de teste fornecidas nesta conversa.

Variáveis usadas:

```text
SCRAPERAPI_KEY
SCRAPINGBEE_KEY
SCRAPEDO_KEY
BRIGHTDATA_TOKEN
BRIGHTDATA_WEB_UNLOCKER_ZONE
APIFY_TOKEN
APIFY_ACTOR_ID
FIRECRAWL_KEY
SCRAPINGANT_KEY
SERPAPI_KEY
CRAWLBASE_KEY
DECODO_TOKEN
BRAVE_SEARCH_KEY
OPENWEBNINJA_KEY
OPENWEBNINJA_ENDPOINT
```

### Observações importantes

- **Bright Data**: além do token, precisa do nome da zone Web Unlocker em `BRIGHTDATA_WEB_UNLOCKER_ZONE`.
- **OpenWebNinja**: precisa do endpoint exato da API que você quer usar em `OPENWEBNINJA_ENDPOINT`.
- **SerpAPI**: usada para complementar dados da Google Play quando disponível.
- **Decodo**: entra como fallback de Web Scraping API para buscar HTML bruto/renderizado das páginas públicas.
- **Brave Search**: entra como radar de busca web para descobrir páginas da Play Store e complementar evidências externas.
- **Firecrawl/ScraperAPI/ScrapingBee/Scrape.do/ScrapingAnt/Crawlbase**: usadas como fetchers/renderizadores extras para HTML/markdown quando o modo permite.

## Estrutura

```text
app_core/
  categories.py      # categorias Play Store
  config.py          # RunConfig e ApiConfig
  database.py        # SQLite local + PostgreSQL/Supabase
  external_apis.py   # APIs externas opcionais
  exports.py         # HTML/JSON/CSV
  googleplay.py      # google-play-scraper
  runner.py          # motor único CLI/Web
  scoring.py         # scores e financeiro
cli.py               # versão terminal Rich
webapp.py            # versão Flask
```

## Honestidade brutal sobre estimativa financeira

Sem dados internos do app, o financeiro é **chute educado**, não raio-X de conta bancária. Ele serve para ranquear oportunidades, não para afirmar “esse app lucra exatamente X”.

A fórmula usa sinais públicos:

- instalações;
- nota e avaliações;
- atualização/idade;
- anúncios;
- compras no app;
- app pago;
- categoria;
- score de confiança.

## Próximos upgrades bons

- Adicionar integração real com AppMagic/Sensor Tower/Data.ai, se tiver API.
- Job cancelável no web.
- Scheduler para monitorar categorias todo dia.
- Comparar evolução entre runs.
- Export PDF bonito.
- Filtro por país e idioma no dashboard.
- Importar lista manual de app IDs.


### OpenWebNinja Play Store Search

Para usar o endpoint de busca da OpenWebNinja, configure no `.env`:

```env
OPENWEBNINJA_KEY=sua_chave
OPENWEBNINJA_ENDPOINT=https://api.openwebninja.com/play-store-apps/search
```

O projeto chama esse endpoint via `GET` com `params={"q": termo}` e header `X-API-Key`.
Não cole `import requests` ou código Python dentro do `.env`; nele entram só valores.

## Atualização de UI - logs ao vivo

A tela de detalhes da run agora tem um console escuro estilo terminal, com:

- progresso geral no topo;
- contador de apps salvos, apps escaneados, categorias e erros;
- logs ao vivo com auto-scroll;
- botão para copiar logs;
- atualização automática dos apps salvos sem precisar recarregar a página.

Se a página estiver aberta durante a coleta, ela consulta `/api/run/<id>/status` e `/api/run/<id>/apps` automaticamente.

## Atualização de UI - App detalhe e Explorer

A página de detalhes do app foi refeita para não jogar um `JSON bruto` gigante na cara do usuário:

- bloco **Leitura humana** com interpretação resumida do app;
- descrição limpa, sem `\u00e3`, `<br>` e HTML mastigado;
- reviews recentes em cards legíveis;
- keywords de reviews em chips;
- screenshots em grade;
- JSON técnico continua disponível, mas dentro de acordeão de debug e com unicode preservado.

A página `/apps` agora também permite ordenar e filtrar por data da pesquisa:

- `Data da pesquisa · mais recente`;
- `Data da pesquisa · mais antiga`;
- filtro por data inicial/final;
- coluna `Pesquisa` exibindo quando o app foi coletado e a run correspondente.

## Correção de ambiente virtual no Windows

Se aparecer algo como:

```text
'.venv\Scripts\activate.bat' não é reconhecido
ModuleNotFoundError: No module named 'flask'
```

isso significa que a pasta `.venv` não existe, está incompleta ou as dependências não foram instaladas.

A partir desta versão os `.bat` não dependem mais do `activate.bat`. Eles usam diretamente:

```bat
.venv\Scripts\python.exe
```

Arquivos novos/atualizados:

- `_bootstrap_venv.bat`: cria/repara `.venv` e instala dependências.
- `instalar.bat`: instala tudo.
- `rodar_web.bat`: repara automaticamente se `.venv` estiver quebrado ou Flask ausente.
- `rodar_terminal.bat`: mesma lógica para o CLI.
- `reparar_venv.bat`: apaga e recria `.venv` do zero.

Solução rápida:

```bat
reparar_venv.bat
rodar_web.bat
```

## Atualização: histórico e controle em tempo real

A versão web agora tem uma seção própria de **Histórico de pesquisas**.

Controles disponíveis em cada busca:

- **Pausar**: solicita pausa no próximo ponto seguro da coleta.
- **Continuar**: retoma uma busca pausada.
- **Cancelar**: para a busca e mantém apps/logs já salvos.
- **Excluir**: remove run, apps e logs. Se estiver rodando, primeiro solicita parada segura.
- **Reiniciar**: para a busca atual e cria uma nova com a mesma configuração.
- **Refazer**: cria uma nova busca com a mesma configuração, sem mexer na antiga.

A pausa/cancelamento não mata a thread à força; o worker obedece entre categorias/apps/chamadas externas. Isso evita banco corrompido e request pendurada igual fantasma no corredor.


## Filtro fino por categorias

No dashboard web, em **Nova busca**, o campo **Escopo** agora manda no filtro:

- **Apps + Jogos**: roda tudo, sem filtro fino.
- **Somente Aplicativos**: abre um dropdown com checkbox de todas as categorias de apps. O padrão é todas selecionadas.
- **Somente Jogos**: abre um dropdown com checkbox de todas as categorias de jogos. O padrão também é todas.

Dá para marcar uma, várias ou deixar todas. No CLI, o mesmo filtro existe após escolher o escopo; ENTER mantém todas as categorias. Também existe o argumento:

```bat
python cli.py --no-interactive --scope APPS --categories PRODUCTIVITY,TOOLS
python cli.py --no-interactive --scope JOGOS --categories GAME_CASUAL,GAME_PUZZLE
```

## Atualização: configurações de API no dashboard

Agora existe o menu **Configurações** no topo do dashboard.

Nele dá para:

- adicionar/editar chaves de API sem abrir o `.env`;
- manter valores do `.env` com prioridade automática;
- testar uma API individualmente;
- testar todas as APIs configuradas;
- ver cards de uso local por API, com apps enriquecidos, menções em logs, último teste, status e latência.

Regra de prioridade:

```text
.env preenchido > configuração salva no painel > vazio
```

Ou seja: se `BRIGHTDATA_TOKEN` estiver no `.env`, o app usa ele. Se não estiver, ele tenta usar o valor salvo em `data/api_settings.json` pelo menu Configurações.

## Atualização: página de app mais compacta

A página `/app/<id>` foi redesenhada para não virar um pergaminho infinito:

- hero menor;
- ficha/financeiro ficam em coluna lateral;
- conteúdo principal agora usa abas: Resumo, Descrição, Reviews, Mídia e Técnico;
- descrição, reviews e JSON usam rolagem interna;
- JSON principal fica fechado por padrão.

Agora dá para ler o app como ferramenta de decisão, não como autópsia de JSON.


### Ordenação rápida em `/apps`

A seção **Resultado** agora tem um menu de sort rápido por **Pesquisa**, **Nota**, **Installs**, **Scores** e **Receita/mês**. Cada campo tem dois cliques diretos: maior/menor ou mais nova/mais antiga, preservando os filtros atuais.

## Atualização: pacote grande de APIs e grupos

A tela **Configurações** agora organiza os provedores em grupos:

- **Scraping / Render**: ScraperAPI, ScrapingBee, Scrape.do, Bright Data, Apify, Firecrawl, ScrapingAnt, Crawlbase, Decodo, Scrapfly, WebScraping.AI, ZenRows, AlterLab e Jina AI Reader.
- **Search / Discovery**: SerpAPI, Brave Search, OpenWebNinja, Scavio, Exa, Tavily, You.com, Jina Search e WolframAlpha.
- **LLM / Insights**: DeepSeek, OpenRouter, Groq, Mistral, Gemini, Fireworks, Cohere e NLPCloud.
- **Embeddings / Vision**: Jina AI, Voyage AI, Replicate e Roboflow.
- **Automation / Recipes**: SimpleScraper, Browse AI, AbstractAPI e Ollama.

Novas variáveis reconhecidas:

```env
SCRAPFLY_KEY=
WEBSCRAPING_AI_KEY=
ZENROWS_KEY=
ALTERLAB_KEY=
ALTERLAB_PLAYGROUND_KEY=
SCAVIO_KEY=
EXA_API_KEY=
TAVILY_API_KEY=
YOU_API_KEY=
WOLFRAM_APP_ID=
DEEPSEEK_API_KEY=
OPENROUTER_API_KEY=
GROQ_API_KEY=
MISTRAL_API_KEY=
GEMINI_API_KEY=
FIREWORKS_API_KEY=
COHERE_API_KEY=
NLPCLOUD_TOKEN=
JINA_API_KEY=
VOYAGE_API_KEY=
REPLICATE_API_TOKEN=
ROBOFLOW_API_KEY=
SIMPLESCRAPER_KEY=
BROWSEAI_KEY=
ABSTRACTAPI_KEY=
OLLAMA_API_KEY=
```

Integrações funcionais no pipeline:

- **Scrapfly / WebScraping.AI / ZenRows / AlterLab / Jina Reader** entram como fetchers de HTML/markdown nos modos Full e Ultra Full.
- **Scavio / Exa / Tavily / You.com / Jina Search** entram como descoberta extra de candidatos da Play Store.
- **DeepSeek / OpenRouter / Groq / Mistral / Gemini / Fireworks** podem gerar um parecer curto de oportunidade no modo Ultra Full, usando o primeiro provider configurado que responder.
- **SimpleScraper, Browse AI e AbstractAPI** aparecem no painel e nos testes, mas alguns exigem recipe/robot/produto específico para uso real. Sem isso, o app marca como configurado mas avisa no teste.

## Atualização — exportação e tabelas compactas

- Exportação HTML das runs refeita: saiu o modelo de cards e entrou uma tabela comparativa com ícone, app, dev, resumo, categoria, perfil, nota, installs, scores, receita, lucro, data da pesquisa e fontes.
- JSON bruto deixou de poluir o HTML exportado. O relatório visual é para leitura; o JSON completo continua no arquivo `.json` exportado.
- Relatório HTML agora tem filtros rápidos e sort local por pesquisa, nota, installs, scores e receita.
- Dashboard e tela da Run agora exibem os apps salvos em tabela compacta com imagens e métricas, em vez de cards grandes.

## Atualização — export HTML com modal completo por app

A exportação HTML da Run agora mantém a tabela compacta, mas cada linha é clicável.
Ao clicar em um app, abre um modal completo com:

- resumo e ficha técnica;
- financeiro estimado;
- descrição da loja e changelog;
- reviews recentes e palavras frequentes;
- screenshots e links de mídia;
- dados técnicos;
- JSON bruto completo daquele app, com botão para copiar.

Assim o HTML exportado fica bom para comparar em tabela e também serve como relatório completo offline, sem jogar o JSON cru na cara logo de primeira.

## Atualização — Railway + Supabase sem perder o modo local

O app agora possui banco híbrido:

- **local**: continua usando `data/playstore_radar.db` em SQLite, sem configuração adicional;
- **online**: ao definir `DATABASE_URL` ou `SUPABASE_DB_URL`, usa PostgreSQL/Supabase automaticamente.

Foram adicionados:

- `Dockerfile`, `railway.json`, `Procfile` e configuração Gunicorn;
- endpoint público `/health` com teste real do banco;
- criação automática das tabelas no PostgreSQL;
- compatibilidade das mesmas funções de runs, apps, logs, filtros e exportações nos dois bancos;
- script `scripts/migrate_sqlite_to_supabase.py` para copiar o histórico existente;
- login e chave de sessão configuráveis por variáveis de ambiente;
- suporte ao `PORT` injetado pelo Railway;
- `.dockerignore` e `.gitignore` para não publicar `.env`, banco local, venv e relatórios.

Veja o passo a passo completo em `DEPLOY_RAILWAY_SUPABASE.md`.
