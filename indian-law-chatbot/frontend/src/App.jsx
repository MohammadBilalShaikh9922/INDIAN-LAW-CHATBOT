import { useEffect, useRef, useState } from 'react';

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  'https://indian-law-chatbot-nvrv.onrender.com'
).replace(/\/$/, '');

const suggestions = [
  'Explain Article 21 and the right to life',
  'What are general consumer rights in India?',
  'How can I find free legal aid?',
  'What should I know about tenant rights?'
];

const welcome = {
  role: 'assistant',
  text: 'Namaste! I’m NyayaAI, an educational Indian-law information assistant. Ask a question in everyday language, or choose a suggested topic below.',
  sources: [],
  disclaimer: 'General information only — not legal advice.'
};

export default function App() {
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, loading]);

  async function sendMessage(value) {
    const message = (value ?? input).trim();

    if (!message || loading) return;

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
        body: JSON.stringify({
          message,
          history: messages
            .filter(msg => msg.role === 'user' || msg.role === 'assistant')
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
        throw new Error('The API response did not contain a valid answer.');
      }

      setMessages(previous => [
        ...previous,
        {
          role: 'assistant',
          text: data.answer,
          sources: Array.isArray(data.sources) ? data.sources : [],
          disclaimer: data.disclaimer || 'General information only — not legal advice.'
        }
      ]);
    } catch (err) {
      setError(`${err.message}. Backend: ${API_BASE}`);
      setMessages(previous => [
        ...previous,
        {
          role: 'assistant',
          text: 'I could not retrieve an answer. Please check the connection and try again.',
          sources: [],
          disclaimer: 'General information only — not legal advice.'
        }
      ]);
    } finally {
      setLoading(false);
    }
  }

  function resetChat() {
    setMessages([welcome]);
    setInput('');
    setError('');
  }

  
function formatText(text) {
  const lines = String(text ?? '')
    // Convert escaped newlines and remove unwanted escape characters.
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\\*/g, '*')
    .replace(/\\\*/g, '*')
    .split('\n');

  return lines.map((line, index) => {
    const cleanedLine = line.trim();

    // Display Markdown-style headings as bold text.
    const headingMatch = cleanedLine.match(/^\*\*(.*?)\*\*$/);

    return (
      <span key={index}>
        {headingMatch ? (
          <strong>{headingMatch[1]}</strong>
        ) : (
          cleanedLine.replace(/\*\*/g, '')
        )}
        {index < lines.length - 1 && <br />}
      </span>
    );
  });
}


  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">§</div>
          <div>
            <strong>NyayaAI</strong>
            <span>INDIAN LAW ASSISTANT</span>
          </div>
        </div>

        <button className="new-chat" onClick={resetChat}>
          + New conversation
        </button>

        <div className="side-label">EXPLORE</div>
        <div className="nav-item active">Legal chatbot</div>
        <a className="nav-item" href="https://www.indiacode.nic.in/" target="_blank" rel="noreferrer">
          India Code ↗
        </a>
        <a className="nav-item" href="https://nalsa.gov.in/" target="_blank" rel="noreferrer">
          Free legal aid ↗
        </a>

        <div className="sidebar-bottom">
          <div className="privacy-note">
            <b>Use with care</b>
            <span>Don't enter private case details or sensitive personal data.</span>
          </div>
          <div className="version">Educational prototype · v1.0</div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">Workspace / <b>Legal assistant</b></div>
          <div className="top-status">
            <span className="status-dot" /> Information mode
          </div>
        </header>

        <section className="content">
          <div className="hero">
            <div className="eyebrow">AI-POWERED LEGAL INFORMATION</div>
            <h1>Understand the law.<br /><em>Know your next step.</em></h1>
            <p>
              Ask questions about Indian laws in plain language and explore
              useful starting points from official legal resources.
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
                <b>Legal information assistant</b>
                <span>Ask a question to begin</span>
              </div>
              <span className="prototype-badge">STARTER DATABASE</span>
            </div>

            <div className="messages" aria-live="polite">
              {messages.map((msg, index) => (
                <div className={`message-row ${msg.role}`} key={`${index}-${msg.role}`}>
                  {msg.role === 'assistant' && <div className="avatar">§</div>}
                  <div className="message-body">
                    <div className="message-label">
                      {msg.role === 'assistant' ? 'NYAYAAI' : 'YOU'}
                    </div>
                    <div className={`bubble ${msg.role}`}>
                      {formatText(msg.text ?? '')}
                    </div>

                    {Array.isArray(msg.sources) && msg.sources.length > 0 && (
                      <div className="sources">
                        <div className="sources-title">References to verify</div>
                        {msg.sources.map((source, sourceIndex) => (
                          <a
                            key={`${source.url}-${sourceIndex}`}
                            href={source.url}
                            target="_blank"
                            rel="noreferrer"
                            className="source-link"
                          >
                            <span>
                              <b>{source.title || 'Legal reference'}</b>
                              {source.act && (
                                <small>
                                  {source.act}
                                  {source.provision ? ` · ${source.provision}` : ''}
                                </small>
                              )}
                            </span>
                            <span>↗</span>
                          </a>
                        ))}
                      </div>
                    )}

                    {msg.disclaimer && msg.role === 'assistant' && (
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
                    <div className="message-label">NYAYAAI</div>
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

            {error && <div className="error-banner">{error}</div>}

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
                placeholder="Ask about a law, right, Act, or legal process…"
                maxLength={2000}
                aria-label="Your legal question"
              />
              <button type="submit" disabled={!input.trim() || loading}>
                Send
              </button>
            </form>

            <div className="composer-foot">
              <span>Answers are based on a limited starter dataset.</span>
              <span>{input.length}/2000</span>
            </div>
          </div>

          <div className="bottom-notice">
            <p>
              <b>Important legal notice</b> NyayaAI provides general educational
              information, not legal advice. Laws change and the right answer
              depends on your facts. Verify every source and consult a qualified
              advocate before taking legal action.
            </p>
          </div>

          <footer>
            <span>NyayaAI · AI Powered Indian Law Chatbot</span>
            <div>
              <a href="https://www.indiacode.nic.in/" target="_blank" rel="noreferrer">India Code</a>
              <a href="https://legislative.gov.in/" target="_blank" rel="noreferrer">Legislative Department</a>
              <a href="https://nalsa.gov.in/" target="_blank" rel="noreferrer">NALSA</a>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}
