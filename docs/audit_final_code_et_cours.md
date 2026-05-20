# Audit final code et cours

Projet : **LangGraph-Based Multi-Agent System for Automated Software Testing**  
Depot audite : `Test-automation-malak`  
Date de l'audit : 2026-05-20  
Regle appliquee : analyse seulement, aucune suppression, aucune refactorisation.

## 1. Resume simple du projet

Le projet automatise une partie du travail de test logiciel. L'utilisateur donne un depot cible, soit avec `repo_path`, soit avec `repo_url`, puis donne l'URL de l'application a tester avec `target_url`. Le systeme analyse le code du depot, retrouve les informations importantes, cree un plan de tests, execute des tests API/UI/performance, classe les anomalies, puis genere un rapport HTML lisible.

Le probleme resolu est le suivant : avant de tester une application, il faut comprendre son architecture, ses routes, ses pages, son authentification, ses risques et ses resultats de tests. Le projet transforme ce processus manuel en pipeline structure.

Le projet utilise un systeme multi-agents parce que chaque etape a une responsabilite differente :

- Orchestrator : valide la demande et choisit les agents.
- Repository Analyzer : lit le depot sans l'executer.
- RAG Agent : prepare le contexte utile.
- Test Planner : genere le plan de tests.
- API/UI/Performance Agents : executent les tests.
- Bug Analysis Agent : classe les problemes.
- Report Agent : genere les livrables finaux.

LangGraph est utilise parce que le cours du professeur presente les workflows comme un graphe avec un `State`, des `nodes` et des `edges`. Ici, chaque agent est un node LangGraph, et tous les agents communiquent par le `TestAutomationState`.

Le RAG est utilise pour eviter que le LLM invente des tests. Le systeme indexe des fichiers du depot, retrouve les chunks utiles, puis donne ce contexte au Test Planner. Le Test Planner doit generer un plan de tests base sur des preuves.

MCP et les tools servent a standardiser l'acces aux actions techniques : lister les fichiers, cloner un depot, envoyer une requete HTTP, generer un rapport HTML. Les tools locaux sont le mode par defaut ; MCP est optionnel avec `--use-mcp-tools`.

Le projet genere des JSON parce que chaque agent produit une sortie structuree, testable et reutilisable. Le rapport HTML est genere pour la demonstration et pour rendre les resultats faciles a lire.

L'utilisateur utilise l'application de deux facons :

- Dashboard Flask : `python app.py`, puis ouvrir `http://127.0.0.1:5000`.
- CLI : `python -m test_auto.main ...`.

## 2. Flux global du projet

### Lancement

Avec le dashboard, `app.py` cree l'application Flask via `test_auto.interface.flask_app.create_app()`. Le formulaire construit un `initial_state` dans `src/test_auto/interface/run_service.py`, puis appelle `run_workflow()`.

Avec le CLI, `src/test_auto/main.py` lit les arguments, construit `user_preferences`, puis appelle aussi `run_workflow()`.

### Entrees utilisateur

Les principales entrees sont :

- `repo_path` : depot local, prioritaire si fourni.
- `repo_url` : depot GitHub/Git a cloner si pas de depot local.
- `target_url` : URL de l'application cible a tester.
- `test_types` : `api`, `ui`, `performance`.
- `focus` ou `rag_query` : sujet de recherche RAG.
- `planner_use_llm` : active le planner LLM dans le workflow.
- `use_mcp_tools` : active MCP si possible.

### Workflow reel

```text
START
-> orchestrator
-> repo_analyzer
-> rag
-> test_planner
-> api_testing
-> ui_testing
-> performance_testing
-> bug_analysis
-> report
-> END
```

Le workflow est **mixte** :

- il est principalement sequentiel ;
- il utilise des edges conditionnels ;
- certains agents sont sautes selon les preferences ou selon les donnees disponibles ;
- il n'y a pas de parallelisme LangGraph reel dans `workflow.py`.

Exemples de conditions :

- si le depot est invalide, on s'arrete apres Orchestrator ;
- si `skip_ui_testing=True`, le node UI est saute ;
- si aucun test API n'est planifie, API Testing peut etre saute ;
- si `skip_report=True`, Report Agent est saute.

### Resultats generes

Chaque execution cree un dossier :

```text
results/runs/<run_id>/
```

Le rapport HTML est cree dans :

```text
reports/generated/report_<run_id>.html
```

## 3. Analyse LangGraph

Fichiers principaux :

- `src/test_auto/graph/state.py`
- `src/test_auto/graph/workflow.py`
- `src/test_auto/graph/routing.py`

Le `State` est defini dans `state.py` avec `TestAutomationState(TypedDict, total=False)`. Il contient les entrees utilisateur, les decisions de l'orchestrator, les resultats de chaque agent, les chemins des artefacts et les logs.

