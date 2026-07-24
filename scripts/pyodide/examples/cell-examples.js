// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

globalThis.PYODIDE_CELL_EXAMPLES = Object.freeze([
  {
    id: "compute",
    title: "1. Compute and return a value",
    purpose: "Start with ordinary Python computation and a notebook-style final expression.",
    coverage: ["python-runtime", "returned-value", "jupyter-display", "pretty-display", "persistent-kernel", "execution-count", "syntax-highlighting", "repl"],
    input: "3, 5, 8",
    source: `raw = inputs.get("user_input", "3, 5, 8")
values = [int(part.strip()) for part in raw.split(",")]

{
    "example": "compute",
    "sum": sum(values),
    "squares": [value ** 2 for value in values],
}`,
  },
  {
    id: "output-channels",
    title: "2. Separate progress from the result",
    purpose: "Keep printed progress, returned data, and errors in separate UI channels.",
    coverage: ["stdout", "stderr", "returned-value", "markdown-display", "code-display", "ipython-display-helpers"],
    input: "4, 9, 16",
    source: `raw = inputs.get("user_input", "4, 9, 16")
values = [int(part.strip()) for part in raw.split(",")]

print(f"parsed {len(values)} values")
print("calculating square roots")
display_markdown(f"**Progress:** parsed {len(values)} values; the structured result follows.")
display_code("""roots = [value ** 0.5 for value in values]
result = {"roots": roots}""", language="python")

{
    "example": "output-channels",
    "roots": [value ** 0.5 for value in values],
}`,
  },
  {
    id: "user-input",
    title: "3. Accept learner input",
    purpose: "Pass a user-controlled message into Python without rewriting the cell.",
    coverage: ["editable-input", "worker-message", "html-display", "json-display", "ipython-display-helpers"],
    input: "How does browser Python work?",
    source: `message = inputs.get("user_input", "").strip()
words = [word.strip(".,?!").lower() for word in message.split()]
display_html(f"<p><strong>Input preview:</strong> {len(words)} words were received.</p>")
display_json({"normalized_words": words, "unique_words": len(set(words))})

{
    "example": "user-input",
    "message": message,
    "word_count": len(words),
    "keywords": sorted(set(word for word in words if len(word) > 5)),
}`,
  },
  {
    id: "messages",
    title: "4. Build a chat request",
    purpose: "Represent system and user turns with the OpenAI-compatible message shape.",
    coverage: ["chat-completions", "structured-messages", "table-display", "ipython-display-helpers"],
    input: "Explain workers in one sentence.",
    source: `user_message = inputs.get("user_input", "Explain workers in one sentence.")
messages = [
    {"role": "system", "content": "Answer clearly and briefly."},
    {"role": "user", "content": user_message},
]
display_table(messages, headers=["role", "content"])

{
    "example": "messages",
    "messages": messages,
    "request_turns": len(messages),
}`,
  },
  {
    id: "local-chat",
    title: "5. Add a Python assistant",
    purpose: "Turn a message list into a deterministic chat response that runs without credentials.",
    coverage: ["chatbot", "local-fallback"],
    input: "Why use a Web Worker?",
    source: `def answer(message):
    text = message.lower()
    if "worker" in text:
        return "A Web Worker keeps Python execution off the page's main UI thread."
    if "reset" in text:
        return "Reset terminates the worker and starts a clean Python interpreter."
    if "error" in text:
        return "Errors belong in stderr while successful values remain separate."
    return f"I received {len(message.split())} words. Ask about workers, reset, or errors."

user_message = inputs.get("user_input", "Why use a Web Worker?")

{
    "example": "local-chat",
    "assistant": answer(user_message),
}`,
  },
  {
    id: "tool-call",
    title: "6. Let the assistant call a tool",
    purpose: "Select a typed Python function, parse arguments, execute it, and return the observation.",
    coverage: ["function-calling", "tool-execution", "json-arguments"],
    input: "Add 14 and 28",
    source: `import re

def add(left, right):
    return left + right

message = inputs.get("user_input", "Add 14 and 28")
numbers = [int(value) for value in re.findall(r"-?\\d+", message)]
tool_call = {"name": "add", "arguments": {"left": numbers[0], "right": numbers[1]}}
observation = add(**tool_call["arguments"])

{
    "example": "tool-call",
    "tool_call": tool_call,
    "observation": observation,
    "assistant": f"The result is {observation}.",
}`,
  },
  {
    id: "mcp",
    title: "7. Describe an MCP tool source",
    purpose: "Build the same MCP descriptor shape used by a Responses-style request without contacting a server.",
    coverage: ["mcp", "responses-api", "allowed-tools"],
    input: "search",
    source: `requested_tool = inputs.get("user_input", "search").strip() or "search"
mcp_source = {
    "type": "mcp",
    "server_label": "course-reference",
    "server_url": inputs.get("mcp_server_url", "<course-mcp-server-url>"),
    "allowed_tools": [requested_tool],
    "require_approval": "always",
}

{
    "example": "mcp",
    "tool_source": mcp_source,
    "network_called": False,
}`,
  },
  {
    id: "agent-loop",
    title: "8. Run a small agent loop",
    purpose: "Plan, call a tool, record an observation, and finish with an answer.",
    coverage: ["agent-loop", "tool-execution", "trace"],
    input: "Multiply 6 by 7",
    source: `import re

def multiply(left, right):
    return left * right

message = inputs.get("user_input", "Multiply 6 by 7")
numbers = [int(value) for value in re.findall(r"-?\\d+", message)]
trace = [{"step": "plan", "detail": "Use multiply for the two numbers."}]
observation = multiply(numbers[0], numbers[1])
trace.append({"step": "tool", "name": "multiply", "observation": observation})
trace.append({"step": "answer", "detail": f"The result is {observation}."})

{
    "example": "agent-loop",
    "answer": trace[-1]["detail"],
    "trace": trace,
}`,
  },
  {
    id: "background-job",
    title: "9. Register background work",
    purpose: "Start a named asyncio task, keep it alive across cell executions, and inspect its lifecycle.",
    coverage: ["asyncio", "background-process", "process-registration", "process-status", "worker-lifecycle"],
    input: "Summarize browser Python capabilities",
    source: `import asyncio

async def prepare_summary(topic):
    await asyncio.sleep(0.03)
    return {
        "topic": topic,
        "bullets": ["persistent namespace", "streaming chat", "downloadable artifacts"],
    }

topic = inputs.get("user_input", "Summarize browser Python capabilities")
registration = register_background("prepare-summary", prepare_summary(topic))
display_json(background_status())

{
    "example": "background-job",
    "registration": registration,
    "worker_continues": True,
}`,
  },
  {
    id: "artifact-generation",
    title: "10. Generate a downloadable artifact",
    purpose: "Wait for background work, serialize its result, preview it safely, and expose the exact bytes for download.",
    coverage: ["artifact-generation", "artifact-preview", "artifact-download", "background-result", "json-serialization"],
    input: "browser-python-report.json",
    source: `import asyncio
import json

if background_status("prepare-summary") is None:
    async def prepare_summary(topic):
        await asyncio.sleep(0.01)
        return {
            "topic": topic,
            "bullets": ["persistent namespace", "streaming chat", "downloadable artifacts"],
        }
    register_background("prepare-summary", prepare_summary("Browser Python capabilities"))

completed = await wait_background("prepare-summary")
filename = inputs.get("user_input", "browser-python-report.json").strip() or "browser-python-report.json"
artifact_data = {
    "title": "Browser Python report",
    "background_job": completed,
    "generated_by": "Pyodide",
}
artifact_text = json.dumps(artifact_data, indent=2)
display_artifact(filename, artifact_text, mime_type="application/json", language="json")

{
    "example": "artifact-generation",
    "filename": filename,
    "bytes": len(artifact_text.encode("utf-8")),
    "job_state": completed["state"],
}`,
  },
  {
    id: "portable-request",
    title: "11. Use an optional WebSocket transport",
    purpose: "Open a real secure WebSocket when a URL is supplied, while keeping the endpoint and message outside the Python source.",
    coverage: ["api-settings", "openai-compatible", "nim-portability", "secret-handling", "websocket", "connection-state"],
    input: "hello from browser Python",
    source: `import json

user_message = inputs.get("user_input", "hello from browser Python")
websocket_url = inputs.get("websocket_url", "").strip()
socket_result = None
if websocket_url:
    from js import courseWebSocketRoundTrip
    socket_result = json.loads(str(await courseWebSocketRoundTrip(
        websocket_url, user_message, __request_id, 8000
    )))

request = {
    "base_url": inputs.get("base_url", "https://integrate.api.nvidia.com/v1"),
    "model": inputs.get("model", "nvidia/nemotron-3-nano-30b-a3b"),
    "messages": [{"role": "user", "content": user_message}],
    "max_tokens": 120,
}

{
    "example": "portable-request",
    "request": request,
    "websocket": socket_result or "Add a wss:// URL above to run the round trip.",
    "credential_present": bool(inputs.get("api_key")),
    "credential_value_returned": False,
}`,
  },
  {
    id: "chat-app",
    title: "12. Stream a build.nvidia.com chat",
    purpose: "Use a learner key to stream a hosted NVIDIA model response; without a key, retain the deterministic local assistant.",
    coverage: ["chat-application", "conversation-history", "user-input", "reset", "build-nvidia", "http-sse", "streaming", "cancel"],
    input: "How do I reset the Python runtime?",
    chat: true,
    source: `import json

def respond_locally(message):
    text = message.lower()
    if "reset" in text:
        return "Select Reset runtime. The worker is terminated, so globals and pending work are cleared."
    if "stop" in text:
        return "Select Stop to terminate the current worker immediately."
    if "error" in text:
        return "Run the error example to see a Python traceback in the stderr panel."
    return "This chat is running entirely in Python inside the browser."

history = list(inputs.get("history", []))
user_message = inputs.get("user_input", "Hello").strip()
transport = "local"
if inputs.get("api_key"):
    from js import courseStreamChat
    request = {
        "base_url": inputs.get("base_url"),
        "model": inputs.get("model"),
        "messages": history + [{"role": "user", "content": user_message}],
        "temperature": 0.1,
        "max_tokens": 512,
    }
    streamed = json.loads(str(await courseStreamChat(
        json.dumps(request), inputs.get("api_key"), __request_id
    )))
    assistant_message = streamed["content"]
    transport = streamed["transport"]
else:
    assistant_message = respond_locally(user_message)
history.extend([
    {"role": "user", "content": user_message},
    {"role": "assistant", "content": assistant_message},
])

{
    "example": "chat-app",
    "assistant": assistant_message,
    "history": history,
    "turns": len(history),
    "transport": transport,
}`,
  },
]);
