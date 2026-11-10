# BrisaSync — pacote de ícones

## Conteúdo
- master/brisasync-original.png: arte raster aprovada, 1254 × 1254, com transparência fora do bloco azul.
- hicolor/: PNGs RGBA em 16, 22, 24, 32, 48, 64, 96, 128, 256, 512 e 1024 px, no padrão de pastas de um tema de ícones Linux.
- tray/: adaptação simbólica vetorial desenhada para tamanhos pequenos; SVG com currentColor, SVG claro/escuro com cor fixa e PNGs de 16, 22, 24, 32 e 48 px.
- PREVIA.png: comparação visual em tamanho real e sobre fundos claro/escuro.
- PROMPT_ANTIGRAVITY.md: instrução de integração no projeto existente.
- SHA256SUMS.txt: checksums dos arquivos do pacote, exceto este próprio manifesto.

O ícone colorido é raster: não foi convertido para um falso SVG com PNG embutido. O SVG de bandeja é uma adaptação simplificada, e não o vetor original do ícone colorido. Os PNGs foram redimensionados com Lanczos e alfa pré-multiplicado para preservar as bordas.

## Integração
Incorpore os recursos ao pacote existente e garanta sua inclusão no build. O lançador pode usar Icon=brisasync quando os arquivos hicolor forem instalados pelo empacotamento. Não instale arquivos globalmente apenas para visualizar os ícones.

A versão dark tem desenho escuro para painel claro; light tem desenho claro para painel escuro. SVG currentColor depende do renderizador/tema: verifique o resultado no Qt efetivamente usado e mantenha os PNGs fixos como alternativa. Não presuma que o Qt recolorirá todo SVG automaticamente.

O pacote contém apenas recursos visuais, sem o código ou a base de projeto anteriormente descartados. Não altera o projeto no computador do usuário. Integração real com KDE/GNOME continua dependendo de teste nesses ambientes.

## Origem
Ícone principal criado por geração de imagem e escolhido pelo usuário. Adaptação vetorial de bandeja desenhada para este pacote. Não utiliza símbolos oficiais do Google.
