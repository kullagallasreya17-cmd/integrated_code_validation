import { useRef, useState } from "react";
import JSZip from "jszip";
import type { ProjectFile } from "../types/finding";

interface FileUploadProps {
  onFilesReady: (files: ProjectFile[]) => void;
}

export function FileUpload({ onFilesReady }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const directoryInputRef = useRef<HTMLInputElement | null>(null);
  const [fileNames, setFileNames] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function handleFiles(fileList: FileList) {
    setError(null);
    const selectedFiles = Array.from(fileList);
    const pyFiles = selectedFiles.filter((file) => file.name.toLowerCase().endsWith(".py"));
    const zipFiles = selectedFiles.filter((file) => file.name.toLowerCase().endsWith(".zip"));

    if (pyFiles.length === 0 && zipFiles.length === 0) {
      setError("Select Python files, a project folder, or a ZIP archive.");
      return;
    }

    try {
      const readFiles: ProjectFile[] = await Promise.all(
        pyFiles.map(async (file) => ({
          path: file.webkitRelativePath || file.name,
          content: await file.text(),
        }))
      );

      for (const archive of zipFiles) {
        const zip = await JSZip.loadAsync(archive);
        const entries = Object.values(zip.files).filter((entry) => !entry.dir && entry.name.toLowerCase().endsWith(".py"));
        if (entries.length === 0) continue;
        const extracted = await Promise.all(entries.map(async (entry) => ({ path: entry.name, content: await entry.async("string") })));
        readFiles.push(...extracted);
      }

      const uniqueFiles = Array.from(new Map(readFiles.map((file) => [file.path, file])).values());
      if (uniqueFiles.length === 0) {
        setError("No Python files were found in the selected input.");
        return;
      }

      setFileNames(uniqueFiles.map((file) => file.path));
      onFilesReady(uniqueFiles);
    } catch {
      setError("The selected archive could not be read. Please try another ZIP file.");
    }
  }

  return (
    <div className="file-upload">
      <div
        className={`file-upload__dropzone ${fileNames.length > 0 ? "file-upload__dropzone--ready" : ""}`}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
      >
        <span className="upload-glyph">↑</span>
        <p><strong>Drop Python files, a folder, or ZIP archive</strong><br /><span className="file-upload__hint">Only Python source files are sent for analysis</span></p>
        <div className="upload-actions">
          <button type="button" className="btn btn--secondary upload-action" onClick={(event) => { event.stopPropagation(); inputRef.current?.click(); }}>Choose files or ZIP</button>
          <button type="button" className="btn btn--link upload-action" onClick={(event) => { event.stopPropagation(); directoryInputRef.current?.click(); }}>Choose folder</button>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".py"
          hidden
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
        <input
          type="file"
          multiple
          hidden
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
          ref={(element) => {
            if (element) element.setAttribute("webkitdirectory", "");
            directoryInputRef.current = element;
          }}
        />
      </div>

      {error && <p className="file-upload__error">{error}</p>}

      {fileNames.length > 0 && (
        <ul className="file-upload__list">
          {fileNames.map((name) => (
            <li key={name}><span>PY</span>{name}<b>ready</b></li>
          ))}
        </ul>
      )}
    </div>
  );
}
