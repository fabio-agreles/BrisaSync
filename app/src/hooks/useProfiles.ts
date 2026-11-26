import { useCallback, useState } from "react";
import { api, errorMessage } from "../lib/bridge";
import { t as tr } from "../lib/i18n";
import type { Profile, Snapshot } from "../lib/types";

type NotifyFn = (message: string, kind?: "info" | "ok" | "error") => void;

export function useProfiles(
  notify: NotifyFn,
  setSnapshot: (snapshot: Snapshot) => void,
) {
  const [profiles, setProfiles] = useState<Profile[]>([]);

  const refreshProfiles = useCallback(async () => {
    setProfiles(await api.listProfiles());
  }, []);

  const syncProfile = useCallback(
    async (id: string, resync = false) => {
      try {
        setSnapshot(await api.startSync(id, resync));
        notify(tr("Sincronização iniciada."), "ok");
      } catch (cause) {
        notify(errorMessage(cause), "error");
      }
    },
    [notify, setSnapshot],
  );

  const updateProfile = useCallback(
    async (profile: Profile) => {
      try {
        const updated = await api.updateProfile(profile);
        setProfiles((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
        notify(
          updated.enabled ? tr("Pasta ativada.") : tr("Pasta desativada."),
          "ok",
        );
      } catch (cause) {
        notify(errorMessage(cause), "error");
      }
    },
    [notify],
  );

  const deleteProfile = useCallback(
    async (id: string) => {
      try {
        await api.deleteProfile(id);
        await refreshProfiles();
        notify(tr("Pasta removida."), "ok");
      } catch (cause) {
        notify(errorMessage(cause), "error");
      }
    },
    [notify, refreshProfiles],
  );

  const addFolder = useCallback(
    async (input: { account: string; remotePath: string; localPath: string }) => {
      const profile = await api.createProfile({ ...input, enabled: true });
      setProfiles((items) => [...items, profile]);
      notify(tr("Pasta adicionada. Sincronizando pela primeira vez…"), "ok");
      void syncProfile(profile.id, true);
    },
    [notify, syncProfile],
  );

  return {
    profiles,
    setProfiles,
    refreshProfiles,
    syncProfile,
    updateProfile,
    deleteProfile,
    addFolder,
  };
}
