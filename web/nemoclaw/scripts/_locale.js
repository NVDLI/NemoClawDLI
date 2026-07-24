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
  "localhost points to this browser, not the Brev VM. Expose port 5000 with Brev Using Tunnels and paste its HTTPS URL ending in /v1": "localhost aponta para este navegador, não para a VM do Brev. Exponha a porta 5000 com Using Tunnels e cole a URL HTTPS terminada em /v1",
  "A Brev Jupyter /lab URL is not a model API. Expose port 5000 with Brev Using Tunnels and paste its HTTPS URL ending in /v1": "Uma URL /lab do Jupyter no Brev não é uma API de modelo. Exponha a porta 5000 com Using Tunnels e cole a URL HTTPS terminada em /v1",
  "The default embedding route needs an nvapi- key": "A rota padrão de embeddings precisa de uma chave nvapi-",
  "Enter the key for the embedding route": "Informe a chave da rota de embeddings",
  "model discovery returned no model IDs": "A descoberta de modelos não retornou IDs de modelo",
  "embedding model discovery returned no model IDs": "A descoberta de modelos de embeddings não retornou IDs de modelo",
  "Brev fallback: expose port 5000 with Using Tunnels, make the tunnel public, then paste its /v1 URL, key EMPTY, and served model ID. A private tunnel cannot accept cross-origin course requests. Do not paste the Jupyter /lab URL or localhost.": "Fallback do Brev: exponha a porta 5000 com Using Tunnels, torne o túnel público e cole a URL /v1, a chave EMPTY e o ID do modelo servido. Um túnel privado não aceita requisições do curso entre origens. Não cole a URL /lab do Jupyter nem localhost.",
  "Open Brev connectivity steps →": "Abrir as etapas de conectividade do Brev →",
  "Model discovery did not return JSON. Confirm the Brev tunnel is public, then try again": "A descoberta de modelos não retornou JSON. Confirme que o túnel do Brev é público e tente novamente",
  "A presenter can prefill ?base_url=...&model=.... This tab reuses the keys across lessons and discards them when it closes.": "O instrutor pode preencher ?base_url=...&model=.... Esta aba reutiliza as chaves entre as aulas e as descarta ao fechar.",
  "Free-tier models cover every exercise. A presenter can prefill one compatible endpoint with": "Os modelos gratuitos atendem a todos os exercícios. O instrutor pode preencher previamente um endpoint compatível com",
  ". Review it, then Save & verify once; every lesson reuses it.": ". Revise o endereço e selecione Salvar e verificar uma vez para que todas as aulas reutilizem essa configuração."
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
  "localhost points to this browser, not the Brev VM. Expose port 5000 with Brev Using Tunnels and paste its HTTPS URL ending in /v1": "localhost apunta a este navegador, no a la VM de Brev. Exponga el puerto 5000 con Using Tunnels y pegue su URL HTTPS terminada en /v1",
  "A Brev Jupyter /lab URL is not a model API. Expose port 5000 with Brev Using Tunnels and paste its HTTPS URL ending in /v1": "Una URL /lab de Jupyter en Brev no es una API de modelo. Exponga el puerto 5000 con Using Tunnels y pegue su URL HTTPS terminada en /v1",
  "The default embedding route needs an nvapi- key": "La ruta predeterminada de embeddings necesita una clave nvapi-",
  "Enter the key for the embedding route": "Introduzca la clave de la ruta de embeddings",
  "model discovery returned no model IDs": "El descubrimiento de modelos no devolvió IDs de modelo",
  "embedding model discovery returned no model IDs": "El descubrimiento de modelos de embeddings no devolvió IDs de modelo",
  "Brev fallback: expose port 5000 with Using Tunnels, make the tunnel public, then paste its /v1 URL, key EMPTY, and served model ID. A private tunnel cannot accept cross-origin course requests. Do not paste the Jupyter /lab URL or localhost.": "Alternativa de Brev: exponga el puerto 5000 con Using Tunnels, haga público el túnel y pegue la URL /v1, la clave EMPTY y el ID del modelo servido. Un túnel privado no acepta solicitudes del curso entre orígenes. No pegue la URL /lab de Jupyter ni localhost.",
  "Open Brev connectivity steps →": "Abrir los pasos de conectividad de Brev →",
  "Model discovery did not return JSON. Confirm the Brev tunnel is public, then try again": "El descubrimiento de modelos no devolvió JSON. Confirme que el túnel de Brev sea público e inténtelo de nuevo",
  "A presenter can prefill ?base_url=...&model=.... This tab reuses the keys across lessons and discards them when it closes.": "El instructor puede precompletar ?base_url=...&model=.... Esta pestaña reutiliza las claves entre lecciones y las descarta al cerrarse.",
  "Free-tier models cover every exercise. A presenter can prefill one compatible endpoint with": "Los modelos gratuitos cubren todos los ejercicios. El instructor puede precompletar un endpoint compatible con",
  ". Review it, then Save & verify once; every lesson reuses it.": ". Revise la dirección y seleccione Guardar y verificar una vez para que todas las lecciones reutilicen esa configuración.",
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

