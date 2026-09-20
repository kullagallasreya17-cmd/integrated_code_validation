import Editor, { type OnMount } from "@monaco-editor/react";

interface CodeEditorProps {
  path: string;
  value: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
  height?: string;
  highlightLine?: number | null;
}

export function CodeEditor({ path, value, readOnly = false, onChange, height = "360px", highlightLine }: CodeEditorProps) {
  const handleMount: OnMount = (editor, monaco) => {
    if (!highlightLine) return;
    editor.revealLineInCenter(highlightLine);
    editor.setPosition({ lineNumber: highlightLine, column: 1 });
    editor.deltaDecorations([], [{
      range: new monaco.Range(highlightLine, 1, highlightLine, 1),
      options: { isWholeLine: true, className: "code-editor__highlight-line", glyphMarginClassName: "code-editor__highlight-glyph" },
    }]);
  };

  return (
    <div className="code-editor">
      <div className="code-editor__filename">{path}</div>
      <Editor
        height={height}
        defaultLanguage="python"
        path={path}
        value={value}
        theme="vs-dark"
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          scrollBeyondLastLine: false,
        }}
        onChange={(next) => onChange?.(next ?? "")}
        onMount={handleMount}
      />
    </div>
  );
}
