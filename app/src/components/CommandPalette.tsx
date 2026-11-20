import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "./Icons";
import { useT } from "../lib/i18n";

export type PaletteAction = {
  id: string;
  label: string;
  group: string;
  icon: IconName;
  shortcut?: string;
  run: () => void;
};

export function CommandPalette({
  open,
  onClose,
  actions,
}: {
  open: boolean;
  onClose: () => void;
  actions: PaletteAction[];
}) {
  const t = useT();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return actions;
    return actions.filter((action) =>
      `${action.label} ${action.group}`.toLowerCase().includes(needle),
    );
  }, [actions, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setIndex(0);
    const timer = setTimeout(() => inputRef.current?.focus(), 20);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    setIndex(0);
  }, [query]);

  if (!open) return null;

  const groups: { name: string; items: PaletteAction[] }[] = [];
  for (const action of filtered) {
    let group = groups.find((item) => item.name === action.group);
    if (!group) {
      group = { name: action.group, items: [] };
      groups.push(group);
    }
    group.items.push(action);
  }

  const run = (action: PaletteAction) => {
    onClose();
    action.run();
  };

  return (
    <div
      className="overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label={t("Paleta de comandos")}>
        <div className="palette-input">
          <Icon name="search" size={18} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") onClose();
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setIndex((current) => Math.min(current + 1, filtered.length - 1));
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setIndex((current) => Math.max(current - 1, 0));
              }
              if (event.key === "Enter" && filtered[index]) {
                event.preventDefault();
                run(filtered[index]);
              }
            }}
            placeholder={t("Buscar ações…")}
            aria-label={t("Buscar ações")}
          />
          <span className="kbd">Esc</span>
        </div>
        <div className="palette-list">
          {filtered.length === 0 ? (
            <div className="palette-empty">{t("Nenhuma ação encontrada.")}</div>
          ) : (
            groups.map((group) => (
              <div key={group.name}>
                <div className="palette-group">{group.name}</div>
                {group.items.map((action) => {
                  const position = filtered.indexOf(action);
                  return (
                    <button
                      key={action.id}
                      className={`palette-item ${position === index ? "active" : ""}`}
                      onMouseEnter={() => setIndex(position)}
                      onClick={() => run(action)}
                    >
                      <Icon name={action.icon} size={16} />
                      <span>{action.label}</span>
                      {action.shortcut ? (
                        <span className="shortcut kbd">{action.shortcut}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
