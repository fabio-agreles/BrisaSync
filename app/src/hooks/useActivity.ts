import { useCallback, useState } from "react";
import { api, errorMessage } from "../lib/bridge";
import { t as tr } from "../lib/i18n";
import type { ActivityEntry } from "../lib/types";

type NotifyFn = (message: string, kind?: "info" | "ok" | "error") => void;

export function useActivity(notify: NotifyFn) {
  const [activity, setActivity] = useState<ActivityEntry[]>([]);

  const refreshActivity = useCallback(async () => {
    setActivity(await api.recentActivity());
  }, []);

  const clearActivity = useCallback(async () => {
    try {
      await api.clearActivity();
      setActivity([]);
      notify(tr("Histórico de atividade limpo."), "ok");
    } catch (cause) {
      notify(errorMessage(cause), "error");
      void refreshActivity();
    }
  }, [notify, refreshActivity]);

  return { activity, setActivity, refreshActivity, clearActivity };
}
