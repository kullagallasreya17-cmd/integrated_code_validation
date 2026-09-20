interface ToolStatusPanelProps { quality: string[]; }

export function ToolStatusPanel({ quality }: ToolStatusPanelProps) {
  const tools = quality.map((tool) => [tool, "configured"]);
  return <section className="tool-status"><div className="section-label"><h2>Tool status</h2><span>MCP / analysis sources</span></div><div className="tool-status__grid">{tools.map(([tool, status]) => <div className="tool-status__item" key={tool}><i className={status === "configured" ? "tool-status__ok" : "tool-status__pending"} /> <strong>{tool}</strong><small>{status}</small></div>)}</div></section>;
}