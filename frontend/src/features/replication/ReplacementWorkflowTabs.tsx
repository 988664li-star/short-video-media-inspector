import { Check, LockKeyhole } from "lucide-react";

export type ReplacementWorkflowStep = 1 | 2 | 3 | 4;

const STEPS: Array<{ id: ReplacementWorkflowStep; label: string }> = [
  { id: 1, label: "识别视频" },
  { id: 2, label: "选择商品" },
  { id: 3, label: "生成锚点" },
  { id: 4, label: "检查生成" },
];

interface ReplacementWorkflowTabsProps {
  activeStep: ReplacementWorkflowStep;
  availableStep: ReplacementWorkflowStep;
  onSelect: (step: ReplacementWorkflowStep) => void;
}

export function ReplacementWorkflowTabs({
  activeStep,
  availableStep,
  onSelect,
}: ReplacementWorkflowTabsProps) {
  return (
    <nav className="replacement-workflow-tabs" aria-label="商品替换步骤">
      {STEPS.map((step) => {
        const available = step.id <= availableStep;
        const completed = step.id < activeStep && available;
        const active = step.id === activeStep;
        return (
          <button
            className={`replacement-workflow-tabs__item${active ? " replacement-workflow-tabs__item--active" : ""}`}
            key={step.id}
            type="button"
            disabled={!available}
            aria-current={active ? "step" : undefined}
            onClick={() => onSelect(step.id)}
          >
            <span className="replacement-workflow-tabs__index">
              {completed ? <Check aria-label="已完成" /> : step.id}
            </span>
            <span>{step.label}</span>
            {!available ? <LockKeyhole aria-label="尚未完成上一步" /> : null}
          </button>
        );
      })}
    </nav>
  );
}
