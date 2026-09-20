import { AnalysisProgress, DEFAULT_STEPS, type ProgressStep, type StepStatus } from "../components/AnalysisProgress";

interface AnalysisPageProps {
  /** Index of the step currently in progress, or DEFAULT_STEPS.length once done. */
  activeStepIndex: number;
  progressMessage?: string;
}

function buildSteps(activeStepIndex: number): ProgressStep[] {
  return DEFAULT_STEPS.map((label, i) => {
    let status: StepStatus = "pending";
    if (i < activeStepIndex) status = "done";
    if (i === activeStepIndex) status = "active";
    return { label, status };
  });
}

export function AnalysisPage({ activeStepIndex, progressMessage }: AnalysisPageProps) {
  return (
    <section className="page page--analysis analysis-shell">
      <div className="kicker">Live workflow <span>02 / 04</span></div>
      <h1>Reading the shape<br /><em>of your code.</em></h1>
      {progressMessage && <p className="analysis-pulse"><i />{progressMessage}</p>}
      <AnalysisProgress steps={buildSteps(activeStepIndex)} />
      <div className="analysis-contract"><span>Frontend</span><i>→</i><strong>Orchestrator</strong><i>→</i><span>Code Quality Agent</span><small>Ruff · Pylint · Radon</small></div>
      <p className="analysis-pulse"><i /> Findings and evidence are being assembled in the background</p>
    </section>
  );
}
