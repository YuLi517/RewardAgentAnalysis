// src/main.tsx
// v1.0.2: React 19 入口, 渲染 ScenarioPage
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ScenarioPage } from './scenario/ScenarioPage';
import './styles/scenario.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root not found in index.html');
createRoot(root).render(
  <StrictMode>
    <ScenarioPage />
  </StrictMode>,
);
