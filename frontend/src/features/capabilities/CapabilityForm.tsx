import { LoaderCircle, Zap } from "lucide-react";

import { FIELD_META, type CapabilityDefinition, type CapabilityField } from "./catalog";
import type { CapabilityValues } from "./useCapabilityRunner";


interface CapabilityFormProps {
  definition: CapabilityDefinition;
  values: CapabilityValues;
  loading: boolean;
  hasLogin: boolean;
  onChange: (field: CapabilityField, value: string) => void;
}

export function CapabilityForm({ definition, values, loading, hasLogin, onChange }: CapabilityFormProps) {
  const requiredFields = definition.fields.filter((field) => field !== "userId");
  const missingInput = requiredFields.some((field) => !values[field].trim());
  const loginBlocked = Boolean(definition.loginRequired && !hasLogin);

  return (
    <div className="capability-form">
      <div className="capability-form__heading">
        <div>
          <span className="capability-eyebrow">{definition.group}</span>
          <h2>{definition.title}</h2>
          <p>{definition.description}</p>
        </div>
        <span className={`status-chip ${definition.loginRequired && hasLogin ? "status-chip--active" : ""}`}>
          {definition.loginRequired ? (hasLogin ? "登录能力可用" : "需要登录 Cookie") : "游客模式可用"}
        </span>
      </div>
      {definition.fields.length ? (
        <div className="capability-fields">
          {definition.fields.map((field) => (
            <label key={field}>
              <span>{FIELD_META[field].label}</span>
              <input
                value={values[field]}
                onChange={(event) => onChange(field, event.target.value)}
                placeholder={FIELD_META[field].placeholder}
                spellCheck={false}
              />
            </label>
          ))}
        </div>
      ) : (
        <p className="capability-no-fields">此能力无需额外参数，直接调用即可。</p>
      )}
      {loginBlocked ? <p className="capability-login-note">请在上方 Cookie 面板载入登录态后再调用此能力。</p> : null}
      {!loginBlocked ? (
        <div className={`capability-auto-status ${loading ? "capability-auto-status--loading" : ""}`} role="status">
          {loading ? <LoaderCircle className="spin" /> : <Zap />}
          <span>{missingInput ? "补全必填参数后自动获取" : loading ? "正在自动获取数据" : "切换能力或修改参数后自动获取"}</span>
        </div>
      ) : null}
    </div>
  );
}