Chaque node lit le State et retourne un dictionnaire partiel. LangGraph fusionne ce dictionnaire dans le State global. C'est conforme a la logique du cours.

Dans `workflow.py`, le graphe est construit avec :

- `StateGraph(TestAutomationState)`
- `add_node(...)`
- `add_edge(START, "orchestrator")`
- `add_conditional_edges(...)`
- `add_edge("report", END)`
- `compile()`
- `graph.invoke(initial_state)`

### Tableau LangGraph

| Element du cours LangGraph | Present ? | Fichier | Explication |
|---|---:|---|---|
| `StateGraph` | Oui | `src/test_auto/graph/workflow.py` | Construit le workflow principal. |
| `START` | Oui | `workflow.py` | Point d'entree du graphe. |
| `END` | Oui | `workflow.py` | Fin du graphe. |
| TypedDict State | Oui | `state.py` | `TestAutomationState` definit la memoire partagee. |
| Nodes | Oui | `workflow.py` | Chaque agent est ajoute avec `add_node`. |
| Edges | Oui | `workflow.py` | `START -> orchestrator`, puis `report -> END`. |
| Conditional edges | Oui | `workflow.py`, `routing.py` | Routage selon erreurs, preferences et donnees disponibles. |
| `graph.invoke` | Oui | `workflow.py`, mini workflows | Lance le graphe avec un State initial. |
| `compile` | Oui | `workflow.py` | Compile le graphe avant invocation. |
| State update par dict | Oui | tous les agents | Chaque node retourne un dictionnaire partiel. |

Ce qu'il faut montrer au professeur :

1. `state.py` pour la memoire partagee.
2. `workflow.py` pour le graphe complet.
3. `routing.py` pour les conditions.
4. Un agent node, par exemple `test_planner_node`, pour montrer le retour par dictionnaire.

## 4. Analyse des agents

| Agent | Type | LLM ? | Tools ? | MCP ? | JSON produit | Conforme cours ? | Remarque |
|---|---|---:|---:|---:|---|---|---|
| Orchestrator | Deterministe | Non | Oui, validation locale | Non | `orchestrator_result.json` | Oui | Valide l'entree et choisit les agents. |
| Repository Analyzer | Deterministe | Non | Oui, `repo_tools` | Optionnel | `repo_analyzer_result.json`, `project_info.json` | Oui | Lit ou clone le depot sans executer le code. |
| RAG Agent | Deterministe RAG | Non | Oui, `rag_tools` | Non | `rag_result.json`, `retrieved_context.json`, `rag_index/*` | Oui | Prepare le contexte pour le planner. |
| Test Planner | Agent LLM principal | Oui si active | Oui, planning tools | Non | `test_plan.json`, `test_planner_result.json` | Oui avec la correction `create_agent` | Genere le plan de tests depuis le contexte RAG. |
| API Testing Agent | Execution deterministe | Non | Oui, `api_tools` | Optionnel | `api_result.json` | Oui | Execute les tests API planifies. |
| UI Testing Agent | Execution deterministe | Non | Oui, `selenium_tools` | Non | `ui_result.json`, `screenshots/` | Oui | Execute les tests UI planifies avec Selenium. |
| Performance Testing Agent | Execution deterministe | Non | Oui, `performance_tools` | Non | `performance_result.json`, `performance/` | Oui | Lance de petites charges Locust sures. |
| Bug Analysis Agent | Analyse deterministe | Non | Oui, `bug_tools`, `analysis/bug_rules.py` | Non | `bug_result.json` | Oui | Classe les anomalies. |
| Report Agent | Aggregation deterministe | Non | Oui, `report_tools`, `reporting/` | Optionnel | `final_results.json`, `report_result.json`, HTML | Oui | Produit le rapport final. |
| Base | Support | Non | Non | Non | helper generique | Support | Centralise erreurs et sauvegarde JSON. |

Les agents API/UI/Performance peuvent etre deterministes parce qu'ils executent des tests techniques. Ce n'est pas leur role d'inventer une strategie. Le Test Planner est le bon endroit pour le LLM car c'est lui qui transforme des preuves du depot en plan de tests.

Phrase utile pour la soutenance : les agents d'execution sont deterministes pour rester fiables et reproductibles ; le LLM est reserve a la planification, ou le raisonnement sur le contexte est utile.

## 5. Test Planner et `create_agent`

Fichiers inspectes :

- `src/test_auto/agents/test_planner.py`
- `src/test_auto/tools/planning_tools.py`
- `src/test_auto/planning/llm_planner.py`
- `src/test_auto/planning/deterministic_planner.py`
- `src/test_auto/planning/prompt_builder.py`
- `src/test_auto/planning/validators.py`

Constats :

