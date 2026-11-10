"""Catálogo centralizado de traduções para Português (Brasil) e English.

Regras de integridade:
- Nomes de arquivos, caminhos do sistema, IDs remotos, endereços de e-mail e dados do Pix
  (beneficiário, chave e payload) permanecem estritamente inalterados.
- Todas as chaves devem ter paridade exata em pt_BR e en.
"""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, dict[str, str]] = {
    "pt_BR": {
        # Aplicação e Navegação
        "app_title": "BrisaSync",
        "app_tagline": "Sincronizador bidirecional nativo e seguro para Linux Desktop com Google Drive",
        "nav_overview": "Visão geral",
        "nav_folders": "Pastas",
        "nav_activity": "Atividade",
        "nav_settings": "Ajustes",
        "nav_help": "Ajuda",
        "nav_about": "Sobre",
        "nav_connecting": "Conectando...",

        # Cabeçalho
        "header_title": "BrisaSync",
        "header_subtitle_overview": "O estado das suas pastas em uma olhada",
        "header_subtitle_folders": "Escolha o que fica igual nos dois lados",
        "header_subtitle_activity": "Registro detalhado das sincronizações e eventos",
        "header_subtitle_settings": "Contas, sincronização e preferências do sistema",
        "header_badge_connected": "Conectado",
        "header_badge_not_connected": "Não conectado",
        "header_badge_paused": "Pausado",
        "header_badge_attention": "Atenção necessária",
        "header_badge_syncing": "Sincronizando",
        "header_badge_verifying": "Verificando",
        "header_badge_waiting": "Aguardando",
        "header_btn_configure": "Configurar",
        "header_btn_sync_now": "Sincronizar",
        "header_btn_options": "Opções ▾",

        # Menu Opções
        "menu_account_info": "Conta: {email}",
        "menu_no_account": "Nenhuma conta vinculada",
        "menu_pause_sync": "Pausar Sincronização Automática",
        "menu_resume_sync": "Retomar Sincronização Automática",
        "menu_open_local_folder": "Abrir Pasta Local",
        "menu_view_diagnostics": "Diagnóstico de Dependências...",
        "menu_about": "Sobre o BrisaSync...",
        "menu_disconnect_account": "Desconectar Conta Google...",
        "menu_exit": "Sair do BrisaSync…",

        # Hero Banner
        "hero_title_unconfigured": "Configuração Inicial do BrisaSync",
        "hero_subtitle_unconfigured": "Mantenha seus arquivos sincronizados e disponíveis offline.",
        "hero_title_healthy": "Sincronização em Operação",
        "hero_subtitle_healthy": "Suas pastas locais e o Google Drive estão em perfeita harmonia.",
        "hero_title_paused": "Sincronização Pausada",
        "hero_subtitle_paused": "A sincronização periódica está suspensa temporariamente.",
        "hero_title_attention": "Atenção Necessária",
        "hero_subtitle_attention": "Verifique as pendências abaixo para retomar a sincronização.",
        "hero_title_offline": "Sem Conexão de Rede",
        "hero_subtitle_offline": "Aguardando restabelecimento da conexão com a internet.",
        "hero_title_syncing": "Sincronizando...",
        "hero_subtitle_syncing": "Transferindo alterações entre o Google Drive e o seu computador.",
        "hero_title_verifying": "Verificando...",
        "hero_subtitle_verifying": "Conferindo integridade dos arquivos e conectividade.",

        # Ações do Hero
        "hero_action_connect": "Conectar Conta Google",
        "hero_action_setup_folders": "Configurar Pastas",
        "hero_action_sync_now": "Sincronizar Agora",
        "hero_action_pause": "Pausar Sincronização",
        "hero_action_resume": "Retomar Sincronização",
        "hero_action_resolve_conflicts": "Revisar Conflitos",
        "hero_action_reconnect": "Reconectar Conta",

        # Estatísticas do Hero
        "hero_stat_speed": "VELOCIDADE",
        "hero_stat_transferred": "TRANSFERIDO",
        "hero_stat_active_folders": "PASTAS ATIVAS",

        # Assistente Inicial (Wizard)
        "wizard_step1_title": "1. Conectar conta Google",
        "wizard_step1_desc": "Conecte sua conta do Google Drive para iniciar a sincronização com este computador. Seu navegador padrão será aberto para autorizar com segurança via Google OAuth.",
        "wizard_step1_not_connected": "Nenhuma conta Google conectada no momento.",
        "wizard_step1_connected": "Conta conectada com sucesso: {email}",
        "wizard_step2_title": "2. Configurar pastas de sincronização",
        "wizard_step2_desc": "Selecione uma pasta no seu Google Drive e uma pasta local dedicada. A pasta local deve estar vazia para estabelecer a linha de base segura.",
        "wizard_step3_title": "3. Primeira sincronização segura",
        "wizard_step3_desc": "A sincronização inicial baixará seus arquivos da nuvem e criará a base de comparação segura sem risco de perdas.",

        # Aba Pastas
        "folders_card_title": "Configuração de Pastas",
        "folders_card_subtitle": "Escolha o que fica igual nos dois lados",
        "folders_remote_label": "Pasta Remota no Google Drive (Identificada por ID Imutável):",
        "folders_remote_list_btn": "Listar Pastas",
        "folders_remote_new_btn": "Nova pasta",
        "folders_remote_status_selected": "Status da pasta remota: [SELECIONADA] {name} (ID: {id})",
        "folders_remote_status_none": "Status da pasta remota: [NENHUMA SELECIONADA]",
        "folders_local_label": "Pasta Local Dedicada (Vazia na Primeira Sincronização):",
        "folders_local_browse_btn": "Escolher Pasta...",
        "folders_local_save_btn": "Salvar e Validar Pasta",
        "folders_local_open_btn": "Abrir Pasta Local",
        "folders_local_sync_btn": "Sincronizar",
        "folders_status_ready": "Conferência pré-execução: [PRONTO] {local} ⮂ Google Drive: {remote}",
        "folders_status_mode": "Modo: Reconciliação bidirecional incremental",
        "folders_status_local_ok": "Status da pasta: [OK — CONFIGURADA E ACESSÍVEL] {path}",
        "folders_status_local_empty_needed": "Status da pasta: [ATENÇÃO — PASTA NÃO ESTÁ VAZIA] Escolha uma pasta local vazia para a primeira sincronização segura.",
        "folders_status_local_missing": "Status da pasta: [NÃO CONFIGURADA]",
        "folders_pending_notice": "Configuração pendente: Nenhum par de sincronização configurado.",
        "folders_waiting_first_sync": "Aguardando 1ª sincronização",
        "folders_rule_notice": "O modo bisync propaga alterações bidirecionalmente. Ao alterar caminhos, a próxima execução faz uma ressincronização segura.",

        # Aba Atividade
        "activity_card_title": "Histórico de Atividade",
        "activity_card_subtitle": "Últimas sincronizações e eventos registrados",
        "activity_col_timestamp": "Data / Hora",
        "activity_col_operation": "Operação",
        "activity_col_status": "Status",
        "activity_col_files": "Arquivos",
        "activity_col_duration": "Duração",
        "activity_col_details": "Detalhes",
        "activity_empty_state": "Nenhuma sincronização realizada ainda nesta sessão.",
        "activity_btn_details": "Ver Detalhes...",
        "activity_btn_clear": "Limpar Histórico",
        "activity_status_success": "Sucesso",
        "activity_status_failed": "Falha",
        "activity_status_attention": "Atenção",
        "activity_status_running": "Em andamento",

        # Aba Ajustes
        "settings_card_accounts": "Contas",
        "settings_card_engine": "Motor de sincronização",
        "settings_card_system": "Sistema",
        "settings_card_advanced": "Avançado (desenvolvedores e forks)",
        "settings_card_about": "Sobre o BrisaSync",
        "settings_about_license": "Distribuído sob licença GNU General Public License v3.0 ou posterior.",
        "settings_btn_open_about": "Sobre o BrisaSync...",
        "settings_account_status_label": "Estado da Conta Google:",
        "settings_account_status_connected": "Conectada: {email}",
        "settings_account_status_disconnected": "Nenhuma conta autorizada no cofre.",
        "settings_btn_disconnect": "Desconectar Conta Google...",
        "settings_btn_connect": "Conectar Conta Google",
        "settings_account_security_notice": "Segurança: Tokens protegidos no cofre da sessão (Secret Service / KWallet), nunca gravados em texto claro nem incluídos em arquivos de pacote.",
        "settings_engine_bisync_mode": "Modo bisync: Duas vias, com reconciliação bidirecional incremental.",
        "settings_btn_diagnostics": "Abrir Diagnóstico de Dependências...",
        "settings_theme_label": "Aparência:",
        "settings_language_label": "Idioma / Language:",
        "settings_interval_label": "Intervalo de verificação da nuvem:",
        "settings_tray_label": "Ícone na bandeja do sistema:",
        "settings_autostart_checkbox": "Iniciar automaticamente ao fazer login",
        "settings_notifications_checkbox": "Notificações na área de trabalho",
        "settings_lifecycle_notice": "Fechar a janela apenas oculta a interface. O serviço de sincronização continua ativo em segundo plano.",
        "settings_btn_exit": "Sair do BrisaSync…",

        # Opções dos Seletores
        "theme_system": "Sistema",
        "theme_light": "Claro",
        "theme_dark": "Escuro",
        "tray_auto": "Automático",
        "tray_light": "Claro (para barra escura)",
        "tray_dark": "Escuro (para barra clara)",
        "interval_1min": "1 minuto",
        "interval_2min": "2 minutos",
        "interval_5min": "5 minutos (padrão)",
        "interval_10min": "10 minutos",
        "interval_15min": "15 minutos",
        "interval_30min": "30 minutos",
        "interval_60min": "60 minutos",

        # Diálogo Sobre
        "about_dialog_title": "Sobre o BrisaSync",
        "about_headline": "Sincronizador bidirecional nativo e seguro para Linux Desktop com Google Drive.",
        "about_support_title": "Apoie o BrisaSync",
        "about_support_message": (
            "O BrisaSync é gratuito e de código aberto. Seu desenvolvimento envolve "
            "investimento de tempo, esforço e recursos. Se ele é útil para você, considere "
            "contribuir via Pix para apoiar sua manutenção e evolução. Toda contribuição é "
            "voluntária e todos os recursos continuam disponíveis."
        ),
        "about_beneficiary_label": "Beneficiário:",
        "about_pix_key_label": "Chave Pix:",
        "about_btn_copy_key": "Copiar chave Pix",
        "about_btn_copy_payload": "Copiar Pix Copia e Cola",
        "about_copy_key_success": "✓ Chave copiada!",
        "about_copy_payload_success": "✓ Copiado!",
        "about_copy_hint_key": "Chave copiada para a área de transferência.",
        "about_copy_hint_payload": "Código Copia e Cola copiado com sucesso.",
        "about_independence_title": "Declaração de Independência do Google",
        "about_independence_text": (
            "O BrisaSync é um aplicativo independente de código aberto desenvolvido pela comunidade "
            "e não possui vínculo, endosso ou afiliação oficial com a Google LLC. 'Google', "
            "'Google Drive' e marcas associadas são marcas comerciais registradas de propriedade da Google LLC."
        ),
        "about_btn_close": "Fechar",

        # Diálogo de Sair
        "exit_dialog_title": "Sair do BrisaSync",
        "exit_question": "O que você deseja fazer?",
        "exit_option_keep_service": "Manter sincronização",
        "exit_option_keep_service_desc": "Oculta a interface gráfica. O serviço de sincronização continuará verificando suas pastas automaticamente a cada intervalo configurado.",
        "exit_option_shutdown": "Encerrar tudo",
        "exit_option_shutdown_desc": "Interrompe todas as sincronizações ativas, encerra o serviço de segundo plano e libera os recursos do sistema.",
        "exit_btn_cancel": "Cancelar",
        "exit_btn_confirm": "Confirmar",

        # Diálogo de Diagnósticos
        "diag_dialog_title": "Diagnóstico de Dependências e Sistema",
        "diag_section_environment": "Ambiente do Sistema",
        "diag_section_engine": "Motor de Sincronização",
        "diag_section_vault": "Cofre de Credenciais",
        "diag_section_service": "Serviço de Segundo Plano",
        "diag_btn_refresh": "Atualizar Diagnóstico",
        "diag_btn_close": "Fechar",

        # Diálogo de Detalhes de Execução
        "details_dialog_title": "Detalhes da Execução da Sincronização",
        "details_btn_close": "Fechar",

        # Bandeja do Sistema
        "tray_tooltip_active": "{app_name} — Serviço de Sincronização Ativo",
        "tray_tooltip_state": "{app_name} — [{status}]",
        "tray_tooltip_state_detail": "{app_name} — [{status}] {detail}",
        "tray_tooltip_stopped": "{app_name} — [{status}] (Serviço parado)",
        "tray_status_header": "Estado: [{status}]",
        "tray_status_header_stopped": "Estado: [{status}] (Serviço parado)",
        "tray_updated_header": "Atualizado: {time}",
        "tray_updated_none": "Atualizado: Nenhuma confirmação",
        "tray_action_open_panel": "Abrir Painel",
        "tray_action_open_folder": "Abrir Pasta Local",
        "tray_action_sync_now": "Sincronizar Agora",
        "tray_action_pause": "Pausar Sincronização Automática",
        "tray_action_resume": "Retomar Sincronização Automática",
        "tray_action_quit": "Sair…",
        "tray_action_quit_ui": "Encerrar Interface / Bandeja (Manter Serviço)",
        "tray_action_shutdown_service": "Encerrar Serviço de Sincronização",

        # Estados de Protocolo
        "state_waiting": "AGUARDANDO",
        "state_verifying": "VERIFICANDO",
        "state_syncing": "SINCRONIZANDO",
        "state_pausing": "PAUSANDO",
        "state_paused": "PAUSADO",
        "state_offline": "SEM CONEXÃO",
        "state_attention_required": "ATENÇÃO NECESSÁRIA",

        # Notificações de Desktop
        "notif_title_attention": "BrisaSync — Atenção Necessária",
        "notif_title_auth_expired": "BrisaSync — Autenticação Expirada",
        "notif_title_vault_locked": "BrisaSync — Cofre Bloqueado",
        "notif_title_conflict": "BrisaSync — Conflito de Edição Preservado",
        "notif_title_mass_deletion": "BrisaSync — Salvaguarda Contra Exclusão Ativada",
        "notif_title_failure": "BrisaSync — Falha Persistente de Sincronização",
        "notif_body_default": "Abra o painel do BrisaSync para verificar uma situação que exige atenção.",
        "notif_body_conflict": "Foram detectados {count} arquivo(s) com alterações concorrentes (.conflict). Ambas as versões foram preservadas com segurança.",
        "notif_body_auth_expired": "As credenciais do Google Drive expiraram ou o cofre da sessão está inacessível. Abra o painel para reconectar.",
        "notif_body_mass_deletion": "A exclusão de um grande volume de arquivos locais foi interrompida para proteger seus dados na nuvem.",

        # Mensagens Operacionais em Segundo Plano
        "op_pausing": "Pausando sincronização automática: aguardando término seguro da operação atual...",
        "op_verifying": "Verificando acessibilidade, marcadores .brisasync_check e limites de exclusão...",
        "op_syncing": "Sincronizando arquivos bidirecionalmente via rclone bisync...",
        "op_waiting": "Aguardando próximo ciclo periódico de sincronização...",
        "op_paused": "Sincronização automática pausada pelo usuário.",

        # Barra lateral e Rodapé
        "sidebar_section_nav": "NAVEGAÇÃO",
        "sidebar_rclone_connected": "rclone conectado",
        "sidebar_tray_sync": "Sincroniza na bandeja",
        "sidebar_tray_desc": "Fechar a janela não interrompe as pastas.",
        "settings_lifecycle_notice_tray": (
            "Bandeja do sistema: [ATIVA] — "
            "Fechar a janela (X) oculta o painel na bandeja mantendo a sincronização ativa. "
            "O botão 'Sair do BrisaSync…' permite escolher entre manter o serviço ativo ou encerrar tudo com segurança."
        ),
        "settings_lifecycle_notice_no_tray": (
            "Bandeja do sistema: [INDISPONÍVEL / MODO SEM BANDEJA] — Nenhuma extensão de bandeja é exigida. "
            "Fechar a janela (X) encerra este painel mantendo o serviço ativo em segundo plano. "
            "O painel pode ser reaberto pelo lançador a qualquer momento."
        ),
        "about_qr_hint": "Escaneie no app do banco",
        "about_license_title": "Licenciamento e Terceiros",

        # Tempo Relativo e Formatação
        "time_just_now": "agora mesmo",
        "time_1_min_ago": "há 1 min",
        "time_mins_ago": "há {count} min",
        "time_1_hour_ago": "há 1 hora",
        "time_hours_ago": "há {count} horas",
        "op_baseline_resync": "Sincronização inicial",
        "op_sync": "Sincronização",
        "op_resync": "Ressincronização",
        "op_precheck": "Validação prévia",
        "activity_status_completed": "✓ Concluído",
        "activity_status_in_progress": "🔄 Em execução",
        "activity_status_stopped": "⏹ Interrompido",
        "activity_status_offline": "⏳ Sem conexão",
        "activity_status_attention_needed": "⚠ Atenção necessária",

        # Ações e Pílulas Dinâmicas
        "menu_action_diagnostics": "Ajuda e Diagnóstico...",
        "menu_action_about": "Sobre o BrisaSync...",
        "menu_action_exit": "Sair…",
        "pill_vault_locked": "✕ Cofre bloqueado",
        "pill_config_pending": "○ Configuração pendente",
        "pill_unconfigured": "○ Não configurado",
        "pill_attention": "● Atenção",
        "pill_paused": "● Pausado",
        "pill_syncing": "● Sincronizando",
        "pill_healthy": "● Tudo em dia",
        "header_account_connected": "Conta conectada",
        "header_account_pending_suffix": "(pendente)",
        "header_vault_locked": "✕ Cofre bloqueado",
        "header_not_connected": "○ Não conectado",
        "header_no_account_linked": "Nenhuma conta Google vinculada",
        "hero_vault_locked_title": "Cofre bloqueado",
        "hero_vault_locked_subtitle": "O chaveiro da sessão está bloqueado. Desbloqueie para acessar suas credenciais e sincronizar.",
        "hero_btn_unlock": "Desbloquear",
        "hero_btn_unlock_vault": "Desbloquear cofre",
        "hero_btn_complete_setup": "Concluir conexão",
        "hero_btn_connect_account": "Conectar conta",
        "hero_welcome_title": "Bem-vindo ao BrisaSync",
        "hero_config_pending_subtitle": "Credenciais salvas no cofre. Conclua a conexão para iniciar.",
        "hero_unconfigured_subtitle": "Configure sua conta Google e pastas abaixo para iniciar.",
        "hero_btn_help": "Ajuda",
        "hero_attention_title": "Atenção necessária",
        "hero_btn_inspect": "Inspecionar",
        "hero_paused_title": "Sincronização pausada",
        "hero_paused_subtitle": "O serviço da sessão está em repouso.",
        "hero_btn_resume": "Retomar",
        "hero_syncing_title": "Sincronizando...",
        "hero_syncing_subtitle": "Reconciliando alterações em andamento...",
        "hero_btn_pause": "Pausar",
        "hero_healthy_title": "Tudo em dia",
        "hero_last_check": "Última verificação {rel_time}",
        "hero_waiting_first_check": "Aguardando primeira verificação",
        "hero_btn_pause_all": "Pausar tudo",
        "hero_btn_sync_now": "Sincronizar agora",
        "overview_header_attention_pending": "Atenção pendente",
        "overview_header_in_progress": "Operação em andamento",
        "overview_header_in_queue": "Na fila",
        "overview_recent_activity_title": "Atividade Recente",
        "overview_btn_view_all_history": "Ver histórico completo →",
        "folder_status_pending": "○ pendente",
        "folder_status_up_to_date": "em dia",
        "folder_status_up_to_date_check": "✓ em dia",
        "folder_status_waiting_first_sync": "● Aguardando 1ª sincronização",
        "folder_status_recovery_pending": "● Recuperação pendente",
        "folder_status_blocked": "● Bloqueado",
        "folder_status_paused": "● Pausado",
        "folder_status_syncing": "● Sincronizando",

        # Histórico de Atividade
        "history_btn_refresh": "Atualizar Histórico",
        "history_btn_clear": "Limpar histórico",
        "history_clear_confirm_title": "Limpar histórico de atividades",
        "history_clear_confirm_message": (
            "Tem certeza de que deseja limpar o histórico de atividades exibido? "
            "Novas sincronizações continuarão sendo registradas normalmente."
        ),
        "history_summary_count": "Atividade recente ({count} execuções registradas)",
        "history_hint_double_click": "Dica: Dê um duplo-clique em qualquer linha para abrir os detalhes completos da auditoria técnica.",
        "history_table_header_started": "Início",
        "history_table_header_operation": "Operação",
        "history_table_header_status": "Estado",
        "history_table_header_folders": "Pastas",
        "history_table_header_summary": "Resumo das Alterações",

        # Resumos de Sincronização
        "summary_completed_no_conflicts": "Concluído sem conflitos.",
        "summary_attention_needed": "Atenção necessária.",
        "summary_bidirectional_success": "Sincronização bidirecional concluída com sucesso.",
        "summary_baseline_success": "Baseline inicial estabelecida com sucesso.",
        "summary_stopped_by_user": "Operação interrompida de forma controlada pelo usuário (SIGTERM graceful shutdown). Estado recuperável preservado para o próximo ciclo.",
        "summary_conflicts_preserved": "Conflitos preservados pelo backend ({count}): {files}.",

        # Visão Geral - Atividade recente
        "overview_recent_empty": "Nenhuma atividade registrada ainda.",
        "overview_op_completed": "{op} concluída",
        "overview_folder_up_to_date": "{target} está em dia",

        # Barra lateral
        "sidebar_brand_sub": "Sincronizador Google Drive",

        # Estado da Conta em Ajustes
        "wizard_btn_switch_account": "Trocar de Conta...",
        "settings_oauth_desktop_metadata": "Metadados OAuth Desktop",
        "folder_status_connected": "conectada",
        "folder_status_not_connected": "○ não conectada",
        "settings_acc_vault_locked": "Conta Google: [COFRE BLOQUEADO] {detail} (Desbloqueie o cofre da sessão para acessar as credenciais).",
        "settings_acc_config_pending": "Estado da Conta Google: [CONFIGURAÇÃO PENDENTE] {email} (Credenciais salvas no cofre, mas configuração rclone pendente de materialização).",
        "settings_acc_connected": "Estado da Conta Google: [CONECTADA] {email} (Credenciais protegidas no cofre e motor rclone configurado).",
        "settings_acc_not_connected": "Estado da Conta Google: [NÃO CONECTADA] Nenhuma conta autorizada no cofre.",

        # Botões da Conta em Ajustes
        "settings_btn_unlock_vault": "Desbloquear Cofre",
        "settings_btn_complete_setup": "Concluir Conexão",
        "settings_btn_reconnect": "Reconectar Conta Google",

        # Desconexão e Reconexão Segura
        "folders_btn_remove_pair": "Remover vínculo de sincronização",
        "folders_remove_pair_confirm_title": "Remover vínculo de sincronização",
        "folders_remove_pair_confirm_message": (
            "Tem certeza de que deseja remover o vínculo de sincronização entre estas pastas?\n\n"
            "Esta ação apenas remove a configuração do par no aplicativo. "
            "Seus arquivos locais, seus arquivos no Google Drive e o histórico de execuções permanecem totalmente intactos.\n\n"
            "O serviço de sincronização deixará de monitorar e agendar este par."
        ),
        "folder_status_waiting_account": "○ Aguardando conexão",
        "folders_status_waiting_connection": "Conferência pré-execução: [AGUARDANDO CONEXÃO] Conecte sua conta Google para validar o par.",
        "hero_title_no_account": "Nenhuma conta conectada",
        "hero_subtitle_no_account": "Conecte sua conta Google para sincronizar suas pastas locais.",
        "hero_btn_connect_account_action": "Conectar conta",
        "tray_status_header_no_account": "Nenhuma conta conectada",
        "tray_tooltip_no_account": "{app_name} — Nenhuma conta conectada",
        "folders_no_pair_title": "Nenhum par configurado",
        "folders_no_pair_subtitle": "Nenhum par de sincronização configurado.",
        "folders_btn_connect_account": "Conectar conta",
        "folders_remote_connect_prompt": "Conecte sua Conta Google para listar e selecionar pastas do Drive.",
        "tray_tooltip_vault_locked_detail": "Cofre de credenciais bloqueado. Desbloqueie o chaveiro da sessão para continuar.",
        "tray_tooltip_auth_expired_detail": "A autorização da conta expirou ou foi revogada. Reconecte a conta pela interface.",
        "folders_diff_account_notice": (
            "A conta conectada ({new_email}) é diferente da conta anteriormente vinculada ({prev_email}). "
            "Para sua segurança, a baseline anterior foi invalidada. "
            "Selecione e confirme a pasta remota no Google Drive para esta nova conta."
        ),
        "folders_remote_blocked_no_account": "Conecte sua conta Google antes de acessar ou listar pastas remotas.",
        "sync_blocked_no_account": "Conecte sua conta Google antes de iniciar a sincronização.",
        "folders_pair_removed_feedback": "Status da pasta: [NENHUM PAR CONFIGURADO]",
        "hero_stat_folders_ratio": "{active} de {total}",
        "folders_unknown_prev_account_notice": (
            "A identidade da conta vinculada anteriormente era desconhecida. "
            "Por segurança, selecione e confirme explicitamente a pasta remota no Google Drive para ativar a sincronização."
        ),
        "folders_remote_inaccessible_notice": (
            "A pasta remota '{folder}' configurada anteriormente não foi encontrada ou está inacessível no Google Drive. "
            "Selecione ou crie uma pasta para reativar."
        ),
    },

    "en": {
        # Application and Navigation
        "app_title": "BrisaSync",
        "app_tagline": "Native, secure bidirectional synchronizer for Linux Desktop with Google Drive",
        "nav_overview": "Overview",
        "nav_folders": "Folders",
        "nav_activity": "Activity",
        "nav_settings": "Settings",
        "nav_help": "Help",
        "nav_about": "About",
        "nav_connecting": "Connecting...",

        # Header
        "header_title": "BrisaSync",
        "header_subtitle_overview": "Your folders status at a glance",
        "header_subtitle_folders": "Choose what stays in sync on both sides",
        "header_subtitle_activity": "Detailed log of synchronizations and events",
        "header_subtitle_settings": "Accounts, synchronization, and system preferences",
        "header_badge_connected": "Connected",
        "header_badge_not_connected": "Not connected",
        "header_badge_paused": "Paused",
        "header_badge_attention": "Attention required",
        "header_badge_syncing": "Syncing",
        "header_badge_verifying": "Verifying",
        "header_badge_waiting": "Waiting",
        "header_btn_configure": "Configure",
        "header_btn_sync_now": "Sync Now",
        "header_btn_options": "Options ▾",

        # Options Menu
        "menu_account_info": "Account: {email}",
        "menu_no_account": "No account linked",
        "menu_pause_sync": "Pause Automatic Sync",
        "menu_resume_sync": "Resume Automatic Sync",
        "menu_open_local_folder": "Open Local Folder",
        "menu_view_diagnostics": "Dependency Diagnostics...",
        "menu_about": "About BrisaSync...",
        "menu_disconnect_account": "Disconnect Google Account...",
        "menu_exit": "Quit BrisaSync…",

        # Hero Banner
        "hero_title_unconfigured": "Initial BrisaSync Setup",
        "hero_subtitle_unconfigured": "Keep your files synchronized and available offline.",
        "hero_title_healthy": "Synchronization in Operation",
        "hero_subtitle_healthy": "Your local folders and Google Drive are in perfect sync.",
        "hero_title_paused": "Synchronization Paused",
        "hero_subtitle_paused": "Periodic synchronization is temporarily suspended.",
        "hero_title_attention": "Attention Required",
        "hero_subtitle_attention": "Check the items below to resume synchronization.",
        "hero_title_offline": "No Network Connection",
        "hero_subtitle_offline": "Waiting for internet connection to be restored.",
        "hero_title_syncing": "Syncing...",
        "hero_subtitle_syncing": "Transferring changes between Google Drive and your computer.",
        "hero_title_verifying": "Verifying...",
        "hero_subtitle_verifying": "Checking file integrity and connectivity.",

        # Hero Actions
        "hero_action_connect": "Connect Google Account",
        "hero_action_setup_folders": "Configure Folders",
        "hero_action_sync_now": "Sync Now",
        "hero_action_pause": "Pause Sync",
        "hero_action_resume": "Resume Sync",
        "hero_action_resolve_conflicts": "Review Conflicts",
        "hero_action_reconnect": "Reconnect Account",

        # Hero Stats
        "hero_stat_speed": "SPEED",
        "hero_stat_transferred": "TRANSFERRED",
        "hero_stat_active_folders": "ACTIVE FOLDERS",

        # Setup Wizard
        "wizard_step1_title": "1. Connect Google account",
        "wizard_step1_desc": "Connect your Google Drive account to start syncing with this computer. Your default browser will open to safely authorize via Google OAuth.",
        "wizard_step1_not_connected": "No Google account connected at this time.",
        "wizard_step1_connected": "Account connected successfully: {email}",
        "wizard_step2_title": "2. Configure sync folders",
        "wizard_step2_desc": "Select a folder in your Google Drive and a dedicated local folder. The local folder must be empty to establish a safe baseline.",
        "wizard_step3_title": "3. Safe first synchronization",
        "wizard_step3_desc": "The initial sync will download your files from the cloud and create a safe comparison baseline with zero risk of file loss.",

        # Folders Tab
        "folders_card_title": "Folder Configuration",
        "folders_card_subtitle": "Choose what stays in sync on both sides",
        "folders_remote_label": "Remote Folder in Google Drive (Identified by Immutable ID):",
        "folders_remote_list_btn": "List Folders",
        "folders_remote_new_btn": "New folder",
        "folders_remote_status_selected": "Remote folder status: [SELECTED] {name} (ID: {id})",
        "folders_remote_status_none": "Remote folder status: [NONE SELECTED]",
        "folders_local_label": "Dedicated Local Folder (Empty on First Sync):",
        "folders_local_browse_btn": "Browse Folder...",
        "folders_local_save_btn": "Save and Validate Folder",
        "folders_local_open_btn": "Open Local Folder",
        "folders_local_sync_btn": "Sync Now",
        "folders_status_ready": "Pre-run check: [READY] {local} ⮂ Google Drive: {remote}",
        "folders_status_mode": "Mode: Incremental bidirectional reconciliation",
        "folders_status_local_ok": "Folder status: [OK — CONFIGURED AND ACCESSIBLE] {path}",
        "folders_status_local_empty_needed": "Folder status: [ATTENTION — FOLDER IS NOT EMPTY] Please select an empty local folder for the safe first synchronization.",
        "folders_status_local_missing": "Folder status: [NOT CONFIGURED]",
        "folders_pending_notice": "Pending configuration: No sync pair configured.",
        "folders_waiting_first_sync": "Waiting for 1st sync",
        "folders_rule_notice": "Bisync mode propagates changes bidirectionally. Changing paths will trigger a safe full resynchronization on the next run.",

        # Activity Tab
        "activity_card_title": "Activity History",
        "activity_card_subtitle": "Recent synchronizations and recorded events",
        "activity_col_timestamp": "Date / Time",
        "activity_col_operation": "Operation",
        "activity_col_status": "Status",
        "activity_col_files": "Files",
        "activity_col_duration": "Duration",
        "activity_col_details": "Details",
        "activity_empty_state": "No sync events recorded yet in this session.",
        "activity_btn_details": "View Details...",
        "activity_btn_clear": "Clear History",
        "activity_status_success": "Success",
        "activity_status_failed": "Failed",
        "activity_status_attention": "Attention",
        "activity_status_running": "In progress",

        # Settings Tab
        "settings_card_accounts": "Accounts",
        "settings_card_engine": "Sync Engine",
        "settings_card_system": "System",
        "settings_card_advanced": "Advanced (developers and forks)",
        "settings_card_about": "About BrisaSync",
        "settings_about_license": "Distributed under the GNU General Public License v3.0 or later.",
        "settings_btn_open_about": "About BrisaSync...",
        "settings_account_status_label": "Google Account Status:",
        "settings_account_status_connected": "Connected: {email}",
        "settings_account_status_disconnected": "No account authorized in the vault.",
        "settings_btn_disconnect": "Disconnect Google Account...",
        "settings_btn_connect": "Connect Google Account",
        "settings_account_security_notice": "Security: Tokens protected in session vault (Secret Service / KWallet), never stored in plaintext or included in packages.",
        "settings_engine_bisync_mode": "Bisync mode: Two-way, with incremental bidirectional reconciliation.",
        "settings_btn_diagnostics": "Open Dependency Diagnostics...",
        "settings_theme_label": "Appearance:",
        "settings_language_label": "Language / Idioma:",
        "settings_interval_label": "Cloud check interval:",
        "settings_tray_label": "System tray icon:",
        "settings_autostart_checkbox": "Start automatically on login",
        "settings_notifications_checkbox": "Desktop notifications",
        "settings_lifecycle_notice": "Closing the window only hides the interface. The synchronization service remains active in the background.",
        "settings_btn_exit": "Quit BrisaSync…",

        # Selector Options
        "theme_system": "System",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "tray_auto": "Automatic",
        "tray_light": "Light (for dark panel)",
        "tray_dark": "Dark (for light panel)",
        "interval_1min": "1 minute",
        "interval_2min": "2 minutes",
        "interval_5min": "5 minutes (default)",
        "interval_10min": "10 minutes",
        "interval_15min": "15 minutes",
        "interval_30min": "30 minutes",
        "interval_60min": "60 minutes",

        # About Dialog
        "about_dialog_title": "About BrisaSync",
        "about_headline": "Native, secure bidirectional synchronizer for Linux Desktop with Google Drive.",
        "about_support_title": "Support BrisaSync",
        "about_support_message": (
            "BrisaSync is free and open source. Its development involves investment of "
            "time, effort, and resources. If it is useful to you, consider contributing "
            "via Pix to support its maintenance and evolution. Every contribution is "
            "voluntary and all features remain available."
        ),
        "about_beneficiary_label": "Beneficiary:",
        "about_pix_key_label": "Pix Key:",
        "about_btn_copy_key": "Copy Pix Key",
        "about_btn_copy_payload": "Copy Pix Copy-Paste",
        "about_copy_key_success": "✓ Key copied!",
        "about_copy_payload_success": "✓ Copied!",
        "about_copy_hint_key": "Key copied to clipboard.",
        "about_copy_hint_payload": "Pix Copy-Paste code copied successfully.",
        "about_independence_title": "Google Independence Disclaimer",
        "about_independence_text": (
            "BrisaSync is an independent open source application developed by the community "
            "and is not affiliated, associated, authorized, endorsed by, or in any way officially "
            "connected with Google LLC. 'Google', 'Google Drive', and related marks are registered "
            "trademarks owned by Google LLC."
        ),
        "about_btn_close": "Close",

        # Exit Dialog
        "exit_dialog_title": "Quit BrisaSync",
        "exit_question": "What would you like to do?",
        "exit_option_keep_service": "Keep syncing",
        "exit_option_keep_service_desc": "Hides the graphical interface. The synchronization service will continue checking your folders automatically at the configured interval.",
        "exit_option_shutdown": "Quit completely",
        "exit_option_shutdown_desc": "Stops all active synchronizations, shuts down the background service, and releases system resources.",
        "exit_btn_cancel": "Cancel",
        "exit_btn_confirm": "Confirm",

        # Diagnostics Dialog
        "diag_dialog_title": "System and Dependency Diagnostics",
        "diag_section_environment": "System Environment",
        "diag_section_engine": "Sync Engine",
        "diag_section_vault": "Credentials Vault",
        "diag_section_service": "Background Service",
        "diag_btn_refresh": "Refresh Diagnostics",
        "diag_btn_close": "Close",

        # Run Details Dialog
        "details_dialog_title": "Synchronization Run Details",
        "details_btn_close": "Close",

        # System Tray
        "tray_tooltip_active": "{app_name} — Sync Service Active",
        "tray_tooltip_state": "{app_name} — [{status}]",
        "tray_tooltip_state_detail": "{app_name} — [{status}] {detail}",
        "tray_tooltip_stopped": "{app_name} — [{status}] (Service stopped)",
        "tray_status_header": "Status: [{status}]",
        "tray_status_header_stopped": "Status: [{status}] (Service stopped)",
        "tray_updated_header": "Updated: {time}",
        "tray_updated_none": "Updated: No confirmation",
        "tray_action_open_panel": "Open Panel",
        "tray_action_open_folder": "Open Local Folder",
        "tray_action_sync_now": "Sync Now",
        "tray_action_pause": "Pause Automatic Sync",
        "tray_action_resume": "Resume Automatic Sync",
        "tray_action_quit": "Quit…",
        "tray_action_quit_ui": "Quit Interface / Tray (Keep Service)",
        "tray_action_shutdown_service": "Shut Down Sync Service",

        # Protocol States
        "state_waiting": "WAITING",
        "state_verifying": "VERIFYING",
        "state_syncing": "SYNCING",
        "state_pausing": "PAUSING",
        "state_paused": "PAUSED",
        "state_offline": "NO CONNECTION",
        "state_attention_required": "ATTENTION REQUIRED",

        # Desktop Notifications
        "notif_title_attention": "BrisaSync — Attention Required",
        "notif_title_auth_expired": "BrisaSync — Authentication Expired",
        "notif_title_vault_locked": "BrisaSync — Vault Locked",
        "notif_title_conflict": "BrisaSync — Edit Conflict Preserved",
        "notif_title_mass_deletion": "BrisaSync — Safeguard Activated Against Deletion",
        "notif_title_failure": "BrisaSync — Persistent Sync Failure",
        "notif_body_default": "Open the BrisaSync panel to review an item requiring attention.",
        "notif_body_conflict": "{count} file(s) with concurrent changes (.conflict) detected. Both versions were preserved safely.",
        "notif_body_auth_expired": "Google Drive credentials have expired or the session vault is locked. Open the panel to reconnect.",
        "notif_body_mass_deletion": "A large volume of local file deletions was halted to protect your cloud data.",

        # Operational Background Messages
        "op_pausing": "Pausing automatic sync: waiting for current operation to safely finish...",
        "op_verifying": "Verifying accessibility, .brisasync_check sentinels, and deletion limits...",
        "op_syncing": "Synchronizing files bidirectionally via rclone bisync...",
        "op_waiting": "Waiting for next periodic sync cycle...",
        "op_paused": "Automatic synchronization paused by user.",

        # Sidebar and Footer
        "sidebar_section_nav": "NAVIGATION",
        "sidebar_rclone_connected": "rclone connected",
        "sidebar_tray_sync": "Syncs in tray",
        "sidebar_tray_desc": "Closing the window does not stop folders.",
        "settings_lifecycle_notice_tray": (
            "System tray: [ACTIVE] — "
            "Closing the window (X) minimizes the panel to the tray keeping sync active. "
            "The 'Quit BrisaSync…' button lets you choose between keeping the background service active or shutting down safely."
        ),
        "settings_lifecycle_notice_no_tray": (
            "System tray: [UNAVAILABLE / NO-TRAY MODE] — No tray extension is required. "
            "Closing the window (X) closes this panel while keeping the background sync service running. "
            "The panel can be reopened from the launcher at any time."
        ),
        "about_qr_hint": "Scan with your banking app",
        "about_license_title": "Licensing and Third Parties",

        # Relative Time and Formatting
        "time_just_now": "just now",
        "time_1_min_ago": "1 min ago",
        "time_mins_ago": "{count} min ago",
        "time_1_hour_ago": "1 hour ago",
        "time_hours_ago": "{count} hours ago",
        "op_baseline_resync": "Initial sync",
        "op_sync": "Sync",
        "op_resync": "Resync",
        "op_precheck": "Pre-check validation",
        "activity_status_completed": "✓ Completed",
        "activity_status_in_progress": "🔄 Running",
        "activity_status_stopped": "⏹ Stopped",
        "activity_status_offline": "⏳ No connection",
        "activity_status_attention_needed": "⚠ Attention required",

        # Dynamic Actions and Pills
        "menu_action_diagnostics": "Help and Diagnostics...",
        "menu_action_about": "About BrisaSync...",
        "menu_action_exit": "Quit…",
        "pill_vault_locked": "✕ Vault locked",
        "pill_config_pending": "○ Setup pending",
        "pill_unconfigured": "○ Not configured",
        "pill_attention": "● Attention",
        "pill_paused": "● Paused",
        "pill_syncing": "● Syncing",
        "pill_healthy": "● Up to date",
        "header_account_connected": "Connected account",
        "header_account_pending_suffix": "(pending)",
        "header_vault_locked": "✕ Vault locked",
        "header_not_connected": "○ Not connected",
        "header_no_account_linked": "No Google account connected",
        "hero_vault_locked_title": "Vault locked",
        "hero_vault_locked_subtitle": "The session keyring is locked. Unlock it to access credentials and sync.",
        "hero_btn_unlock": "Unlock",
        "hero_btn_unlock_vault": "Unlock vault",
        "hero_btn_complete_setup": "Complete setup",
        "hero_btn_connect_account": "Connect account",
        "hero_welcome_title": "Welcome to BrisaSync",
        "hero_config_pending_subtitle": "Credentials saved in vault. Complete setup to start.",
        "hero_unconfigured_subtitle": "Configure your Google account and folders below to start.",
        "hero_btn_help": "Help",
        "hero_attention_title": "Attention required",
        "hero_btn_inspect": "Inspect",
        "hero_paused_title": "Sync paused",
        "hero_paused_subtitle": "The session service is idle.",
        "hero_btn_resume": "Resume",
        "hero_syncing_title": "Syncing...",
        "hero_syncing_subtitle": "Reconciling changes in progress...",
        "hero_btn_pause": "Pause",
        "hero_healthy_title": "Up to date",
        "hero_last_check": "Last checked {rel_time}",
        "hero_waiting_first_check": "Waiting for first check",
        "hero_btn_pause_all": "Pause all",
        "hero_btn_sync_now": "Sync now",
        "overview_header_attention_pending": "Attention pending",
        "overview_header_in_progress": "Operation in progress",
        "overview_header_in_queue": "Queued",
        "overview_recent_activity_title": "Recent Activity",
        "overview_btn_view_all_history": "View full history →",
        "folder_status_pending": "○ pending",
        "folder_status_up_to_date": "up to date",
        "folder_status_up_to_date_check": "✓ up to date",
        "folder_status_waiting_first_sync": "● Waiting for 1st sync",
        "folder_status_recovery_pending": "● Recovery pending",
        "folder_status_blocked": "● Blocked",
        "folder_status_paused": "● Paused",
        "folder_status_syncing": "● Syncing",

        # Activity History
        "history_btn_refresh": "Refresh History",
        "history_btn_clear": "Clear History",
        "history_clear_confirm_title": "Clear Activity History",
        "history_clear_confirm_message": (
            "Are you sure you want to clear the displayed activity history? "
            "New synchronizations will continue to be recorded normally."
        ),
        "history_summary_count": "Recent activity ({count} runs recorded)",
        "history_hint_double_click": "Tip: Double-click any row to view full technical audit details.",
        "history_table_header_started": "Started",
        "history_table_header_operation": "Operation",
        "history_table_header_status": "Status",
        "history_table_header_folders": "Folders",
        "history_table_header_summary": "Summary of Changes",

        # Sync Summaries
        "summary_completed_no_conflicts": "Completed without conflicts.",
        "summary_attention_needed": "Attention required.",
        "summary_bidirectional_success": "Bidirectional synchronization completed successfully.",
        "summary_baseline_success": "Initial baseline established successfully.",
        "summary_stopped_by_user": "Operation gracefully interrupted by user (SIGTERM graceful shutdown). Recoverable state preserved for next cycle.",
        "summary_conflicts_preserved": "Conflicts preserved by backend ({count}): {files}.",

        # Overview - Recent Activity
        "overview_recent_empty": "No activity recorded yet.",
        "overview_op_completed": "{op} completed",
        "overview_folder_up_to_date": "{target} is up to date",

        # Sidebar
        "sidebar_brand_sub": "Google Drive Synchronizer",

        # Account Status in Settings
        "wizard_btn_switch_account": "Switch Account...",
        "settings_oauth_desktop_metadata": "Desktop OAuth Metadata",
        "folder_status_connected": "connected",
        "folder_status_not_connected": "○ not connected",
        "settings_acc_vault_locked": "Google Account: [VAULT LOCKED] {detail} (Unlock the session vault to access credentials).",
        "settings_acc_config_pending": "Google Account Status: [CONFIGURATION PENDING] {email} (Credentials saved in vault, but rclone setup pending materialization).",
        "settings_acc_connected": "Google Account Status: [CONNECTED] {email} (Credentials protected in vault and rclone engine configured).",
        "settings_acc_not_connected": "Google Account Status: [NOT CONNECTED] No authorized account in vault.",

        # Account Buttons in Settings
        "settings_btn_unlock_vault": "Unlock Vault",
        "settings_btn_complete_setup": "Complete Connection",
        "settings_btn_reconnect": "Reconnect Google Account",

        # Disconnect and Safe Reconnect
        "folders_btn_remove_pair": "Remove sync link",
        "folders_remove_pair_confirm_title": "Remove Synchronization Link",
        "folders_remove_pair_confirm_message": (
            "Are you sure you want to remove the synchronization link between these folders?\n\n"
            "This action only removes the pair configuration from the app. "
            "Your local files, your files in Google Drive, and execution history remain completely intact.\n\n"
            "The synchronization service will stop monitoring and scheduling this pair."
        ),
        "folder_status_waiting_account": "○ Waiting for connection",
        "folders_status_waiting_connection": "Pre-run check: [WAITING FOR CONNECTION] Connect your Google account to validate the pair.",
        "hero_title_no_account": "No account connected",
        "hero_subtitle_no_account": "Connect your Google account to sync your local folders.",
        "hero_btn_connect_account_action": "Connect account",
        "tray_status_header_no_account": "No account connected",
        "tray_tooltip_no_account": "{app_name} — No account connected",
        "folders_no_pair_title": "No pair configured",
        "folders_no_pair_subtitle": "No sync pair configured.",
        "folders_btn_connect_account": "Connect account",
        "folders_remote_connect_prompt": "Connect your Google account to list and select Drive folders.",
        "tray_tooltip_vault_locked_detail": "Credentials vault locked. Unlock session keyring to continue.",
        "tray_tooltip_auth_expired_detail": "Account authorization expired or revoked. Reconnect account via interface.",
        "folders_diff_account_notice": (
            "The connected account ({new_email}) is different from the previously linked account ({prev_email}). "
            "For your safety, the previous baseline was invalidated. "
            "Please select and confirm the remote folder on Google Drive for this new account."
        ),
        "folders_remote_blocked_no_account": "Connect your Google account before accessing or listing remote folders.",
        "sync_blocked_no_account": "Connect your Google account before starting synchronization.",
        "folders_pair_removed_feedback": "Folder status: [NO PAIR CONFIGURED]",
        "hero_stat_folders_ratio": "{active} of {total}",
        "folders_unknown_prev_account_notice": (
            "The previous linked account identity was unknown. "
            "For safety, please explicitly select and confirm the remote folder on Google Drive to activate sync."
        ),
        "folders_remote_inaccessible_notice": (
            "The previously configured remote folder '{folder}' was not found or is inaccessible on Google Drive. "
            "Select or create a folder to reactivate."
        ),
    },
}
