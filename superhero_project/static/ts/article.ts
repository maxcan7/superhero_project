(function () {
  const root = document.getElementById('article-root');
  if (!root) return;
  const id = root.dataset.identifier as string;

  // ── Votes ────────────────────────────────────────────────────────────────────
  const upBtn = document.getElementById('vote-up') as HTMLButtonElement | null;
  const downBtn = document.getElementById('vote-down') as HTMLButtonElement | null;
  const scoreEl = document.getElementById('vote-score') as HTMLElement | null;
  const voteBar = document.querySelector('.vote-bar') as HTMLElement | null;

  interface VoteState {
    userVote: 1 | -1 | null;
    upvotes: number;
    downvotes: number;
  }

  interface VoteResponse {
    upvotes: number;
    downvotes: number;
  }

  if (upBtn && downBtn && scoreEl && voteBar) {
    const raw = voteBar.dataset.userVote;
    const state: VoteState = {
      userVote: raw === '1' ? 1 : raw === '-1' ? -1 : null,
      upvotes: parseInt(scoreEl.dataset.upvotes ?? '0', 10),
      downvotes: parseInt(scoreEl.dataset.downvotes ?? '0', 10),
    };

    function applyVoteUI(): void {
      scoreEl!.textContent = String(state.upvotes - state.downvotes);
      upBtn!.textContent = `▲ ${state.upvotes}`;
      downBtn!.textContent = `▽ ${state.downvotes}`;
      upBtn!.classList.toggle('vote-btn--active', state.userVote === 1);
      downBtn!.classList.toggle('vote-btn--active', state.userVote === -1);
    }

    async function castVote(value: 1 | -1): Promise<VoteResponse | null> {
      const res = await fetch(`/votes/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      });
      return res.ok ? (res.json() as Promise<VoteResponse>) : null;
    }

    async function removeVote(): Promise<void> {
      await fetch(`/votes/${id}`, { method: 'DELETE' });
    }

    upBtn.addEventListener('click', async () => {
      if (state.userVote === 1) {
        await removeVote();
        state.upvotes -= 1;
        state.userVote = null;
      } else {
        const data = await castVote(1);
        if (!data) return;
        if (state.userVote === -1) state.downvotes -= 1;
        state.upvotes = data.upvotes;
        state.downvotes = data.downvotes;
        state.userVote = 1;
      }
      applyVoteUI();
    });

    downBtn.addEventListener('click', async () => {
      if (state.userVote === -1) {
        await removeVote();
        state.downvotes -= 1;
        state.userVote = null;
      } else {
        const data = await castVote(-1);
        if (!data) return;
        if (state.userVote === 1) state.upvotes -= 1;
        state.upvotes = data.upvotes;
        state.downvotes = data.downvotes;
        state.userVote = -1;
      }
      applyVoteUI();
    });
  }

  // ── Comments ─────────────────────────────────────────────────────────────────
  const commentList = document.getElementById('comment-list') as HTMLUListElement | null;
  const commentForm = document.getElementById('comment-form') as HTMLFormElement | null;

  interface CommentResponse {
    id: string;
    author_name: string;
    body: string;
    created_at: string;
  }

  function escHtml(str: string): string {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function bindCommentActions(li: HTMLElement): void {
    li.querySelector('.comment-edit-btn')?.addEventListener('click', () => {
      const bodyEl = li.querySelector('.comment-body') as HTMLElement;
      const original = bodyEl.textContent ?? '';
      bodyEl.style.display = 'none';

      const form = document.createElement('div');
      form.className = 'comment-edit-form';
      form.innerHTML = `
        <textarea class="comment-textarea">${escHtml(original)}</textarea>
        <div class="comment-edit-actions">
          <button class="btn btn-primary save-edit-btn">Save</button>
          <button class="btn btn-ghost cancel-edit-btn">Cancel</button>
        </div>`;
      li.insertBefore(form, li.querySelector('.comment-actions'));

      (form.querySelector('.cancel-edit-btn') as HTMLButtonElement).addEventListener('click', () => {
        bodyEl.style.display = '';
        form.remove();
      });

      (form.querySelector('.save-edit-btn') as HTMLButtonElement).addEventListener('click', async () => {
        const newBody = (form.querySelector('textarea') as HTMLTextAreaElement).value.trim();
        if (!newBody) return;
        const commentId = li.dataset.id as string;
        const res = await fetch(`/comments/${id}/${commentId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ body: newBody }),
        });
        if (res.ok) {
          bodyEl.textContent = newBody;
          bodyEl.style.display = '';
          form.remove();
        }
      });
    });

    li.querySelector('.comment-delete-btn')?.addEventListener('click', async () => {
      if (!confirm('Delete this comment?')) return;
      const commentId = li.dataset.id as string;
      const res = await fetch(`/comments/${id}/${commentId}`, { method: 'DELETE' });
      if (res.ok) {
        li.remove();
        const emptyEl = document.getElementById('comment-empty');
        if (emptyEl) return;
        if (commentList && !commentList.querySelector('.comment')) {
          const emptyLi = document.createElement('li');
          emptyLi.id = 'comment-empty';
          emptyLi.className = 'comment-empty';
          emptyLi.textContent = 'No comments yet.';
          commentList.appendChild(emptyLi);
        }
      }
    });
  }

  commentList?.querySelectorAll<HTMLElement>('.comment').forEach(bindCommentActions);

  if (commentForm && commentList) {
    commentForm.addEventListener('submit', async (e: Event) => {
      e.preventDefault();
      const textarea = commentForm.querySelector('textarea') as HTMLTextAreaElement;
      const body = textarea.value.trim();
      if (!body) return;
      const res = await fetch(`/comments/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body }),
      });
      if (!res.ok) return;
      const comment = (await res.json()) as CommentResponse;

      document.getElementById('comment-empty')?.remove();

      const li = document.createElement('li');
      li.className = 'comment';
      li.dataset.id = comment.id;
      const date = new Date(comment.created_at).toISOString().slice(0, 10);
      li.innerHTML = `
        <div class="comment-header">
          <span class="comment-author">${escHtml(comment.author_name)}</span>
          <span class="comment-date">${date}</span>
        </div>
        <div class="comment-body">${escHtml(comment.body)}</div>
        <div class="comment-actions">
          <button class="btn btn-ghost comment-edit-btn" data-id="${comment.id}">Edit</button>
          <button class="btn btn-ghost comment-delete-btn" data-id="${comment.id}">Delete</button>
        </div>`;
      commentList.appendChild(li);
      bindCommentActions(li);
      textarea.value = '';
    });
  }
})();
