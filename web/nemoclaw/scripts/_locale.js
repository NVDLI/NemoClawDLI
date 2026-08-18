// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Accessible course-language switcher backed by the build-time language manifest.
// The manifest lists only built locales; each locale lists pages that passed localization review.

const PT_TEXT = new Map(Object.entries({
  "The Agent": "O agente",
  "The ReAct Loop": "O ciclo ReAct",
  "Tools at Scale": "Ferramentas em escala",
  "Workflows": "Workflows",
  "The Index Agent": "O agente de índice",
  "Deep Agents": "Agentes profundos",
  "Connect NemoClaw": "Conectar o NemoClaw",
  "Always-On": "Operação contínua",
  "Modern CLIs": "CLIs modernas",
  "Going Further": "Próximos passos",
  "loop · LLM as function": "ciclo · LLM como função",
  "tools · finish_reason": "ferramentas · finish_reason",
  "JSON · MCP · routing": "JSON · MCP · roteamento",
  "router · planner · ReWOO": "roteador · planejador · ReWOO",
  "embed · retrieve · bundle": "incorporar · recuperar · pacote",
  "planner · sub-agents · VFS": "planejador · subagentes · VFS",
  "launchable · first call": "launchable · primeira chamada",
  "file-as-context · paste URL": "arquivo como contexto · colar URL",
  "sandbox · policy · CI gate": "sandbox · política · gate de CI",
  "Section": "Seção",
  "Section 1": "Seção 1",
  "Section 2": "Seção 2",
  "Section 3": "Seção 3",
  "Section 4": "Seção 4",
  "Course map": "Mapa do curso",
  "click to see all sections": "clique para ver todas as seções",
  "start": "início",
  "end": "fim",
  "No API key": "Sem chave de API",
  "Key …": "Chave …",
  "Key set ✓": "Chave definida ✓",
  "Key rejected ✗": "Chave rejeitada ✗",
  "Model": "Modelo",
  "Pages": "Páginas",
  "none pinned = auto-select": "nenhuma fixada = seleção automática",
  "🧠 memory: on": "🧠 memória: ativa",
  "🧠 memory: off": "🧠 memória: inativa",
  "↺ New chat": "↺ Nova conversa",
  "Ask a question…": "Faça uma pergunta…",
  "Send": "Enviar",
  "⏹ Stop": "⏹ Parar",
  "▶ Run": "▶ Executar",
  "▶ Run all": "▶ Executar tudo",
  "⏳ Running…": "⏳ Executando…",
  "↺ Reset": "↺ Restaurar",
  "↺ Reset code": "↺ Restaurar código",
  "Ready": "Pronto",
  "clear": "limpar",
  "■ stop": "■ parar",
  "Stopping…": "Parando…",
  "+ branch": "+ ramificação",
  "Connect your launchable on Module 3a first (its URL and token), then your agent is reachable here.": "Primeiro conecte seu launchable no Módulo 3a com a URL e o token. Depois disso, o agente ficará acessível aqui.",
  "Connected to your agent over the gateway. Ask anything, type /help, click a prompt, or press Tab to autocomplete.": "Conectado ao agente pelo gateway. Faça uma pergunta, digite /help, selecione uma sugestão ou pressione Tab para autocompletar.",
  "Use /commands for the live gateway list. /clear empties this screen; /new and /branch manage independent agent sessions. Text without a slash is sent to the active agent session.": "Use /commands para listar os comandos atuais do gateway. /clear limpa a tela; /new e /branch gerenciam sessões independentes. Texto sem barra é enviado à sessão ativa.",
  "No commands reported by the gateway.": "O gateway não informou comandos.",
  "setting up this session (the first reply takes a moment)…": "preparando esta sessão (a primeira resposta pode demorar)…",
  "empty until you Run": "vazio até executar",
  "reset. empty until you Run": "restaurado; vazio até executar",
  "javascript · editable · re-run": "javascript · editável · execute novamente",
  "JSON · editable": "JSON · editável",
  "click to collapse": "clique para recolher",
  "click to expand": "clique para expandir",
  "in scope inside every node:": "disponível em todos os nós:",
  "click a row to inspect & edit its source": "clique em uma linha para inspecionar e editar o código-fonte",
  "in scope for this cell. Click a row to read its source": "disponível nesta célula. Clique em uma linha para ler o código-fonte",
  "✓ API key available in this tab": "✓ Chave de API disponível nesta aba",
  "Chat route:": "Rota de chat:",
  "Embedding route:": "Rota de embeddings:",
  "Chat API base URL": "URL base da API de chat",
  "Chat model ID": "ID do modelo de chat",
  "Chat API bearer key (NVIDIA keys start with": "Chave bearer da API de chat (chaves NVIDIA começam com",
  "Embedding route (persistent and independent)": "Rota de embeddings (persistente e independente)",
  "Embedding exercises keep this route when the chat route changes.": "Os exercícios de embeddings mantêm esta rota quando a rota de chat muda.",
  "Embedding API base URL": "URL base da API de embeddings",
  "Embedding model ID": "ID do modelo de embeddings",
  "Embedding API bearer key": "Chave bearer da API de embeddings",
  "Base URL": "URL base",
  "Bearer token": "Token bearer",
  "Access provider": "Provedor de acesso",
  "Access session": "Sessão de acesso",
  "Enter the launchable URL and its browser access session. The course discovers everything else.": "Informe a URL do launchable e a sessão de acesso do navegador. O curso descobre o restante.",
  "Enter Base URL and Access session. Provider, relay route, and gateway token are discovered automatically.": "Informe a URL base e a sessão de acesso. O provedor, a rota do relay e o token do gateway são descobertos automaticamente.",
  "Show session": "Mostrar sessão",
  "Show or hide access session": "Mostrar ou ocultar a sessão de acesso",
  "Hide session": "Ocultar sessão",
  "Test connection": "Testar conexão",
  "Test again": "Testar novamente",
  "Waiting to test.": "Aguardando o teste.",
  "Agent metadata": "Metadados do agente",
  "Gateway WebSocket": "WebSocket do gateway",
  "Terminal WebSocket": "WebSocket do terminal",
  "Health": "Saúde",
  "Pending": "Pendente",
  "Testing": "Testando",
  "Passed": "Aprovado",
  "Failed": "Falhou",
  "Redacted request and response": "Requisição e resposta com dados sensíveis ocultos",
  "Provider and transport are discovered from the Base URL.": "O provedor e o transporte são descobertos pela URL base.",
  "Paste the launchable browser session when this page is hosted separately": "Cole a sessão do navegador do launchable quando esta página estiver hospedada separadamente",
  "Detected automatically from Base URL:": "Detectado automaticamente pela URL base:",
  "Access session:": "Sessão de acesso:",
  "Sensitive values stay in this tab.": "Os valores sensíveis permanecem nesta aba.",
  "Paste _pomerium when this page is hosted separately": "Cole _pomerium quando esta página estiver hospedada separadamente",
  "Paste CF_Authorization when this page is hosted separately": "Cole CF_Authorization quando esta página estiver hospedada separadamente",
  "Checking this browser for a signed-in launchable session.": "Verificando se este navegador tem uma sessão autenticada do launchable.",
  "Signed-in browser session detected.": "Sessão autenticada do navegador detectada.",
  "Query": "Consulta",
  "What": "O que é",
  "Why": "Motivo",
  "Credential": "Credencial",
  "Failure": "Falha",
  "Testing required routes in order.": "Testando as rotas obrigatórias na ordem.",
  "Enter the NemoClaw launchable Base URL.": "Informe a URL base do launchable NemoClaw.",
  "Connection ready. Metadata, gateway, terminal, and health checks passed.": "Conexão pronta. Os testes de metadados, gateway, terminal e saúde foram aprovados.",
  "Connection failed. Open the failed check for its redacted request and response.": "A conexão falhou. Abra o teste que falhou para ver a requisição e a resposta com dados sensíveis ocultos.",
  "Gateway recovery": "Recuperação do gateway",
  "Retry Cloudflare WebSockets through the hosted relay": "Tentar novamente os WebSockets do Cloudflare pelo relay hospedado",
  "Use only when a direct Cloudflare gateway or terminal socket fails.": "Use somente quando um socket direto do gateway ou do terminal do Cloudflare falhar.",
  "The recovery relay applies only to Cloudflare Access launchables.": "O relay de recuperação se aplica somente aos launchables com Cloudflare Access.",
  "Use the NemoClaw App URL: https://nemoclaw-<id>.brevlab.com or https://nemoclaw-<id>.apps.run.brev.nvidia.com": "Use a URL do aplicativo NemoClaw: https://nemoclaw-<id>.brevlab.com ou https://nemoclaw-<id>.apps.run.brev.nvidia.com",
  "Access provider must be Automatic, Cloudflare Access, or Pomerium": "O provedor de acesso deve ser Automático, Cloudflare Access ou Pomerium",
  "Selected access provider does not match the launchable URL": "O provedor de acesso selecionado não corresponde à URL do launchable",
  "OpenClaw relay URL cannot include credentials, query parameters, or a fragment": "A URL do relay do OpenClaw não pode incluir credenciais, parâmetros de consulta nem fragmento",
  "Automatic from URL": "Automático pela URL",
  "Cloudflare Access": "Cloudflare Access",
  "Pomerium": "Pomerium",
  "Hosted relay": "Relay hospedado",
  "Relay URL": "URL do relay",
  "Use for cross-origin Cloudflare connections": "Usar em conexões do Cloudflare entre origens",
  "saved separately": "salva separadamente",
  "Model endpoint:": "Endpoint do modelo:",
  "Model API base URL": "URL base da API de modelos",
  "Custom endpoint uses direct browser requests": "O endpoint personalizado usa requisições diretas do navegador",
  "Use the NVIDIA DLI browser relay": "Usar o relay de navegador da NVIDIA DLI",
  "Change": "Alterar",
  "API bearer key (NVIDIA keys start with": "Chave bearer da API (chaves NVIDIA começam com",
  "Save & verify": "Salvar e verificar",
  "No key yet?": "Ainda não tem uma chave?",
  "Sign up at build.nvidia.com →": "Cadastre-se em build.nvidia.com →",
  "Key should start with nvapi-": "A chave deve começar com nvapi-",
  "Enter the key for this endpoint": "Informe a chave deste endpoint",
  "Verifying?": "Verificando…",
  "Discovering models and verifying…": "Descobrindo modelos e verificando…",
  "✓ Connected.": "✓ Conectado.",
  "Model API base URL must use HTTPS": "A URL base da API de modelos deve usar HTTPS",
  "Model API base URL cannot include credentials, query parameters, or a fragment": "A URL base da API de modelos não pode conter credenciais, parâmetros de consulta ou fragmento",
  "Model ID must be one non-empty value without spaces": "O ID do modelo deve ser um único valor não vazio e sem espaços",
  "localhost points to this browser, not a remote host. Enter the HTTPS model API base URL ending in /v1": "localhost aponta para este navegador, não para um host remoto. Informe a URL base HTTPS da API de modelos terminada em /v1",
  "A Brev Jupyter /lab URL is not a model API. Enter the HTTPS model API base URL ending in /v1": "Uma URL /lab do Jupyter no Brev não é uma API de modelo. Informe a URL base HTTPS da API de modelos terminada em /v1",
  "Model discovery did not return JSON. Confirm this endpoint serves the OpenAI-compatible /models route, then try again": "A descoberta de modelos não retornou JSON. Confirme que este endpoint serve a rota /models compatível com OpenAI e tente novamente",
  "then open API Keys and generate one. This tab reuses the keys across lessons and discards them when it closes.": "e abra API Keys para gerar uma. Esta aba reutiliza as chaves entre as aulas e as descarta ao fechar.",
  "The default embedding route needs an nvapi- key": "A rota padrão de embeddings precisa de uma chave nvapi-",
  "Enter the key for the embedding route": "Informe a chave da rota de embeddings",
  "model discovery returned no model IDs": "A descoberta de modelos não retornou IDs de modelo",
  "embedding model discovery returned no model IDs": "A descoberta de modelos de embeddings não retornou IDs de modelo",
}));