const LOCALIZED_UI = "#journey-map,.topbar,.cf-wrap,.rc-card,.chatui,.key-panel,.claw-probe,.da-term";

function localeMaps() {
  const locale = document.documentElement.lang.toLowerCase();
  if (locale === "pt-br") return { text: PT_TEXT, attrs: PT_ATTRS, prefixes: PT_PREFIXES, previous: "Anterior: ", next: "Próxima: " };
  if (locale === "es-es") return { text: ES_TEXT, attrs: ES_ATTRS, prefixes: ES_PREFIXES, previous: "Anterior: ", next: "Siguiente: " };
  return null;
}

function translatedText(value) {
  const maps = localeMaps();
  if (!maps) return value;
  const direct = maps.text.get(value);
  if (direct) return direct;
  for (const [prefix, replacement] of [["Previous: ", maps.previous], ["Next: ", maps.next]]) {
    if (value.startsWith(prefix)) return replacement + (maps.text.get(value.slice(prefix.length)) || value.slice(prefix.length));
  }
  for (const [prefix, replacement] of maps.prefixes) {
    if (value.startsWith(prefix)) return replacement + value.slice(prefix.length);
  }
  return value;
}

export function localizeCourseUiText(value) {
  return translatedText(String(value == null ? "" : value));
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
  });
}

function mountLocalizedUi() {
  if (!localeMaps() || document.documentElement.dataset.localeUiMounted === "1") return;
  document.documentElement.dataset.localeUiMounted = "1";
  localizeUi();
  new MutationObserver(mutations => mutations.forEach(mutation => {
    const root = mutation.target.nodeType === Node.ELEMENT_NODE ? mutation.target : mutation.target.parentElement;
    localizeUi(root);
  })).observe(document.body, { childList: true, subtree: true, characterData: true });
}

function manifestCandidates() {
  const parts = location.pathname.split("/").filter(Boolean);
  const courseAt = parts.lastIndexOf("nemoclaw");
  const parent = courseAt > 0 ? parts[courseAt - 1] : "";
  const nested = parent === "web" || /^[a-z]{2}(?:-[a-z0-9]+)?$/.test(parent);
  const first = nested ? "../../languages.json" : "../languages.json";
  return [first, "../languages.json", "../../languages.json", "../../../languages.json", "../../../../languages.json"]
    .filter((item, index, all) => all.indexOf(item) === index);
}

async function findManifest() {
  for (const rel of manifestCandidates()) {
    try {
      const url = new URL(rel, location.href);
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) continue;
      const data = await response.json();
      if (data?.schema === "nemoclaw-languages/1" && Array.isArray(data.languages)) {
        return { data, url };
      }
    } catch (_) {}
  }
  return null;
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
