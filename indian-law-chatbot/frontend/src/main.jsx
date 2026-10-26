
import React from 'react';
import { createRoot } from 'react-dom/client';

function ReactDiagnostic() {
  const [count, setCount] = React.useState(0);

  return (
    <main style={{
      fontFamily: 'Arial, sans-serif',
      padding: '40px',
      color: '#172033',
      background: '#f4f7fb',
      minHeight: '100vh'
    }}>
      <h1>NyayaAI React Diagnostic</h1>
      <p>If you can see this, React is rendering successfully.</p>
      <p>Button clicks: {count}</p>
      <button onClick={() => setCount(value => value + 1)}>
        Test React state
      </button>
    </main>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ReactDiagnostic />
  </React.StrictMode>
);