const PT_PREFIXES = new Map(Object.entries({
  "Prerequisite: ": "Pré-requisito: ",
  "running ": "executando ",
  "commands.list failed: ": "commands.list falhou: ",
  "branches: ": "ramificações: ",
  "Branch '": "Ramificação '",
  "✓ Connected. Model replied: ": "✓ Conectado. O modelo respondeu: ",
  "Connection failed: ": "Falha na conexão: ",
  "Model ID is not served by this endpoint. Choose one of: ": "O ID do modelo não é servido por este endpoint. Escolha um destes: ",
  "Embedding model ID is not served by this endpoint. Choose one of: ": "O ID do modelo de embeddings não é servido por este endpoint. Escolha um destes: ",
  "A NemoClaw launchable is not a model API. Connect it in Module 3a and keep this route on a model endpoint such as ": "Um launchable do NemoClaw não é uma API de modelo. Conecte-o no Módulo 3a e mantenha esta rota em um endpoint de modelo como ",
  "model discovery failed: ": "a descoberta de modelos falhou: ",
  "embedding model discovery failed: ": "a descoberta de modelos de embeddings falhou: "
}));

const PT_ATTRS = new Map(Object.entries({
  "Ask a question…": "Faça uma pergunta…",
  "Course progression; current step highlighted.": "Progresso do curso; etapa atual destacada.",
  "Show the whole course map": "Mostrar o mapa completo do curso",
  "Choose language": "Escolher idioma",
  "Run every node in order": "Executar todos os nós em ordem",
  "Run this cell": "Executar esta célula",
  "Restore every node's code to its original": "Restaurar o código original de todos os nós",
  "Restore this cell's original code and clear its output": "Restaurar o código original desta célula e limpar a saída",
  "Copy current code": "Copiar o código atual",
  "model key verified this session": "chave do modelo verificada nesta sessão",
  "the saved nvapi key was refused (401/403). Re-enter it on Module 1a.": "a chave nvapi salva foi recusada (401/403). Informe-a novamente no Módulo 1a."
}));