- `create_agent` est utilise dans `src/test_auto/planning/llm_planner.py`.
- `ChatGroq` est utilise si `LLM_PROVIDER=groq`.
- `ChatMistralAI` est utilise si `LLM_PROVIDER=mistral`.
- `InMemorySaver` est utilise comme checkpointer.
- Le fallback deterministe est conserve dans `plan_with_llm_or_fallback`.
- `planner_use_llm=True` active le LLM dans le workflow principal via `test_planner_node`.
- `--planner-no-llm` force le fallback dans le CLI principal.
- Le JSON est extrait avec `_extract_json`, normalise avec `_normalize_llm_test_plan`, puis valide avec `TestPlan(...)`.
- Le plan est ensuite verifie contre les preuves avec `validate_test_plan_against_evidence`.

Variables `.env` utiles :

```text
LLM_PROVIDER=groq
GROQ_API_KEY : a renseigner dans .env
GROQ_MODEL=...
```

ou :

```text
LLM_PROVIDER=mistral
MISTRAL_API_KEY : a renseigner dans .env
MISTRAL_MODEL=...
```

Attention : le fichier `.env.example` actuel contient des valeurs qui ressemblent a de vraies cles. Il faut les remplacer par des placeholders et faire une rotation des cles avant rendu.

Phrase attendue :

> Les agents d'execution sont deterministes, tandis que le Test Planner est l'agent LLM principal, construit avec `create_agent`, qui utilise le contexte RAG pour generer un plan de tests.

Autre phrase de soutenance :

> Le Test Planner est maintenant un agent LangChain cree avec `create_agent`, utilisant Groq ou Mistral selon la configuration, avec fallback deterministe si aucune cle API n'est disponible.

## 6. Analyse RAG

Fichiers principaux :

- `src/test_auto/rag/chunking.py`
- `src/test_auto/rag/embeddings.py`
- `src/test_auto/rag/vector_store.py`
- `src/test_auto/rag/retriever.py`
- `src/test_auto/agents/rag_agent.py`
- `src/test_auto/tools/rag_tools.py`

Le RAG indexe les fichiers selectionnes par Repository Analyzer : README/docs, fichiers API, fichiers UI, tests et config utiles. Les fichiers sont lus de facon sure par `read_text_file`.

Le chunking est local :

- Markdown decoupe par titres.
- Python decoupe autour des fonctions/classes/routes.
- Autres fichiers decoupes par lignes avec overlap.

Les embeddings sont deterministes avec `LocalHashEmbeddingModel`, base sur hash de tokens en 256 dimensions. Ce n'est pas un embedding semantique OpenAI ou HuggingFace ; c'est un MVP local, reproductible et sans cout.

L'index est stocke ici :

```text
results/runs/<run_id>/rag_index/
  chunks.json
  vectors.json
  manifest.json
```

Le retrieval calcule la similarite cosinus et sauvegarde :

```text
results/runs/<run_id>/retrieved_context.json
results/runs/<run_id>/rag_result.json
```

Le contexte recupere est injecte dans le Test Planner via le State, champ `retrieved_context`.

### Tableau RAG

| Etape RAG | Present ? | Fichier | Commentaire |
|---|---:|---|---|
| Document loading | Oui | `rag_agent.py`, `rag_tools.py`, `repo_tools.py` | Selectionne et lit les fichiers candidats. |
| Chunking | Oui | `rag/chunking.py` | Chunking Markdown/Python/generique. |
| Embeddings | Oui | `rag/embeddings.py` | Embeddings locaux par hash, MVP. |
| Vector store | Oui | `rag/vector_store.py` | JSON local, pas de base vectorielle externe. |
| Retrieval | Oui | `rag/retriever.py` | Top-k par similarite cosinus. |
| Context injection to planner | Oui | `rag_agent.py`, `test_planner.py` | `retrieved_context` passe par le State. |

Conclusion : RAG conforme au cours dans l'architecture, mais MVP sur les embeddings.

## 7. Tools et MCP

Tools locaux dans `src/test_auto/tools/` :

- `repo_tools.py` : clone, liste, lecture, detection framework/routes/UI.
- `rag_tools.py` : selection, indexation, retrieval.
- `planning_tools.py` : contexte planner, appel LLM/fallback, persistence.
- `api_tools.py` : requetes HTTP, assertions, sauvegarde.
- `selenium_tools.py` : Selenium, screenshots, assertions UI.
- `performance_tools.py` : generation Locust, execution, parsing CSV, seuils.
- `bug_tools.py` : chargement, masquage, sauvegarde bug.
- `report_tools.py` : sauvegarde final/report/latest.

Constat important : il n'y a pas de decorators `@tool` LangChain dans `src/test_auto/tools/`. Les tools locaux sont des fonctions Python classiques. Les tools MCP, eux, sont de vrais tools exposes avec `@mcp.tool`.

MCP :

