//! Detecção rápida de alterações remotas via APIs de mudanças (Google Drive
//! Changes API e Microsoft Graph OneDrive Delta API).
//!
//! Em vez de esperar o intervalo completo (`syncIntervalMin`) para descobrir que
//! um arquivo mudou na nuvem, consultamos apenas o token de alterações a cada
//! 30 segundos. Se não houver novidade, nenhuma tarefa `bisync` é disparada.

use crate::{commands::dump_da_configuracao, oauth, state::AppState};
use reqwest::StatusCode;
use serde_json::Value;
use std::{
    collections::{HashMap, HashSet},
    time::{Duration, Instant},
};

const REMOTE_POLL_INTERVAL: Duration = Duration::from_secs(30);

#[derive(Default)]
pub struct RemoteWatcher {
    /// Último `pageToken` (Drive) ou `@odata.deltaLink` (OneDrive) por conta.
    tokens: HashMap<String, String>,
    /// `access_token` renovado em memória quando o token do `rclone.conf` expira (401).
    refreshed_tokens: HashMap<String, String>,
    last_check: Option<Instant>,
}

impl RemoteWatcher {
    /// Verifica se alguma das contas ativas teve alterações na nuvem desde a
    /// última consulta. Retorna os nomes das contas com mudanças detectadas.
    pub async fn check_accounts(
        &mut self,
        state: &AppState,
        active_accounts: &HashSet<String>,
    ) -> HashSet<String> {
        let mut changed = HashSet::new();
        if active_accounts.is_empty() {
            return changed;
        }
        if let Some(last) = self.last_check {
            if last.elapsed() < REMOTE_POLL_INTERVAL {
                return changed;
            }
        }
        self.last_check = Some(Instant::now());

        let Ok(dump) = dump_da_configuracao(state).await else {
            return changed;
        };

        let Ok(client) = reqwest::Client::builder()
            .no_proxy()
            .timeout(Duration::from_secs(10))
            .build()
        else {
            return changed;
        };

        let (id_do_app, segredo_do_app) = oauth::do_build().unwrap_or_default();

        for account in active_accounts {
            let Some(config) = dump.get(account) else {
                continue;
            };
            let provider = config
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or_default();
            if provider == "webdav" {
                if self.check_nextcloud(state, account).await {
                    changed.insert(account.clone());
                }
                continue;
            }
            if provider != "drive" && provider != "onedrive" && provider != "dropbox" {
                continue;
            }
            let Some(access_token) = self
                .refreshed_tokens
                .get(account)
                .cloned()
                .or_else(|| extract_access_token(config))
            else {
                continue;
            };

            let has_changes = match provider {
                "drive" => {
                    self.check_drive(
                        &client,
                        account,
                        &access_token,
                        config,
                        &id_do_app,
                        &segredo_do_app,
                    )
                    .await
                }
                "onedrive" => {
                    self.check_onedrive(&client, account, &access_token, config)
                        .await
                }
                "dropbox" => {
                    self.check_dropbox(&client, account, &access_token, config)
                        .await
                }
                _ => false,
            };
            if has_changes {
                changed.insert(account.clone());
            }
        }

        changed
    }

