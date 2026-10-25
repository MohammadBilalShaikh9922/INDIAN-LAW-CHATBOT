import { useEffect, useRef, useState } from 'react';
import { Scale, Send, ShieldCheck, BookOpen, Sparkles, ExternalLink, Menu, Plus, MessageCircle, AlertTriangle } from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
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

function formatText(text) {
  return text.split('\n').map((line, i) => <span key={i}>{line}{i < text.split('\n').length - 1 && <br />}</span>);
}

export default function App() {
  const [messages, setMessages] = useState([welcome]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mobileMenu, setMobileMenu] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }), [messages, loading]);

  async function sendMessage(value = input) {
    const message = value.trim();
    if (!message || loading) return;
    setInput('');
    setError('');
    setMessages(prev => [...prev, { role: 'user', text: message }]);
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
      });
      if (!response.ok) throw new Error(`The server returned ${response.status}. Check that the backend is running.`);
      const data = await response.json();
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.answer,
        sources: data.sources || [],
        confidence: data.confidence,
        disclaimer: data.disclaimer
      }]);
    } catch (e) {
      setError(`${e.message} Backend URL: ${API_BASE}`);
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: 'I could not reach the chatbot service. Please check the backend URL and try again.',
        sources: [],
        disclaimer: 'General information only — not legal advice.'
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function resetChat() {
    setMessages([welcome]);
    setError('');
    setInput('');
    setMobileMenu(false);
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileMenu ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Scale size={22} /></div>
          <div><strong>NyayaAI</strong><span>INDIAN LAW ASSISTANT</span></div>
        </div>
        <button className="new-chat" onClick={resetChat}><Plus size={17} /> New conversation</button>
        <div className="side-label">EXPLORE</div>
        <div className="nav-item active"><MessageCircle size={17} /> Legal chatbot</div>
        <a className="nav-item" href="https://www.indiacode.nic.in/" target="_blank" rel="noreferrer"><BookOpen size={17} /> India Code <ExternalLink size={13} /></a>
        <a className="nav-item" href="https://nalsa.gov.in/" target="_blank" rel="noreferrer"><ShieldCheck size={17} /> Free legal aid <ExternalLink size={13} /></a>
        <div className="sidebar-bottom">
          <div className="privacy-note"><ShieldCheck size={17} /><div><b>Use with care</b><span>Don't enter private case details or sensitive personal data.</span></div></div>
          <div className="version">Educational prototype · v1.0</div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <button className="mobile-menu" aria-label="Open menu" onClick={() => setMobileMenu(v => !v)}><Menu size={20} /></button>
          <div className="breadcrumb">Workspace <span>/</span> <b>Legal assistant</b></div>
          <div className="top-status"><span className="status-dot" /> Information mode</div>
        </header>

        <section className="content">
          <div className="hero">
            <div className="eyebrow"><Sparkles size={14} /> AI-POWERED LEGAL INFORMATION</div>
            <h1>Understand the law.<br /><em>Know your next step.</em></h1>
            <p>Ask questions about Indian laws in plain language and explore useful starting points from official legal resources.</p>
            <div className="hero-tags"><span><ShieldCheck size={14} /> Source-linked answers</span><span><BookOpen size={14} /> Indian law focus</span><span>Available anytime</span></div>
          </div>

          <div className="chat-panel">
            <div className="chat-heading">
              <div className="chat-icon"><Scale size={19} /></div>
              <div><b>Legal information assistant</b><span>Ask a question to begin</span></div>
              <span className="prototype-badge">STARTER DATABASE</span>
            </div>
            <div className="messages" aria-live="polite">
              {messages.map((msg, index) => (
                <div className={`message-row ${msg.role}`} key={`${index}-${msg.role}`}>
                  {msg.role === 'assistant' && <div className="avatar"><Scale size={16} /></div>}
                  <div className="message-body">
                    <div className="message-label">{msg.role === 'assistant' ? 'NYAYAAI' : 'YOU'}</div>
                    <div className={`bubble ${msg.role}`}>{formatText(msg.text)}</div>
                    {msg.sources?.length > 0 && <div className="sources">
                      <div className="sources-title"><BookOpen size={13} /> References to verify</div>
                      {msg.sources.map((source, i) => <a key={`${source.url}-${i}`} href={source.url} target="_blank" rel="noreferrer" className="source-link">
                        <span><b>{source.title}</b>{source.act && <small>{source.act}{source.provision ? ` · ${source.provision}` : ''}</small>}</span><ExternalLink size={14} />
                      </a>)}
                    </div>}
                    {msg.disclaimer && msg.role === 'assistant' && <div className="message-disclaimer"><AlertTriangle size={13} /> {msg.disclaimer}</div>}
                  </div>
                </div>
              ))}
              {loading && <div className="message-row assistant"><div className="avatar"><Scale size={16} /></div><div className="message-body"><div className="message-label">NYAYAAI</div><div className="bubble loading-bubble"><span></span><span></span><span></span> Searching legal references…</div></div></div>}
              <div ref={endRef} />
            </div>
            {messages.length === 1 && <div className="suggestions"><div className="suggestion-title">TRY ASKING</div><div className="suggestion-grid">{suggestions.map((s, i) => <button key={s} className="suggestion" onClick={() => sendMessage(s)}><span>{['§', '◈', '↗', '⌂'][i]}</span>{s}<span className="suggestion-arrow">↗</span></button>)}</div></div>}
            {error && <div className="error-banner">{error}</div>}
            <form className="composer" onSubmit={e => { e.preventDefault(); sendMessage(); }}>
              <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} placeholder="Ask about a law, right, Act, or legal process…" maxLength={2000} aria-label="Your legal question" />
              <button type="submit" disabled={!input.trim() || loading} aria-label="Send question"><Send size={17} /></button>
            </form>
            <div className="composer-foot"><span>Answers are based on a limited starter dataset.</span><span>{input.length}/2000</span></div>
          </div>

          <div className="bottom-notice"><ShieldCheck size={17} /><p><b>Important legal notice</b> NyayaAI provides general educational information, not legal advice. Laws change and the right answer depends on your facts. Verify every source and consult a qualified advocate before taking legal action.</p></div>
          <footer><span>NyayaAI · AI Powered Indian Law Chatbot</span><div><a href="https://www.indiacode.nic.in/" target="_blank" rel="noreferrer">India Code</a><a href="https://legislative.gov.in/" target="_blank" rel="noreferrer">Legislative Department</a><a href="https://nalsa.gov.in/" target="_blank" rel="noreferrer">NALSA</a></div></footer>
        </section>
      </main>
    </div>
  );
}