const ES_TEXT = new Map(Object.entries({
  "The Agent": "El agente", "The ReAct Loop": "El ciclo ReAct", "Tools at Scale": "Herramientas a escala",
  "Workflows": "Flujos de trabajo", "The Index Agent": "El agente de índice", "Deep Agents": "Agentes profundos",
  "Connect NemoClaw": "Conectar NemoClaw", "Always-On": "Operación continua", "Modern CLIs": "CLI modernas",
  "Going Further": "Siguientes pasos", "Section": "Sección", "Section 1": "Sección 1", "Section 2": "Sección 2",
  "Section 3": "Sección 3", "Section 4": "Sección 4", "Course map": "Mapa del curso",
  "click to see all sections": "pulse para ver todas las secciones", "start": "inicio", "end": "fin",
  "No API key": "Sin clave de API", "Key …": "Clave …", "Key set ✓": "Clave guardada ✓",
  "Key rejected ✗": "Clave rechazada ✗", "Model": "Modelo", "Pages": "Páginas",
  "none pinned = auto-select": "ninguna fijada = selección automática", "🧠 memory: on": "🧠 memoria: activa",
  "🧠 memory: off": "🧠 memoria: inactiva", "↺ New chat": "↺ Nueva conversación",
  "Ask a question…": "Escriba una pregunta…", "Send": "Enviar", "⏹ Stop": "⏹ Detener",
  "▶ Run": "▶ Ejecutar", "▶ Run all": "▶ Ejecutar todo", "⏳ Running…": "⏳ Ejecutando…",
  "↺ Reset": "↺ Restablecer", "↺ Reset code": "↺ Restablecer código", "Ready": "Listo",
  "clear": "borrar", "■ stop": "■ detener", "Stopping…": "Deteniendo…", "+ branch": "+ rama",
  "Connect your launchable on Module 3a first (its URL and token), then your agent is reachable here.": "Conecta primero tu launchable en el Módulo 3a con su URL y su token. Después podrás acceder al agente desde aquí.",
  "Connected to your agent over the gateway. Ask anything, type /help, click a prompt, or press Tab to autocomplete.": "Conectado a tu agente mediante el gateway. Formula una pregunta, escribe /help, elige una sugerencia o pulsa Tab para autocompletar.",
  "Use /commands for the live gateway list. /clear empties this screen; /new and /branch manage independent agent sessions. Text without a slash is sent to the active agent session.": "Usa /commands para consultar la lista activa del gateway. /clear vacía la pantalla; /new y /branch administran sesiones independientes. El texto sin barra se envía a la sesión activa.",
  "No commands reported by the gateway.": "El gateway no ha informado de ningún comando.",
  "setting up this session (the first reply takes a moment)…": "preparando esta sesión (la primera respuesta puede tardar un momento)…",
  "empty until you Run": "vacío hasta ejecutar", "reset. empty until you Run": "restablecido; vacío hasta ejecutar",
  "click to collapse": "pulse para contraer", "click to expand": "pulse para ampliar",
  "✓ API key available in this tab": "✓ Clave de API disponible en esta pestaña",
  "Chat route:": "Ruta de chat:", "Embedding route:": "Ruta de embeddings:",
  "Chat API base URL": "URL base de la API de chat", "Chat model ID": "ID del modelo de chat",
  "Chat API bearer key (NVIDIA keys start with": "Clave bearer de la API de chat (las claves NVIDIA empiezan por",
  "Embedding route (persistent and independent)": "Ruta de embeddings (persistente e independiente)",
  "Embedding exercises keep this route when the chat route changes.": "Los ejercicios de embeddings conservan esta ruta cuando cambia la ruta de chat.",
  "Embedding API base URL": "URL base de la API de embeddings", "Embedding model ID": "ID del modelo de embeddings",
  "Embedding API bearer key": "Clave bearer de la API de embeddings", "saved separately": "guardada por separado",
  "Base URL": "URL base", "Bearer token": "Token bearer", "Access provider": "Proveedor de acceso",
  "Access session": "Sesión de acceso", "Automatic from URL": "Automático según la URL",
  "Enter the launchable URL and its browser access session. The course discovers everything else.": "Introduzca la URL del launchable y la sesión de acceso del navegador. El curso descubre el resto.",
  "Enter Base URL and Access session. Provider, relay route, and gateway token are discovered automatically.": "Introduzca la URL base y la sesión de acceso. El proveedor, la ruta del relay y el token del gateway se descubren automáticamente.",
  "Show session": "Mostrar sesión", "Show or hide access session": "Mostrar u ocultar la sesión de acceso",
  "Hide session": "Ocultar sesión", "Test connection": "Probar conexión", "Test again": "Probar de nuevo",
  "Waiting to test.": "Esperando la prueba.", "Agent metadata": "Metadatos del agente",
  "Gateway WebSocket": "WebSocket del gateway", "Terminal WebSocket": "WebSocket del terminal",
  "Health": "Estado", "Pending": "Pendiente", "Testing": "Probando", "Passed": "Aprobado", "Failed": "Falló",
  "Redacted request and response": "Solicitud y respuesta con datos sensibles ocultos",
  "Provider and transport are discovered from the Base URL.": "El proveedor y el transporte se descubren a partir de la URL base.",
  "Paste the launchable browser session when this page is hosted separately": "Pegue la sesión del navegador del launchable cuando esta página esté alojada por separado",
  "Detected automatically from Base URL:": "Detectado automáticamente a partir de la URL base:",
  "Access session:": "Sesión de acceso:", "Sensitive values stay in this tab.": "Los valores sensibles permanecen en esta pestaña.",
  "Paste _pomerium when this page is hosted separately": "Pegue _pomerium cuando esta página esté alojada por separado",
  "Paste CF_Authorization when this page is hosted separately": "Pegue CF_Authorization cuando esta página esté alojada por separado",
  "Checking this browser for a signed-in launchable session.": "Comprobando si este navegador tiene una sesión autenticada del launchable.",
  "Signed-in browser session detected.": "Se detectó una sesión autenticada del navegador.",
  "Query": "Consulta", "What": "Qué es", "Why": "Motivo", "Credential": "Credencial", "Failure": "Fallo",
  "Testing required routes in order.": "Probando las rutas obligatorias en orden.",
  "Enter the NemoClaw launchable Base URL.": "Introduzca la URL base del launchable de NemoClaw.",
  "Connection ready. Metadata, gateway, terminal, and health checks passed.": "Conexión lista. Las pruebas de metadatos, gateway, terminal y estado se aprobaron.",
  "Connection failed. Open the failed check for its redacted request and response.": "La conexión falló. Abra la prueba que falló para ver la solicitud y la respuesta con datos sensibles ocultos.",
  "Gateway recovery": "Recuperación del gateway",
  "Retry Cloudflare WebSockets through the hosted relay": "Reintentar los WebSockets de Cloudflare mediante el relay alojado",
  "Use only when a direct Cloudflare gateway or terminal socket fails.": "Úsalo solo cuando falle un socket directo del gateway o del terminal de Cloudflare.",
  "The recovery relay applies only to Cloudflare Access launchables.": "El relay de recuperación se aplica únicamente a los launchables con Cloudflare Access.",
  "Use the NemoClaw App URL: https://nemoclaw-<id>.brevlab.com or https://nemoclaw-<id>.apps.run.brev.nvidia.com": "Usa la URL de la aplicación NemoClaw: https://nemoclaw-<id>.brevlab.com o https://nemoclaw-<id>.apps.run.brev.nvidia.com",
  "Access provider must be Automatic, Cloudflare Access, or Pomerium": "El proveedor de acceso debe ser Automático, Cloudflare Access o Pomerium",
  "Selected access provider does not match the launchable URL": "El proveedor de acceso seleccionado no coincide con la URL del launchable",
  "OpenClaw relay URL cannot include credentials, query parameters, or a fragment": "La URL del relay de OpenClaw no puede incluir credenciales, parámetros de consulta ni fragmentos",
  "Cloudflare Access": "Cloudflare Access", "Pomerium": "Pomerium",
  "Hosted relay": "Relay alojado", "Relay URL": "URL del relay",
  "Use for cross-origin Cloudflare connections": "Usar para conexiones de Cloudflare entre orígenes",
  "Model endpoint:": "Endpoint del modelo:", "Model API base URL": "URL base de la API de modelos",
  "Custom endpoint uses direct browser requests": "El endpoint personalizado usa solicitudes directas del navegador",
  "Use the NVIDIA DLI browser relay": "Usar el relé de navegador de NVIDIA DLI",
  "API bearer key (NVIDIA keys start with": "Clave bearer de la API (las claves NVIDIA empiezan por",
  "Key should start with nvapi-": "La clave debe comenzar por nvapi-",
  "Enter the key for this endpoint": "Introduzca la clave de este endpoint",
  "Verifying?": "Verificando…", "Discovering models and verifying…": "Descubriendo modelos y verificando…", "✓ Connected.": "✓ Conectado.",
  "Model API base URL must use HTTPS": "La URL base de la API de modelos debe usar HTTPS",
  "Model API base URL cannot include credentials, query parameters, or a fragment": "La URL base de la API de modelos no puede incluir credenciales, parámetros de consulta ni fragmentos",
  "Model ID must be one non-empty value without spaces": "El ID del modelo debe ser un único valor no vacío y sin espacios",
  "localhost points to this browser, not a remote host. Enter the HTTPS model API base URL ending in /v1": "localhost apunta a este navegador, no a un host remoto. Introduzca la URL base HTTPS de la API de modelos terminada en /v1",
  "A Brev Jupyter /lab URL is not a model API. Enter the HTTPS model API base URL ending in /v1": "Una URL /lab de Jupyter en Brev no es una API de modelos. Introduzca la URL base HTTPS de la API de modelos terminada en /v1",
  "Model discovery did not return JSON. Confirm this endpoint serves the OpenAI-compatible /models route, then try again": "El descubrimiento de modelos no devolvió JSON. Confirme que este endpoint sirve la ruta /models compatible con OpenAI e inténtelo de nuevo",
  "then open API Keys and generate one. This tab reuses the keys across lessons and discards them when it closes.": "y abra API Keys para generar una. Esta pestaña reutiliza las claves entre lecciones y las descarta al cerrarse.",
  "The default embedding route needs an nvapi- key": "La ruta predeterminada de embeddings necesita una clave nvapi-",
  "Enter the key for the embedding route": "Introduzca la clave de la ruta de embeddings",
  "model discovery returned no model IDs": "El descubrimiento de modelos no devolvió IDs de modelo",
  "embedding model discovery returned no model IDs": "El descubrimiento de modelos de embeddings no devolvió IDs de modelo",
  "Change": "Cambiar", "Save & verify": "Guardar y verificar", "No key yet?": "¿Aún no tiene una clave?",
  "Sign up at build.nvidia.com →": "Regístrese en build.nvidia.com →"
}));

const ES_PREFIXES = new Map(Object.entries({
  "Prerequisite: ": "Requisito previo: ",
  "running ": "ejecutando ",
  "commands.list failed: ": "commands.list falló: ",
  "branches: ": "ramas: ",
  "Branch '": "Rama '",
  "✓ Connected. Model replied: ": "✓ Conectado. El modelo respondió: ",
  "Connection failed: ": "Error de conexión: ",
  "Model ID is not served by this endpoint. Choose one of: ": "El ID del modelo no se sirve en este endpoint. Elija uno de estos: ",
  "Embedding model ID is not served by this endpoint. Choose one of: ": "El ID del modelo de embeddings no se sirve en este endpoint. Elija uno de estos: ",
  "A NemoClaw launchable is not a model API. Connect it in Module 3a and keep this route on a model endpoint such as ": "Un launchable de NemoClaw no es una API de modelos. Conéctelo en el Módulo 3a y mantenga esta ruta en un endpoint de modelos como ",
  "model discovery failed: ": "falló el descubrimiento de modelos: ",
  "embedding model discovery failed: ": "falló el descubrimiento de modelos de embeddings: "
}));

const ES_ATTRS = new Map(Object.entries({
  "Ask a question…": "Escriba una pregunta…", "Course progression; current step highlighted.": "Progreso del curso; la etapa actual está resaltada.",
  "Show the whole course map": "Mostrar el mapa completo del curso", "Choose language": "Elegir idioma",
  "Run every node in order": "Ejecutar todos los nodos en orden", "Run this cell": "Ejecutar esta celda",
  "Restore every node's code to its original": "Restablecer el código original de todos los nodos",
  "Restore this cell's original code and clear its output": "Restablecer el código original de esta celda y borrar su salida",
  "Copy current code": "Copiar el código actual",
  "model key verified this session": "clave del modelo verificada en esta sesión",
  "the saved nvapi key was refused (401/403). Re-enter it on Module 1a.": "la clave nvapi guardada fue rechazada (401/403). Introdúzcala de nuevo en el Módulo 1a."
}));

