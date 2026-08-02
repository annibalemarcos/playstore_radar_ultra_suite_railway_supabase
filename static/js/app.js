console.log('PlayStore Radar Ultra carregado. Pequeno gafanhoto dos apps, bora garimpar.');


(function () {
  // Campo de busca livre por nome/termo: quando preenchido, escopo e categorias
  // ficam apagados (visualmente) porque a busca por termo os ignora.
  const searchQueryInput = document.getElementById('searchQueryInput');
  const scopeFieldWrap = document.getElementById('scopeFieldWrap');
  if (searchQueryInput && scopeFieldWrap) {
    const categoryWraps = [
      document.getElementById('appsCategoryWrap'),
      document.getElementById('gamesCategoryWrap')
    ].filter(Boolean);

    function updateSearchModeUI() {
      const active = searchQueryInput.value.trim().length > 0;
      scopeFieldWrap.classList.toggle('opacity-50', active);
      categoryWraps.forEach(el => el.classList.toggle('opacity-50', active));
    }

    searchQueryInput.addEventListener('input', updateSearchModeUI);
    updateSearchModeUI();
  }
})();

(function () {
  const scopeSelect = document.getElementById('scopeSelect');
  if (!scopeSelect) return;

  const wraps = {
    APPS: document.getElementById('appsCategoryWrap'),
    JOGOS: document.getElementById('gamesCategoryWrap')
  };

  function boxes(group) {
    return Array.from(document.querySelectorAll(`[data-category-group="${group}"]`));
  }

  function titleFor(group) {
    return document.querySelector(`[data-title-for="${group}"]`);
  }

  function masterFor(group) {
    return document.querySelector(`[data-master-for="${group}"]`);
  }

  function updateTitle(group) {
    const all = boxes(group);
    const selected = all.filter(cb => cb.checked);
    const title = titleFor(group);
    const master = masterFor(group);
    if (!title) return;
    const label = group === 'apps' ? 'apps' : 'jogos';

    if (selected.length === 0) {
      title.textContent = `Nenhuma marcada — padrão: todas de ${label}`;
    } else if (selected.length === all.length) {
      title.textContent = `Todas as categorias de ${label}`;
    } else if (selected.length === 1) {
      const text = selected[0].closest('label')?.querySelector('span')?.textContent?.trim() || '1 categoria';
      title.textContent = text;
    } else {
      title.textContent = `${selected.length} categorias selecionadas`;
    }

    if (master) {
      master.checked = selected.length === all.length;
      master.indeterminate = selected.length > 0 && selected.length < all.length;
    }
  }

  function subBoxes(group) {
    return Array.from(document.querySelectorAll(`[data-subcat-group="${group}"]`));
  }

  function syncSubcats(group) {
    subBoxes(group).forEach(sub => {
      const parentCode = sub.dataset.subcatParent;
      const parentCb = document.querySelector(`input[data-category-group="${group}"][value="${parentCode}"]`);
      const groupEnabled = parentCb ? !parentCb.disabled : true;
      sub.disabled = !groupEnabled || !(parentCb && parentCb.checked);
    });
  }

  function setGroupEnabled(group, enabled) {
    boxes(group).forEach(cb => { cb.disabled = !enabled; });
    const master = masterFor(group);
    if (master) master.disabled = !enabled;
    syncSubcats(group);
  }

  function updateScopeUI() {
    const scope = scopeSelect.value;
    Object.entries(wraps).forEach(([key, el]) => {
      if (!el) return;
      const visible = scope === key;
      el.classList.toggle('d-none', !visible);
      setGroupEnabled(key === 'APPS' ? 'apps' : 'games', visible);
    });
    // Em TODOS, nenhum checkbox de categoria é submetido. É busca geral, sem meias palavras.
    if (scope === 'TODAS') {
      setGroupEnabled('apps', false);
      setGroupEnabled('games', false);
    }
  }

  ['apps', 'games'].forEach(group => {
    const master = masterFor(group);
    if (master) {
      master.addEventListener('change', () => {
        boxes(group).forEach(cb => { cb.checked = master.checked; });
        updateTitle(group);
        syncSubcats(group);
      });
    }
    boxes(group).forEach(cb => cb.addEventListener('change', () => {
      updateTitle(group);
      syncSubcats(group);
    }));
    subBoxes(group).forEach(sub => sub.addEventListener('change', () => {
      // Marcar uma subcategoria implica marcar a categoria pai — senão ela nem entra na busca.
      if (sub.checked) {
        const parentCode = sub.dataset.subcatParent;
        const parentCb = document.querySelector(`input[data-category-group="${group}"][value="${parentCode}"]`);
        if (parentCb && !parentCb.checked) {
          parentCb.checked = true;
          updateTitle(group);
          syncSubcats(group);
        }
      }
    }));
    updateTitle(group);
    syncSubcats(group);
  });

  // Submenu (dropdown) de subcategorias: abre/fecha sem fechar o dropdown principal.
  document.querySelectorAll('[data-subcat-toggle]').forEach(btn => {
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const panel = document.getElementById(`subcat-${btn.dataset.subcatToggle}`);
      if (!panel) return;
      const isOpen = panel.classList.toggle('open');
      btn.classList.toggle('open', isOpen);
      btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
  });

  scopeSelect.addEventListener('change', updateScopeUI);
  updateScopeUI();
})();
