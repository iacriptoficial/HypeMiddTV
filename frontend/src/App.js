import React, { useState, useEffect } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [status, setStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [webhooks, setWebhooks] = useState([]);
  const [responses, setResponses] = useState([]);
  const [strategies, setStrategies] = useState({});
  const [availableStrategyIds, setAvailableStrategyIds] = useState([]);
  const [selectedStrategies, setSelectedStrategies] = useState({});
  const [logFilter, setLogFilter] = useState('ERROR'); // Filter for logs (ERROR, INFO, ALL)
  const [currentEnvironment, setCurrentEnvironment] = useState("testnet");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [loading, setLoading] = useState(true);
  const [copySuccess, setCopySuccess] = useState(false);

  const copyToClipboard = async (text) => {
    try {
      // Método 1: Tentar usar a API moderna do Clipboard
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        setCopySuccess(true);
        setTimeout(() => setCopySuccess(false), 2000);
        return;
      }
      
      // Método 2: Fallback para document.execCommand (legacy)
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);
      
      if (successful) {
        setCopySuccess(true);
        setTimeout(() => setCopySuccess(false), 2000);
      } else {
        throw new Error('Copy command failed');
      }
      
    } catch (err) {
      console.error('Failed to copy text: ', err);
      // Método 3: Fallback final - selecionar o texto para cópia manual
      const input = document.querySelector('input[readonly]');
      if (input) {
        input.focus();
        input.select();
      }
      
      // Adicionar mensagem de erro nos logs
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "WARNING",
        message: "Clipboard API blocked - text selected for manual copy",
        details: err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  // Fetch data functions
  const fetchStatus = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setStatus(response.data);
    } catch (err) {
      console.error("Error fetching status:", err);
      // Add error to logs instead of showing in banner
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: "Failed to fetch server status",
        details: err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  const fetchLogs = async (limit = 200) => {
    try {
      const response = await axios.get(`${API}/logs?limit=${limit}`);
      setLogs(response.data.logs);
    } catch (err) {
      console.error("Error fetching logs:", err);
      // Add error to logs
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "ERROR", 
        message: "Failed to fetch logs",
        details: err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  const fetchWebhooks = async (limit = 100) => {
    try {
      // Build strategy filter parameter
      const activeStrategies = Object.keys(selectedStrategies).filter(id => selectedStrategies[id]);
      
      // Se nenhuma estratégia está selecionada, não buscar dados (mostrar vazio)
      if (activeStrategies.length === 0) {
        setWebhooks([]);
        return;
      }
      
      const strategyParam = `&strategy_ids=${activeStrategies.join(',')}`;
      const response = await axios.get(`${API}/webhooks?limit=${limit}${strategyParam}`);
      setWebhooks(response.data.webhooks);
    } catch (err) {
      console.error("Error fetching webhooks:", err);
    }
  };

  const fetchResponses = async (limit = 100) => {
    try {
      // Build strategy filter parameter
      const activeStrategies = Object.keys(selectedStrategies).filter(id => selectedStrategies[id]);
      
      // Se nenhuma estratégia está selecionada, não buscar dados (mostrar vazio)
      if (activeStrategies.length === 0) {
        setResponses([]);
        return;
      }
      
      const strategyParam = `&strategy_ids=${activeStrategies.join(',')}`;
      const response = await axios.get(`${API}/responses?limit=${limit}${strategyParam}`);
      setResponses(response.data.responses);
    } catch (err) {
      console.error("Error fetching responses:", err);
    }
  };

  const fetchEnvironment = async () => {
    try {
      const response = await axios.get(`${API}/environment`);
      setCurrentEnvironment(response.data.environment);
    } catch (err) {
      console.error("Error fetching environment:", err);
    }
  };

  const fetchStrategies = async () => {
    try {
      const response = await axios.get(`${API}/strategies`);
      setStrategies(response.data.strategies);
    } catch (err) {
      console.error("Error fetching strategies:", err);
    }
  };

  const fetchStrategyIds = async () => {
    try {
      const response = await axios.get(`${API}/strategies/ids`);
      const ids = response.data.strategy_ids;
      setAvailableStrategyIds(ids);
      
      // Initialize selectedStrategies with PRIMEIRO filtro ATIVO por padrão
      const initialSelection = {};
      ids.forEach((id, index) => {
        initialSelection[id] = index === 0; // Apenas o primeiro ativo
      });
      setSelectedStrategies(initialSelection);
    } catch (err) {
      console.error("Error fetching strategy IDs:", err);
    }
  };

  const toggleStrategy = async (strategyId) => {
    try {
      await axios.post(`${API}/strategies/${strategyId}/toggle`);
      // Refresh strategies data
      fetchStrategies();
    } catch (err) {
      console.error("Error toggling strategy:", err);
    }
  };

  const toggleStrategyFilter = (strategyId) => {
    setSelectedStrategies(prev => ({
      ...prev,
      [strategyId]: !prev[strategyId]
    }));
  };

  const switchEnvironment = async (env) => {
    try {
      await axios.post(`${API}/environment`, null, {
        params: { environment: env }
      });
      setCurrentEnvironment(env);
      // Refresh data after switching
      fetchStatus();
    } catch (err) {
      console.error("Error switching environment:", err);
      // Add error to logs instead of showing in banner
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: "Failed to switch environment",
        details: err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  // Restart server function
  const restartServer = async () => {
    try {
      const response = await axios.post(`${API}/restart`);
      
      // Add success log
      const successLog = {
        timestamp: new Date().toISOString(),
        level: "INFO",
        message: "Server restart initiated",
        details: "Restart requested successfully"
      };
      setLogs(prevLogs => [successLog, ...prevLogs]);
      
      // Refresh data after a delay
      setTimeout(() => {
        fetchStatus();
        fetchLogs();
      }, 3000);
      
    } catch (err) {
      console.error("Error restarting server:", err);
      // Add error to logs
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: "Failed to restart server",
        details: err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  // Clear logs function
  const clearLogs = async () => {
    try {
      const response = await axios.delete(`${API}/logs`);
      
      // Clear the logs from the frontend state
      setLogs([]);
      
      // Add success log
      const successLog = {
        timestamp: new Date().toISOString(),
        level: "INFO",
        message: "Logs cleared successfully",
        details: `${response.data.deleted_count || 0} logs deleted`
      };
      setLogs([successLog]);
      
    } catch (err) {
      console.error("Error clearing logs:", err);
      // Add error to logs
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: "Failed to clear logs",
        details: err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  // Reset uptime stats function
  const resetUptimeStats = async () => {
    try {
      const response = await axios.post(`${API}/reset-uptime-stats`);
      
      // Add success log
      const successLog = {
        timestamp: new Date().toISOString(),
        level: "INFO",
        message: "Uptime statistics reset successfully",
        details: "Uptime monitoring stats cleared"
      };
      setLogs(prevLogs => [successLog, ...prevLogs]);
      
      // Refresh status to show updated stats
      fetchStatus();
      
    } catch (err) {
      console.error("Error resetting uptime stats:", err);
      // Add error to logs
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: "Failed to reset uptime statistics",
        details: err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  // Re-execute webhook function
  const reExecuteWebhook = async (webhookData) => {
    try {
      const response = await axios.post(`${API}/webhook/re-execute`, webhookData);
      
      // Add success log
      const successLog = {
        timestamp: new Date().toISOString(),
        level: "INFO",
        message: `Webhook re-executed successfully`,
        details: `Webhook ID: ${response.data.webhook_id}`
      };
      setLogs(prevLogs => [successLog, ...prevLogs]);
      
      // Refresh data
      fetchWebhooks();
      fetchResponses();
      
    } catch (err) {
      console.error("Error re-executing webhook:", err);
      
      // Add error to logs
      const errorLog = {
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: "Failed to re-execute webhook",
        details: err.response?.data?.detail || err.message
      };
      setLogs(prevLogs => [errorLog, ...prevLogs]);
    }
  };

  // Auto-refresh data
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      
      // Load each endpoint independently with timeout
      const loadWithTimeout = async (fetchFunc, name) => {
        try {
          const timeoutPromise = new Promise((_, reject) => 
            setTimeout(() => reject(new Error(`${name} timeout`)), 10000)
          );
          await Promise.race([fetchFunc(), timeoutPromise]);
        } catch (error) {
          console.error(`Error loading ${name}:`, error);
        }
      };
      
      // Load data independently
      await Promise.allSettled([
        loadWithTimeout(fetchStatus, 'status'),
        loadWithTimeout(fetchLogs, 'logs'),
        loadWithTimeout(fetchEnvironment, 'environment'),
        loadWithTimeout(fetchStrategies, 'strategies'),
        loadWithTimeout(fetchStrategyIds, 'strategy_ids')
        // Não carregar webhooks/responses inicialmente - aguardar seleção de filtros
      ]);
      
      setLoading(false);
    };

    loadData();

    // Auto-refresh with different intervals for different data types
    const statusInterval = setInterval(() => {
      fetchStatus();  // Status every 10 seconds
    }, 10000);  // Every 10 seconds for real-time dashboard updates
    
    const dataInterval = setInterval(() => {
      fetchLogs();
      // IMPORTANTE: NÃO atualizar webhooks e responses automaticamente para manter filtros
      // fetchWebhooks(); 
      // fetchResponses();
    }, 5000);  // Apenas logs são atualizados automaticamente

    return () => {
      clearInterval(statusInterval);
      clearInterval(dataInterval);
    };
  }, []);

  // Separate useEffect to handle strategy filter changes
  useEffect(() => {
    if (availableStrategyIds.length > 0) {
      fetchWebhooks();
      fetchResponses();
    }
  }, [selectedStrategies]);

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  const getStatusColor = (status) => {
    switch (status) {
      case "running":
        return "text-green-400";
      case "error":
        return "text-red-400";
      case "warning":
        return "text-yellow-400";
      default:
        return "text-gray-400";
    }
  };

  const getLogLevelColor = (level) => {
    switch (level) {
      case "ERROR":
        return "text-red-400";
      case "WARNING":
        return "text-yellow-400";
      case "INFO":
        return "text-green-400";
      default:
        return "text-gray-400";
    }
  };

  // Filter logs based on selected filter
  const filteredLogs = logs.filter(log => {
    switch (logFilter) {
      case 'ERROR':
        return log.level === 'ERROR';
      case 'INFO':
        return log.level === 'INFO';
      case 'ALL':
      default:
        return true;
    }
  });

  // Strategy Filter Component - SIMPLIFIED
  const StrategyFilters = ({ showTitle = true }) => {
    if (availableStrategyIds.length === 0) return null;

    return (
      <div className="mb-4 p-4 bg-gray-800 rounded-lg border border-gray-700">
        {showTitle && (
          <h3 className="text-lg font-semibold text-white mb-3">Filtros de Estratégia</h3>
        )}
        
        {/* Simple Strategy Toggle Buttons */}
        <div className="flex flex-wrap gap-2">
          {availableStrategyIds.map(strategyId => {
            const isSelected = selectedStrategies[strategyId];
            const strategy = strategies[strategyId];
            const isEnabled = strategy?.enabled !== false;
            
            return (
              <button
                key={strategyId}
                onClick={() => toggleStrategyFilter(strategyId)}
                className={`px-4 py-2 text-sm rounded-lg border transition-all duration-200 flex items-center space-x-2 ${
                  isSelected
                    ? 'bg-blue-600 border-blue-500 text-white shadow-lg'
                    : 'bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${isEnabled ? 'bg-green-400' : 'bg-red-400'}`}></span>
                <span>{strategyId}</span>
                {strategy?.stats && (
                  <span className="text-xs opacity-75">
                    ({strategy.stats.total_webhooks})
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  // Simple copy function for webhook URL
  const copyWebhookUrl = () => {
    const url = `${process.env.REACT_APP_BACKEND_URL || ''}/api/webhook/tradingview`;
    const textArea = document.createElement('textarea');
    textArea.value = url;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    document.body.removeChild(textArea);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2000);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-white text-xl">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Fixed Header */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-gray-800 border-b border-gray-700 shadow-lg">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-4">
              <h1 className="text-xl font-bold">TradingView → Hyperliquid</h1>
              <span className="text-sm text-gray-400">
                Environment: {currentEnvironment}
              </span>
            </div>
            <div className="flex items-center space-x-4">
              <button
                onClick={() => setCurrentEnvironment(currentEnvironment === "testnet" ? "mainnet" : "testnet")}
                className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors"
              >
                Switch to {currentEnvironment === "testnet" ? "Mainnet" : "Testnet"}
              </button>
              <button
                onClick={restartServer}
                className="bg-orange-600 hover:bg-orange-700 text-white px-3 py-1 rounded text-sm transition-colors"
                title="Restart server to fix webhook issues"
              >
                🔄 Restart Server
              </button>
            </div>
          </div>
          
          {/* Page Title */}
          <div className="py-2 border-b border-gray-700">
            <h2 className="text-lg font-semibold capitalize">
              {activeTab === "dashboard" && "Dashboard"}
              {activeTab === "logs" && "Recent Logs"}
              {activeTab === "webhooks" && "Webhooks"}
              {activeTab === "responses" && "Hyperliquid Responses"}
            </h2>
          </div>
          
          {/* Tab Navigation */}
          <div className="flex space-x-1 pb-0 -mb-px">
            {["dashboard", "logs", "webhooks", "responses"].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-3 text-sm font-medium capitalize transition-colors border-b-2 ${
                  activeTab === tab
                    ? "text-blue-400 border-blue-400"
                    : "text-gray-400 border-transparent hover:text-white hover:border-gray-600"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="pt-40 px-4 py-8 max-w-7xl mx-auto">
        {activeTab === "dashboard" && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Server Status */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Server Status</h3>
              {status && (
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Status:</span>
                    <span className={getStatusColor(status.status)}>{status.status}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Environment:</span>
                    <span className="text-white">{status.environment}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Uptime:</span>
                    <span className="text-white">{status.uptime}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Hyperliquid:</span>
                    <span className={status.hyperliquid_connected ? 'text-green-400' : 'text-red-400'}>
                      {status.hyperliquid_connected ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Account Balance */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Account Balance</h3>
              <div className="text-center">
                <div className="text-3xl font-bold text-green-400">
                  ${typeof status?.balance === 'number' ? status.balance.toFixed(2) : (status?.balance || "0.00")}
                </div>
                <div className="text-sm text-gray-400 mt-2">
                  {currentEnvironment === "testnet" ? "Testnet Balance" : "Mainnet Balance"}
                </div>
                {status?.wallet_address && (
                  <div className="text-xs text-gray-500 mt-2 break-all">
                    Wallet: {status.wallet_address}
                  </div>
                )}
              </div>
            </div>

            {/* Statistics */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Statistics</h3>
              {status && (
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Webhooks:</span>
                    <span className="text-white">{status.statistics?.total_webhooks || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Successful:</span>
                    <span className="text-green-400">{status.statistics?.successful_forwards || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Failed:</span>
                    <span className="text-red-400">{status.statistics?.failed_forwards || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Success Rate:</span>
                    <span className="text-white">
                      {status.statistics?.success_rate || '0%'}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* External Uptime */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">External Uptime</h3>
                <button
                  onClick={resetUptimeStats}
                  className="bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1 rounded text-sm transition-colors"
                  title="Reset uptime statistics"
                >
                  🔄 Reset
                </button>
              </div>
              {status?.uptime_monitoring && (
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Network Uptime:</span>
                    <span className={`font-bold ${
                      parseFloat(status.uptime_monitoring.percentage) >= 95 ? 'text-green-400' :
                      parseFloat(status.uptime_monitoring.percentage) >= 85 ? 'text-yellow-400' : 'text-red-400'
                    }`}>
                      {status.uptime_monitoring.percentage}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Pings:</span>
                    <span className="text-white">{status.uptime_monitoring.total_pings}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Successful:</span>
                    <span className="text-green-400">{status.uptime_monitoring.successful_pings}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Failed:</span>
                    <span className="text-red-400">{status.uptime_monitoring.failed_pings}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Monitoring Since:</span>
                    <span className="text-white">{status.uptime_monitoring.monitoring_since}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "logs" && (
          <div className="bg-gray-800 border border-gray-700 rounded-lg">
            <div className="p-6">
              {/* Log Filter and Clear Button */}
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <label className="text-sm font-medium text-gray-300">Filter by level:</label>
                  <div className="flex space-x-2">
                    {['ERROR', 'INFO', 'ALL'].map((level) => (
                      <button
                        key={level}
                        onClick={() => setLogFilter(level)}
                        className={`px-3 py-1 rounded text-sm transition-colors ${
                          logFilter === level
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                        }`}
                      >
                        {level}
                      </button>
                    ))}
                  </div>
                  <span className="text-sm text-gray-400">
                    ({filteredLogs.length} of {logs.length} logs)
                  </span>
                </div>
                
                {/* Clear Logs Button */}
                <button
                  onClick={clearLogs}
                  className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded text-sm transition-colors"
                  title="Clear all logs from database"
                >
                  🗑️ Clear Logs
                </button>
              </div>
              
              {/* Logs Display */}
              <div className="space-y-3">
                {filteredLogs.map((log, index) => (
                  <div key={index} className="flex items-start space-x-3 text-sm">
                    <span className="text-gray-500 w-32 flex-shrink-0">
                      {formatTimestamp(log.timestamp)}
                    </span>
                    <span className={`w-16 flex-shrink-0 ${getLogLevelColor(log.level)}`}>
                      {log.level}
                    </span>
                    <span className="text-gray-300 flex-1">{log.message}</span>
                  </div>
                ))}
                {filteredLogs.length === 0 && (
                  <div className="text-center text-gray-500 py-8">
                    No logs available for selected filter
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === "webhooks" && (
          <div className="space-y-6">
            {/* Strategy Filters */}
            <StrategyFilters showTitle={true} />
            
            {/* Webhook Configuration */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg">
              <div className="p-6">
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      Webhook URL (Para configurar no TradingView)
                    </label>
                    <div className="flex items-center space-x-2">
                      <input
                        type="text"
                        value={`${process.env.REACT_APP_BACKEND_URL || ''}/api/webhook/tradingview`}
                        readOnly
                        className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white font-mono"
                      />
                      <button
                        onClick={copyWebhookUrl}
                        className={`px-3 py-2 rounded-lg text-sm transition-colors ${
                          copySuccess 
                            ? 'bg-green-600 hover:bg-green-700 text-white' 
                            : 'bg-blue-600 hover:bg-blue-700 text-white'
                        }`}
                      >
                        {copySuccess ? '✓ Copiado!' : 'Copiar'}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Recent Webhooks */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg">
              <div className="p-6">
                <div className="space-y-4">
                {webhooks.map((webhook, index) => (
                  <div key={index} className="bg-gray-700 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center space-x-3">
                        <span className="text-sm text-gray-400">
                          {formatTimestamp(webhook.timestamp)}
                        </span>
                        <span className={`px-2 py-1 rounded text-xs ${
                          webhook.status === 'received' ? 'bg-green-700 text-green-200' :
                          webhook.status === 'failed' ? 'bg-red-700 text-red-200' :
                          'bg-gray-600 text-gray-200'
                        }`}>
                          {webhook.status}
                        </span>
                        <span className="px-2 py-1 rounded text-xs bg-purple-700 text-purple-200">
                          {webhook.strategy_id || 'OTHERS'}
                        </span>
                      </div>
                      <button
                        onClick={() => reExecuteWebhook(webhook)}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors"
                        title="Re-execute this webhook"
                      >
                        ▶️ Execute
                      </button>
                    </div>
                    <pre className="text-sm text-gray-300 bg-gray-800 p-3 rounded overflow-x-auto">
                      {JSON.stringify(webhook.payload, null, 2)}
                    </pre>
                  </div>
                ))}
                {webhooks.length === 0 && (
                  <div className="text-center text-gray-500 py-8">
                    {Object.values(selectedStrategies).some(Boolean) 
                      ? "Nenhum webhook encontrado para as estratégias selecionadas" 
                      : "Selecione uma ou mais estratégias nos filtros acima para ver os webhooks"}
                  </div>
                )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "responses" && (
          <div className="space-y-6">
            {/* Strategy Filters */}
            <StrategyFilters showTitle={true} />
            
            {/* Recent Responses */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg">
              <div className="p-6">
                <div className="space-y-4">
                  {responses.map((response, index) => (
                    <div key={index} className="bg-gray-700 rounded-lg p-4">
                      <div className="flex justify-between items-start mb-2">
                        <div className="flex items-center space-x-3">
                          <span className="text-sm text-gray-400">
                            {formatTimestamp(response.timestamp)}
                          </span>
                          <span className={`px-2 py-1 rounded text-xs ${
                            response.status === 'sent' ? 'bg-blue-700 text-blue-200' :
                            response.status === 'failed' ? 'bg-red-700 text-red-200' :
                            'bg-gray-600 text-gray-200'
                          }`}>
                            {response.status}
                          </span>
                          <span className="px-2 py-1 rounded text-xs bg-purple-700 text-purple-200">
                            {response.strategy_id || 'OTHERS'}
                          </span>
                        </div>
                      </div>
                    <pre className="text-sm text-gray-300 bg-gray-800 p-3 rounded overflow-x-auto">
                      {JSON.stringify(response.response_data, null, 2)}
                    </pre>
                  </div>
                ))}
                {responses.length === 0 && (
                  <div className="text-center text-gray-500 py-8">
                    {Object.values(selectedStrategies).some(Boolean) 
                      ? "Nenhuma response encontrada para as estratégias selecionadas" 
                      : "Selecione uma ou mais estratégias nos filtros acima para ver as responses"}
                  </div>
                )}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;