const ZH_TEXT = new Map(Object.entries({
  "Live artifacts": "交互页面",
  "Shared state": "共享状态",
  "Model calls": "模型调用",
  "Model configuration": "模型配置",
  "Web search": "Web 搜索",
  "Embeddings & similarity": "嵌入与相似度",
  "Tokens & context": "token 与上下文",
  "Raw HTTP": "原始 HTTP",
  "Launchable terminal": "可启动实例终端",
  "OpenShell policy": "OpenShell 策略",
  "Course content": "课程内容",
  "Diagram strings": "图表字符串",
  "OpenClaw gateway": "OpenClaw 网关",
  "Run control": "运行控制",
  "Instrumentation": "追踪与日志",
  "Visualization": "可视化",
  "Other": "其他",
  "One-shot, non-streaming chat completion. Returns the raw OpenAI-shape response. Use when you just want the final message.": "单次、非流式聊天补全。返回原始 OpenAI 格式响应。只需要最终消息时使用。",
  "Cosine similarity between two vectors. Closer to 1 = closer match. The standard retrieval primitive.": "计算两个向量的余弦相似度。越接近 1，匹配度越高。这是标准的检索基本操作。",
  "Gantt-style bar chart comparing per-worker duration against total wall time.": "甘特式条形图，用于比较各工作线程耗时和总墙钟时间。",
  "Horizontal score bars for retrieval results, with the top-k entries highlighted green and the rest dimmed.": "检索结果的水平分数条形图，以绿色突出显示 top-k 条目，并调暗其它条目。",
  "Mount the live OpenClaw command/chat artifact without copying gateway RPC, session-tab, autocomplete, and rendering plumbing into a learner cell.": "挂载 OpenClaw 实时命令/聊天界面，无需将网关 RPC、会话标签页、自动补全和渲染支撑代码复制到学习者单元格中。",
  "Automatic retries for network, HTTP 429, or transient 5xx failures": "针对网络、HTTP 429 或暂时性 5xx 故障自动重试",
  "Failures remain visible. Retries are off by default and apply only before a stream starts.": "故障始终可见。默认关闭重试，且只在流式传输开始前重试。",
  "Wait for response headers or the next stream chunk (seconds)": "等待响应标头或下一个流式数据块（秒）",
  "Need a value? Select the ? beside that field for its source and fallback.": "需要某个值？请选择该字段旁的 ?，查看其来源和回退值。",
  "I'm a deep research agent. Ask me something and I'll plan a few parallel sub-investigations across curated NVIDIA materials and this course's own sections, then synthesize a grounded answer.": "我是一个深度研究智能体。请向我提问；我会针对精选的 NVIDIA 资料和本课程内容规划若干并行子调查，再综合形成有依据的回答。",
  "How does this course's OpenShell sandbox relate to agent safety in general?": "本课程的 OpenShell 沙箱与一般的智能体安全有何关系？",
  "What is RAG, and how does this course build it?": "什么是 RAG？本课程如何构建 RAG？",
  "Compare the ReAct loop with the deep-agent pattern": "比较 ReAct 循环和深度智能体模式",
  "What are the main failure modes of autonomous agents?": "自主智能体有哪些主要故障模式？",
  "How do production CLI agents sandbox themselves?": "生产环境中的 CLI 智能体如何进行沙箱隔离？",
  "Trace this course from a single LLM call to an always-on agent": "梳理本课程从单次 LLM 调用到持续运行智能体的演进路径",
  "✗ Error: Embedding key missing. Open the course setup and configure the persistent embedding route.": "✗ 错误：缺少嵌入密钥。请打开课程设置并配置持久化嵌入路由。",
  "Error: Embedding key missing. Open the course setup and configure the persistent embedding route.": "错误：缺少嵌入密钥。请打开课程设置并配置持久化嵌入路由。",
  "Checks env status, toolSearch, stuck approvals, and one trivial command. HEALTHY needs no repair; DEGRADED shows what to inspect next.": "检查环境状态、toolSearch、卡住的审批以及一条简单命令。HEALTHY 表示无需修复；DEGRADED 会指出接下来要检查的内容。",
  "Disables tools.toolSearch only when the live config has it enabled. Session clearing and restart default off, so running this cell against a healthy launchable is non-destructive.": "仅当实时配置已启用 tools.toolSearch 时才将其禁用。默认不清除会话、不重启，因此对健康的可启动实例运行此单元格不会造成破坏性更改。",
  "Tails the gateway/agent log (logs.tail): model calls, tool dispatches, errors, hangs. The deepest view when a run stalls and Health check is green; reasoning itself is not exposed over the gateway.": "持续读取网关/智能体日志（logs.tail），包括模型调用、工具分派、错误和卡顿。当运行停滞但健康检查为绿色时，这是最深入的诊断视图；网关本身不会公开推理过程。",
  "Detect & recover · health check, then escalating reset": "检测并恢复 · 先做健康检查，再逐级重置",
  "Health check": "健康检查",
  "Runtime logs": "运行时日志",
  "Clean up": "清理",
  "Clear": "清除",
  "Connect": "连接",
  "Recover": "恢复",
  "Debug info": "调试信息",
  "Advanced": "高级",
  "Request handling": "请求处理",
  "Value": "值",
  "apply override": "应用覆盖设置",
  "not yet run": "尚未运行",
  "returned value": "返回值",
  "raw response": "原始响应",
  "live artifacts": "交互页面",
  "No OpenClaw": "未检测到 OpenClaw",
  "The agent doing its job": "智能体正常执行任务",
  "The agent off the rails": "智能体行为失控",
  "the agent tries to ": "智能体尝试 ",
  "   ·   run Confirm next, then Compare": "   ·   接下来运行“确认”，然后运行“比较”",
  "接下来运行 Confirm，然后运行 Compare": "接下来运行“确认”，然后运行“比较”",
  "list available models": "列出可用模型",
  "send a chat completion": "发送聊天补全请求",
  "exfiltrate data to an outside host": "将数据外泄到外部主机",
  "read cloud-instance credentials (metadata SSRF)": "读取云实例凭据（元数据 SSRF）",
  "clone tooling from GitHub": "从 GitHub 克隆工具",
  "reach the inference API as a stray curl, not the runtime": "绕过运行时，直接用 curl 访问推理 API",
  "pull an npm package directly with curl": "直接使用 curl 拉取 npm 软件包",
  "Run the live-policy cell above to draw your launchable's policy as an interactive map.": "请运行上方的实时策略单元格，将可启动实例的策略绘制为交互式地图。",
  "tips for building a RAG pipeline": "构建 RAG 工作流的建议",
  "The Agent": "智能体",
  "The ReAct Loop": "ReAct 循环",
  "Tools at Scale": "规模化工具",
  "Workflows": "工作流",
  "The Index Agent": "索引智能体",
  "Deep Agents": "深度智能体",
  "Connect NemoClaw": "连接 NemoClaw",
  "Always-On": "持续运行",
  "Modern CLIs": "现代 CLI",
  "Going Further": "深入探索",
  "loop · LLM as function": "循环 · 将 LLM 作为函数",
  "tools · finish_reason": "工具 · finish_reason",
  "JSON · MCP · routing": "JSON · MCP · 路由",
  "router · planner · ReWOO": "路由 · planner · ReWOO",
  "embed · retrieve · bundle": "嵌入 · 检索 · 打包",
  "planner · sub-agents · VFS": "planner · 子智能体 · VFS",
  "launchable · first call": "可启动 · 首次调用",
  "file-as-context · paste URL": "文件即上下文 · 粘贴 URL",
  "sandbox · policy · CI gate": "沙盒 · 策略 · CI 门控",
  "Section": "章节",
  "Section 1": "第 1 章",
  "Section 2": "第 2 章",
  "Section 3": "第 3 章",
  "Section 4": "第 4 章",
  "Course map": "课程地图",
  "click to see all sections": "点击查看所有章节",
  "start": "开始",
  "end": "结束",
  "No API key": "未设置 API 密钥",
  "Key …": "密钥…",
  "Key set ✓": "密钥已设置 ✓",
  "Key rejected ✗": "密钥被拒绝 ✗",
  "Model": "模型",
  "Pages": "页面",
  "none pinned = auto-select": "未固定 = 自动选择",
  "🧠 memory: on": "🧠 记忆：开启",
  "🧠 memory: off": "🧠 记忆：关闭",
  "↺ New chat": "↺ 新建对话",
  "Ask a question…": "请输入问题…",
  "Send": "发送",
  "⏹ Stop": "⏹ 停止",
  "▶ Run": "▶ 运行",
  "▶ Run all": "▶ 全部运行",
  "⏳ Running…": "⏳ 正在运行…",
  "↺ Reset": "↺ 重置",
  "↺ Reset code": "↺ 重置代码",
  "Ready": "就绪",
  "clear": "清除",
  "■ stop": "■ 停止",
  "Stopping…": "正在停止…",
  "+ branch": "+ 分支",
  "Connect your launchable on Module 3a first (its URL and token), then your agent is reachable here.": "请先在模块 3a 中连接可启动实例（其 URL 和 token），然后即可从此处访问智能体。",
  "Connected to your agent over the gateway. Ask anything, type /help, click a prompt, or press Tab to autocomplete.": "已通过网关连接到智能体。可以提出任何问题、输入 /help、点击提示词，或按 Tab 键自动补全。",
  "Use /commands for the live gateway list. /clear empties this screen; /new and /branch manage independent agent sessions. Text without a slash is sent to the active agent session.": "使用 /commands 查看网关的实时命令列表。/clear 会清空此屏幕；/new 和 /branch 用于管理相互独立的智能体会话。不带斜杠的文本将发送到当前智能体会话。",
  "No commands reported by the gateway.": "网关未报告任何命令。",
  "setting up this session (the first reply takes a moment)…": "正在设置此会话（首次回复需要一些时间）…",
  "empty until you Run": "在您运行前为空",
  "reset. empty until you Run": "已重置。在您运行前为空",
  "javascript · editable · re-run": "javascript · 可编辑 · 可重新运行",
  "JSON · editable": "JSON · 可编辑",
  "click to collapse": "点击折叠",
  "click to expand": "点击展开",
  "in scope inside every node:": "每个节点内的作用域均包含：",
  "click a row to inspect & edit its source": "点击行可检查并编辑其源代码",
  "in scope for this cell. Click a row to read its source": "位于此单元格的作用域内。点击行可查看其源代码",
  "✓ API key available in this tab": "✓ 此标签页中可使用 API key",
  "Chat route:": "聊天路由：",
  "Embedding route:": "嵌入路由：",
  "Chat API base URL": "聊天 API 基础 URL",
  "Chat model ID": "聊天模型 ID",
  "Chat API bearer key (NVIDIA keys start with": "聊天 API bearer 密钥（NVIDIA 密钥以以下内容开头",
  "Embedding route (persistent and independent)": "嵌入路由（持久且独立）",
  "Embedding exercises keep this route when the chat route changes.": "聊天路由发生变化时，嵌入练习仍使用此路由。",
  "Embedding API base URL": "嵌入 API 基础 URL",
  "Embedding model ID": "嵌入模型 ID",
  "Embedding API bearer key": "嵌入 API bearer 密钥",
  "Base URL": "基础 URL",
  "Bearer token": "Bearer token",
  "Access provider": "访问提供商",
  "Access session": "访问会话",
  "Enter the launchable URL and its browser access session. The course discovers everything else.": "输入可启动实例的 URL 及其浏览器访问会话。本课程会自动发现其它所有信息。",
  "Enter Base URL and Access session. Provider, relay route, and gateway token are discovered automatically.": "输入基础 URL 和访问会话。系统会自动发现提供商、中继路由和网关 token。",
  "Show session": "显示会话",
  "Show or hide access session": "显示或隐藏访问会话",
  "Hide session": "隐藏会话",
  "Test connection": "测试连接",
  "Test again": "再次测试",
  "Waiting to test.": "等待测试。",
  "Agent metadata": "智能体元数据",
  "Gateway WebSocket": "网关 WebSocket",
  "Terminal WebSocket": "终端 WebSocket",
  "Health": "健康状态",
  "Pending": "待处理",
  "Testing": "正在测试",
  "Passed": "已通过",
  "Failed": "失败",
  "Redacted request and response": "已隐去敏感信息的请求和响应",
  "Provider and transport are discovered from the Base URL.": "系统会根据基础 URL 自动发现提供商和传输方式。",
  "Paste the launchable browser session when this page is hosted separately": "当此页面单独托管时，请粘贴可启动实例的浏览器会话",
  "Detected automatically from Base URL:": "根据基础 URL 自动检测：",
  "Access session:": "访问会话：",
  "Sensitive values stay in this tab.": "敏感值仅保留在此标签页中。",
  "Paste _pomerium when this page is hosted separately": "当此页面单独托管时，请粘贴 _pomerium",
  "Paste CF_Authorization when this page is hosted separately": "当此页面单独托管时，请粘贴 CF_Authorization",
  "Checking this browser for a signed-in launchable session.": "正在检查此浏览器中是否存在已登录的可启动实例会话。",
  "Signed-in browser session detected.": "检测到已登录的浏览器会话。",
  "Query": "查询",
  "What": "内容",
  "Why": "原因",
  "Credential": "凭据",
  "Failure": "失败",
  "Testing required routes in order.": "正在按顺序测试必需路由。",
  "Enter the NemoClaw launchable Base URL.": "请输入 NemoClaw 可启动实例的基础 URL。",
  "Connection ready. Metadata, gateway, terminal, and health checks passed.": "连接已就绪。元数据、网关、终端和健康检查均已通过。",
  "Connection failed. Open the failed check for its redacted request and response.": "连接失败。请打开失败的检查，查看其中已脱敏的请求和响应。",
  "Gateway recovery": "网关恢复",
  "Retry Cloudflare WebSockets through the hosted relay": "通过托管中继重试 Cloudflare WebSockets",
  "Use only when a direct Cloudflare gateway or terminal socket fails.": "仅当 Cloudflare 网关或终端套接字的直接连接失败时使用。",
  "The recovery relay applies only to Cloudflare Access launchables.": "恢复中继仅适用于 Cloudflare Access 可启动实例。",
  "Use the NemoClaw App URL: https://nemoclaw-<id>.brevlab.com or https://nemoclaw-<id>.apps.run.brev.nvidia.com": "使用 NemoClaw 应用 URL：https://nemoclaw-<id>.brevlab.com 或 https://nemoclaw-<id>.apps.run.brev.nvidia.com",
  "Access provider must be Automatic, Cloudflare Access, or Pomerium": "访问提供方必须为“自动”、Cloudflare Access 或 Pomerium",
  "Selected access provider does not match the launchable URL": "所选访问提供方与可启动实例 URL 不匹配",
  "OpenClaw relay URL cannot include credentials, query parameters, or a fragment": "OpenClaw 中继 URL 不能包含凭据、查询参数或片段",
  "Automatic from URL": "根据 URL 自动选择",
  "Cloudflare Access": "Cloudflare Access",
  "Pomerium": "Pomerium",
  "Hosted relay": "托管中继",
  "Relay URL": "中继 URL",
  "Use for cross-origin Cloudflare connections": "用于跨源 Cloudflare 连接",
  "saved separately": "单独保存",
  "Model endpoint:": "模型 API 入口：",
  "Model API base URL": "模型 API 基础 URL",
  "Custom endpoint uses direct browser requests": "自定义 API 入口使用浏览器直接请求",
  "Use the NVIDIA DLI browser relay": "使用 NVIDIA DLI 浏览器中继",
  "Change": "更改",
  "API bearer key (NVIDIA keys start with": "API bearer 密钥（NVIDIA 密钥以此开头：",
  "Save & verify": "保存并验证",
  "No key yet?": "还没有密钥？",
  "Sign up at build.nvidia.com →": "前往 build.nvidia.com 注册 →",
  "Key should start with nvapi-": "密钥应以 nvapi- 开头",
  "Enter the key for this endpoint": "请输入此 API 入口的密钥",
  "Verifying?": "正在验证？",
  "Discovering models and verifying…": "正在发现模型并验证…",
  "✓ Connected.": "✓ 已连接。",
  "Model API base URL must use HTTPS": "模型 API 基础 URL 必须使用 HTTPS",
  "Model API base URL cannot include credentials, query parameters, or a fragment": "模型 API 基础 URL 不能包含凭据、查询参数或片段",
  "Model ID must be one non-empty value without spaces": "模型 ID 必须是一个不含空格的非空值",
  "localhost points to this browser, not a remote host. Enter the HTTPS model API base URL ending in /v1": "localhost 指向此浏览器，而非远程主机。请输入以 /v1 结尾的 HTTPS 模型 API 基础 URL",
  "A Brev Jupyter /lab URL is not a model API. Enter the HTTPS model API base URL ending in /v1": "Brev Jupyter /lab URL 不是模型 API。请输入以 /v1 结尾的 HTTPS 模型 API 基础 URL",
  "Model discovery did not return JSON. Confirm this endpoint serves the OpenAI-compatible /models route, then try again": "模型发现未返回 JSON。请确认此 API 入口提供与 OpenAI 兼容的 /models 路由，然后重试",
  "then open API Keys and generate one. This tab reuses the keys across lessons and discards them when it closes.": "然后打开 API 密钥页面并生成一个密钥。此标签页会在各课时之间复用这些密钥，并在关闭时将其丢弃。",
  "The default embedding route needs an nvapi- key": "默认嵌入路由需要 nvapi- 密钥",
  "Enter the key for the embedding route": "请输入嵌入路由的密钥",
  "model discovery returned no model IDs": "模型发现未返回任何模型 ID",
  "embedding model discovery returned no model IDs": "嵌入模型发现未返回任何模型 ID"
}));

