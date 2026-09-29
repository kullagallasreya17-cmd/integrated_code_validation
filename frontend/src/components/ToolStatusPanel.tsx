interface ToolStatusPanelProps {
  readonly quality: string[];
}

export function ToolStatusPanel({ quality }: ToolStatusPanelProps) {
  return <section className="tool-status"><div className="section-label"><h2>Selected tools</h2><span>Execution status appears in the run results</span></div><div className="tool-status__grid">{quality.map((tool) => <div className="tool-status__item" key={tool}><i className="tool-status__pending" /> <strong>{tool}</strong><small>Selected · not run yet</small></div>)}</div></section>;
}