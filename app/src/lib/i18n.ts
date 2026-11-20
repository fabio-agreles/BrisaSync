// Idioma da interface — português (padrão) e inglês.
//
// As chaves do dicionário são o **próprio texto em português**. Isso tem duas
// consequências boas:
//   · se faltar tradução, a tela mostra português (nunca uma chave feia tipo
//     "settings.title"), então nada quebra;
//   · quem lê o código vê o texto que o usuário vê, sem consultar tabela.
// A contrapartida é que mudar o texto em português exige atualizar a chave aqui —
// e o texto novo, sem tradução, aparece em português até alguém traduzir.
//
// `scripts/checar-i18n.mjs` lista as chaves usadas no código que ainda não têm
// tradução, para isso não passar batido.
import { useSyncExternalStore } from "react";

export type Lang = "pt" | "en";

export const IDIOMAS: { id: Lang; nome: string; nomeNativo: string }[] = [
  { id: "pt", nome: "Português (Brasil)", nomeNativo: "Português" },
  { id: "en", nome: "Inglês", nomeNativo: "English" },
];

let idioma: Lang = "pt";
const ouvintes = new Set<() => void>();

export function idiomaAtual(): Lang {
  return idioma;
}

/** Valor para o atributo `lang` do <html>: "pt-BR" ou "en". */
export function idiomaDoDocumento(lang: Lang): string {
  return lang === "en" ? "en" : "pt-BR";
}

export function definirIdioma(novo: Lang) {
  if (novo !== "pt" && novo !== "en") return;
  if (novo === idioma) return;
  idioma = novo;
  if (typeof document !== "undefined") {
    document.documentElement.lang = idiomaDoDocumento(novo);
  }
  ouvintes.forEach((avisar) => avisar());
}

function inscrever(avisar: () => void) {
  ouvintes.add(avisar);
  return () => {
    ouvintes.delete(avisar);
  };
}

/** Troca `{nome}` pelos valores passados. */
export function traduzir(
  lang: Lang,
  texto: string,
  valores?: Record<string, string | number>,
): string {
  const base = lang === "en" ? EN[texto] ?? texto : texto;
  if (!valores) return base;
  return base.replace(/\{(\w+)\}/g, (bruto, nome: string) =>
    nome in valores ? String(valores[nome]) : bruto,
  );
}

/** Tradução fora de componente (formatadores, mensagens montadas em `lib/`). */
export function t(texto: string, valores?: Record<string, string | number>): string {
  return traduzir(idioma, texto, valores);
}

/** Assina as mudanças de idioma: quem usa isto re-renderiza ao trocar. */
export function useIdioma(): Lang {
  return useSyncExternalStore(inscrever, idiomaAtual, idiomaAtual);
}

/** Em componentes: `const t = useT()`. */
export function useT() {
  const lang = useIdioma();
  return (texto: string, valores?: Record<string, string | number>) =>
    traduzir(lang, texto, valores);
}

/** Locale para Intl/`toLocaleDateString`. */
export function locale(lang: Lang = idioma): string {
  return lang === "en" ? "en-US" : "pt-BR";
}