const ZH_PREFIXES = new Map(Object.entries({
  "Prerequisite: ": "前提条件：",
  "running ": "正在运行 ",
  "commands.list failed: ": "commands.list 失败：",
  "branches: ": "分支：",
  "Branch '": "分支 '",
  "✓ Connected. Model replied: ": "✓ 已连接。模型回复：",
  "Connection failed: ": "连接失败：",
  "Model ID is not served by this endpoint. Choose one of: ": "此 API 入口不提供模型 ID。请选择以下模型之一：",
  "Embedding model ID is not served by this endpoint. Choose one of: ": "此 API 入口不提供嵌入模型 ID。请选择以下模型之一：",
  "A NemoClaw launchable is not a model API. Connect it in Module 3a and keep this route on a model endpoint such as ": "NemoClaw 可启动实例不是模型 API。请在模块 3a 中连接该实例，并将此路由保留为模型 API 入口，例如 ",
  "model discovery failed: ": "模型发现失败：",
  "embedding model discovery failed: ": "嵌入模型发现失败："
}));

const ZH_ATTRS = new Map(Object.entries({
  "Ask a question…": "请输入问题…",
  "Course progression; current step highlighted.": "课程进度；当前步骤已突出显示。",
  "Show the whole course map": "显示完整课程地图",
  "Choose language": "选择语言",
  "Run every node in order": "按顺序运行所有节点",
  "Run this cell": "运行此单元格",
  "Restore every node's code to its original": "将所有节点的代码恢复为原始版本",
  "Restore this cell's original code and clear its output": "恢复此单元格的原始代码并清除其输出",
  "Copy current code": "复制当前代码",
  "model key verified this session": "模型密钥已在本次会话中验证",
  "the saved nvapi key was refused (401/403). Re-enter it on Module 1a.": "已保存的 nvapi 密钥被拒绝（401/403）。请在模块 1a 中重新输入。"
}));

