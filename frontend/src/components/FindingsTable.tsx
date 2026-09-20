import { Fragment, useState } from "react";
import type { Finding, Severity } from "../types/finding";

interface FindingsTableProps {
  findings: Finding[];
  onSelect?: (finding: Finding) => void;
}

const SEVERITY_ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const SEVERITY_FILTERS: Array<"all" | Severity> = ["all", "critical", "high", "medium", "low"];
const CATEGORY_FILTERS = ["all", "code_quality", "security", "bug", "resource"] as const;

export function FindingsTable({ findings, onSelect }: FindingsTableProps) {
  const [severity, setSeverity] = useState<"all" | Severity>("all");
  const [category, setCategory] = useState<(typeof CATEGORY_FILTERS)[number]>("all");
  const [tool, setTool] = useState("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const query = search.trim().toLowerCase();
  const sorted = [...findings]
    .filter((finding) => severity === "all" || finding.severity === severity)
    .filter((finding) => category === "all" || finding.category === category)
    .filter((finding) => tool === "all" || finding.tool === tool)
    .filter(
      (finding) =>
        !query ||
        finding.file.toLowerCase().includes(query) ||
        finding.issue.toLowerCase().includes(query) ||
        finding.description.toLowerCase().includes(query),
    )
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);

  return (
    <div className="findings-table__container">
      <div className="findings-table__controls">
        <div className="findings-table__filter-groups">
        <div className="findings-table__filters" role="group" aria-label="Filter by severity">
          {SEVERITY_FILTERS.map((filter) => (
            <button
              key={filter}
              className={`btn ${severity === filter ? "btn--primary" : ""}`}
              onClick={() => setSeverity(filter)}
            >
              {filter[0].toUpperCase() + filter.slice(1)}
            </button>
          ))}
        </div>
        <div className="findings-table__filters" role="group" aria-label="Filter by category">
          {CATEGORY_FILTERS.map((filter) => <button key={filter} className={`btn ${category === filter ? "btn--primary" : ""}`} onClick={() => setCategory(filter)}>{filter === "all" ? "All areas" : filter.replace("_", " ")}</button>)}
        </div>
        <select className="findings-table__tool-select" value={tool} onChange={(event) => setTool(event.target.value)} aria-label="Filter by tool"><option value="all">All tools</option><option value="ruff">Ruff</option><option value="pylint">Pylint</option><option value="radon">Radon</option></select>
        </div>
        <input
          type="search"
          value={search}
          placeholder="Search files or issues"
          aria-label="Search files or issues"
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>
      {sorted.length === 0 ? (
        <p className="findings-table__empty">No findings match these filters.</p>
      ) : (
        <table className="findings-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>File</th>
              <th>Line</th>
              <th>Issue</th>
              <th>Category</th>
              <th>Tool</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((finding) => (
              <Fragment key={finding.finding_id}>
                <tr
                  className={`findings-table__row findings-table__row--${finding.severity}`}
                  onClick={() => { setExpanded(expanded === finding.finding_id ? null : finding.finding_id); onSelect?.(finding); }}
                >
                  <td>{finding.severity}</td>
                  <td>{finding.file}</td>
                  <td>{finding.line_number ?? "-"}</td>
                  <td>{finding.issue}</td>
                  <td>{finding.subcategory ?? finding.category}</td>
                  <td>{finding.tool ?? finding.evidence?.match(/^\[([^\]]+)/)?.[1] ?? "-"}</td>
                  <td><span className="status-pill status-pill--unknown">{finding.status}</span></td>
                </tr>
                {expanded === finding.finding_id && (
                  <tr key={`${finding.finding_id}-details`} className="findings-table__details">
                    <td colSpan={7}>
                      <strong>Description:</strong> {finding.description}
                      {finding.recommendation && (
                        <p>
                          <strong>Recommendation:</strong> {finding.recommendation}
                        </p>
                      )}
                      {finding.evidence && <p><strong>Evidence:</strong> {finding.evidence}</p>}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );

}
