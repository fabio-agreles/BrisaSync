import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../lib/bridge";
import { t as tr } from "../lib/i18n";
import type { EngineStatus, Profile, Snapshot } from "../lib/types";

const EMPTY_SNAPSHOT: Snapshot = {
  engineReady: false,
  paused: false,
  running: false,
  speed: 0,
  bytes: 0,
  totalBytes: 0,
  errors: 0,
  transfers: [],
  jobs: 0,
};

type NotifyFn = (message: string, kind?: "info" | "ok" | "error") => void;

export function useEngineStatus(profiles: Profile[], notify: NotifyFn) {
  const [engine, setEngine] = useState<EngineStatus | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY_SNAPSHOT);

  useEffect(() => {
    const timer = setInterval(() => {
      void api
        .syncStatus()
        .then(setSnapshot)
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  const syncAll = useCallback(async () => {
    if (snapshot.paused) {
      try {
        setSnapshot(await api.setPaused(false));
        notify(tr("Sincronização retomada."), "ok");
      } catch (cause) {
        notify(errorMessage(cause), "error");
      }
      return;
    }
    const targets = profiles.filter((profile) => profile.enabled);
    if (targets.length === 0) {
      notify(tr("Adicione uma pasta antes de sincronizar."), "info");
      return;
    }
    const results = await Promise.allSettled(
      targets.map((profile) => api.startSync(profile.id, profile.resyncNeeded)),
    );
    const failure = results.find((result) => result.status === "rejected");
    if (failure && failure.status === "rejected") {
      notify(errorMessage(failure.reason), "error");
    } else {
      notify(tr("Sincronização iniciada."), "ok");
    }
  }, [notify, profiles, snapshot.paused]);

  const togglePause = useCallback(async () => {
    try {
      setSnapshot(await api.setPaused(!snapshot.paused));
      notify(
        snapshot.paused ? tr("Sincronização retomada.") : tr("Sincronização pausada."),
        "ok",
      );
    } catch (cause) {
      notify(errorMessage(cause), "error");
    }
  }, [notify, snapshot.paused]);

  const pauseFor = useCallback(
    async (minutes: number) => {
      try {
        setSnapshot(await api.setPaused(true, minutes));
        notify(tr("Sincronização pausada."), "ok");
      } catch (cause) {
        notify(errorMessage(cause), "error");
      }
    },
    [notify],
  );

  return {
    engine,
    setEngine,
    snapshot,
    setSnapshot,
    syncAll,
    togglePause,
    pauseFor,
  };
}