    async fn refresh_for_account(
        &mut self,
        account: &str,
        provider: &str,
        config: &Value,
        id_do_app: &str,
        segredo_do_app: &str,
    ) -> Option<String> {
        let raw = config.get("token").and_then(Value::as_str)?;
        let token: Value = serde_json::from_str(raw).ok()?;
        let novo = match provider {
            "drive" => {
                let client_id = config
                    .get("client_id")
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty())
                    .unwrap_or(id_do_app);
                let client_secret = config
                    .get("client_secret")
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty())
                    .unwrap_or(segredo_do_app);
                crate::login_google::renovar_token(&token, client_id, client_secret).await
            }
            "onedrive" => {
                let client_id = config.get("client_id").and_then(Value::as_str);
                crate::login_microsoft::renovar_token(&token, client_id).await
            }
            "dropbox" => {
                let client_id = config.get("client_id").and_then(Value::as_str);
                let client_secret = config.get("client_secret").and_then(Value::as_str);
                crate::login_dropbox::renovar_token(&token, client_id, client_secret).await
            }
            _ => None,
        }?;
        self.refreshed_tokens
            .insert(account.to_string(), novo.clone());
        Some(novo)
    }

    async fn check_drive(
        &mut self,
        client: &reqwest::Client,
        account: &str,
        access_token: &str,
        config: &Value,
        id_do_app: &str,
        segredo_do_app: &str,
    ) -> bool {
        let Some(current_token) = self.tokens.get(account).cloned() else {
            let url = "https://www.googleapis.com/drive/v3/changes/startPageToken";
            let mut resp = match client.get(url).bearer_auth(access_token).send().await {
                Ok(r) => r,
                Err(_) => return false,
            };
            if resp.status() == StatusCode::UNAUTHORIZED {
                if let Some(novo) = self
                    .refresh_for_account(account, "drive", config, id_do_app, segredo_do_app)
                    .await
                {
                    if let Ok(r) = client.get(url).bearer_auth(&novo).send().await {
                        resp = r;
                    }
                }
            }
            if resp.status().is_success() {
                if let Ok(body) = resp.json::<Value>().await {
                    if let Some(token) = body.get("startPageToken").and_then(Value::as_str) {
                        self.tokens.insert(account.to_string(), token.to_string());
                    }
                }
            }
            return false;
        };

        let url = format!(
            "https://www.googleapis.com/drive/v3/changes?pageToken={current_token}&fields=newStartPageToken,nextPageToken,changes(fileId)&pageSize=10"
        );
        let mut resp = match client.get(&url).bearer_auth(access_token).send().await {
            Ok(r) => r,
            Err(_) => return false,
        };
        if resp.status() == StatusCode::UNAUTHORIZED {
            if let Some(novo) = self
                .refresh_for_account(account, "drive", config, id_do_app, segredo_do_app)
                .await
            {
                if let Ok(r) = client.get(&url).bearer_auth(&novo).send().await {
                    resp = r;
                }
            }
        }
        if !resp.status().is_success() {
            return false;
        }
        let Ok(body) = resp.json::<Value>().await else {
            return false;
        };

        let (has_changes, next_token) = parse_drive_changes(&body);
        if let Some(token) = next_token {
            self.tokens.insert(account.to_string(), token);
        }
        has_changes
    }

    async fn check_onedrive(
        &mut self,
        client: &reqwest::Client,
        account: &str,
        access_token: &str,
        config: &Value,
    ) -> bool {
        let Some(delta_link) = self.tokens.get(account).cloned() else {
            let url = "https://graph.microsoft.com/v1.0/me/drive/root/delta?token=latest";
            let mut resp = match client.get(url).bearer_auth(access_token).send().await {
                Ok(r) => r,
                Err(_) => return false,
            };
            if resp.status() == StatusCode::UNAUTHORIZED {
                if let Some(novo) = self
                    .refresh_for_account(account, "onedrive", config, "", "")
                    .await
                {
                    if let Ok(r) = client.get(url).bearer_auth(&novo).send().await {
                        resp = r;
                    }
                }
            }
            if resp.status().is_success() {
                if let Ok(body) = resp.json::<Value>().await {
                    if let Some(link) = body.get("@odata.deltaLink").and_then(Value::as_str) {
                        self.tokens.insert(account.to_string(), link.to_string());
                    }
                }
            }
            return false;
        };

        let mut resp = match client.get(&delta_link).bearer_auth(access_token).send().await {
            Ok(r) => r,
            Err(_) => return false,
        };
        if resp.status() == StatusCode::UNAUTHORIZED {
            if let Some(novo) = self
                .refresh_for_account(account, "onedrive", config, "", "")
                .await
            {
                if let Ok(r) = client.get(&delta_link).bearer_auth(&novo).send().await {
                    resp = r;
                }
            }
        }
        if !resp.status().is_success() {
            return false;
        }
        let Ok(body) = resp.json::<Value>().await else {
            return false;
        };

        let (has_changes, next_link) = parse_onedrive_delta(&body);
        if let Some(link) = next_link {
            self.tokens.insert(account.to_string(), link);
        }
        has_changes
    }

    async fn check_dropbox(
        &mut self,
        client: &reqwest::Client,
        account: &str,
        access_token: &str,
        config: &Value,
    ) -> bool {
        let Some(cursor) = self.tokens.get(account).cloned() else {
            let url = "https://api.dropboxapi.com/2/files/list_folder/get_latest_cursor";
            let payload = serde_json::json!({ "path": "", "recursive": true });
            let mut resp = match client
                .post(url)
                .bearer_auth(access_token)
                .json(&payload)
                .send()
                .await
            {
                Ok(r) => r,
                Err(_) => return false,
            };
            if resp.status() == StatusCode::UNAUTHORIZED {
                if let Some(novo) = self
                    .refresh_for_account(account, "dropbox", config, "", "")
                    .await
                {
                    if let Ok(r) = client
                        .post(url)
                        .bearer_auth(&novo)
                        .json(&payload)
                        .send()
                        .await
                    {
                        resp = r;
                    }
                }
            }
            if resp.status().is_success() {
                if let Ok(body) = resp.json::<Value>().await {
                    if let Some(c) = body.get("cursor").and_then(Value::as_str) {
                        self.tokens.insert(account.to_string(), c.to_string());
                    }
                }
            }
            return false;
        };

        let url = "https://api.dropboxapi.com/2/files/list_folder/continue";
        let payload = serde_json::json!({ "cursor": cursor });
        let mut resp = match client
            .post(url)
            .bearer_auth(access_token)
            .json(&payload)
            .send()
            .await
        {
            Ok(r) => r,
            Err(_) => return false,
        };
        if resp.status() == StatusCode::UNAUTHORIZED {
            if let Some(novo) = self
                .refresh_for_account(account, "dropbox", config, "", "")
                .await
            {
                if let Ok(r) = client
                    .post(url)
                    .bearer_auth(&novo)
                    .json(&payload)
                    .send()
                    .await
                {
                    resp = r;
                }
            }
        }
        if !resp.status().is_success() {
            return false;
        }
        let Ok(body) = resp.json::<Value>().await else {
            return false;
        };
        if let Some(next_cursor) = body.get("cursor").and_then(Value::as_str) {
            self.tokens
                .insert(account.to_string(), next_cursor.to_string());
        }
        body.get("entries")
            .and_then(Value::as_array)
            .map(|entries| !entries.is_empty())
            .unwrap_or(false)
    }

    async fn check_nextcloud(&mut self, state: &AppState, account: &str) -> bool {
        let Ok(resp) = state
            .rclone
            .call(
                "operations/list",
                serde_json::json!({ "fs": format!("{account}:"), "remote": "" }),
                Duration::from_secs(10),
            )
            .await
        else {
            return false;
        };
        let Some(list) = resp.get("list").and_then(Value::as_array) else {
            return false;
        };
        let mut fingerprint = String::new();
        for item in list {
            let name = item.get("Name").and_then(Value::as_str).unwrap_or_default();
            let mod_time = item
                .get("ModTime")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let size = item.get("Size").and_then(Value::as_i64).unwrap_or(0);
            fingerprint.push_str(&format!("{name}|{mod_time}|{size};"));
        }
        match self.tokens.get(account) {
            None => {
                self.tokens.insert(account.to_string(), fingerprint);
                false
            }
            Some(prev) if prev == &fingerprint => false,
            Some(_) => {
                self.tokens.insert(account.to_string(), fingerprint);
                true
            }
        }
    }
}

