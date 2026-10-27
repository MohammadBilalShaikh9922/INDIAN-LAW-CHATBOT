
import { useEffect, useRef, useState } from 'react';

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  'https://indian-law-chatbot-nvrv.onrender.com'
).replace(/\/$/, '');

const STORAGE_KEY = 'kanoon_ai_conversations_v1';
const MAX_CONVERSATIONS = 50;
const MAX_MESSAGES = 100;

const suggestions = [
  'What is Section 43 of the IT Act, 2000?',
  'What is the punishment for hacking under the IT Act?',
  'What does Section 66 of the IT Act say?',
  'What are the penalties for identity theft under Section 66C?'
];

const welcome = {
  role: 'assistant',
  text: 'Namaste! I’m KANOON AI, an educational Indian-law information assistant. Ask a question about the Information Technology Act, 2000.',
  sources: [],
  disclaimer: 'General information only — not legal advice.'
};

function createConversation() {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: 'New conversation',
    messages: [{ ...welcome }],
    updatedAt: Date.now()
  };
}

function loadConversations() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);

    if (saved) {
      const parsed = JSON.parse(saved);

      if (Array.isArray(parsed)) {
        const valid = parsed
          .filter(
            chat =>
              chat &&
              typeof chat.id === 'string' &&
              Array.isArray(chat.messages) &&
              chat.messages.every(
                msg =>
                  msg &&
                  ['user', 'assistant'].includes(msg.role) &&
                  typeof msg.text === 'string'
              )
          )
          .slice(0, MAX_CONVERSATIONS)
          .map(chat => ({
            id: chat.id,
            title:
              typeof chat.title === 'string'
                ? chat.title
                : 'Saved conversation',
            messages: chat.messages
              .slice(-MAX_MESSAGES)
              .map(msg => ({
                role: msg.role,
                text: msg.text,
                sources: Array.isArray(msg.sources)
                  ? msg.sources
                  : [],
                ...(typeof msg.disclaimer === 'string'
                  ? { disclaimer: msg.disclaimer }
                  : {})
              })),
            updatedAt: Number(chat.updatedAt) || Date.now()
          }));

        if (valid.length > 0) {
          return valid;
        }
      }
    }
  } catch {
    console.warn('Could not restore KANOON AI history.');
  }

  return [createConversation()];
}

