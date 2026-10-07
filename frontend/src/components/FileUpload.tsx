import { useRef, useState } from "react";
import JSZip from "jszip";
import type { ProjectFile } from "../types/finding";
import { validatePythonPath } from "../api/files";

interface PreparedFile extends ProjectFile {
  readonly sizeBytes: number;
}

interface FileUploadProps {
  readonly onFilesReady: (files: ProjectFile[]) => void;
}

export function FileUpload({ onFilesReady }: Readonly<FileUploadProps>) {
  const inputRef = useRef<HTMLInputElement>(null);
  const directoryInputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<PreparedFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ readonly completed: number; readonly total: number } | null>(null);

  async function handleFiles(fileList: FileList) {
    setError(null);
    const selectedFiles = Array.from(fileList);
    const pyFiles = selectedFiles.filter((file) => file.name.toLowerCase().endsWith(".py"));
    const zipFiles = selectedFiles.filter((file) => file.name.toLowerCase().endsWith(".zip"));
    const totalInputs = pyFiles.length + zipFiles.length;
    let completedInputs = 0;
    const otherCode = selectedFiles.filter((file) => /\.(js|jsx|ts|tsx|java|go|rs|c|h|cpp|rb|php|cs|swift|kt)$/i.test(file.name));

    if (otherCode.length > 0) {
      setError("This workspace accepts Python projects only. Remove non-Python source files and try again.");
      return;
    }

    if (pyFiles.length === 0 && zipFiles.length === 0) {
      setError("Select Python files, a project folder, or a ZIP archive.");
      return;
    }

    try {
      setProgress({ completed: 0, total: totalInputs });
      const readFiles: PreparedFile[] = await Promise.all(pyFiles.map(async (file) => {
        const prepared = {
          path: validatePythonPath(file.webkitRelativePath || file.name),
          content: await file.text(),
          sizeBytes: file.size,
        };
        completedInputs += 1;
        setProgress({ completed: completedInputs, total: totalInputs });
        return prepared;
      }));

      for (const archive of zipFiles) {
        const zip = await JSZip.loadAsync(archive);
        const nonPythonCode = Object.values(zip.files).some((entry) => !entry.dir && /\.(js|jsx|ts|tsx|java|go|rs|c|h|cpp|rb|php|cs|swift|kt)$/i.test(entry.name));
        if (nonPythonCode) throw new Error("The archive contains non-Python source files.");
        const entries = Object.values(zip.files).filter((entry) => !entry.dir && entry.name.toLowerCase().endsWith(".py"));
        const extracted = await Promise.all(entries.map(async (entry) => {
          const content = await entry.async("string");
          return { path: validatePythonPath(entry.name), content, sizeBytes: new Blob([content]).size };
        }));
        readFiles.push(...extracted);
        completedInputs += 1;
        setProgress({ completed: completedInputs, total: totalInputs });
      }

      const uniqueFiles = Array.from(new Map(readFiles.map((file) => [file.path, file])).values());
      if (uniqueFiles.length === 0) {
        setError("No Python files were found in the selected input.");
        return;
      }

      setFiles(uniqueFiles);
      onFilesReady(uniqueFiles.map(({ path, content }) => ({ path, content })));
    } catch {
      setError("Input could not be read. Use relative .py paths only; absolute paths and '..' segments are rejected.");
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
      if (directoryInputRef.current) directoryInputRef.current.value = "";
    }
  }

  function removeFile(path: string) {
    const remaining = files.filter((file) => file.path !== path);
    setFiles(remaining);
    onFilesReady(remaining.map(({ path, content }) => ({ path, content })));
  }

  const totalSize = files.reduce((sum, file) => sum + file.sizeBytes, 0);

  return (
    <div className="file-upload">
      <div
        className={`file-upload__dropzone ${files.length > 0 ? "file-upload__dropzone--ready" : ""}`}
        onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }}
        onDrop={(e) => {
          e.preventDefault();
          if (!progress && e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files);
        }}
        aria-busy={progress !== null}
      >
        <label className="file-upload__prompt" htmlFor="project-files-input">
          <span className="upload-glyph">↑</span>
          <span className="file-upload__prompt-copy"><strong>Drop Python files, a folder, or ZIP archive</strong><br /><span className="file-upload__hint">Only Python source files are sent for analysis</span></span>
        </label>
        <div className="upload-actions">
          <button type="button" className="btn btn--secondary upload-action" disabled={progress !== null} onClick={() => inputRef.current?.click()}>Choose files or ZIP</button>
          <button type="button" className="btn btn--link upload-action" disabled={progress !== null} onClick={() => directoryInputRef.current?.click()}>Choose folder</button>
        </div>
        <input
          ref={inputRef}
          id="project-files-input"
          type="file"
          multiple
          accept=".py,.zip"
          hidden
          onChange={(e) => e.target.files && void handleFiles(e.target.files)}
        />
        <input
          type="file"
          multiple
          hidden
          onChange={(e) => e.target.files && void handleFiles(e.target.files)}
          ref={(element) => {
            if (element) element.setAttribute("webkitdirectory", "");
            if (element) element.setAttribute("accept", ".py,.zip");
            directoryInputRef.current = element;
          }}
        />
      </div>

      {progress && <div className="file-upload__progress" role="status" aria-live="polite"><span>Preparing selected files: {progress.completed} of {progress.total}</span><progress max={progress.total} value={progress.completed} aria-label="Preparing selected files" /></div>}
      {error && <p className="file-upload__error" role="alert">{error}</p>}

      {files.length > 0 && (
        <>
        <p className="file-upload__summary">{files.length} Python files · {formatBytes(totalSize)}. Selecting another set replaces these files.</p>
        <ul className="file-upload__list">
          {files.map((file) => (
            <li key={file.path}><span>PY</span><span>{file.path}<small>{formatBytes(file.sizeBytes)}</small></span><b>ready</b><button type="button" className="btn btn--ghost" aria-label={`Remove ${file.path}`} onClick={() => removeFile(file.path)}>Remove</button></li>
          ))}
        </ul>
        </>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