- `FastMCP` est utilise dans `mcp_servers/testing_tools_server.py`.
- Les tools MCP sont decores avec `@mcp.tool()`.
- `MultiServerMCPClient` est utilise dans `src/test_auto/mcp/testing_mcp_client.py`.
- Le routage optionnel local/MCP est dans `src/test_auto/mcp/tool_router.py`.
- Les agents qui peuvent utiliser MCP : Repository Analyzer, API Testing Agent, Report Agent.
- Activation : CLI `--use-mcp-tools` ou dashboard checkbox `Use MCP tools when available`.
- MCP n'est pas obligatoire. En cas d'echec MCP, le code retombe sur les tools locaux.

### Tableau tools

| Tool | Local ou MCP | Fichier | Utilise par | Role | Conforme cours ? |
|---|---|---|---|---|---|
| `list_project_files` | Local | `tools/repo_tools.py` | Repository Analyzer, RAG | Lister les fichiers | Partiel, fonction locale |
| `clone_repository` | Local | `tools/repo_tools.py` | Repository Analyzer | Cloner un repo public | Partiel |
| `read_text_file` | Local | `tools/repo_tools.py` | RAG, MCP server | Lire un fichier safe | Partiel |
| `index_project_documents` | Local | `tools/rag_tools.py` | RAG Agent | Creer index RAG | Conforme RAG |
| `generate_test_plan_from_context` | Local | `tools/planning_tools.py` | Test Planner | LLM/fallback | Conforme avec agent planner |
| `send_http_request` | Local | `tools/api_tools.py` | API Agent, MCP server | Executer requete HTTP | Partiel |
| `execute_ui_test_case` | Local | `tools/selenium_tools.py` | UI Agent | Test UI Selenium | Partiel |
| `execute_performance_test_case` | Local | `tools/performance_tools.py` | Performance Agent | Test Locust | Partiel |
| `save_bug_result` | Local | `tools/bug_tools.py` | Bug Agent | Sauvegarder bug JSON | Support |
| `render_and_save_report` | Local | `reporting/html_renderer.py` | Report Agent | Generer HTML | Support |
| `health_check` | MCP | `mcp_servers/testing_tools_server.py` | Demo/tests MCP | Verifier serveur | Conforme MCP |
| `validate_url_tool` | MCP | `testing_tools_server.py` | MCP demo | Valider URL | Conforme MCP |
| `list_project_files_tool` | MCP | `testing_tools_server.py` | Repository Analyzer optionnel | Lister fichiers via MCP | Conforme MCP |
| `read_text_file_tool` | MCP | `testing_tools_server.py` | MCP demo | Lire fichier via MCP | Conforme MCP |
| `clone_repository_tool` | MCP | `testing_tools_server.py` | Repository Analyzer optionnel | Cloner repo via MCP | Conforme MCP |
| `send_http_request_tool` | MCP | `testing_tools_server.py` | API Agent optionnel | Requete HTTP via MCP | Conforme MCP |
| `generate_html_report_tool` | MCP | `testing_tools_server.py` | Report Agent optionnel | Rapport HTML via MCP | Conforme MCP |
| `save_json_artifact_tool` | MCP | `testing_tools_server.py` | Demo/tests MCP | Sauvegarde JSON | Conforme MCP |

Point a dire au professeur : le projet montre MCP comme couche optionnelle standardisee ; le workflow reste robuste car les tools locaux sont le fallback.

## 8. Interface Flask

Fichiers :

- `app.py`
- `src/test_auto/interface/flask_app.py`
- `src/test_auto/interface/run_service.py`
- `src/test_auto/interface/dashboard_helpers.py`
- `templates/`
- `static/dashboard.css`

Le dashboard Flask permet de lancer le workflow sans CLI. Il affiche :

- formulaire de repo GitHub/local ;
- target URL ;
- focus RAG ;
- test types API/UI/Performance ;
- options skip ;
- option MCP ;
- disponibilite LLM ;
- derniers runs ;
- rapport HTML integre.

Commande :

```powershell
python app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000
```

L'interface est un bonus fort pour la demo, mais le coeur du projet reste le package `src/test_auto` et le workflow LangGraph.

## 9. Reporting et resultats

Le reporting part des JSON produits par les agents, calcule des KPIs, construit `final_results.json`, puis rend le template Jinja2 `reports/templates/report.html.j2`.

