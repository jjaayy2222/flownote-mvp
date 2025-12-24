// frontend/src/App.js

import React from 'react';
import ParaClassifier from './components/ParaClassifier';
import SyncMonitor from './components/SyncMonitor';
import './App.css';

function App() {
  return (
    <div className="app">
      <h1>FlowNote Dashboard</h1>
      <SyncMonitor />
      <ParaClassifier />
    </div>
  );
}

export default App;
