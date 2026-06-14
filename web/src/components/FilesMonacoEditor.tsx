import { useEffect, useRef } from "react";
import Editor, { type Monaco } from "@monaco-editor/react";
import type { editor, IDisposable } from "monaco-editor";

function languageForPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    json: "json",
    md: "markdown",
    py: "python",
    rs: "rust",
    go: "go",
    css: "css",
    html: "html",
    yml: "yaml",
    yaml: "yaml",
    sh: "shell",
    toml: "ini",
  };
  return map[ext] ?? "plaintext";
}

type Props = {
  path: string;
  value: string;
  onChange: (value: string) => void;
  /** LSP stub — Monaco path completion from workspace file list. */
  pathSuggestions?: string[];
};

export function FilesMonacoEditor({
  path,
  value,
  onChange,
  pathSuggestions = [],
}: Props) {
  const disposeRef = useRef<IDisposable | null>(null);

  function registerPathCompletion(monaco: Monaco) {
    disposeRef.current?.dispose();
    if (!pathSuggestions.length) return;
    disposeRef.current = monaco.languages.registerCompletionItemProvider(
      languageForPath(path),
      {
        triggerCharacters: ["/", ".", "@"],
        provideCompletionItems: (model, position) => {
          const word = model.getWordUntilPosition(position);
          const range = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn,
          };
          const query = word.word.toLowerCase();
          const suggestions = pathSuggestions
            .filter((p) => !query || p.toLowerCase().includes(query))
            .slice(0, 40)
            .map((p) => ({
              label: p,
              kind: monaco.languages.CompletionItemKind.File,
              insertText: p,
              range,
            }));
          return { suggestions };
        },
      },
    );
  }

  useEffect(() => {
    return () => {
      disposeRef.current?.dispose();
    };
  }, []);

  useEffect(() => {
    const monaco = (window as Window & { monaco?: Monaco }).monaco;
    if (monaco) registerPathCompletion(monaco);
  }, [path, pathSuggestions]);

  function handleMount(_editor: editor.IStandaloneCodeEditor, monaco: Monaco) {
    registerPathCompletion(monaco);
  }

  return (
    <div className="files-monaco">
      <Editor
        height="100%"
        language={languageForPath(path)}
        value={value}
        onChange={(next) => onChange(next ?? "")}
        onMount={handleMount}
        theme="vs-dark"
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "var(--font-mono, ui-monospace, monospace)",
          wordWrap: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          padding: { top: 8, bottom: 8 },
          quickSuggestions: { other: true, strings: true, comments: false },
        }}
      />
    </div>
  );
}