| Fichier genere | Qui le genere | Role | Quand le montrer |
|---|---|---|---|
| `orchestrator_result.json` | Orchestrator | Decision initiale | Pour expliquer la selection des agents. |
| `project_info.json` | Repository Analyzer | Metadata du depot | Pour montrer l'analyse statique. |
| `repo_analyzer_result.json` | Repository Analyzer | Resultat complet agent | Pour les preuves repo. |
| `rag_result.json` | RAG Agent | Resume index/retrieval | Pour montrer le RAG. |
| `retrieved_context.json` | RAG Agent | Chunks donnes au planner | Tres important pour expliquer grounding. |
| `rag_index/chunks.json` | RAG | Chunks indexes | Demo technique RAG. |
| `rag_index/vectors.json` | RAG | Vecteurs locaux | Demo technique, pas besoin de l'ouvrir longuement. |
| `rag_index/manifest.json` | RAG | Metadata index | Utile pour preuve. |
| `test_plan.json` | Test Planner | Plan de tests | Fichier central a montrer. |
| `test_planner_result.json` | Test Planner | Sortie agent + model_info | Montrer `agent_mode` et fallback/LLM. |
| `api_result.json` | API Agent | Resultats API | Demo execution. |
| `ui_result.json` | UI Agent | Resultats UI | Demo UI/Selenium. |
| `screenshots/` | UI Agent | Captures d'echec | Demo si disponible. |
| `performance_result.json` | Performance Agent | Resultats Locust | Demo performance. |
| `performance/` | Performance Agent | Locustfile/CSV/artefacts | Demo technique. |
| `bug_result.json` | Bug Agent | Anomalies/recommendations | Demo analyse. |
| `final_results.json` | Report Agent | Agregation finale | Base du rapport. |
| `report_result.json` | Report Agent | Sortie agent report | Preuve reporting. |
| `workflow_state.json` | Workflow | State final complet | Tres utile pour expliquer LangGraph. |
| `reports/generated/report_<run_id>.html` | Report Agent | Rapport lisible | A montrer en soutenance. |

## 10. Tests

La commande `pytest --collect-only -q` collecte **317 tests**. La derniere execution complete connue a donne :

```text
317 passed
```

Les tests couvrent :

- schemas Pydantic ;
- orchestrator ;
- repository analyzer ;
- RAG chunking/vector store/retrieval ;
- Test Planner et fallback ;
- API tools/agent/workflow ;
- UI tools/agent/workflow ;
- performance tools/agent/workflow ;
- bug rules/agent/workflow ;
- reporting et KPIs ;
- dashboard Flask ;
- MCP server/client/router ;
- workflow integre.

Difference importante :

- Les tests pytest testent le systeme lui-meme.
- Les tests generes/executés par le workflow testent l'application cible donnee par `target_url`.

Scripts utiles :

- `scripts/final_smoke_test.py`
- `scripts/check_no_secrets.py`
- `scripts/validate_llm_config.py`
- `scripts/validate_optional_llm_config.py`
- `scripts/llm_planner_smoke_test.py`
- `scripts/validate_github_input.py`
- `scripts/validate_notebook_env.py`
- `scripts/setup_notebook_kernel.py`
- `scripts/setup_notebooks.ps1`
- `scripts/setup_notebooks.sh`

Les notebooks servent de traces pedagogiques par milestone. Ils sont utiles pour la soutenance si le professeur veut voir l'evolution.

## 11. Commandes Windows PowerShell

### Installer et preparer

```powershell
cd C:\Users\aicha\Documents\PFA_SMA\Test-automation-malak
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Alternative sans editable install :

```powershell
$env:PYTHONPATH="src"
```

### Lancer le dashboard

```powershell
python app.py
```

Puis :

```text
http://127.0.0.1:5000
```

### Lancer le workflow sans LLM

```powershell
python -m test_auto.main --repo-url "https://github.com/Vitaee/DjangoRestAPI" --target-url "http://localhost:8000" --test-types api ui performance --execution-mode sequential --focus "JWT authentication todo CRUD API tests" --planner-no-llm
```

### Lancer le workflow avec LLM

Dans `.env` :

```text
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

Puis :

```powershell
python -m test_auto.main --repo-url "https://github.com/Vitaee/DjangoRestAPI" --target-url "http://localhost:8000" --test-types api ui performance --execution-mode sequential --focus "JWT authentication todo CRUD API tests"
```

### Lancer avec repo local

```powershell
python -m test_auto.main --repo-path "..\DjangoRestAPI" --target-url "http://localhost:8000" --test-types api ui performance --execution-mode sequential --focus "JWT authentication todo CRUD API tests" --planner-no-llm
```

### Lancer avec repo GitHub

```powershell
python -m test_auto.main --repo-url "https://github.com/Vitaee/DjangoRestAPI" --target-url "http://localhost:8000" --test-types api ui performance --execution-mode sequential --focus "JWT authentication todo CRUD API tests" --planner-no-llm
```

### Lancer pytest

```powershell
pytest -q
```

## 12. Dossiers utiles / inutiles

