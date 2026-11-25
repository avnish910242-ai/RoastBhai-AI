
/* ==========================================
   RoastBhai AI — Complete Frontend Script
   Chat + History + Responsive Sidebar
   ========================================== */

const $ = (selector) => document.querySelector(selector);

const input = $('#messageInput');
const form = $('#chatForm');
const messagesEl = $('#messages');
const historyEl = $('#historyList');
const welcomeEl = $('#welcome');
const chatScroll = $('#chatScroll');
const sendButton = $('#sendButton');

const appShell = $('#appShell');
const sidebar = $('#sidebar');
const scrim = $('#scrim');

const openSidebarBtn = $('#openSidebar');
const collapseSidebarBtn = $('#collapseSidebar');
const closeSidebarBtn = $('#closeSidebar');

let currentId = null;
let busy = false;
let toastTimer;

const isMobile = () => window.innerWidth <= 760;

/* ==========================================
   Toast
   ========================================== */

function toast(message) {
  const el = $('#toast');
  if (!el) return;

  el.textContent = message;
  el.classList.add('show');

  clearTimeout(toastTimer);

  toastTimer = setTimeout(() => {
    el.classList.remove('show');
  }, 2800);
}

/* ==========================================
   Helpers
   ========================================== */

function escapeText(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[c]));
}

function setStarted(started) {
  welcomeEl.hidden = started;
  document.body.classList.toggle('started', started);
}

function scrollBottom() {
  requestAnimationFrame(() => {
    chatScroll.scrollTop = chatScroll.scrollHeight;
  });
}

/* ==========================================
   Sidebar
   ========================================== */

function openSidebar() {
  if (isMobile()) {
    sidebar.classList.add('mobile-open');
    scrim.classList.add('show');
  } else {
    appShell.classList.remove('sidebar-collapsed');
  }
}

function closeSidebar() {
  sidebar.classList.remove('mobile-open');
  scrim.classList.remove('show');
}

function toggleSidebar() {
  if (isMobile()) {
    if (sidebar.classList.contains('mobile-open')) {
      closeSidebar();
    } else {
      openSidebar();
    }
    return;
  }

  appShell.classList.toggle('sidebar-collapsed');
}

openSidebarBtn?.addEventListener('click', openSidebar);

collapseSidebarBtn?.addEventListener('click', toggleSidebar);

closeSidebarBtn?.addEventListener('click', closeSidebar);

scrim?.addEventListener('click', closeSidebar);

window.addEventListener('resize', () => {
  if (!isMobile()) {
    closeSidebar();
  } else {
    appShell.classList.remove('sidebar-collapsed');
  }
});

/* ==========================================
   Message Rendering
   ========================================== */