// ---------------------------------------------------------------------------
// Dicionário: português → inglês.
// Agrupado por tela, na mesma ordem em que o usuário encontra as coisas.
// ---------------------------------------------------------------------------
const EN: Record<string, string> = {
  // ---- comum -------------------------------------------------------------
  Fechar: "Close",
  Cancelar: "Cancel",
  Salvar: "Save",
  "Salvar credenciais": "Save credentials",
  Adicionar: "Add",
  Remover: "Remove",
  Desconectar: "Disconnect",
  Copiar: "Copy",
  Escolher: "Choose",
  Abrir: "Open",
  Nome: "Name",
  Conta: "Account",
  Pastas: "Folders",
  Arquivos: "Files",
  Atividade: "Activity",
  Conflitos: "Conflicts",
  Ajustes: "Settings",
  "Visão geral": "Overview",
  Navegação: "Navigation",
  Buscar: "Search",
  "Buscar ações": "Search actions",
  "Buscar ações…": "Search actions…",
  "Paleta de comandos": "Command palette",
  "Nenhuma ação encontrada.": "No actions found.",
  "Dispensar aviso": "Dismiss notification",
  "Algo deu errado.": "Something went wrong.",
  "rclone conectado": "rclone connected",
  "Motor indisponível": "Engine unavailable",
  "versão desconhecida": "unknown version",
  "Instale o rclone para sincronizar de verdade.":
    "Install rclone to sync for real.",
  "Sincroniza na bandeja": "Keeps syncing in the tray",
  "Fechar a janela não interrompe as pastas.":
    "Closing the window does not stop the folders.",
  "Modo demonstração": "Demo mode",
  "Dados simulados, sem rclone nem contas reais.":
    "Simulated data, no rclone and no real accounts.",
  "sincronização simples": "simple syncing",
  "Tudo em dia": "All up to date",
  Pausado: "Paused",
  "Sincronizando 1 tarefa": "Syncing 1 job",
  "Sincronizando {n} tarefas": "Syncing {n} jobs",
  "Abrir visão geral": "Open overview",
  "Abrir busca de ações": "Open action search",
  "Ativar tema escuro": "Switch to dark theme",
  "Ativar tema claro": "Switch to light theme",
  "Tema escuro": "Dark theme",
  "Tema claro": "Light theme",
  Hoje: "Today",
  Ontem: "Yesterday",
  agora: "just now",
  nunca: "never",
  "há {n} min": "{n} min ago",
  "há {n} h": "{n} h ago",
  "há {n} dia": "{n} day ago",
  "há {n} dias": "{n} days ago",

  // ---- doações (Pix) -----------------------------------------------------
  "Ajude a manter o projeto": "Help keep the project going",
  "Gratuito e de código aberto. Se ele é útil para você, considere uma contribuição voluntária via Pix.":
    "Free and open source. If it helps you, consider a voluntary contribution via Pix.",
  "Este aplicativo é gratuito e de código aberto. Seu desenvolvimento envolve investimento financeiro, tempo e dedicação.":
    "This application is free and open source. Its development takes money, time and dedication.",
  "Se ele é útil para você, considere fazer uma contribuição voluntária via Pix. Seu apoio ajuda a manter o projeto e a desenvolver novas melhorias.":
    "If it is useful to you, consider a voluntary contribution via Pix. Your support helps keep the project alive and fund new improvements.",
  "Obrigado por fazer parte dessa história!":
    "Thank you for being part of this story!",
  "Doar com Pix": "Donate with Pix",
  "Copiar código Pix": "Copy Pix code",
  "Código Pix copiado. Cole no app do banco.":
    "Pix code copied. Paste it in your bank app.",
  "Não foi possível copiar o código Pix.": "Could not copy the Pix code.",
  "Chave Pix": "Pix key",
  "QR code para doação via Pix": "QR code for donations via Pix",
  "Aponte a câmera do celular para o QR ou use o botão abaixo para copiar o código e colar no app do banco em":
    "Point your phone camera at the QR code, or copy the code below and paste it in your bank app under",
  "Pix → Pix copia e cola": "Pix → Pix copy and paste",

  // ---- títulos das telas (topo) ----------------------------------------
  "O estado das suas pastas em uma olhada": "The state of your folders at a glance",
  "Navegue pela nuvem sem baixar nada": "Browse the cloud without downloading anything",
  "Escolha o que fica igual nos dois lados": "Pick what stays the same on both sides",
  "Envios, conflitos e erros em ordem": "Uploads, conflicts and errors in order",
  "Nada é sobrescrito sem você ver": "Nothing is overwritten without you seeing it",
  "Contas, banda e comportamento do app": "Accounts, bandwidth and app behavior",

  // ---- avisos (toasts) --------------------------------------------------
  "Histórico de atividade limpo.": "Activity history cleared.",
  "Sincronização retomada.": "Sync resumed.",
  "Sincronização iniciada.": "Sync started.",
  "Sincronização pausada.": "Sync paused.",
  "Adicione uma pasta antes de sincronizar.": "Add a folder before syncing.",
  "Pasta ativada.": "Folder enabled.",
  "Pasta desativada.": "Folder disabled.",
  "Pasta removida.": "Folder removed.",
  "Pasta adicionada. Sincronizando pela primeira vez…":
    "Folder added. Syncing for the first time…",
  "BrisaSync abrirá junto com o sistema.": "BrisaSync will start with the system.",
  "Início automático desativado.": "Autostart disabled.",
  "Conta “{nome}” removida.": "Account “{nome}” removed.",
  "Conta “{nome}” conectada.": "Account “{nome}” connected.",
  "Conflito resolvido: {arquivo}": "Conflict resolved: {arquivo}",
  "Limites salvos.": "Limits saved.",
  "Essa regra já existe.": "That rule already exists.",
  "Caminho copiado.": "Path copied.",
  "Não foi possível copiar.": "Could not copy.",

  // ---- paleta de comandos ----------------------------------------------
  "Ir para": "Go to",
  "Sincronização": "Sync",
  "Sistema": "System",
  "Sincronizar agora": "Sync now",
  "Retomar sincronização": "Resume sync",
  "Pausar tudo": "Pause all",
  "Adicionar pasta": "Add folder",
  "Conectar conta": "Connect account",
  "Sair do BrisaSync": "Quit BrisaSync",
  "Sair do BrisaSync?": "Quit BrisaSync?",
  "Sair e interromper": "Quit and stop syncing",
  "Continuar em segundo plano": "Keep running in the background",
  "A sincronização está rodando agora. Se o app for encerrado no meio, a próxima execução pode precisar refazer a comparação da pasta inteira.":
    "A sync is running right now. If the app quits in the middle, the next run may have to compare the whole folder again.",
  "Fechar a janela encerra o app": "Closing the window quits the app",
  "Desligado, a janela some e o BrisaSync continua sincronizando na bandeja.":
    "Left off, the window disappears and BrisaSync keeps syncing from the tray.",
  "Sair da janela interrompe a sincronização. O aviso da bandeja deixa de aparecer.":
    "Leaving the window stops syncing. The tray notice no longer appears.",

  // ---- visão geral ------------------------------------------------------
  "Sincronização pausada": "Sync paused",
  "Sincronizando agora": "Syncing now",
  "Nada foi perdido: retome quando quiser.": "Nothing was lost: resume whenever you want.",
  "{n} tarefa em andamento": "{n} job running",
  "{n} tarefas em andamento": "{n} jobs running",
  "Última verificação {tempo}": "Last check {tempo}",
  "Adicione uma pasta para começar.": "Add a folder to get started.",
  "Retomar": "Resume",
  "Velocidade": "Speed",
  "Transferido": "Transferred",
  "Pastas ativas": "Active folders",
  "{a} de {b}": "{a} of {b}",
  "Na fila": "In the queue",
  "Verificando alterações…": "Checking for changes…",
  "Comparando arquivos locais e da nuvem.": "Comparing local and cloud files.",
  "Nada para transferir": "Nothing to transfer",
  "A sincronização está pausada.": "Syncing is paused.",
  "Todas as pastas ativas estão atualizadas.": "All active folders are up to date.",
  "Verificar novamente": "Check again",
  "faltam {tempo}": "{tempo} left",
  "Atividade recente": "Recent activity",
  "Ver tudo": "See all",
  "Nada por aqui ainda.": "Nothing here yet.",
  "Contas": "Accounts",
  "1 pasta": "1 folder",
  "{n} pastas": "{n} folders",
  "atenção": "attention",
  "conectada": "connected",
  "sem pasta": "no folder",
  "Remover conta": "Remove account",
  "Remover a conta {nome}": "Remove account {nome}",
  "Nenhuma conta ainda": "No accounts yet",
  "Conecte Google Drive, OneDrive, Dropbox ou Nextcloud para começar.":
    "Connect Google Drive, OneDrive, Dropbox, or Nextcloud to get started.",
  "Armazenamento": "Storage",
  "Conecte uma conta para ver a cota.": "Connect an account to see the quota.",
  "Lendo a cota…": "Reading the quota…",
  "não consegui ler agora": "could not read it now",
  "lendo…": "reading…",
  "desatualizada": "out of date",
  "tentar de novo": "try again",
  "{n}% usado": "{n}% used",
  "Gerenciar": "Manage",
  "Nenhuma pasta ativa.": "No active folders.",
  "erro": "error",
  "ressincronizar": "resync",
  "em dia": "up to date",
  "Sincronizar esta pasta": "Sync this folder",
  "Sincronizar {pasta}": "Sync {pasta}",
  "Remover {nome}?": "Remove {nome}?",
  "Abrir Pastas": "Open Folders",
  "O BrisaSync apaga as credenciais desta conta do rclone neste computador. Nada é apagado na nuvem nem no disco.":
    "BrisaSync deletes this account's credentials from rclone on this computer. Nothing is deleted in the cloud or on disk.",
  "Esta conta ainda tem pasta configurada. Remova a pasta antes para não deixar um par de sincronização apontando para uma conta que não existe.":
    "This account still has a folder set up. Remove the folder first so no sync pair points at an account that no longer exists.",
  "Para voltar depois, é só conectar de novo (o navegador abre para a autorização).":
    "To come back later, just connect again (the browser opens for authorization).",

  // ---- conectar conta / adicionar pasta ---------------------------------
  "Nome da conta (opcional)": "Account name (optional)",
  "Endereço do servidor": "Server URL",
  "Usuário": "Username",
  "Senha de aplicativo": "App password",
  "Gere uma senha de aplicativo em Segurança nas configurações da sua conta Nextcloud.":
    "Generate an app password under Security in your Nextcloud account settings.",
  "É o nome que aparece no BrisaSync e no rclone. Pode ser qualquer apelido.":
    "This is the name shown in BrisaSync and in rclone. Any nickname works.",
  "A autorização acontece no navegador. O BrisaSync nunca vê sua senha.":
    "Authorization happens in your browser. BrisaSync never sees your password.",
  "Aguardando a autorização no navegador — {tempo} de {prazo}.":
    "Waiting for authorization in the browser — {tempo} of {prazo}.",
  "Esta caixa fecha sozinha ao concluir. Se o navegador não abriu, clique em Cancelar e tente de novo.":
    "This dialog closes by itself when done. If the browser did not open, click Cancel and try again.",
  "O Google ainda não verificou este app: na tela do Google, clique em “Continuar”. Se aparecer “acesso bloqueado” por limite de usuários, use um projeto OAuth seu em Ajustes → Avançado.":
    "Google has not verified this app yet: on the Google screen, click “Continue”. If you see “access blocked” because of the user limit, use your own OAuth project in Settings → Advanced.",
  "Como contornar":
    "How to work around it",
  "Aguardando autorização…": "Waiting for authorization…",
  "Conectar": "Connect",
  "No navegador, digite o caminho manualmente.": "In the browser, type the path manually.",
  "Escolha a pasta local": "Choose the local folder",
  "Conecte uma conta primeiro.": "Connect an account first.",
  "Escolha a pasta local.": "Choose the local folder.",
  "Pasta na nuvem": "Cloud folder",
  "Projetos (vazio = raiz da conta)": "Projects (empty = account root)",
  "Escolha na lista ou digite o caminho (vazio = raiz da conta).":
    "Pick from the list or type the path (empty = account root).",
  "Subir um nível": "Go up one level",
  "Início": "Home",
  "Usar {caminho}": "Use {caminho}",
  "Usar a raiz da conta": "Use the account root",
  "Usar “{pasta}”": "Use “{pasta}”",
  "Usar a raiz": "Use the root",
  "Lendo a nuvem…": "Reading the cloud…",
  "Nenhuma subpasta aqui.": "No subfolders here.",
  "Entrar em {pasta}": "Open {pasta}",
  "Entrar": "Open",
  "Pasta local": "Local folder",
  "/home/você/Nuvem/Projetos": "/home/you/Cloud/Projects",
  "A pasta é criada se não existir.": "The folder is created if it does not exist.",

  // ---- pastas -----------------------------------------------------------
  "Pastas sincronizadas": "Synced folders",
  "Cada pasta liga uma pasta da nuvem a uma pasta local.":
    "Each folder links a cloud folder to a local folder.",
  "Conecte uma conta antes de escolher pastas.": "Connect an account before choosing folders.",
  "Nenhuma pasta ainda": "No folders yet",
  "Escolha uma pasta na nuvem e uma pasta local. O BrisaSync mantém as duas iguais, nos dois sentidos.":
    "Pick a cloud folder and a local folder. BrisaSync keeps both identical, in both directions.",
  "Raiz da conta": "Account root",
  "Clique para Ressincronizar: aceita o estado atual das duas pastas e refaz a base de comparação.":
    "Click to Resync: it accepts the current state of both folders and rebuilds the comparison baseline.",
  "{erro} — Ressincronizar {pasta}": "{erro} — Resync {pasta}",
  "desativada": "disabled",
  "precisa ressincronizar": "needs resync",
  "em dia · {tempo}": "up to date · {tempo}",
  "Abrir pasta local": "Open local folder",
  "Abrir {caminho}": "Open {caminho}",
  "Desativar": "Disable",
  "Ativar": "Enable",
  "Desativar pasta": "Disable folder",
  "Ativar pasta": "Enable folder",
  "Remover {pasta}": "Remove {pasta}",
  "O modo": "The",
  "compara os dois lados e propaga as mudanças. Ao alterar caminhos, a próxima execução faz uma ressincronização completa.":
    "mode compares both sides and propagates changes. When you change paths, the next run does a full resync.",
  "Remover pasta?": "Remove folder?",
  "A pasta local": "The local folder",
  "não será apagada nem enviada. Apenas o par de sincronização sai do BrisaSync.":
    "will not be deleted or uploaded. Only the sync pair is removed from BrisaSync.",
  "Sincronização seletiva": "Selective sync",
  "Escolher subpastas": "Choose subfolders",
  "{n} subpasta ignorada": "{n} subfolder excluded",
  "{n} subpastas ignoradas": "{n} subfolders excluded",
  "Desmarque as subpastas que não devem ser baixadas para este computador.":
    "Uncheck subfolders that should not be downloaded to this computer.",
  "Nenhuma subpasta encontrada aqui.": "No subfolders found here.",
  "Raiz da pasta": "Folder root",
  "Salvar seleção": "Save selection",
  "Seleção salva. A próxima sincronização aplicará os filtros.":
    "Selection saved. The next sync will apply the filters.",

  // ---- arquivos ---------------------------------------------------------
  "Enviar arquivos para a nuvem": "Upload files to the cloud",
  "Enviando {atual} de {total}…": "Uploading {atual} of {total}…",
  "Solte aqui para enviar para {conta}:{caminho}": "Drop here to upload to {conta}:{caminho}",
  "Arquivos e pastas serão enviados para a pasta aberta.":
    "Files and folders will be uploaded to the open folder.",
  "Enviado para {conta}:{caminho}.": "Uploaded to {conta}:{caminho}.",
  "{n} arquivos enviados para {conta}:{caminho}.": "{n} files uploaded to {conta}:{caminho}.",
  "Demonstração: {caminho} entrou na lista.": "Demo: {caminho} was added to the list.",
  "Escolha a pasta para baixar": "Choose the folder to download to",
  "Baixado para {caminho}": "Downloaded to {caminho}",
  "Conecte uma conta para navegar": "Connect an account to browse",
  "Seus arquivos aparecem aqui sem precisar baixar nada antes.":
    "Your files show up here without downloading anything first.",
  "Filtrar nesta pasta": "Filter this folder",
  "Filtrar arquivos": "Filter files",
  "Enviar arquivos desta pasta do computador": "Upload files from this computer into this folder",
  "Enviar": "Upload",
  "Atualizar": "Refresh",
  "Atualizar listagem": "Refresh listing",
  "1 item": "1 item",
  "{n} itens": "{n} items",
  " · {n} sem tamanho informado": " · {n} without a reported size",
  "Listando {conta}:{caminho}": "Listing {conta}:{caminho}",
  "Nada encontrado": "Nothing found",
  "Pasta vazia": "Empty folder",
  "Nenhum item corresponde a “{busca}”.": "No item matches “{busca}”.",
  "Esta pasta não tem arquivos na nuvem. Você pode enviar um agora.":
    "This folder has no files in the cloud. You can upload one now.",
  "Tamanho": "Size",
  "Modificado": "Modified",
  "Ações": "Actions",
  "Baixar para o computador": "Download to this computer",
  "Baixar arquivo": "Download file",
  "Copiar caminho": "Copy path",
  "Enviar e baixar arquivos avulsos não substitui uma pasta de sincronização: para manter tudo igual nos dois lados, crie um par em":
    "Uploading and downloading individual files is no substitute for a sync folder: to keep both sides identical, create a pair in",
  "Voltar um nível": "Go up one level",

  // ---- atividade --------------------------------------------------------
  "Tudo": "All",
  "Envios": "Uploads",
  "Downloads": "Downloads",
  "Erros": "Errors",
  "Apagar todo o histórico": "Delete the whole history",
  "Limpar": "Clear",
  "Nada registrado": "Nothing recorded",
  "As sincronizações, conflitos e erros aparecem aqui em ordem.":
    "Syncs, conflicts and errors show up here in order.",
  "ocultar": "hide",
  "ver arquivos": "see files",
  "Pasta:": "Folder:",
  "Limpar a atividade?": "Clear the activity?",
  "Limpando…": "Clearing…",
  "Limpar tudo": "Clear everything",
  "O histórico de envios, downloads, conflitos e erros é apagado deste computador. Os arquivos não são tocados — nem aqui, nem na nuvem.":
    "The history of uploads, downloads, conflicts and errors is erased from this computer. The files are not touched — not here, not in the cloud.",
  "São {n} registros. As próximas sincronizações voltam a aparecer normalmente.":
    "That is {n} entries. The next syncs show up normally again.",
  "São 1 registro. As próximas sincronizações voltam a aparecer normalmente.":
    "That is 1 entry. The next syncs show up normally again.",

  // ---- rótulos de arquivos (lib/files.ts) -------------------------------
  enviado: "sent",
  enviados: "sent",
  baixado: "downloaded",
  baixados: "downloaded",
  "apagado na nuvem": "deleted in the cloud",
  "apagados na nuvem": "deleted in the cloud",
  "apagado aqui": "deleted here",
  "apagados aqui": "deleted here",

  // ---- conflitos --------------------------------------------------------
  "Conflitos de sincronização": "Sync conflicts",
  "O bisync guarda as duas versões com os sufixos": "bisync keeps both versions with the suffixes",
  e: "and",
  "Verificar de novo": "Check again",
  "Verificando…": "Checking…",
  "Nenhum conflito": "No conflicts",
  "Quando o mesmo arquivo muda dos dois lados, o BrisaSync avisa aqui em vez de escolher sozinho.":
    "When the same file changes on both sides, BrisaSync tells you here instead of choosing by itself.",
  "Na nuvem": "In the cloud",
  "Neste computador": "On this computer",
  "versão não encontrada": "version not found",
  "Abrir pasta": "Open folder",
  "Manter da nuvem": "Keep the cloud version",
  "Manter a minha": "Keep mine",
  "Manter as duas": "Keep both",
  "Manter a versão da nuvem?": "Keep the cloud version?",
  "Manter a versão deste computador?": "Keep this computer's version?",
  "Manter as duas versões?": "Keep both versions?",
  "A cópia deste computador vai para a pasta “conflitos-resolvidos” da configuração do BrisaSync. Nada é apagado, e a versão da nuvem volta ao nome original.":
    "This computer's copy goes to the “conflitos-resolvidos” folder in BrisaSync's configuration. Nothing is deleted, and the cloud version returns to the original name.",
  "A cópia da nuvem vai para a pasta “conflitos-resolvidos” da configuração do BrisaSync. Nada é apagado, e a versão local volta ao nome original.":
    "The cloud copy goes to the “conflitos-resolvidos” folder in BrisaSync's configuration. Nothing is deleted, and the local version returns to the original name.",
  "As duas cópias continuam na pasta, renomeadas com “(nuvem)” e “(local)”. O próximo bisync envia o resultado para a nuvem.":
    "Both copies stay in the folder, renamed with “(nuvem)” and “(local)”. The next bisync sends the result to the cloud.",
  "Resolver": "Resolve",
  "A versão descartada fica guardada em “conflitos-resolvidos” dentro da configuração do BrisaSync.":
    "The discarded version is kept in “conflitos-resolvidos” inside BrisaSync's configuration.",

  // ---- ajustes ----------------------------------------------------------
  "Nenhuma conta conectada.": "No account connected.",
  "Autorizada com o seu projeto OAuth": "Authorized with your OAuth project",
  "cota própria": "own quota",
  "Autorizada com o projeto OAuth do BrisaSync":
    "Authorized with the BrisaSync OAuth project",
  "cota do Nuvem": "Nuvem quota",
  "Autorizada no projeto OAuth compartilhado do rclone, de antes desta versão: reconecte a conta (em Avançado) para usar a cota do BrisaSync.":
    "Authorized on rclone's shared OAuth project, from before this version: reconnect the account (under Advanced) to use the BrisaSync quota.",
  "projeto antigo · reconectar": "old project · reconnect",
  "Motor de sincronização": "Sync engine",
  "não encontrado": "not found",
  "indisponível": "unavailable",
  "Modo bisync": "Bisync mode",
  "Duas vias, com ressincronização automática ao mudar caminhos.":
    "Two-way, with automatic resync when paths change.",
  ativo: "active",
  "Você está no modo demonstração (navegador).": "You are in demo mode (browser).",
  "Instale o rclone ou defina NUVEM_RCLONE.": "Install rclone or set NUVEM_RCLONE.",
  "Banda e regras": "Bandwidth and rules",
  "Limite de envio": "Upload limit",
  "Vazio = sem limite. Ex.: 5M, 800k.": "Empty = no limit. E.g.: 5M, 800k.",
  "Limite de download": "Download limit",
  "Aplicado na próxima sincronização.": "Applied on the next sync.",
  "Salvar limites": "Save limits",
  "Regras de ignorar": "Ignore rules",
  "Remover regra {regra}": "Remove rule {regra}",
  "nova regra, ex.: *.iso": "new rule, e.g.: *.iso",
  "Nova regra de ignorar": "New ignore rule",
  "Idioma": "Language",
  "Vale na hora, sem reiniciar o app.": "Applies right away, no restart needed.",
  Português: "Portuguese",
  English: "English",
  "Português (Brasil)": "Portuguese (Brazil)",
  "Inglês": "English",
  Tema: "Theme",
  "Segue sua preferência neste computador.": "Follows your preference on this computer.",
  Claro: "Light",
  Escuro: "Dark",
  "Notificações": "Notifications",
  "Avisar sobre conflitos e falhas.": "Warn about conflicts and failures.",
  "Sincronizar sozinho": "Sync on its own",
  "Verifica as pastas e envia mudanças locais sem você pedir. Reage a arquivos novos em segundos e confere a nuvem no intervalo escolhido.":
    "Checks the folders and uploads local changes without being asked. Reacts to new files within seconds and checks the cloud at the chosen interval.",
  "Sincronizar automaticamente": "Sync automatically",
  "Conferir a nuvem a cada": "Check the cloud every",
  "Mudanças locais entram na hora; este intervalo pega o que mudou do outro lado.":
    "Local changes go in right away; this interval picks up what changed on the other side.",
  "Intervalo da sincronização automática": "Automatic sync interval",
  "1 minuto": "1 minute",
  "5 minutos": "5 minutes",
  "15 minutos": "15 minutes",
  "30 minutos": "30 minutes",
  "1 hora": "1 hour",
  "Tentar de novo sozinho": "Retry on its own",
  "Repete a sincronização até 3 vezes (15 s, 60 s, 180 s) quando a falha parece ser de rede ou de limite do provedor.":
    "Repeats the sync up to 3 times (15 s, 60 s, 180 s) when the failure looks like a network or provider limit problem.",
  "Repetir falhas transitórias": "Retry transient failures",
  "Abrir com o sistema": "Start with the system",
  "Aguardando o sistema confirmar…": "Waiting for the system to confirm…",
  "Inicia minimizado na bandeja.": "Starts minimized in the tray.",
  "Iniciar com o sistema": "Start with the system",
  "Configuração": "Configuration",
  "Perfis e histórico do BrisaSync.": "BrisaSync profiles and history.",
  "Abrindo {caminho}": "Opening {caminho}",
  "Interrompe a sincronização até abrir de novo.": "Stops syncing until you open it again.",
  Sair: "Quit",
  "Avançado · Google Drive": "Advanced · Google Drive",
  "seu projeto": "your project",
  "projeto do BrisaSync": "BrisaSync project",
  "projeto do rclone": "rclone project",
  "O Google cobra a cota de requisições por minuto no projeto OAuth usado na autorização. O projeto compartilhado do rclone é usado por todos os usuários dele e vive estourado — daí a sincronização arrastar mesmo com banda sobrando.":
    "Google charges the requests-per-minute quota to the OAuth project used for authorization. rclone's shared project is used by all of its users and is always maxed out — which is why sync crawls even with bandwidth to spare.",
  "Projeto em uso": "Project in use",
  "sem client_id (projeto compartilhado do rclone)":
    "no client_id (rclone's shared project)",
  "Este build já usa o projeto OAuth do próprio BrisaSync: a cota é do aplicativo e não a do rclone. Preencha os campos abaixo só se quiser usar um projeto seu.":
    "This build already uses BrisaSync's own OAuth project: the quota belongs to the app, not to rclone. Fill in the fields below only if you want to use a project of your own.",
  "As contas Google deste computador usam o projeto que você colou abaixo.":
    "The Google accounts on this computer use the project you pasted below.",
  "Sem projeto próprio, a cota é a do projeto compartilhado do rclone. Crie o seu para a fila ser só sua.":
    "Without your own project, the quota is rclone's shared project. Create yours so the queue is only yours.",
  "1. Crie um projeto no Google Cloud, ative a Drive API e configure a tela de consentimento. 2. Em Credenciais, crie um ID do cliente OAuth do tipo app para computador. 3. Cole aqui os dois valores.":
    "1. Create a project in Google Cloud, enable the Drive API and set up the consent screen. 2. Under Credentials, create an OAuth client ID of type desktop app. 3. Paste both values here.",
  "As contas Google já conectadas continuam no projeto do rclone: remova as pastas que usam a conta, remova a conta em Visão geral → Contas e conecte de novo. O navegador pede a autorização uma vez.":
    "Google accounts already connected stay on the rclone project: remove the folders that use the account, remove the account under Overview → Accounts and connect again. The browser asks for authorization once.",
  "Contas conectadas antes desta mudança só passam a usar as credenciais novas depois de removidas e conectadas de novo.":
    "Accounts connected before this change only use the new credentials after being removed and connected again.",
  "Fica salvo em": "Saved in",
  ", neste computador, do mesmo jeito que o rclone guarda os tokens. Projeto no modo Testing do Google expira a autorização em 7 dias; publicar o app evita reautorizar toda semana.":
    " on this computer, the same way rclone stores tokens. A project in Google's Testing mode expires authorization in 7 days; publishing the app avoids reauthorizing every week.",
  "Preencha o client_id e o client_secret juntos — ou deixe os dois em branco.":
    "Fill in client_id and client_secret together — or leave both blank.",
  "O client_id do Google termina em .apps.googleusercontent.com.":
    "Google's client_id ends with .apps.googleusercontent.com.",
  "Credenciais salvas. As contas conectadas agora precisam ser autorizadas de novo.":
    "Credentials saved. Connected accounts now need to be authorized again.",
  "Credenciais apagadas. O Google Drive volta a usar o projeto do BrisaSync.":
    "Credentials deleted. Google Drive goes back to using the BrisaSync project.",
  "Credenciais apagadas. O Google Drive volta a usar o projeto do rclone.":
    "Credentials deleted. Google Drive goes back to using the rclone project.",
  "Ocultar segredo": "Hide secret",
  "Mostrar segredo": "Show secret",
  Ocultar: "Hide",
  Mostrar: "Show",
  Sobre: "About",
  "Atualizações": "Updates",
  "Atualizar agora": "Update now",
  "Baixando…": "Downloading…",
  "Atualização baixada em {caminho}": "Update downloaded to {caminho}",
  "A versão {versao} já está publicada.": "Version {versao} is already published.",
  "Consulta a última versão publicada no repositório do projeto.":
    "Checks the latest version published in the project repository.",
  "A versão {versao} está disponível.": "Version {versao} is available.",
  "Você está na versão mais nova.": "You are on the newest version.",
  Baixar: "Download",
  "Procurando…": "Checking…",
  Verificar: "Check",
  "Relatório de diagnóstico": "Diagnostics report",
  "Contas, pastas, ajustes e os últimos erros num arquivo de texto — sem senhas nem tokens. Útil ao abrir um problema no projeto.":
    "Accounts, folders, settings and the latest errors in a text file — no passwords or tokens. Useful when opening an issue in the project.",
  "Relatório salvo em {caminho}": "Report saved to {caminho}",
  Privacidade: "Privacy",
  "Credenciais ficam na configuração local do rclone. O BrisaSync não envia dados para servidores próprios.":
    "Credentials stay in rclone's local configuration. BrisaSync does not send data to servers of its own.",

  // ---- atividade gerada pelo backend (títulos fixos) --------------------
  "Sincronização concluída": "Sync finished",
  "Falha na sincronização": "Sync failed",
  "Falha": "Failure",
  "Falha ao retomar": "Could not resume",
  "Conta conectada": "Account connected",
  "Conta removida": "Account removed",
  "Pasta adicionada": "Folder added",
  "Trava antiga do bisync removida": "Old bisync lock removed",
  "Ressincronização iniciada": "Resync started",
  "Configuração recuperada": "Configuration recovered",
  "Conta OneDrive reconfigurada": "OneDrive account reconfigured",
  "Nova tentativa agendada": "Retry scheduled",
  "Não foi possível repetir": "Could not retry",
  "Sincronização automática": "Automatic sync",
  "Todas as tarefas foram paradas.": "All jobs were stopped.",
  "As pastas ativas voltaram a sincronizar.": "Active folders are syncing again.",
  "mantida a versão da nuvem": "kept the cloud version",
  "mantida a versão local": "kept the local version",
  "mantidas as duas versões": "kept both versions",
  // títulos usados só pelo backend de demonstração (navegador)
  "3 arquivos enviados": "3 files uploaded",
  "Conflito detectado": "Conflict detected",
  "Todas as pastas ativas estão em dia.": "All active folders are up to date.",
};

export type ChaveDeTraducao = keyof typeof EN;
export { EN as DICIONARIO_EN };