| Element | Role | Utilise ? | Decision | Justification |
|---|---|---:|---|---|
| `.pytest_cache` | Cache pytest | Non runtime | Nettoyer avant ZIP | Genere automatiquement. |
| `.vscode` | Settings VS Code | Optionnel | Garder si utile | `settings.json` aide l'environnement local. |
| `config` | Exemples config | Oui doc/demo | Garder | Montre config projet et MCP. |
| `docs` | Documentation soutenance | Oui | Garder | Important pour presentation. |
| `mcp_servers` | Serveur FastMCP | Oui optionnel | Garder | Preuve MCP. |
| `notebooks` | Traces pedagogiques | Oui soutenance | Garder | Bonus fort pour le cours. |
| `reports` | Templates + rapports | Oui | Garder templates, nettoyer generated | `templates` obligatoire, `generated` est regenerable. |
| `results` | Artefacts workflow | Oui genere | Garder `.gitkeep`, nettoyer runs | Runs regenerables. |
| `scripts` | Validation/smoke | Oui | Garder | Utile avant demo. |
| `src/sma_test_automation.egg-info` | Metadata install editable | Non source | Nettoyer avant ZIP | Genere par `pip install -e .`. |
| `src/test_auto` | Code principal | Oui | Garder | Coeur du projet. |
| `static` | CSS dashboard | Oui | Garder | Interface Flask. |
| `templates` | Templates Flask | Oui | Garder | Interface Flask. |
| `tests` | Tests pytest | Oui | Garder | Preuve qualite. |
| `venv` | Environnement local | Non version | Exclure ZIP | Trop lourd, regenerable. |
| `.env` | Secrets locaux | Oui local | Ne jamais versionner | Deja ignore. |
| `.env.example` | Exemple env | Oui | Corriger avant rendu | Contient actuellement des valeurs sensibles apparentes. |
| `.gitignore` | Hygiene repo | Oui | Garder | Correct globalement. |
| `app.py` | Launcher dashboard | Oui | Garder | Point entree demo. |
| `pyproject.toml` | Package/tests | Oui | Garder | Pythonpath pytest et packaging. |
| `README.md` | Guide principal | Oui | Garder | Tres utile. |
| `requirements.txt` | Dependances | Oui | Garder | Installation. |

### A supprimer seulement apres validation Aicha

- `.pytest_cache/`
- `venv/`
- `src/sma_test_automation.egg-info/`
- `results/runs/`
- `results/latest_run.txt`
- fichiers HTML generes dans `reports/generated/` sauf `.gitkeep`
- runs de demo obsoletes dans `results/`
- eventuels notebooks checkpoints `.ipynb_checkpoints/`

Ne rien supprimer sans validation, surtout pas `reports/templates/`, `src/test_auto/`, `tests/`, `mcp_servers/`, `templates/`, `static/`, `docs/`.

## 13. `.gitignore` et ZIP final

Le `.gitignore` actuel exclut bien :

- `__pycache__/`
- `*.pyc`
- `*.egg-info/`
- `.pytest_cache/`
- `.venv/`
- `venv/`
- `.env`
- `.env.*`
- `results/runs/`
- `results/latest_run.txt`
- `reports/generated/*`
- checkpoints notebooks
- logs dashboard

Il garde volontairement :

- `.env.example`
- `reports/generated/.gitkeep`
- `.vscode/settings.json`

Probleme urgent : `.env.example` est suivi par Git et contient actuellement des valeurs qui ressemblent a de vraies cles. Il faut le remplacer par :

```text
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=openai/gpt-oss-120b
MISTRAL_API_KEY=your_mistral_key_here
MISTRAL_MODEL=mistral-medium-latest
GITHUB_TOKEN : optionnel, a renseigner dans .env seulement
GITHUB_DEFAULT_BRANCH=main
```

Et il faut considerer les cles exposees comme compromises : rotation/revocation recommandee.

ZIP final recommande :

A inclure :

- `src/test_auto/`
- `mcp_servers/`
- `templates/`
- `static/`
- `reports/templates/`
- `reports/generated/.gitkeep`
- `results/.gitkeep`
- `tests/`
- `docs/`
- `notebooks/`
- `scripts/`
- `config/`
- `README.md`
- `requirements.txt`
- `pyproject.toml`
- `.gitignore`
- `.env.example` apres nettoyage
- `app.py`

A exclure :

- `venv/`
- `.pytest_cache/`
- `__pycache__/`
- `.env`
- `results/runs/`
- `results/latest_run.txt`
- rapports HTML generes sauf si on veut inclure un exemple volontaire
- `src/sma_test_automation.egg-info/`

## 14. Conformite avec le cours

