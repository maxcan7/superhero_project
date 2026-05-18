/**
 * Live Markdown preview for the article editor.
 *
 * Expects the page to contain:
 *   #editor-input  — <textarea> with the raw Markdown
 *   #preview-pane  — <div> where rendered HTML is injected
 *
 * Renders via POST /articles/render so output matches server-side rendering.
 */

const DEBOUNCE_MS = 300;

async function renderPreview(source: string, pane: HTMLElement): Promise<void> {
  pane.classList.add('loading');
  pane.textContent = 'Rendering…';

  const resp = await fetch('/articles/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: source }),
  });

  if (!resp.ok) {
    pane.textContent = 'Preview unavailable.';
    pane.classList.remove('loading');
    return;
  }

  pane.innerHTML = await resp.text();
  pane.classList.remove('loading');
}

function debounce<T extends unknown[]>(
  fn: (...args: T) => void,
  delay: number,
): (...args: T) => void {
  let timer: ReturnType<typeof setTimeout>;
  return (...args: T) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function initPreview(): void {
  const input = document.getElementById('editor-input') as HTMLTextAreaElement | null;
  const pane = document.getElementById('preview-pane') as HTMLElement | null;
  if (!input || !pane) return;

  const debouncedRender = debounce(
    (source: string) => renderPreview(source, pane),
    DEBOUNCE_MS,
  );

  input.addEventListener('input', (e) =>
    debouncedRender((e.target as HTMLTextAreaElement).value),
  );

  // Render initial content if the textarea is pre-populated (e.g. edit form).
  if (input.value.trim()) {
    renderPreview(input.value, pane);
  }
}

document.addEventListener('DOMContentLoaded', initPreview);
