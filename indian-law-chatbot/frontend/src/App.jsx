
import { useEffect, useRef, useState } from 'react';
import './App.css';

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  'https://indian-law-chatbot-nvrv.onrender.com'
).replace(/\/$/, '');

const suggestions = [
  'Explain Article 21 and the right to life',
  'What are consumer rights in India?',
  'How can I get free legal aid?',
  'What should tenants know about their rights?'
];

const welcome = {
  role: 'assistant',
  text: 'Namaste! I’m NyayaAI. Ask me a question about Indian law, your rights, or legal procedures.',
  sources: [],
  disclaimer: 'General educational information only — not legal advice.'
};

const LEGAL_NOTICE =
  'NyayaAI provides general educational information, not legal advice. Verify legal sources and consult a qualified advocate before taking action.';

function formatText(text) {
  return String(text ?? '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\\*/g, '*')
    .split('\n')
    .map((line, index) => {
      const cleaned = line.trim();
      const heading = cleaned.match(/^\*\*(.*?)\*\*$/);

      return (
        <span key={index}>
          {heading ? (
            <strong>{heading[1]}</strong>
          ) : (
            cleaned.replace(/\*\*/g, '')
          )}
          {index < String(text ?? '').replace(/\\n/g, '\n').split('\n').length - 1 && <br />}
        </span>
      );
    });
}

export default function App() {
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end'
    });
  }, [messages, loading]);

  async function sendMessage(value) {
    const message = (value ?? input).trim();

    if (!message || loading) return;

    const history = messages
      .filter(item => item.role === 'user' || item.role === 'assistant')
      .slice(-10)
      .map(item => ({
        role: item.role,
        content: item.text
      }));

    setInput('');
    setError('');
    setMessages(previous => [
      ...previous,
      { role: 'user', text: message }
    ]);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history })
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();

      if (typeof data.answer !== 'string') {
        throw new Error('The API returned an invalid answer.');
      }

      setMessages(previous => [
        ...previous,
        {
          role: 'assistant',
          text: data.answer,
          sources: Array.isArray(data.sources) ? data.sources : [],
          disclaimer:
            data.disclaimer ||
            'General educational information only — not legal advice.'
        }
      ]);
    } catch (err) {
      setError(
        `${err.message}. Please check the backend connection and try again.`
      );
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function resetChat() {
    setMessages([welcome]);
    setInput('');
    setError('');
    inputRef.current?.focus();
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" onClick={event => {
          event.preventDefault();
          resetChat();
        }}>
          <span className="brand-mark">§</span>
          <span className="brand-copy">
            <strong>NyayaAI</strong>
            <small>INDIAN LAW ASSISTANT</small>
          </span>
        </a>

        <div className="header-actions">
          <span className="status-label">
            <span className="status-dot" />
            Legal information
          </span>
          <button className="new-chat" type="button" onClick={resetChat}>
            <span aria-hidden="true">＋</span> New chat
          </button>
        </div>
      </header>

      <main className="main-content">
        <section className={`chat-section ${messages.length === 1 ? 'is-welcome' : ''}`}>
          {messages.length === 1 && (
            <div className="welcome">
              <div className="welcome-icon">§</div>
              <p className="eyebrow">YOUR INDIAN LAW ASSISTANT</p>
              <h1>How can we help<br />you understand the law?</h1>
              <p className="welcome-description">
                Ask a legal question in everyday language.
                Get started with a topic below.
              </p>
            </div>
          )}

          <div className="messages" aria-live="polite">
            {messages.map((msg, index) => (
              <article
                className={`message-row ${msg.role}`}
                key={`${index}-${msg.role}`}
              >
                {msg.role === 'assistant' && (
                  <div className="avatar" aria-hidden="true">§</div>
                )}

                <div className="message-content">
                  <div className="message-label">
                    {msg.role === 'assistant' ? 'NYAYAAI' : 'YOU'}
                  </div>

                  <div className={`bubble ${msg.role}`}>
                    {formatText(msg.text)}
                  </div>

                  {msg.sources?.length > 0 && (
                    <div className="sources">
                      <p className="sources-heading">Sources and references</p>
                      {msg.sources.map((source, sourceIndex) => (
                        <a
                          className="source-link"
                          key={`${source.url}-${sourceIndex}`}
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <span className="source-icon" aria-hidden="true">↗</span>
                          <span className="source-copy">
                            <strong>{source.title || 'Legal reference'}</strong>
                            {source.act && (
                              <small>
                                {source.act}
                                {source.provision ? ` · ${source.provision}` : ''}
                              </small>
                            )}
                          </span>
                        </a>
                      ))}
                    </div>
                  )}

                  {msg.role === 'assistant' && msg.disclaimer && (
                    <p className="message-disclaimer">{msg.disclaimer}</p>
                  )}
                </div>
              </article>
            ))}

            {loading && (
              <article className="message-row assistant">
                <div className="avatar" aria-hidden="true">§</div>
                <div className="message-content">
                  <div className="message-label">NYAYAAI</div>
                  <div className="bubble loading-bubble">
                    <span className="typing-dots" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    Searching for relevant information…
                  </div>
                </div>
              </article>
            )}

            <div ref={endRef} />
          </div>

          {messages.length === 1 && (
            <div className="suggestions">
              <p className="suggestions-heading">Suggested questions</p>
              <div className="suggestion-list">
                {suggestions.map((suggestion, index) => (
                  <button
                    type="button"
                    className="suggestion"
                    key={suggestion}
                    onClick={() => sendMessage(suggestion)}
                    disabled={loading}
                  >
                    <span className="suggestion-number">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span>{suggestion}</span>
                    <span className="suggestion-arrow" aria-hidden="true">↗</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button type="button" onClick={() => setError('')} aria-label="Dismiss error">
                ×
              </button>
            </div>
          )}

          <form
            className="composer"
            onSubmit={event => {
              event.preventDefault();
              sendMessage();
            }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={event => setInput(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="Ask your legal question…"
              maxLength={2000}
              rows={2}
              aria-label="Your legal question"
            />
            <div className="composer-bottom">
              <span className="input-hint">Enter to send · Shift + Enter for a new line</span>
              <span className="input-actions">
                <span className="character-count">{input.length}/2000</span>
                <button
                  className="send-button"
                  type="submit"
                  disabled={!input.trim() || loading}
                  aria-label="Send message"
                >
                  {loading ? '…' : '↑'}
                </button>
              </span>
            </div>
          </form>

          <p className="privacy-hint">
            Avoid entering passwords, identity numbers, or sensitive personal details.
          </p>
        </section>
      </main>

      <footer className="footer">
        <span>© NyayaAI · For educational use</span>
        <nav aria-label="Official legal resources">
          <a href="https://www.indiacode.nic.in/" target="_blank" rel="noreferrer">India Code</a>
          <a href="https://legislative.gov.in/" target="_blank" rel="noreferrer">Legislative Department</a>
          <a href="https://nalsa.gov.in/" target="_blank" rel="noreferrer">NALSA</a>
        </nav>
      </footer>

      <div className="legal-notice">{LEGAL_NOTICE}</div>
    </div>
  );
}

