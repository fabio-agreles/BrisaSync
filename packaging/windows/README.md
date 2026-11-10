# Distribuição do BrisaSync para Windows x64

Este diretório contém os scripts de automação e configuração para geração dos pacotes Windows x64 (Instalador NSIS e Pacote Portátil .zip).

---

## 1. Artefatos Produzidos

1. **Instalador Oficial (`BrisaSync-0.1.26-Setup-x64.exe`)**:
   - Instalação limpa por usuário em `%LOCALAPPDATA%\Programs\BrisaSync` (sem necessidade de elevação de privilégios ou prompts de Administrador/UAC).
   - Criação de atalhos no Menu Iniciar e na Área de Trabalho.
   - Opção de autoinício com o Windows via Registro (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
   - Desinstalador limpo que remove binários e atalhos, **preservando rigorosamente** as configurações em `%APPDATA%\BrisaSync` e todos os arquivos sincronizados nas pastas locais.
2. **Pacote Portátil (`BrisaSync-0.1.26-windows-x64.zip`)**:
   - Standalone, pronto para descompactar e executar em qualquer pasta sem instalação formal.

---

## 2. Aviso sobre Assinatura Digital e Microsoft SmartScreen

> [!NOTE]
> O BrisaSync é um software livre e de código aberto disponibilizado gratuitamente. Certificados comerciais de assinatura de código EV (Extended Validation) exigem taxas anuais corporativas elevadas.
>
> Por essa razão, os executáveis são distribuídos sem certificado corporativo pago. Ao executar o instalador ou aplicativo pela primeira vez no Windows 10/11, o filtro Microsoft Defender SmartScreen poderá exibir a tela *"O Windows protegeu o seu computador - Aplicativo não reconhecido"*.
>
> Para continuar:
> 1. Clique em **"Mais informações"** (*More info*).
> 2. Clique em **"Executar assim mesmo"** (*Run anyway*).
>
> A integridade criptográfica de cada arquivo pode ser conferida contra o arquivo oficial `SHA256SUMS.txt` publicado na release do GitHub.
