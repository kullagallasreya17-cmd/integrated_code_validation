import { useState } from "react";
import type { ProjectFile, WorkflowRunResponse } from "../types/finding";
import { BugResourceTab } from "./BugResourceTab";
import { QualityTab } from "./QualityTab";
import { StructureTab } from "./StructureTab";
import { ToolsTab } from "./ToolsTab";
import { TraceabilityTab } from "./TraceabilityTab";

interface AnalysisTabsProps { readonly result: WorkflowRunResponse | null; readonly files: ProjectFile[]; }
const TABS = ["Structure", "Quality", "Bug & Resource", "Trace", "Tools"] as const;
type Tab = (typeof TABS)[number];

export function AnalysisTabs({ result, files }: Readonly<AnalysisTabsProps>) {
  const [active, setActive] = useState<Tab>("Structure");
  return <section className="analysis-tabs" aria-label="Analysis evidence">
    <nav className="analysis-tabs__nav" aria-label="Analysis tabs">{TABS.map((tab) => <button key={tab} className={active === tab ? "analysis-tabs__tab analysis-tabs__tab--active" : "analysis-tabs__tab"} aria-current={active === tab ? "page" : undefined} onClick={() => setActive(tab)}>{tab}</button>)}</nav>
    {!result && <p className="analysis-tabs__pending">Detailed evidence will appear when this workflow returns its report.</p>}
    {active === "Structure" && <StructureTab files={files} />}
    {active === "Quality" && <QualityTab summary={result?.final_report.quality_summary} findings={result?.findings ?? []} />}
    {active === "Bug & Resource" && <BugResourceTab result={result} />}
    {active === "Trace" && <TraceabilityTab result={result} />}
    {active === "Tools" && <ToolsTab result={result} />}
  </section>;
}