// Helper signatures stay in English because learners call them from code. Only the
// explanatory second column is localized. Keying by helper name also keeps code spans
// such as <code>log.clear()</code> out of the general-purpose text replacement path.
const ZH_HELPER_DESCRIPTIONS = new Map(Object.entries({
  chat: "单次、非流式聊天补全。返回原始 OpenAI 格式响应。只需要最终消息时使用。",
  chatStream: "流式聊天补全；token 到达时会实时显示在此面板的结果视图中。返回的摘要包含 <code>.content</code>、<code>.reasoning</code>、<code>.tool_calls</code>、<code>.finish_reason</code> 和 <code>.usage</code>。",
  webSearch: "无需密钥即可对课程资料目录（<code>assets/materials_index.json</code>）进行排序搜索。目录包含已缓存的 NVIDIA 术语表条目，以及从 Web 收录、按需访问的论文和博客。查询会与各条目的名称、标签和摘要进行匹配；任何页面都能运行，无需密钥或实验环境。每项结果都包含 <code>tier</code>：<code>cached</code> 表示课程附带全文，<code>on_demand</code> 表示通过 <code>href</code> 访问来源。返回 <code>{ results: [{title, body, href, tier, kind}], count, unreachable }</code>。",
  instantAnswer: "当查询中明确包含某个术语时，返回一条 NVIDIA 术语表定义，例如 <code>retrieval-augmented generation</code> 或 <code>deep agents</code>。返回结构与 <code>webSearch</code> 相同，但只有查询与术语高度匹配时才返回一张精选卡片；自由问句不会返回结果。它是 <code>webSearch</code> 面向具体实体的精确查询版本。",
  formatSearchResults: "将 <code>webSearch</code> 或 <code>instantAnswer</code> 的结果转换为带编号的文本块，供 LLM 作为工具消息读取。",
  embed: "向持久化嵌入路由 <code>{cfg.url}/embeddings</code> 发送 POST 请求。返回向量数组（<code>numbers[]</code>）。NVIDIA 嵌入模型要求将 <code>inputType</code> 设为 <code>\"query\"</code> 或 <code>\"passage\"</code>。",
  cosineSim: "计算两个向量的余弦相似度。越接近 1，匹配度越高。这是标准的检索基本操作。",
  fetchRetry: "与 <code>helpers.fetch</code> 类似，并可接受一个有界的可选第三参数，例如 <code>{ retries: 2, timeoutMs: 120000 }</code>。遇到 HTTP 429 时会遵循 <code>Retry-After</code>，其它情况下则报告最终的网络或 HTTP 结果。",
  delay: "等待指定时间，同时允许学习者停止正在运行的单元格。CanvasFlow 和 RunCell 会自动将此辅助函数连接到停止按钮；只有等待过程属于其它生命周期时，才需要传入另一个 <code>AbortSignal</code>。",
  getConfig: "返回当前聊天配置 <code>{ mode, url, model, needsKey, iframeProxy }</code>。学习者可以在课程主页保存一个兼容的聊天 API 入口和模型；嵌入服务使用独立路由。已发布的课程来源和本地文件预览默认使用受限的 NVIDIA DLI 中继，其它来源保持直连；自定义聊天 API 入口始终绕过该中继。",
  getEmbeddingConfig: "返回持久化嵌入路由 <code>{ url, model }</code>。默认使用 NVIDIA 托管 API，学习者选择其它聊天 API 入口时不会随之改变。已发布的课程来源会与聊天路由使用相同的受限中继选择逻辑；自定义嵌入 API 入口仍保持直连。",
  getKey: "返回当前浏览器标签页保存在 <code>sessionStorage</code> 中的模型 bearer 密钥；未设置时返回 <code>null</code>。NVIDIA 密钥以 <code>nvapi-</code> 开头。模型调用会自动使用此标签页范围内的值，关闭标签页后该值即被丢弃。",
  terminal: "通过可启动实例的 <code>/ws/terminal</code> WebSocket 打开 PTY 并运行 <code>cmd</code>。使用 <code>\"bash\"</code> 进入虚拟机 shell，或使用 <code>\"openshell sandbox connect &lt;agent&gt;\"</code> 进入受内核 sandbox 保护的智能体。<code>send</code> 是依次输入 PTY 的 shell 命令行数组，每行都会附加 Enter。绑定浏览器的会话保持直连；粘贴的访问会话会先尝试直连，再尝试获准的提供商专用中继。设置 <code>relayWebSocket: true</code> 可明确选择该恢复路由。返回 <code>{ output, raw, frames, exitCode, transport }</code>；<code>output</code> 已移除 ANSI 控制码，<code>exitCode</code> 是 PTY 返回的退出状态，未收到时为 null，<code>transport</code> 表示成功打开的直连或获准中继路由。可启动实例 URL 从 OpenClaw 探测结果中读取。仅适用于可启动实例。",
  coursePage: "<code>helpers.coursePage(id)</code> 以 Markdown 形式返回一个课程页面的正文。<code>id</code> 是类似 <code>\"01b-react\"</code> 的文件 ID；可以使用 <code>helpers.coursePages()</code> 列出。该请求为同源请求，无需密钥。可将其接入 <code>read_course_page</code> 工具，使回答基于实际课程内容。",
  coursePages: "<code>helpers.coursePages()</code> 以 <code>[{ id, title }]</code> 形式返回页面列表。它是模块菜单或 <code>read_course_page</code> 工具 <code>enum</code> 字段的唯一来源。",
  contextWindow: "<code>helpers.contextWindow(model)</code> 返回模型公布的上下文窗口大小，单位为 token。课程中的交互页面使用它显示上下文预算；未知模型默认按 131072 处理。",
  estimateTokens: "<code>helpers.estimateTokens(textOrMessages)</code> 粗略估算字符串或 <code>{content}</code> 消息数组中的 token 数量，约按每 4 个字符一个 token 计算。它适合运行前检查；权威计数以模型返回的 <code>usage_metadata</code> 为准。",
  browserChatFetch: "返回一个会移除 OpenAI SDK <code>x-stainless-*</code> 标头的 <code>fetch</code>。NVIDIA 模型路由还会收到 <code>X-BILLING-INVOKE-ORIGIN</code> 追踪标记；自定义路由会包含相应的浏览器会话凭据。在浏览器中构造 <code>ChatOpenAI</code> 时，将它传给 <code>configuration.fetch</code>。",
  diagramSVG: "以 SVG 字符串形式返回使用课程主题的节点/边图，也就是 <code>helpers.viz.diagram</code> 的字符串版本，交互页面可通过 <code>view.html(...)</code> 渲染。<code>spec</code> 结构相同：<code>{title?, nodes:[{id, label, kind, x, y, lines?}], edges:[{from, to, label?}]}</code>；<code>kind &isin; env|agent|tool|data|model|neutral</code>。",
  ganttBarsSVG: "以 SVG 字符串形式返回甘特式并发图，也就是 <code>helpers.viz.ganttBars</code> 的字符串版本，可由交互页面通过 <code>view.html(...)</code> 渲染。<code>workers</code> 是 <code>{label, dt}</code> 数组，时间单位为秒；图表会将各工作线程的条形及串行耗时之和与实际 <code>wallSeconds</code> 进行比较。",
  mountFigures: "将 <code>rootSel</code> 下的每个 <code>[data-svg-src]</code> 占位符替换为从相应路径获取的 SVG；默认范围是整个文档。SVG 会以内联方式注入，使 <code>var(--gfx-*)</code> 主题生效，并支持单击或按 Enter 打开适应屏幕的灯箱。页面加载时会自动挂载。",
  mountChatUI: "在 <code>el</code> 中渲染可实时观察的聊天界面，包括控件、流式对话记录和输入框。<code>opts</code> 包含 <code>{ modules:[{id,title}], models:[{id,label}], intro, greeting, showGreetingWithHistory, memory, respond(text, ctx), onReset() }</code>。恢复历史轮次后仍需显示当前上下文提示时，请设置 <code>showGreetingWithHistory:true</code>。设置 <code>memory:true</code> 后，组件会保留对话、显示默认开启的记忆开关，并通过 <code>ctx.history</code> 提供先前轮次；关闭记忆时该数组为空，因此同一个 respond 会表现为无状态函数。编辑按钮会将对话记录回退到相应轮次。<code>respond</code> 通过 <code>ctx.view</code> 流式输出：<code>view.token(t)</code> 显示以 Markdown 渲染的回答，<code>view.reasoning(t)</code> 显示可折叠的思考过程，<code>view.tool(label, detail)</code> 显示可展开的工具标签，<code>view.usage({input, output})</code> 显示本轮 token 和累计上下文，另有 <code>view.html(h)</code> 与 <code>view.error(msg)</code>。<code>ctx</code> 包含 <code>{ module, modules, model, thread, turn, history, memory }</code>；<code>modules</code> 是固定的页面 ID 数组，为空时自动选择。返回 <code>{ thread, reset(), ctx }</code>。",
  mountAgentChat: "基于 LangChain <code>createReactAgent</code> 的实时聊天界面。<code>opts</code> 包含 <code>{ models:[{id,label}], system, buildTools({tool,z,coursePage,coursePages,webSearch,formatSearchResults}), greeting, modules, recursionLimit, growLog, initialHistory, initialActivity, onUserMessage, onTurnSnapshot, onAssistantMessage, onHistoryChange, compactAtTokens, compactKeepMessages }</code>。恢复的历史记录会初始化新的 checkpoint；压缩操作使用当前模型总结较早轮次、保留最近消息并切换到新 thread。设置 <code>growLog:true</code> 后会移除面板内部的滚动高度限制，使长对话随页面展开。此函数加载课程附带的 LangChain bundle，为每个模型构建一个智能体，通过 MemorySaver 支持多轮对话，流式显示 token 和工具标签，并处理缺少密钥的情况。它是 <code>mountChatUI</code> 的现成智能体版本。",
  mountOpenClawCli: "挂载 OpenClaw 实时命令/聊天界面，无需将网关 RPC、会话标签页、自动补全和渲染支撑代码复制到学习者单元格中。",
  mountKeyPanel: "使用现有的 <code>.key-panel</code> CSS 类渲染内联 API 密钥设置面板。保存密钥后，面板会显示紧凑的“? 已保存”行和“更改”按钮。保存时会移除不可见 Unicode 字符、在线验证密钥，然后更新顶部栏中的 <code>#key-status</code> 状态标签。",
  openclawBootstrapRequest: "通过从模块 3a 标准化连接中选择的提供商读取 <code>/api/agent</code> 或 <code>/healthz</code>。对于 Pomerium，这些固定 API 入口会通过终端 WebSocket 从可启动实例的 loopback 读取；系统先尝试已登录的浏览器会话，再尝试获准的提供商专用中继。返回响应元数据和解析后的 JSON，不暴露任何访问凭据。",
  openclawChat: "通过 <code>/cli/gateway</code> WebSocket 向实时 OpenClaw 智能体发送一轮聊天并流式接收回复。可启动实例 URL 和 token 从 OpenClaw 探测结果（Kickstart 页面）中读取。传入 <code>view</code>（即 <code>mountChatUI</code> 的 <code>ctx.view</code>）后，它会完整驱动可观察的执行过程：回答文本、按执行顺序排列的每个工具或命令调用标签（包含参数和完整结果，并标记错误），以及网关报告的上下文 token 预算。也可以传入 <code>onToken(delta)</code> 和 <code>onTool(name,{id,args})</code> 自行处理事件。网关不会传输推理通道，因此页面不显示推理内容。多轮对话应复用同一个 <code>session</code>。它是 chat()/createReactAgent 对应的网关辅助函数。",
  evalSandboxNetwork: "OpenShell 网络 Rego 的静态实现。针对候选连接返回 <code>{action, matched, reason}</code>，采用默认拒绝策略，并执行二进制程序身份以及 L7 方法/路径检查；不会实际访问网络。默认使用实时可启动实例的强化策略。可与 <code>helpers.sandboxExec</code> 配合，在线确认预测结果。",
  evalSandboxFs: "OpenShell 文件系统（Landlock）策略的静态实现。针对 <code>path</code> 的读取或写入返回 <code>\"allow\"</code> 或 <code>\"deny\"</code>。默认使用实时可启动实例的强化策略。",
  sandboxExec: "通过 <code>openshell sandbox exec</code> 在实时 OpenShell sandbox 内运行 <code>command</code>，并返回内核实际允许或拒绝后的输出。未提供 <code>agent</code> 时会自动发现 sandbox 名称。可使用它对正在运行的 sandbox 验证 <code>helpers.evalSandboxNetwork</code> 或 <code>evalSandboxFs</code> 的预测。仅适用于可启动实例。",
  policyGet: "读取可启动实例的实时 OpenShell 策略。通过 operator 终端运行 <code>openshell policy get &lt;agent&gt; --full</code> 并解析 YAML 正文。返回 <code>{ agent, command, raw, status, policy, parseError }</code>，其中包括实际运行的命令、原始返回文本、状态标头、解析后的策略对象，以及策略不可用时的明确解析错误；<code>evalSandboxNetwork</code> 和 <code>evalSandboxFs</code> 会读取该结构。仅适用于可启动实例。",
  "viz.diagram": "根据数据规范自动生成适配主题的节点/边图。<code>spec</code> 为 <code>{title?, caption?, nodes:[{id, label, kind, x, y, lines?}], edges:[{from, to, label?}]}</code>；<code>kind &isin; env|agent|tool|data|model|neutral</code>；<code>x</code> 和 <code>y</code> 表示网格列与行。",
  "viz.lineChart": "为数值序列生成静态折线图。<code>opts</code> 为 <code>{title?, xLabel?, yLabel?, min?, max?, width?}</code>。SVG 的无障碍标签中包含数据点数值；学习者需要精确数据时，请另行返回源数组。",
  "viz.scoreBarChart": "生成 1 到 5 分的评分条形图，并叠加阈值和平均值。<code>scored</code> 是 <code>{score, label?}</code> 数组；<code>opts</code> 为 <code>{threshold, title, width}</code>。",
  "viz.messageList": "用颜色区分的消息序列，其中 USER 为蓝色、ASSISTANT 为绿色、TOOL 为琥珀色。直接接收 OpenAI 格式的 <code>messages</code> 数组。",
  "viz.ganttBars": "甘特式条形图，用于比较各工作线程耗时和总墙钟时间。",
  "viz.retrievalBars": "检索结果的水平分数条形图，以绿色突出显示 top-k 条目，并调暗其它条目。",
  "viz.diffTable": "生成前后对比表，包含按变化着色的差值、勾选标记、页脚说明，以及可选的 <code>verdict({rows})</code>；该函数返回 <code>{ok, text}</code>。<code>spec.rows</code> 条目可以是 <code>{kind:\"check\", label, left, right}</code>，也可以是 <code>{kind:\"num\", label, left, right, betterWhen:\"up\"|\"down\", fmt?}</code>。",
  "viz.chat": "以不同颜色的气泡显示聊天记录。<code>turns</code> 是 <code>[role, content]</code> 对的数组；<code>role &isin; {user, assistant|ai, system, tool}</code>。<code>opts.maxChars</code> 用于限制每轮显示的字符数。",
  "viz.sideBySide": "并排显示两列文本。<code>opts</code> 为 <code>{leftTitle, rightTitle, footer}</code>。",
  state: "所有节点共享的普通对象。在一个节点中设置字段，例如 <code>state.question = \"…\"</code>，之后的任意节点都可以读取。点击 <strong>▶ 全部运行</strong> 时，此对象会重置。",
  fetch: "浏览器原生的 <code>fetch</code>，保持原样公开，使节点可以直接调用任意 HTTP API 入口。参数和返回的 <code>Response</code> 与平台 API 完全相同。它不会重试，也不会附加密钥：上游服务不稳定时请使用 <code>helpers.fetchRetry</code>；模型、搜索或嵌入调用则优先使用上方的专用辅助函数，由它们自动添加路由和密钥。",
  trace: "向每个 CanvasFlow 独立的追踪存储中写入一个符合 OTel 结构的 span 事件。任何实际执行工作的步骤都应记录，而不仅限于 LLM 调用。后续节点可以读取 <code>state.__trace</code>，查看所有已写入事件。",
  log: "向当前单元格的<em>日志</em>区域追加内容。普通值以文本形式追加，对象则渲染为带语法高亮的 JSON。CanvasFlow 和 RunCell 共用以下接口：<code>log(...args)</code>、<code>log.h(title)</code>、<code>log.json(label?, value)</code>、<code>log.kv(object)</code>、<code>log.details(summary, body)</code>、<code>log.html(html)</code>、<code>log.svg(svgString)</code>、<code>log.draw(W, H, body, opts)</code> 和 <code>log.clear()</code>。",
  signal: "本次运行对应的 <code>AbortSignal</code>，已连接到停止按钮。<code>helpers.delay</code>、<code>helpers.chat</code> 和 <code>chatStream</code> 会自动使用它。将它传给 <code>helpers.fetch</code> 或您自己的 <code>WebSocket</code> 清理逻辑，确保学习者按下停止按钮后，长时间运行的任务能够真正取消。"
}));

