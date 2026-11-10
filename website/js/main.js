/**
 * BrisaSync — JavaScript Institucional Mínimo
 * Recursos: Cópia Pix com acessibilidade (ARIA live), menu mobile e alternador de capturas
 * Zero dependências externas / 100% vanilla
 */

(function () {
  'use strict';

  // 1. Menu Mobile
  const mobileToggle = document.querySelector('.mobile-toggle');
  const navMenu = document.querySelector('.nav-menu');

  if (mobileToggle && navMenu) {
    mobileToggle.addEventListener('click', function () {
      const isExpanded = mobileToggle.getAttribute('aria-expanded') === 'true';
      mobileToggle.setAttribute('aria-expanded', !isExpanded);
      navMenu.classList.toggle('open');
    });

    // Fechar menu ao clicar em um link
    navMenu.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        mobileToggle.setAttribute('aria-expanded', 'false');
        navMenu.classList.remove('open');
      });
    });
  }

  // 2. Cópia do Pix (Chave e Copia e Cola)
  const PIX_DATA = {
    key: 'e4bf0532-8016-42bf-bf2a-fd81326b6621',
    payload: '00020126580014BR.GOV.BCB.PIX0136e4bf0532-8016-42bf-bf2a-fd81326b66215204000053039865802BR5921FABIO AGRELES BEZERRA6009GARANHUNS62070503***63046D9B'
  };

  const copyKeyBtn = document.getElementById('btn-copy-pix-key');
  const copyPayloadBtn = document.getElementById('btn-copy-pix-payload');
  const copyFeedback = document.getElementById('pix-feedback');

  function handleCopy(text, btn, successMessage) {
    if (!navigator.clipboard) {
      // Fallback simples
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        showSuccess(btn, successMessage);
      } catch (err) {
        if (copyFeedback) copyFeedback.textContent = 'Não foi possível copiar automaticamente.';
      }
      document.body.removeChild(textArea);
      return;
    }

    navigator.clipboard.writeText(text).then(function () {
      showSuccess(btn, successMessage);
    }).catch(function () {
      if (copyFeedback) copyFeedback.textContent = 'Erro ao copiar para a área de transferência.';
    });
  }

  function showSuccess(btn, message) {
    const originalText = btn.innerHTML;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg> Copiado!`;
    btn.classList.add('copied');
    if (copyFeedback) {
      copyFeedback.textContent = message;
    }

    setTimeout(function () {
      btn.innerHTML = originalText;
      btn.classList.remove('copied');
      if (copyFeedback) {
        copyFeedback.textContent = '';
      }
    }, 2800);
  }

  if (copyKeyBtn) {
    copyKeyBtn.addEventListener('click', function () {
      handleCopy(PIX_DATA.key, copyKeyBtn, '✓ Chave Pix copiada com sucesso!');
    });
  }

  if (copyPayloadBtn) {
    copyPayloadBtn.addEventListener('click', function () {
      handleCopy(PIX_DATA.payload, copyPayloadBtn, '✓ Código Pix Copia e Cola copiado com sucesso!');
    });
  }

  // 3. Alternador de Capturas da Galeria (Showcase)
  const tabButtons = document.querySelectorAll('.gallery-nav .tab-btn');
  const galleryImage = document.getElementById('gallery-screenshot');
  const galleryCaption = document.getElementById('gallery-caption');

  if (tabButtons.length > 0 && galleryImage && galleryCaption) {
    tabButtons.forEach(function (button) {
      button.addEventListener('click', function () {
        tabButtons.forEach(function (btn) {
          btn.classList.remove('active');
          btn.setAttribute('aria-selected', 'false');
        });

        button.classList.add('active');
        button.setAttribute('aria-selected', 'true');

        const imgSrc = button.getAttribute('data-img');
        const imgAlt = button.getAttribute('data-alt');
        const captionText = button.getAttribute('data-caption');

        if (imgSrc) galleryImage.src = imgSrc;
        if (imgAlt) galleryImage.alt = imgAlt;
        if (captionText) galleryCaption.textContent = captionText;
      });
    });
  }
})();

