import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/bridge";
import type { AccountUsage } from "../lib/types";

export function useUsage() {
  const [usage, setUsage] = useState<AccountUsage[]>([]);

  const refreshUsage = useCallback(async () => {
    try {
      setUsage(await api.accountUsage());
    } catch {
      // Silencioso: o cartão de armazenamento segue com o que já foi lido.
    }
  }, []);

  useEffect(() => {
    // A primeira leitura pode cair no momento em que o rclone está subindo: uma
    // segunda tentativa logo depois evita o cartão vazio por até um minuto.
    const primeira = setTimeout(() => void refreshUsage(), 3000);
    const timer = setInterval(() => void refreshUsage(), 30_000);
    return () => {
      clearTimeout(primeira);
      clearInterval(timer);
    };
  }, [refreshUsage]);

  return { usage, setUsage, refreshUsage };
}
