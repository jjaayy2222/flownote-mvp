// frontend/src/App.js

import React from 'react';
import ParaClassifier from './components/ParaClassifier';
import SyncMonitor from './components/SyncMonitor';
import AutomationDashboard from './components/AutomationDashboard';
import GeneralDashboard from './components/GeneralDashboard';
import './App.css';

function App() {
  return (
    <div className="app">
      <h1>FlowNote Dashboard</h1>
      <GeneralDashboard />
      <SyncMonitor />
      <AutomationDashboard />
      <ParaClassifier />
    </div>
  );
}

export default App;
