(function () {
  const form = document.getElementById('editor-form') as HTMLFormElement | null;
  if (!form) return;

  const typeEl = document.getElementById('article-type') as HTMLInputElement | HTMLSelectElement | null;
  const pageNameGroup = document.getElementById('page-name-group') as HTMLElement | null;
  const metaFieldsets = document.querySelectorAll<HTMLElement>('.meta-fieldset');
  const errorEl = document.getElementById('editor-error') as HTMLElement | null;

  function showMetaFor(type: string): void {
    metaFieldsets.forEach((fs) => {
      fs.hidden = fs.id !== `meta-${type}`;
    });
    if (pageNameGroup) {
      pageNameGroup.hidden = !type;
    }
  }

  if (typeEl instanceof HTMLSelectElement) {
    typeEl.addEventListener('change', () => showMetaFor(typeEl.value));
    if (typeEl.value) showMetaFor(typeEl.value);
  } else if (typeEl) {
    showMetaFor(typeEl.value);
  }

  function parseList(val: string): string[] {
    return val.split(',').map((s) => s.trim()).filter(Boolean);
  }

  function collectMetadata(type: string): Record<string, unknown> {
    const fs = document.getElementById(`meta-${type}`);
    if (!fs) return {};
    const meta: Record<string, unknown> = {};
    fs.querySelectorAll<Element>('[data-meta]').forEach((el) => {
      const key = (el as HTMLElement).dataset.meta!;
      const isList = (el as HTMLElement).dataset.list === 'true';
      const val = (el as HTMLInputElement | HTMLSelectElement).value;
      if (isList) {
        meta[key] = parseList(val);
      } else if (el.tagName === 'SELECT') {
        meta[key] = val;
      } else {
        meta[key] = val.trim() || null;
      }
    });
    return meta;
  }

  form.addEventListener('submit', async (e: Event) => {
    e.preventDefault();
    if (errorEl) errorEl.hidden = true;

    const mode = form.dataset.mode as 'create' | 'edit';
    const identifier = form.dataset.identifier ?? '';
    const type = typeEl?.value ?? '';
    const content =
      (document.getElementById('editor-input') as HTMLTextAreaElement | null)?.value ?? '';
    const tagsRaw =
      (document.getElementById('article-tags') as HTMLInputElement | null)?.value ?? '';
    const tags = parseList(tagsRaw);
    const metadata = collectMetadata(type);

    let url: string;
    let method: string;
    let bodyObj: Record<string, unknown>;

    if (mode === 'create') {
      url = '/articles/';
      method = 'POST';
      const pageNameEl = document.getElementById('article-page-name') as HTMLInputElement | null;
      bodyObj = {
        article_type: type,
        page_name: pageNameEl?.value.trim() ?? '',
        metadata,
        content,
        tags,
      };
    } else {
      url = `/articles/${identifier}`;
      method = 'PUT';
      bodyObj = { metadata, content, tags };
    }

    const resp = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bodyObj),
    });

    if (!resp.ok) {
      if (errorEl) {
        errorEl.textContent = `Save failed (${resp.status} ${resp.statusText}).`;
        errorEl.hidden = false;
      }
      return;
    }

    const data = (await resp.json()) as { page_name: string };
    window.location.href = `/articles/${data.page_name}/view`;
  });
})();
