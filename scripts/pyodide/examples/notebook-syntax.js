// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

(function () {
  "use strict";

  const SUPPORTED = Object.freeze([
    "value? / value??", "!command", "%%bash", "%%time", "%who", "%whos",
    "%pwd", "%ls [path]", "%cd path", "%pip list", "%time expression",
    "%timeit expression", "%magic",
  ]);

  function pythonString(value) {
    return JSON.stringify(String(value));
  }

  function normalizeLine(line) {
    if (/^\s*!/.test(line)) {
      return `browser_shell(${pythonString(line.replace(/^\s*!\s?/, ""))})`;
    }
    const prefixInspection = line.match(/^\s*(\?\?|\?)\s*(.+?)\s*$/);
    if (prefixInspection) {
      return `inspect_object(${pythonString(prefixInspection[2])}, detail=${prefixInspection[1].length})`;
    }
    const suffixInspection = line.match(/^\s*(.+?)(\?\?|\?)\s*$/);
    if (suffixInspection && !suffixInspection[1].trim().endsWith("?")) {
      return `inspect_object(${pythonString(suffixInspection[1])}, detail=${suffixInspection[2].length})`;
    }
    const magic = line.match(/^\s*%(\w+)\b\s*(.*)$/);
    if (!magic) return line;
    const [, name, argument] = magic;
    if (name === "who") return "notebook_who(details=False)";
    if (name === "whos") return "notebook_who(details=True)";
    if (name === "pwd") return "notebook_pwd()";
    if (name === "ls") return `notebook_ls(${pythonString(argument || ".")})`;
    if (name === "cd") return `notebook_cd(${pythonString(argument || ".")})`;
    if (name === "magic") return "notebook_magic()";
    if (name === "pip" && argument.trim() === "list") return "notebook_pip_list()";
    if (name === "time" && argument.trim()) return `notebook_time(${pythonString(argument)}, repeat=1)`;
    if (name === "timeit" && argument.trim()) return `notebook_time(${pythonString(argument)}, repeat=5)`;
    const message = `Unsupported notebook magic %${name}. Run %magic to see the supported browser commands.`;
    return `raise SyntaxError(${pythonString(message)})`;
  }

  function normalize(source) {
    const text = String(source || "").replace(/\r\n?/g, "\n");
    if (text.startsWith("%%time\n")) {
      const body = text.slice(7);
      return {
        source: `import time as __course_time\n__course_started = __course_time.perf_counter()\n${body}\nprint(f"Wall time: {__course_time.perf_counter() - __course_started:.3f} s")`,
        lineOffset: 2,
        kind: "cell-magic",
      };
    }
    if (text.startsWith("%%bash\n")) {
      return { source: `browser_shell(${pythonString(text.slice(7).trim())})`, lineOffset: 0, kind: "cell-magic" };
    }
    return { source: text.split("\n").map(normalizeLine).join("\n"), lineOffset: 0, kind: "python" };
  }

  globalThis.PYODIDE_NOTEBOOK_SYNTAX = Object.freeze({ normalize, supported: SUPPORTED });
})();