const LOCALIZED_UI = "main,.topbar";

function localeMaps() {
  const locale = document.documentElement.lang.toLowerCase();
  if (locale === "zh-cn") return { text: ZH_TEXT, attrs: ZH_ATTRS, prefixes: ZH_PREFIXES, previous: "上一课：", next: "下一课：" };
  if (locale === "pt-br") return { text: PT_TEXT, attrs: PT_ATTRS, prefixes: PT_PREFIXES, previous: "Anterior: ", next: "Próxima: " };
  if (locale === "es-es") return { text: ES_TEXT, attrs: ES_ATTRS, prefixes: ES_PREFIXES, previous: "Anterior: ", next: "Siguiente: " };
  return null;
}

function translatedText(value) {
  const maps = localeMaps();
  if (!maps) return value;
  const collapsed = value.replace(/\s+/g, " ").trim();
  const direct = maps.text.get(value) || maps.text.get(collapsed);
  if (direct) return direct;
  if (document.documentElement.lang.toLowerCase() === "zh-cn") {
    let match = value.match(/^\+ show all (\d+) more helpers$/);
    if (match) return `+ 显示其余 ${match[1]} 个辅助函数`;
    match = value.match(/^javascript · editable · (\d+) lines$/);
    if (match) return `javascript · 可编辑 · ${match[1]} 行`;
    const protectedUi = [];
    let embedded = value.replace(/GitHub Pages/g, match => {
      const token = `\u0000NEMO_UI_${protectedUi.length}\u0000`;
      protectedUi.push(match);
      return token;
    });
    // Prefer the longest UI label first ("▶ Run all" before "▶ Run") and never
    // rewrite code/kbd/pre/textarea contents or markup attributes.
    const entries = [...maps.text].sort((a, b) => b[0].length - a[0].length);
    for (const [source, target] of entries) {
      if (source.length < 5 || !embedded.includes(source)) continue;
      embedded = embedded
        .split(/(<(?:code|kbd|pre|textarea)\b[^>]*>[\s\S]*?<\/(?:code|kbd|pre|textarea)>|<[^>]+>)/gi)
        .map(part => {
          if (part.startsWith("<")) return part;
          if (/^[A-Za-z][A-Za-z0-9-]*$/.test(source)) {
            return part.replace(
              new RegExp(`(?<![A-Za-z0-9])${source.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![A-Za-z0-9])`, "g"),
              target,
            );
          }
          return part.split(source).join(target);
        })
        .join("");
    }
    protectedUi.forEach((original, index) => {
      embedded = embedded.split(`\u0000NEMO_UI_${index}\u0000`).join(original);
    });
    if (embedded !== value) return embedded;
  }
  for (const [prefix, replacement] of [["Previous: ", maps.previous], ["Next: ", maps.next]]) {
    if (value.startsWith(prefix)) return replacement + (maps.text.get(value.slice(prefix.length)) || value.slice(prefix.length));
  }
  for (const [prefix, replacement] of maps.prefixes) {
    if (value.startsWith(prefix)) return replacement + value.slice(prefix.length);
  }
  return value;
}

const ZH_INLINE_CONTAINERS = "p,li,td,th,dt,dd,h1,h2,h3,h4,h5,h6,figcaption,summary,label,button,.callout";
const ZH_INLINE_BOUNDARIES = "pre,code,textarea,script,style,select,option,svg";
const ZH_CONTEXT_CHAR = /[\u3400-\u9fff\u3000-\u303f\uff01-\uff65]/;

