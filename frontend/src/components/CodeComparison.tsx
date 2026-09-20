import { CodeEditor } from "./CodeEditor";
import type { ProjectFile } from "../types/finding";

interface CodeComparisonProps {
  original: ProjectFile[];
  repaired: ProjectFile[];
}

export function CodeComparison({ original, repaired }: CodeComparisonProps) {
  const repairedByPath = new Map(repaired.map((f) => [f.path, f.content]));

  return (
    <div className="code-comparison">
      {original.map((file) => (
        <div key={file.path} className="code-comparison__pair">
          <div>
            <h4>Original</h4>
            <CodeEditor path={file.path} value={file.content} readOnly />
          </div>
          <div>
            <h4>Repaired</h4>
            <CodeEditor
              path={`repaired-${file.path}`}
              value={repairedByPath.get(file.path) ?? file.content}
              readOnly
            />
          </div>
        </div>
      ))}
    </div>
  );
}
