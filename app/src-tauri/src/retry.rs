//! Quando uma sincronização falha por um motivo que costuma se resolver sozinho
//! (rede caindo, cota momentânea, erro 5xx do provedor), o app tenta de novo com
//! espera crescente em vez de exigir um clique do usuário.
//!
//! Falhas de configuração — senha/token inválido, pasta sem permissão, caminho
//! errado — nunca são repetidas: repetir só adia o aviso de que algo precisa ser
//! corrigido.

use std::time::Duration;

/// Total de execuções extras (3 = a original + 3 novas tentativas).
pub const MAX_ATTEMPTS: u32 = 3;

const TRANSIENT: &[&str] = &[
    // rede
    "connection refused",
    "connection reset",
    "connection timed out",
    "broken pipe",
    "no such host",
    "network is unreachable",
    "i/o timeout",
    "tls handshake",
    "context deadline exceeded",
    "eof",
    "temporary failure",
    "temporarily unavailable",
    "transport is closing",
    "stream error",
    // cota e limites
    "rate limit",
    "ratelimitexceeded",
    "userratelimitexceeded",
    "quota exceeded",
    "too many requests",
    "try again",
    "backoff",
    // servidor
    "error 500",
    "error 502",
    "error 503",
    "error 504",
    "internalerror",
    "backenderror",
    "service unavailable",
];

/// A mensagem de erro do rclone indica uma falha transitória?
pub fn is_transient(error: &str) -> bool {
    let lower = error.to_lowercase();
    if lower.trim().is_empty() {
        return false;
    }
    TRANSIENT.iter().any(|needle| lower.contains(needle))
}

/// Espera antes da tentativa `attempt` (1 = primeira repetição): 15 s, 60 s, 180 s.
pub fn backoff(attempt: u32) -> Duration {
    let seconds = match attempt {
        0 | 1 => 15,
        2 => 60,
        _ => 180,
    };
    Duration::from_secs(seconds)
}

/// Decide se (e quando) vale repetir uma sincronização que terminou.
///
/// `used` é quantas novas tentativas este perfil já consumiu; devolve a tentativa
/// e a espera, ou `None` quando não deve repetir (deu certo, retry desligado,
/// erro definitivo ou limite atingido).
pub fn next_attempt(
    success: bool,
    error: &str,
    auto_retry: bool,
    used: u32,
) -> Option<(u32, Duration)> {
    if success || !auto_retry || !is_transient(error) {
        return None;
    }
    let attempt = used + 1;
    if attempt > MAX_ATTEMPTS {
        return None;
    }
    Some((attempt, backoff(attempt)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reconhece_falhas_de_rede() {
        assert!(is_transient(
            "couldn't list directory: Get \"https://www.googleapis.com/drive/v3/files\": dial tcp: lookup www.googleapis.com: no such host"
        ));
        assert!(is_transient("connection reset by peer"));
        assert!(is_transient("Post \"http://127.0.0.1:34567/sync/bisync\": EOF"));
        assert!(is_transient("context deadline exceeded"));
    }

    #[test]
    fn reconhece_limites_e_erros_do_servidor() {
        assert!(is_transient(
            "googleapi: Error 503: The service is currently unavailable., backendError"
        ));
        assert!(is_transient(
            "googleapi: Error 403: User Rate Limit Exceeded., userRateLimitExceeded"
        ));
        assert!(is_transient("HTTP error 429 (Too Many Requests)"));
    }

    #[test]
    fn nao_repete_erros_de_configuracao() {
        assert!(!is_transient(""));
        assert!(!is_transient(
            "failed to open source object: directory not found"
        ));
        assert!(!is_transient(
            "couldn't fetch token: invalid_grant: Token has been expired or revoked."
        ));
        assert!(!is_transient("permission denied"));
        assert!(!is_transient("the source and destination are the same"));
    }

    #[test]
    fn decide_quando_repetir() {
        let erro = "dial tcp: connection refused";
        assert_eq!(next_attempt(true, erro, true, 0), None);
        assert_eq!(next_attempt(false, erro, false, 0), None);
        assert_eq!(next_attempt(false, "permission denied", true, 0), None);
        assert_eq!(
            next_attempt(false, erro, true, 0),
            Some((1, Duration::from_secs(15)))
        );
        assert_eq!(
            next_attempt(false, erro, true, 2),
            Some((3, Duration::from_secs(180)))
        );
        // já usou as três: para de tentar e deixa o erro visível
        assert_eq!(next_attempt(false, erro, true, 3), None);
        assert_eq!(next_attempt(false, erro, true, 9), None);
    }

    #[test]
    fn espera_cresce_e_para_de_crescer() {
        let waits: Vec<u64> = (1..=4).map(|attempt| backoff(attempt).as_secs()).collect();
        assert_eq!(waits, vec![15, 60, 180, 180]);
        assert!(waits.windows(2).all(|pair| pair[0] <= pair[1]));
    }
}