function normalizeZhInlineSpacing(root) {
  if (document.documentElement.lang.toLowerCase() !== "zh-cn" || !root) return;
  const containers = [];
  if (root.matches?.(ZH_INLINE_CONTAINERS)) containers.push(root);
  containers.push(...root.querySelectorAll?.(ZH_INLINE_CONTAINERS) || []);
  for (const container of new Set(containers)) {
    if (container.closest(ZH_INLINE_BOUNDARIES)) continue;
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const entries = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      const nearestContainer = parent?.closest(ZH_INLINE_CONTAINERS);
      entries.push({
        node,
        boundary: Boolean(parent?.closest(ZH_INLINE_BOUNDARIES)) || nearestContainer !== container,
      });
    }
    const neighbor = (entryIndex, offset, direction) => {
      let index = entryIndex;
      let cursor = offset;
      while (index >= 0 && index < entries.length) {
        const entry = entries[index];
        if (entry.boundary) return null;
        const text = entry.node.nodeValue || "";
        while (cursor >= 0 && cursor < text.length) {
          if (!/\s/.test(text[cursor])) return text[cursor];
          cursor += direction;
        }
        index += direction;
        if (index < 0 || index >= entries.length) return null;
        const nextText = entries[index].node.nodeValue || "";
        cursor = direction < 0 ? nextText.length - 1 : 0;
      }
      return null;
    };
    entries.forEach((entry, entryIndex) => {
      if (entry.boundary) return;
      const text = entry.node.nodeValue || "";
      const removals = [];
      for (const match of text.matchAll(/\s+/g)) {
        const left = neighbor(entryIndex, match.index - 1, -1);
        const right = neighbor(entryIndex, match.index + match[0].length, 1);
        if (left && right && ZH_CONTEXT_CHAR.test(left) && ZH_CONTEXT_CHAR.test(right)) {
          removals.push([match.index, match.index + match[0].length]);
        }
      }
      if (!removals.length) return;
      let normalized = text;
      removals.reverse().forEach(([start, end]) => {
        normalized = normalized.slice(0, start) + normalized.slice(end);
      });
      entry.node.nodeValue = normalized;
    });
  }
}

export function localizeCourseUiText(value) {
  return translatedText(String(value == null ? "" : value));
}

export function localizeCourseHelperDescription(name, value) {
  const source = String(value == null ? "" : value);
  if (document.documentElement.lang.toLowerCase() === "zh-cn") {
    return ZH_HELPER_DESCRIPTIONS.get(String(name || "")) || translatedText(source);
  }
  return translatedText(source);
}

function localizeUi(root = document.body) {
  const maps = localeMaps();
  if (!maps || !root) return;
  const scopes = [];
  if (root.nodeType === Node.ELEMENT_NODE && root.matches?.(LOCALIZED_UI)) scopes.push(root);
  if (root.nodeType === Node.ELEMENT_NODE) scopes.push(...root.querySelectorAll?.(LOCALIZED_UI) || []);
  if (!scopes.length && root.nodeType === Node.ELEMENT_NODE && root.closest?.(LOCALIZED_UI)) scopes.push(root);
  scopes.forEach(scope => {
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      if (node.parentElement?.closest("pre,code,textarea,script,style")) return;
      const value = node.nodeValue || "";
      const trimmed = value.trim();
      if (!trimmed) return;
      const replacement = translatedText(trimmed);
      if (replacement !== trimmed) node.nodeValue = value.replace(trimmed, replacement);
    });
    scope.querySelectorAll?.("[placeholder],[title],[aria-label]").forEach(element => {
      for (const attr of ["placeholder", "title", "aria-label"]) {
        const value = element.getAttribute(attr);
        if (!value) continue;
        const replacement = maps.attrs.get(value) || translatedText(value);
        if (replacement !== value) element.setAttribute(attr, replacement);
      }
    });
    normalizeZhInlineSpacing(scope);
  });
}

function mountLocalizedUi() {
  if (!localeMaps() || document.documentElement.dataset.localeUiMounted === "1") return;
  document.documentElement.dataset.localeUiMounted = "1";
  if (document.documentElement.lang.toLowerCase() === "zh-cn") {
    document.getElementById("learning-path")?.remove();
    document.querySelectorAll('a[href*="nvidia.com/en-us/learn/training/support/"]').forEach(anchor => {
      anchor.closest("p")?.remove();
    });
  }
  localizeUi();
  new MutationObserver(mutations => mutations.forEach(mutation => {
    const root = mutation.target.nodeType === Node.ELEMENT_NODE ? mutation.target : mutation.target.parentElement;
    localizeUi(root);
  })).observe(document.body, { childList: true, subtree: true, characterData: true });
}

export function languageManifestUrl(pageUrl = location.href) {
  const resolvedPage = new URL(pageUrl, location.href);
  const parts = resolvedPage.pathname.split("/").filter(Boolean);
  const courseAt = parts.lastIndexOf("nemoclaw");
  const parent = courseAt > 0 ? parts[courseAt - 1] : "";
  // Built translations always live at /<locale>/nemoclaw/. The page itself can
  // still be the English fallback, so its <html lang> is not reliable here.
  const nested = parent === "web" || /^[a-z]{2}(?:-[a-z0-9]+)*$/i.test(parent);
  return new URL(nested ? "../../languages.json" : "../languages.json", resolvedPage);
}

async function findManifest() {
  const url = languageManifestUrl();
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    const data = await response.json();
    return data?.schema === "nemoclaw-languages/1" && Array.isArray(data.languages) ? { data, url } : null;
  } catch (_) { return null; }
}

function courseBase(entry, manifestUrl) {
  return new URL(entry.url, manifestUrl);
}

function currentEntry(languages, manifestUrl) {
  const here = location.href.split(/[?#]/)[0];
  return [...languages]
    .map(entry => ({ entry, base: courseBase(entry, manifestUrl).href }))
    .filter(item => here.startsWith(item.base))
    .sort((a, b) => b.base.length - a.base.length)[0]?.entry || languages[0];
}

function pageName(entry, manifestUrl) {
  const base = courseBase(entry, manifestUrl);
  const rel = location.href.split(/[?#]/)[0].slice(base.href.length);
  return (rel || "index.html").split("/").pop() || "index.html";
}

function hasPage(entry, file) {
  return !Array.isArray(entry.available_pages) || entry.available_pages.includes(file);
}

function targetUrl(entry, manifestUrl, file) {
  const base = courseBase(entry, manifestUrl);
  const target = new URL(hasPage(entry, file) ? file : "index.html", base);
  target.search = location.search;
  target.hash = location.hash;
  return target.href;
}

function rewriteUnavailableCourseLinks(current, fallback, manifestUrl) {
  if (!current || current.code === fallback.code) return;
  const currentBase = courseBase(current, manifestUrl);
  const fallbackBase = courseBase(fallback, manifestUrl);
  document.querySelectorAll('a[href]').forEach(anchor => {
    if (!(anchor instanceof HTMLAnchorElement)) return;
    let url;
    try { url = new URL(anchor.getAttribute("href"), location.href); } catch (_) { return; }
    if (url.origin !== location.origin || !url.href.startsWith(currentBase.href)) return;
    const file = url.pathname.split("/").pop() || "index.html";
    if (!file.endsWith(".html") || hasPage(current, file)) return;
    anchor.href = new URL(file, fallbackBase).href;
    anchor.dataset.languageFallback = fallback.code;
    const note = current.locale === "pt-BR" ? "Ainda não disponível em português; abre em inglês."
      : current.locale === "es-ES" ? "Aún no está disponible en español; se abre en inglés."
      : "Not available in this language; opens in English.";
    anchor.title = anchor.title ? `${anchor.title} · ${note}` : note;
    if (!anchor.querySelector(".language-fallback-badge")) {
      const badge = document.createElement("span");
      badge.className = "language-fallback-badge";
      badge.textContent = fallback.code.toUpperCase();
      badge.setAttribute("aria-label", note);
      anchor.appendChild(badge);
    }
  });
}

export async function mountLanguageMenu() {
  mountLocalizedUi();
  const bar = document.querySelector(".topbar");
  if (!bar || bar.querySelector(".language-menu")) return;
  const found = await findManifest();
  if (!found || found.data.languages.length < 2) return;
  const languages = found.data.languages;
  const current = currentEntry(languages, found.url);
  const fallback = languages.find(entry => entry.code === found.data.default) || languages[0];
  const file = pageName(current, found.url);
  rewriteUnavailableCourseLinks(current, fallback, found.url);

  const wrap = document.createElement("div");
  wrap.className = "language-menu";
  const button = document.createElement("button");
  button.className = "language-menu-button";
  button.type = "button";
  button.textContent = "🌐";
  button.setAttribute("aria-label", current.locale === "pt-BR" ? "Escolher idioma" : current.locale === "es-ES" ? "Elegir idioma" : "Choose language");
  button.setAttribute("aria-haspopup", "menu");
  button.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "language-menu-popover";
  menu.setAttribute("role", "menu");
  menu.hidden = true;
  languages.forEach(entry => {
    const link = document.createElement("a");
    link.setAttribute("role", "menuitem");
    link.href = targetUrl(entry, found.url, file);
    link.lang = entry.locale || entry.code;
    link.textContent = entry.native_label || entry.label;
    if (entry.code === current.code) link.setAttribute("aria-current", "page");
    if (!hasPage(entry, file)) {
      const small = document.createElement("small");
      small.textContent = entry.locale === "pt-BR" ? "página inicial" : entry.locale === "es-ES" ? "página de inicio" : "course home";
      link.appendChild(small);
    }
    menu.appendChild(link);
  });
  const close = () => { menu.hidden = true; button.setAttribute("aria-expanded", "false"); };
  button.addEventListener("click", () => {
    const open = menu.hidden;
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) menu.querySelector("a")?.focus();
  });
  wrap.addEventListener("keydown", event => {
    if (event.key === "Escape") { close(); button.focus(); }
  });
  document.addEventListener("click", event => { if (!wrap.contains(event.target)) close(); });
  wrap.append(button, menu);
  const pill = bar.querySelector(".key-pill");
  if (pill) bar.insertBefore(wrap, pill);
  else bar.appendChild(wrap);
}
