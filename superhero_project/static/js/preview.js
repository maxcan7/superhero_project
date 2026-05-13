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

async function renderPreview(source, pane) {
  pane.classList.add("loading");
  pane.textContent = "Rendering…";

  const resp = await fetch("/articles/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: source }),
  });

  if (!resp.ok) {
    pane.textContent = "Preview unavailable.";
    pane.classList.remove("loading");
    return;
  }

  pane.innerHTML = await resp.text();
  pane.classList.remove("loading");
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function initPreview() {
  const input = document.getElementById("editor-input");
  const pane = document.getElementById("preview-pane");
  if (!input || !pane) return;

  const debouncedRender = debounce(
    (source) => renderPreview(source, pane),
    DEBOUNCE_MS,
  );

  input.addEventListener("input", (e) => debouncedRender(e.target.value));

  // Render initial content if the textarea is pre-populated (e.g. edit form).
  if (input.value.trim()) {
    renderPreview(input.value, pane);
  }
}

document.addEventListener("DOMContentLoaded", initPreview);