function addMessage(role, text, { error = false, copy = false } = {}) {
  const row = document.createElement('div');
  row.className = `message-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'assistant' ? 'R' : 'Y';

  const body = document.createElement('div');
  body.className = `message-content${error ? ' error-message' : ''}`;

  // Keep plain text rendering safe.
  body.textContent = text;

  row.append(avatar, body);

  if (role === 'assistant' && copy) {
    const actions = document.createElement('div');
    actions.className = 'message-actions';

    const button = document.createElement('button');
    button.className = 'copy-btn';
    button.type = 'button';
    button.textContent = '▢ Copy';

    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(text);
        toast('Copied to clipboard');
      } catch {
        toast('Could not copy this message');
      }
    });

    actions.append(button);
    body.append(actions);
  }

  messagesEl.append(row);
  scrollBottom();

  return row;
}

/* ==========================================
   Busy State
   ========================================== */

function setBusy(value) {
  busy = value;

  sendButton.disabled = value || !input.value.trim();
  input.disabled = value;
}

/* ==========================================
   API
   ========================================== */

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const error = new Error(
      data.detail || 'Something went wrong. Please try again.'
    );

    error.conversationId =
      response.headers.get('X-Conversation-Id');

    throw error;
  }

  return data;
}

/* ==========================================
   Chat History
   ========================================== */

async function refreshHistory() {
  try {
    const chats = await api('/api/conversations');

    historyEl.replaceChildren();

    if (!chats.length) {
      const hint = document.createElement('div');

      hint.className = 'history-empty';
      hint.textContent = 'Your chats will show up here.';

      historyEl.append(hint);
      return;
    }

    chats.forEach(chat => {
      const item = document.createElement('div');

      item.className =
        `history-item${chat.id === currentId ? ' active' : ''}`;

      const icon = document.createElement('span');
      icon.className = 'chat-icon';
      icon.textContent = '◌';

      const title = document.createElement('span');
      title.className = 'history-title';
      title.textContent = chat.title;

      const del = document.createElement('button');
      del.className = 'delete-chat';
      del.type = 'button';
      del.title = 'Delete chat';
      del.setAttribute('aria-label', `Delete ${chat.title}`);
      del.textContent = '×';

      item.append(icon, title, del);

      // Click anywhere on the history item to open chat.
      item.addEventListener('click', (event) => {
        if (event.target.closest('.delete-chat')) return;
        loadChat(chat.id);
      });

      // Delete individual conversation.
      del.addEventListener('click', async (event) => {
        event.stopPropagation();

        try {
          await api(`/api/conversations/${chat.id}`, {
            method: 'DELETE'
          });

          if (String(currentId) === String(chat.id)) {
            newChat();
          }

          await refreshHistory();
          toast('Chat deleted');

        } catch (err) {
          toast(err.message);
        }
      });

      historyEl.append(item);
    });

  } catch (err) {
    historyEl.replaceChildren();

    const error = document.createElement('div');
    error.className = 'history-error';
    error.textContent = 'Could not load chat history.';

    historyEl.append(error);
  }
}

/* ==========================================
   Load Existing Chat
   ========================================== */

async function loadChat(id) {
  try {
    const chat = await api(`/api/conversations/${id}`);

    currentId = chat.id;
    messagesEl.replaceChildren();

    setStarted(chat.messages.length > 0);

    chat.messages.forEach(message => {
      addMessage(
        message.role,
        message.content,
        {
          copy: message.role === 'assistant'
        }
      );
    });

    await refreshHistory();
    closeSidebar();

  } catch (err) {
    toast(err.message);
  }
}

/* ==========================================
   New Chat
   ========================================== */

function newChat() {
  currentId = null;

  messagesEl.replaceChildren();

  setStarted(false);

  input.value = '';
  input.style.height = 'auto';

  setBusy(false);

  refreshHistory();
  closeSidebar();

  input.focus();
}

/* ==========================================
   Send Message
   ========================================== */

async function submitMessage(value) {
  const content = value.trim();

  if (!content || busy) return;

  setStarted(true);

  addMessage('user', content);

  input.value = '';
  input.style.height = 'auto';

  setBusy(true);

  // Typing animation.
  const typing = addMessage('assistant', '');

  const typingDots = document.createElement('span');
  typingDots.className = 'typing-dots';

  for (let i = 0; i < 3; i++) {
    const dot = document.createElement('span');
    typingDots.append(dot);
  }

  typing.querySelector('.message-content').append(typingDots);

  try {
    const result = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: content,
        conversation_id: currentId
      })
    });

    currentId = result.conversation_id;

    typing.remove();

    addMessage('assistant', result.reply, {
      copy: true
    });

    await refreshHistory();

  } catch (err) {
    typing.remove();

    if (err.conversationId) {
      currentId = Number(err.conversationId);
      await refreshHistory();
    }

    addMessage('assistant', err.message, {
      error: true
    });

  } finally {
    setBusy(false);
    input.focus();
  }
}

/* ==========================================
   Form Events
   ========================================== */

form.addEventListener('submit', event => {
  event.preventDefault();
  submitMessage(input.value);
});

input.addEventListener('input', () => {
  sendButton.disabled = busy || !input.value.trim();

  input.style.height = 'auto';

  input.style.height =
    `${Math.min(input.scrollHeight, 180)}px`;
});

input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

/* ==========================================
   New Chat and Brand
   ========================================== */

$('#newChat')?.addEventListener('click', newChat);

$('#brandHome')?.addEventListener('click', event => {
  event.preventDefault();
  newChat();
});

/* ==========================================
   Suggestions
   ========================================== */

document.querySelectorAll('.suggestion').forEach(button => {
  button.addEventListener('click', () => {
    input.value = button.dataset.prompt || '';

    input.dispatchEvent(new Event('input'));

    submitMessage(input.value);
  });
});

/* ==========================================
   Attachment
   ========================================== */

$('#attachButton')?.addEventListener('click', () => {
  toast('Attachments are not supported yet.');
});

/* ==========================================
   Share
   ========================================== */

$('#shareButton')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(location.href);
    toast('Link copied');
  } catch {
    toast('Could not copy link');
  }
});

/* ==========================================
   Clear All Chats
   ========================================== */

$('#clearAll')?.addEventListener('click', async () => {
  const confirmed = confirm(
    'Delete all saved conversations? This cannot be undone.'
  );

  if (!confirmed) return;

  try {
    await api('/api/conversations', {
      method: 'DELETE'
    });

    newChat();

    toast('All chats cleared');

  } catch (err) {
    toast(err.message);
  }
});

/* ==========================================
   Keyboard Shortcut
   ========================================== */

document.addEventListener('keydown', event => {
  if (
    (event.ctrlKey || event.metaKey) &&
    event.key.toLowerCase() === 'k'
  ) {
    event.preventDefault();
    newChat();
  }

  if (event.key === 'Escape') {
    closeSidebar();
  }
});

/* ==========================================
   Application Initialization
   ========================================== */

(async function init() {
  await refreshHistory();

  try {
    const chats = await api('/api/conversations');

    if (chats.length) {
      await loadChat(chats[0].id);
    }
  } catch (err) {
    console.error('Chat initialization failed:', err);
  }
})();

/* RoastBhai account session integration */

async function checkRoastBhaiSession() {
  try {
    const response = await fetch("/api/auth/me", {
      method: "GET",
      credentials: "same-origin"
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    if (!response.ok) {
      console.error("Could not verify account session.");
      return;
    }

    const user = await response.json();

    // Update profile information if these elements exist
    const profileName = document.getElementById("profileName");
    const profileEmail = document.getElementById("profileEmail");

    if (profileName) {
      profileName.textContent = user.name;
    }

    if (profileEmail) {
      profileEmail.textContent = user.email;
    }

    // Replace login link with logout button
    const profileLogin = document.getElementById("profileLogin");

    if (profileLogin) {
      profileLogin.textContent = "Logout";
      profileLogin.href = "#";
      profileLogin.onclick = async function (event) {
        event.preventDefault();

        try {
          await fetch("/api/auth/logout", {
            method: "POST",
            credentials: "same-origin"
          });

          window.location.href = "/login";
        } catch (error) {
          console.error("Logout failed:", error);
        }
      };
    }

  } catch (error) {
    console.error("Session check failed:", error);
  }
}

checkRoastBhaiSession();