function formatText(text) {
  const lines = String(text ?? '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\\*/g, '*')
    .split('\n');

  return lines.map((line, index) => {
    const cleaned = line.trim();
    const heading = cleaned.match(/^\*\*(.*?)\*\*$/);

    return (
      <span key={index}>
        {heading ? (
          <strong>{heading[1]}</strong>
        ) : (
          cleaned.replace(/\*\*/g, '')
        )}
        {index < lines.length - 1 && <br />}
      </span>
    );
  });
}

function getConversationTitle(messages) {
  const firstQuestion = messages.find(
    message => message.role === 'user'
  );

  if (!firstQuestion) return 'New conversation';

  const title = firstQuestion.text.trim();

  return title.length > 36
    ? `${title.slice(0, 36)}…`
    : title || 'New conversation';
}

export default function App() {
  const [conversations, setConversations] = useState(loadConversations);

  const [activeId, setActiveId] = useState(
    () => loadConversations()[0]?.id
  );

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const endRef = useRef(null);

  const activeConversation =
    conversations.find(chat => chat.id === activeId) ||
    conversations[0];

  const messages = activeConversation?.messages || [welcome];

  // Save all conversations in this browser.
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(
          conversations
            .slice(0, MAX_CONVERSATIONS)
            .map(chat => ({
              ...chat,
              messages: chat.messages.slice(-MAX_MESSAGES)
            }))
        )
      );
    } catch {
      console.warn('Could not save KANOON AI history.');
    }
  }, [conversations]);

  // Keep the latest message visible.
  useEffect(() => {
    endRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end'
    });
  }, [messages, loading, activeId]);

  function updateConversation(id, update) {
    setConversations(previous =>
      previous.map(chat =>
        chat.id === id
          ? {
              ...chat,
              ...update,
              updatedAt: Date.now()
            }
          : chat
      )
    );
  }

  function startNewConversation() {
    if (loading) return;

    const newChat = createConversation();

    setConversations(previous =>
      [newChat, ...previous].slice(0, MAX_CONVERSATIONS)
    );

    setActiveId(newChat.id);
    setInput('');
    setError('');
  }

  function openConversation(id) {
    if (loading) return;

    setActiveId(id);
    setInput('');
    setError('');
  }

  function deleteConversation(id) {
    if (loading) return;

    const remaining = conversations.filter(
      chat => chat.id !== id
    );

    if (remaining.length === 0) {
      const newChat = createConversation();
      setConversations([newChat]);
      setActiveId(newChat.id);
    } else {
      setConversations(remaining);

      if (activeId === id) {
        setActiveId(remaining[0].id);
      }
    }

    setInput('');
    setError('');
  }

  async function sendMessage(value) {
    const question = (value ?? input).trim();

    if (!question || loading || !activeConversation) return;

    const chatId = activeConversation.id;

    const userMessage = {
      role: 'user',
      text: question
    };

    const updatedMessages = [
      ...messages,
      userMessage
    ].slice(-MAX_MESSAGES);

    updateConversation(chatId, {
      messages: updatedMessages,
      title: getConversationTitle(updatedMessages)
    });

    setInput('');
    setError('');
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: question,
          history: messages
            .filter(
              msg =>
                msg.role === 'user' ||
                msg.role === 'assistant'
            )
            .slice(-10)
            .map(msg => ({
              role: msg.role,
              content: msg.text
            }))
        })
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();

      if (typeof data.answer !== 'string') {
        throw new Error(
          'The API response did not contain a valid answer.'
        );
      }

      const finalMessages = [
        ...updatedMessages,
        {
          role: 'assistant',
          text: data.answer,
          sources: Array.isArray(data.sources)
            ? data.sources
            : [],
          disclaimer:
            data.disclaimer ||
            'General information only — not legal advice.'
        }
      ].slice(-MAX_MESSAGES);

      updateConversation(chatId, {
        messages: finalMessages,
        title: getConversationTitle(finalMessages)
      });
    } catch (err) {
      setError(`${err.message}. Backend: ${API_BASE}`);

      const failedMessages = [
        ...updatedMessages,
        {
          role: 'assistant',
          text: 'I could not retrieve an answer. Please check the connection and try again.',
          sources: [],
          disclaimer: 'General information only — not legal advice.'
        }
      ].slice(-MAX_MESSAGES);

      updateConversation(chatId, {
        messages: failedMessages,
        title: getConversationTitle(failedMessages)
      });
    } finally {
      setLoading(false);
    }
  }

  const sortedConversations = [...conversations].sort(
    (a, b) => b.updatedAt - a.updatedAt
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">§</div>
          <div>
            <strong>KANOON AI</strong>
            <span>INDIAN IT ACT Assistant</span>
          </div>
        </div>

        <button
          className="new-chat"
          onClick={startNewConversation}
          disabled={loading}
        >
          + New conversation
        </button>

        <div className="side-label">EXPLORE</div>

        <div className="nav-item active">
          Legal chatbot
        </div>

        <a
          className="nav-item"
          href="https://www.indiacode.nic.in/"
          target="_blank"
          rel="noreferrer"
        >
          India Code ↗
        </a>

        <a
          className="nav-item"
          href="https://nalsa.gov.in/"
          target="_blank"
          rel="noreferrer"
        >
          Free legal aid ↗
        </a>

        <div className="side-label history-heading">
          <span>HISTORY</span>
          <span>{conversations.length}</span>
        </div>

        <div
          className="history-list"
          aria-label="Saved conversations"
        >
          {sortedConversations.map(chat => (
            <div
              key={chat.id}
              className={`history-item ${
                chat.id === activeId ? 'selected' : ''
              }`}
            >
              <button
                type="button"
                className="history-open"
                onClick={() => openConversation(chat.id)}
                disabled={loading}
                title={chat.title}
              >
                <span className="history-icon">◷</span>
                <span className="history-title">
                  {chat.title}
                </span>
              </button>

              <button
                type="button"
                className="history-delete"
                onClick={() => deleteConversation(chat.id)}
                disabled={loading}
                title="Delete conversation"
                aria-label={`Delete ${chat.title}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <div className="sidebar-bottom">
          <div className="privacy-note">
            <b>Use with care</b>
            <span>
              Don't enter private case details or sensitive personal data.
            </span>
          </div>
          <div className="version">
            Educational prototype · v1.0
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace / <b>Legal assistant</b>
          </div>
          <div className="top-status">
            <span className="status-dot" /> Information mode
          </div>
        </header>

        <section className="content">
          <div className="hero">
            <div className="eyebrow">
              AI-POWERED LEGAL INFORMATION
            </div>

            <h1>
              Understand the law.
              <br />
              <em>Know your next step.</em>
            </h1>

            <p>
              Ask questions about the Indian Information Technology
              Act, 2000, and explore useful starting points from
              official legal resources.
            </p>

            <div className="hero-tags">
              <span>Source-linked answers</span>
              <span>Indian law focus</span>
              <span>Available anytime</span>
            </div>
          </div>

          <div className="chat-panel">
            <div className="chat-heading">
              <div className="chat-icon">§</div>
              <div>
                <b>
                  {activeConversation?.title || 'Legal information assistant'}
                </b>
                <span>Ask a question to begin</span>
              </div>
              <span className="prototype-badge">
                STARTER DATABASE
              </span>
            </div>

            <div className="messages" aria-live="polite">
              {messages.map((msg, index) => (
                <div
                  className={`message-row ${msg.role}`}
                  key={`${activeId}-${index}-${msg.role}`}
                >
                  {msg.role === 'assistant' && (
                    <div className="avatar">§</div>
                  )}

                  <div className="message-body">
                    <div className="message-label">
                      {msg.role === 'assistant' ? 'KANOON AI' : 'YOU'}
                    </div>

                    <div className={`bubble ${msg.role}`}>
                      {formatText(msg.text)}
                    </div>

                    {Array.isArray(msg.sources) &&
                      msg.sources.length > 0 && (
                        <div className="sources">
                          <div className="sources-title">
                            References to verify
                          </div>

                          {msg.sources.map((source, sourceIndex) => (
                            <a
                              key={`${source.url}-${sourceIndex}`}
                              href={source.url}
                              target="_blank"
                              rel="noreferrer"
                              className="source-link"
                            >
                              <span>
                                <b>
                                  {source.title || 'Legal reference'}
                                </b>

                                {source.act && (
                                  <small>
                                    {source.act}
                                    {source.provision
                                      ? ` · ${source.provision}`
                                      : ''}
                                  </small>
                                )}
                              </span>
                              <span>↗</span>
                            </a>
                          ))}
                        </div>
                      )}

                    {msg.disclaimer &&
                      msg.role === 'assistant' && (
                        <div className="message-disclaimer">
                          ⚠ {msg.disclaimer}
                        </div>
                      )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="message-row assistant">
                  <div className="avatar">§</div>
                  <div className="message-body">
                    <div className="message-label">KANOON AI</div>
                    <div className="bubble loading-bubble">
                      Searching legal references…
                    </div>
                  </div>
                </div>
              )}

              <div ref={endRef} />
            </div>

            {messages.length === 1 && (
              <div className="suggestions">
                <div className="suggestion-title">TRY ASKING</div>

                <div className="suggestion-grid">
                  {suggestions.map((suggestion, index) => (
                    <button
                      key={suggestion}
                      className="suggestion"
                      onClick={() => sendMessage(suggestion)}
                    >
                      <span>{['§', '◈', '↗', '⌂'][index]}</span>
                      {suggestion}
                      <span className="suggestion-arrow">↗</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="error-banner">{error}</div>
            )}

            <form
              className="composer"
              onSubmit={event => {
                event.preventDefault();
                sendMessage();
              }}
            >
              <input
                value={input}
                onChange={event => setInput(event.target.value)}
                placeholder="Ask about the IT Act, a section, or a cyber offence…"
                maxLength={2000}
                aria-label="Your legal question"
              />

              <button
                type="submit"
                disabled={!input.trim() || loading}
              >
                Send
              </button>
            </form>

            <div className="composer-foot">
              <span>
                Answers are based on a limited starter dataset.
              </span>
              <span>{input.length}/2000</span>
            </div>
          </div>

          <div className="bottom-notice">
            <p>
              <b>Important legal notice</b> KANOON AI provides general
              educational information, not legal advice. Laws change,
              and the right answer depends on the facts. Verify every
              source and consult a qualified advocate before taking
              legal action.
            </p>
          </div>

          <footer>
            <span>KANOON AI · AI Powered Indian Law Chatbot</span>
            <div>
              <a
                href="https://www.indiacode.nic.in/"
                target="_blank"
                rel="noreferrer"
              >
                India Code
              </a>
              <a
                href="https://legislative.gov.in/"
                target="_blank"
                rel="noreferrer"
              >
                Legislative Department
              </a>
              <a
                href="https://nalsa.gov.in/"
                target="_blank"
                rel="noreferrer"
              >
                NALSA
              </a>
            </div>
          </footer>
        </section>
      </main>

      <style>{`
        .history-heading {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 22px;
        }

        .history-list {
          display: flex;
          flex-direction: column;
          gap: 5px;
          max-height: 270px;
          overflow-y: auto;
          margin-top: 8px;
          padding-right: 2px;
        }

        .history-item {
          display: flex;
          align-items: center;
          gap: 4px;
          min-width: 0;
          border-radius: 8px;
          transition: background 0.2s ease;
        }

        .history-item:hover,
        .history-item.selected {
          background: rgba(127, 145, 180, 0.14);
        }

        .history-open {
          display: flex;
          align-items: center;
          gap: 9px;
          flex: 1;
          min-width: 0;
          padding: 10px 8px;
          border: 0;
          background: transparent;
          color: inherit;
          text-align: left;
          cursor: pointer;
          font: inherit;
        }

        .history-open:disabled,
        .history-delete:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .history-icon {
          flex-shrink: 0;
          opacity: 0.75;
        }

        .history-title {
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
          font-size: 12px;
        }

        .history-delete {
          flex-shrink: 0;
          border: 0;
          border-radius: 5px;
          padding: 3px 8px;
          margin-right: 4px;
          background: transparent;
          color: inherit;
          cursor: pointer;
          font-size: 18px;
          opacity: 0.65;
        }

        .history-delete:hover {
          background: rgba(220, 70, 70, 0.14);
          opacity: 1;
        }

        .sidebar {
          min-height: 0;
        }

        .sidebar-bottom {
          margin-top: auto;
        }

        @media (max-width: 700px) {
          .history-list {
            max-height: 180px;
          }
        }
      `}</style>
    </div>
  );
}