| Exigence du cours | Statut | Fichier preuve | Comment expliquer | Correction si besoin |
|---|---|---|---|---|
| LangGraph `StateGraph` | Conforme | `graph/workflow.py` | Workflow principal sous forme de graphe. | Aucune. |
| `START` / `END` | Conforme | `graph/workflow.py` | Entree/sortie explicites. | Aucune. |
| Nodes / edges | Conforme | `graph/workflow.py` | Chaque agent est un node. | Aucune. |
| Conditional edges | Conforme | `graph/workflow.py`, `graph/routing.py` | Routage selon State. | Aucune. |
| State partage | Conforme | `graph/state.py` | TypedDict commun. | Aucune. |
| `create_agent` | Conforme | `planning/llm_planner.py` | Test Planner cree un agent LangChain. | Verifier dependance `langchain` si environnement prof. |
| LLM Groq/Mistral | Conforme | `planning/llm_planner.py`, `shared/secrets.py` | Provider par `.env`. | Nettoyer `.env.example`. |
| Fallback deterministe | Conforme | `planning/llm_planner.py`, `deterministic_planner.py` | Le projet reste fonctionnel sans cle. | Aucune. |
| `@tool` LangChain | Partiel | Aucun dans `src/test_auto/tools` | Tools locaux sont des fonctions Python, pas decorateurs LangChain. | Bonus : decorer quelques tools si exige strictement. |
| FastMCP | Conforme | `mcp_servers/testing_tools_server.py` | Serveur MCP autonome. | Aucune. |
| `@mcp.tool` | Conforme | `testing_tools_server.py` | Plusieurs tools MCP exposes. | Aucune. |
| `MultiServerMCPClient` | Conforme | `mcp/testing_mcp_client.py` | Client MCP via adapter LangChain. | Aucune. |
| RAG | Conforme MVP | `rag/`, `rag_agent.py` | Chargement, chunking, embeddings, retrieval. | Amelioration possible embeddings semantiques. |
| Chunking | Conforme | `rag/chunking.py` | Decoupe par type de fichier. | Aucune. |
| Embeddings | Partiel/MVP | `rag/embeddings.py` | Local hash embeddings. | Bonus : vrai modele embeddings. |
| Retrieval | Conforme | `rag/retriever.py` | Recherche top-k. | Aucune. |
| JSON reports | Conforme | tous agents, `reporting/` | Artefacts structures. | Aucune. |
| Dashboard Flask/Jinja2 | Bonus conforme | `app.py`, `interface/`, `templates/` | Demo visuelle. | Aucune. |
| Notebooks | Bonus | `notebooks/` | Traces de milestones. | Aucune. |
| Pytest | Conforme | `tests/` | 317 tests collectes/passes. | Aucune. |
| Separation agents | Conforme | `agents/` | Responsabilites separees. | Aucune. |

## 15. Corrections avant rendu

### Urgent

| Fichier | Risque | Action recommandee | Effort |
|---|---|---|---|
| `.env.example` | Exposition de secrets apparents | Remplacer par placeholders + rotation des cles | 10 min + rotation comptes |
| Dependances | `langchain.agents.create_agent` peut manquer si seul `langchain-core` est installe | Verifier `pip install -r requirements.txt`, ajouter `langchain` si necessaire apres validation | 10 min |
| Working tree | Fichiers modifies non valides | Verifier `git diff` avant ZIP | 5 min |

### Important

| Fichier | Risque | Action recommandee | Effort |
|---|---|---|---|
| `README.md` | Dit encore "future" ou "no required real LLM calls" par endroits | Harmoniser avec l'etat final `create_agent`/LLM optionnel | 20 min |
| `config/config.example.yml` | `planner.default_mode` indique fallback et `allow_llm: false`, alors que CLI/dashboard sont LLM-first | Clarifier exemple config | 10 min |
| `src/test_auto/agents/base.py` | Commentaire avec caracteres mal encodes | Nettoyer commentaire si autorise | 5 min |
| `src/test_auto/tools/` | Pas de `@tool` LangChain local | Si le prof insiste, decorer 2-3 tools demonstratifs | 30-45 min |

### Bonus

| Fichier | Risque | Action recommandee | Effort |
|---|---|---|---|
| `rag/embeddings.py` | Embeddings MVP non semantiques | Ajouter backend embeddings externe optionnel | 1-2 h |
| Dashboard | Execution synchrone | Ajouter queue/background job | 1 jour |
| UI tests | Selecteurs simples | Ajouter detection de locators plus avancee | 1 jour |
| Performance | Locust local simple | Ajouter profil de charge configurable | 2-3 h |

## 16. Explication pedagogique

Ordre conseille pour lire le projet :

1. `README.md` : comprendre le but et les commandes.
2. `app.py` : point d'entree dashboard.
3. `src/test_auto/graph/state.py` : comprendre la memoire partagee.
4. `src/test_auto/graph/workflow.py` : comprendre le graphe.
5. `src/test_auto/agents/orchestrator.py` : validation et selection.
6. `src/test_auto/agents/repo_analyzer.py` : analyse statique du depot.
7. `src/test_auto/agents/rag_agent.py` : creation du contexte.
8. `src/test_auto/agents/test_planner.py` : agent de planification.
9. `src/test_auto/planning/llm_planner.py` : `create_agent`, Groq/Mistral, fallback.
10. `src/test_auto/agents/api_testing_agent.py` : execution API.
11. `src/test_auto/agents/ui_testing_agent.py` : execution UI.
12. `src/test_auto/agents/performance_testing_agent.py` : execution performance.
13. `src/test_auto/agents/bug_analysis_agent.py` : analyse anomalies.
14. `src/test_auto/agents/report_agent.py` : rapport final.
15. `src/test_auto/tools/` : fonctions techniques.
16. `src/test_auto/mcp/` et `mcp_servers/` : MCP optionnel.
17. `src/test_auto/reporting/` : generation final JSON/HTML.
18. `tests/` : preuve de robustesse.

