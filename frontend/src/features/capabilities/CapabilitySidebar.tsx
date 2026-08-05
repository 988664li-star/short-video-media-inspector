import { useEffect, useRef } from "react";
import { LockKeyhole } from "lucide-react";

import { CAPABILITIES, CAPABILITY_GROUPS, type CapabilityDefinition, type CapabilityId } from "./catalog";


interface CapabilitySidebarProps {
  selectedId: CapabilityId;
  hasLogin: boolean;
  onSelect: (definition: CapabilityDefinition) => void;
}

export function CapabilitySidebar({ selectedId, hasLogin, onSelect }: CapabilitySidebarProps) {
  const activeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    activeButton.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [selectedId]);

  return (
    <aside className="capability-sidebar scroll-surface" aria-label="抖音能力列表">
      {CAPABILITY_GROUPS.map((group) => (
        <section key={group} className="capability-group">
          <h3>{group}</h3>
          {CAPABILITIES.filter((item) => item.group === group).map((item) => (
            <button
              ref={selectedId === item.id ? activeButton : undefined}
              key={item.id}
              type="button"
              className={`capability-link ${selectedId === item.id ? "capability-link--active" : ""}`}
              onClick={() => onSelect(item)}
            >
              <span>{item.title}</span>
              {item.loginRequired ? <LockKeyhole aria-label={hasLogin ? "已登录" : "需要 Cookie"} /> : null}
            </button>
          ))}
        </section>
      ))}
    </aside>
  );
}
