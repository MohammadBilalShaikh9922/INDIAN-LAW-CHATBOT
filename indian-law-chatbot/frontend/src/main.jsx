
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';

window.addEventListener('error', (event) => {
  console.error(
    '[NyayaAI global error]',
    event.message,
    event.filename,
    event.lineno,
    event.colno
  );
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('[NyayaAI unhandled promise rejection]', event.reason);
});

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('[NyayaAI React crash]', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <main style={{
          margin: '32px auto',
          padding: '24px',
          maxWidth: '800px',
          fontFamily: 'Arial, sans-serif',
          color: '#222',
          background: '#fff'
        }}>
          <h1>NyayaAI frontend error</h1>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {String(this.state.error?.stack || this.state.error)}
          </pre>
          <button onClick={() => window.location.reload()}>
            Reload
          </button>
        </main>
      );
    }

    return this.props.children;
  }
}

const rootElement = document.getElementById('root');

if (!rootElement) {
  document.body.innerHTML =
    '<p style="padding:24px;font-family:Arial">NyayaAI error: root element not found.</p>';
} else {
  createRoot(rootElement).render(
    <ErrorBoundary>
      <React.StrictMode>
        <App />
      </React.StrictMode>
    </ErrorBoundary>
  );
}
