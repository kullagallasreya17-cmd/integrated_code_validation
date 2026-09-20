import { FindingsTable } from "../components/FindingsTable";
import type { Finding } from "../types/finding";

export function FindingsReviewPage({ findings, onNewAnalysis }: { findings: Finding[]; onNewAnalysis: () => void }) {
  return <section className="page review-page"><div className="kicker">Findings review <span>02 / 04</span></div><h1>Evidence,<br /><em>in context.</em></h1><p className="review-page__intro">Search every finding returned by the validation pipeline, then open a row for its evidence and remediation guidance.</p><div className="review-page__count">{findings.length} findings in current workspace</div>{findings.length === 0 ? <div className="empty-state"><strong>No findings yet.</strong><span>Run an analysis first, then return here to review file, line, tool, and remediation evidence.</span><button className="btn btn--primary" onClick={onNewAnalysis}>Start new analysis →</button></div> : <FindingsTable findings={findings} />}</section>;
}