fn extract_access_token(config: &Value) -> Option<String> {
    let raw = config.get("token").and_then(Value::as_str)?;
    let parsed: Value = serde_json::from_str(raw).ok()?;
    parsed
        .get("access_token")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
        .map(ToString::to_string)
}

pub(crate) fn parse_drive_changes(body: &Value) -> (bool, Option<String>) {
    let has_changes = body
        .get("changes")
        .and_then(Value::as_array)
        .map(|arr| !arr.is_empty())
        .unwrap_or(false);
    let next_token = body
        .get("newStartPageToken")
        .or_else(|| body.get("nextPageToken"))
        .and_then(Value::as_str)
        .map(ToString::to_string);
    (has_changes, next_token)
}

pub(crate) fn parse_onedrive_delta(body: &Value) -> (bool, Option<String>) {
    let has_changes = body
        .get("value")
        .and_then(Value::as_array)
        .map(|arr| !arr.is_empty())
        .unwrap_or(false);
    let next_link = body
        .get("@odata.deltaLink")
        .or_else(|| body.get("@odata.nextLink"))
        .and_then(Value::as_str)
        .map(ToString::to_string);
    (has_changes, next_link)
}

#[cfg(test)]
mod tests {
    use super::{extract_access_token, parse_drive_changes, parse_onedrive_delta};
    use serde_json::json;

    #[test]
    fn extrai_access_token_do_rclone_conf() {
        let cfg = json!({
            "type": "drive",
            "token": r#"{"access_token":"ya29.abc","token_type":"Bearer"}"#
        });
        assert_eq!(extract_access_token(&cfg), Some("ya29.abc".to_string()));

        let sem_token = json!({ "type": "drive" });
        assert_eq!(extract_access_token(&sem_token), None);
    }

    #[test]
    fn interpreta_resposta_de_mudancas_do_drive() {
        let vazio = json!({
            "newStartPageToken": "105",
            "changes": []
        });
        assert_eq!(parse_drive_changes(&vazio), (false, Some("105".to_string())));

        let com_mudanca = json!({
            "newStartPageToken": "106",
            "changes": [{ "fileId": "1abc" }]
        });
        assert_eq!(
            parse_drive_changes(&com_mudanca),
            (true, Some("106".to_string()))
        );
    }

    #[test]
    fn interpreta_resposta_delta_do_onedrive() {
        let vazio = json!({
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/drive/root/delta?token=2",
            "value": []
        });
        assert_eq!(
            parse_onedrive_delta(&vazio),
            (
                false,
                Some("https://graph.microsoft.com/v1.0/me/drive/root/delta?token=2".to_string())
            )
        );

        let com_mudanca = json!({
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/drive/root/delta?token=3",
            "value": [{ "id": "item1" }]
        });
        assert_eq!(
            parse_onedrive_delta(&com_mudanca),
            (
                true,
                Some("https://graph.microsoft.com/v1.0/me/drive/root/delta?token=3".to_string())
            )
        );
    }
}
