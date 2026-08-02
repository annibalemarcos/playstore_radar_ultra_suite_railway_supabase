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

(function () {
  const statusOrder = {
    running: 90,
    queued: 80,
    pause_requested: 70,
    paused: 68,
    cancel_requested: 60,
    restart_requested: 58,
    delete_requested: 56,
    finished_with_warnings: 45,
    finished: 40,
    failed: 20,
    cancelled: 10,
    deleted: 0
  };
  const sortState = new WeakMap();

  function normalizeText(value) {
    return (value || '').toString().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  function numberValue(value) {
    if (value === null || value === undefined || value === '') return Number.NEGATIVE_INFINITY;
    const cleaned = String(value).replace(/[^\d,.-]/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.');
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
  }

  function sortValue(row, key, type) {
    const dataValue = row.getAttribute(`data-sort-${key}`);
    const cell = row.querySelector(`[data-sort-key="${key}"]`);
    const value = dataValue ?? cell?.getAttribute('data-sort-value') ?? cell?.textContent ?? '';
    if (type === 'number') return numberValue(value);
    if (type === 'status') return statusOrder[normalizeText(value)] ?? -1;
    if (type === 'date') return normalizeText(value);
    return normalizeText(value);
  }

  function setHeaderState(table, key, dir) {
    table.querySelectorAll('[data-sort-key]').forEach((button) => {
      const active = button.dataset.sortKey === key;
      button.classList.toggle('active', active);
      button.dataset.sortDir = active ? dir : '';
      button.setAttribute('aria-sort', active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none');
    });
  }

  function sortTable(table, key, type, dir) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr[data-sort-row]'));
    rows.sort((a, b) => {
      const av = sortValue(a, key, type);
      const bv = sortValue(b, key, type);
      let result = 0;
      if (type === 'number' || type === 'status') result = av - bv;
      else result = String(av).localeCompare(String(bv), 'pt-BR', { numeric: true, sensitivity: 'base' });
      if (result === 0) {
        result = numberValue(a.getAttribute('data-sort-id')) - numberValue(b.getAttribute('data-sort-id'));
      }
      return dir === 'asc' ? result : -result;
    });
    rows.forEach((row) => tbody.appendChild(row));
    sortState.set(table, { key, type, dir });
    setHeaderState(table, key, dir);
  }

  function urlParamNames(table) {
    const prefix = table.dataset.sortParamPrefix || '';
    return {
      sort: prefix ? `${prefix}_sort` : 'sort',
      dir: prefix ? `${prefix}_dir` : 'dir'
    };
  }

  function syncSortUrl(table, key, dir) {
    if (table.dataset.sortPersist === 'off') return;
    const params = new URLSearchParams(window.location.search);
    const names = urlParamNames(table);
    params.set(names.sort, key);
    params.set(names.dir, dir);
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
    window.history.replaceState(null, '', nextUrl);
  }

  function restoreSort(table) {
    if (table.dataset.sortPersist === 'off') return;
    const params = new URLSearchParams(window.location.search);
    const names = urlParamNames(table);
    const key = params.get(names.sort);
    if (!key) return;
    const escapeCss = window.CSS?.escape || ((value) => value.replace(/["\\]/g, '\\$&'));
    const button = table.querySelector(`[data-sort-key="${escapeCss(key)}"]`);
    if (!button) return;
    const type = button.dataset.sortType || 'text';
    const dir = params.get(names.dir) || button.dataset.sortDefault || (type === 'text' ? 'asc' : 'desc');
    sortTable(table, key, type, dir === 'asc' ? 'asc' : 'desc');
  }

  function bindTable(table) {
    table.querySelectorAll('[data-sort-key]').forEach((button) => {
      button.addEventListener('click', () => {
        const previous = sortState.get(table);
        const key = button.dataset.sortKey;
        const type = button.dataset.sortType || 'text';
        const defaultDir = button.dataset.sortDefault || (type === 'text' ? 'asc' : 'desc');
        const dir = previous?.key === key ? (previous.dir === 'asc' ? 'desc' : 'asc') : defaultDir;
        sortTable(table, key, type, dir);
        syncSortUrl(table, key, dir);
      });
    });
    restoreSort(table);
  }

  document.querySelectorAll('[data-sortable-table]').forEach(bindTable);
  window.PlayRadarSort = {
    refresh(table) {
      if (!table) return;
      const previous = sortState.get(table);
      if (previous) sortTable(table, previous.key, previous.type, previous.dir);
    },
    sort: sortTable
  };
})();