Questions possibles du professeur :

- Pourquoi LangGraph ? Pour expliciter State, nodes, edges et conditions.
- Pourquoi pas un LLM partout ? Parce que les agents d'execution doivent etre deterministes, reproductibles et surs.
- Pourquoi RAG ? Pour donner au planner des preuves du depot et reduire les hallucinations.
- Pourquoi JSON ? Pour avoir des sorties validables, testables et reutilisables.
- Que fait MCP ? Il expose certains tools sous forme standardisee, optionnelle.
- Que se passe-t-il sans cle API ? Fallback deterministe, le workflow continue.
- Ou est `create_agent` ? Dans `src/test_auto/planning/llm_planner.py`.

## 17. Verdict final

Le projet fonctionne-t-il ? **Oui.**

Le projet suit-il le cours ? **Oui avec reserves mineures.** LangGraph, RAG, MCP, JSON, dashboard, tests et separation d'agents sont bien presents. Le Test Planner est maintenant aligne avec `create_agent`. La reserve principale est l'absence de decorators `@tool` LangChain dans les tools locaux ; MCP utilise bien `@mcp.tool`.

Est-il clair pour etre explique ? **Oui.** L'architecture est lisible et les noms de fichiers correspondent aux agents.

Risques restants :

- `.env.example` contient des secrets apparents : correction urgente avant rendu.
- Verifier que l'environnement du professeur installe bien `langchain` complet, pas seulement `langchain-core`.
- Nettoyer les artefacts generes avant ZIP.

Faut-il nettoyer des dossiers ? **Oui, mais seulement apres validation Aicha.** Nettoyer `venv`, `.pytest_cache`, `results/runs`, `reports/generated/*.html`, egg-info.

Faut-il corriger encore du code ? **Pas pour la demo fonctionnelle**, sauf nettoyage secrets et eventuellement dependance `langchain`.

Peut-on preparer la presentation avec ce projet ? **Oui avec reserves**, apres nettoyage des secrets et verification finale `pytest -q`.

## 18. Livrables de cette analyse

### Fichiers lus principaux

- `README.md`
- `.gitignore`
- `.env.example`
- `requirements.txt`
- `pyproject.toml`
- `app.py`
- `src/test_auto/main.py`
- `src/test_auto/graph/state.py`
- `src/test_auto/graph/workflow.py`
- `src/test_auto/graph/routing.py`
- tous les fichiers de `src/test_auto/agents/`
- fichiers de `src/test_auto/planning/`
- fichiers de `src/test_auto/rag/`
- fichiers de `src/test_auto/tools/`
- fichiers de `src/test_auto/mcp/`
- `mcp_servers/testing_tools_server.py`
- fichiers de `src/test_auto/interface/`
- fichiers de `src/test_auto/reporting/`
- `reports/templates/report.html.j2`
- `templates/index.html`
- `tests/`
- `scripts/`
- `notebooks/`
- `config/`

### Fichiers suspects ou inutiles

Suspects / a corriger :

- `.env.example` : contient des secrets apparents.
- `config/config.example.yml` : valeurs planner un peu incoherentes avec LLM-first actuel.
- `src/test_auto/agents/base.py` : commentaire encode bizarrement.

Inutiles ou regenerables :

- `.pytest_cache/`
- `venv/`
- `src/sma_test_automation.egg-info/`
- `results/runs/`
- `results/latest_run.txt`
- `reports/generated/*.html`

### Commandes a tester

```powershell
pytest -q
python scripts/check_no_secrets.py
python scripts/validate_llm_config.py
python scripts/final_smoke_test.py
python mcp_servers/testing_tools_server.py --self-test
python app.py
```

### Verdict final court

**Oui, le projet est presentable et coherent avec le cours, avec deux actions avant rendu : nettoyer les secrets dans `.env.example` et verifier la dependance `langchain` pour `create_agent`.**

### Prochaines actions recommandees

1. Remplacer les cles dans `.env.example` par des placeholders.
2. Revoquer/rotater les cles qui ont ete exposees.
3. Verifier `pip install -r requirements.txt` dans un venv propre.
4. Lancer `pytest -q`.
5. Nettoyer les dossiers generes apres validation Aicha.
6. Preparer la demo dashboard + rapport HTML + code `workflow.py` + code `llm_planner.py`.
