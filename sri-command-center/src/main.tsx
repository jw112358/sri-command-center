import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import './layout.css';
import App from './App';

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
