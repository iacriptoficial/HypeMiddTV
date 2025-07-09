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
  const [currentEnvironment, setCurrentEnvironment] = useState("testnet");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch data functions
  const fetchStatus = async () => {
    try {
      const response = await axios.get(`${API}/status`);
      setStatus(response.data);
    } catch (err) {
      console.error("Error fetching status:", err);
      setError("Failed to fetch server status");
    }
  };

  const fetchLogs = async (limit = 100) => {
    try {
      const response = await axios.get(`${API}/logs?limit=${limit}`);
      setLogs(response.data.logs);
    } catch (err) {
      console.error("Error fetching logs:", err);
    }
  };

  const fetchWebhooks = async (limit = 50) => {
    try {
      const response = await axios.get(`${API}/webhooks?limit=${limit}`);
      setWebhooks(response.data.webhooks);
    } catch (err) {
      console.error("Error fetching webhooks:", err);
    }
  };

  const fetchResponses = async (limit = 50) => {
    try {
      const response = await axios.get(`${API}/responses?limit=${limit}`);
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
      setError("Failed to switch environment");
    }
  };

  // Auto-refresh data
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        fetchStatus(),
        fetchLogs(),
        fetchWebhooks(),
        fetchResponses(),
        fetchEnvironment()
      ]);
      setLoading(false);
    };

    loadData();

    // Auto-refresh every 5 seconds
    const interval = setInterval(() => {
      fetchStatus();
      fetchLogs();
      fetchWebhooks();
      fetchResponses();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

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

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-white text-xl">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 p-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <h1 className="text-2xl font-bold">TradingView → Hyperliquid</h1>
            <div className="flex items-center space-x-2">
              <span className="text-sm text-gray-400">Environment:</span>
              <div className="flex space-x-2">
                <button
                  onClick={() => switchEnvironment("testnet")}
                  className={`px-3 py-1 rounded text-sm ${
                    currentEnvironment === "testnet"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                  }`}
                >
                  Testnet
                </button>
                <button
                  onClick={() => switchEnvironment("mainnet")}
                  className={`px-3 py-1 rounded text-sm ${
                    currentEnvironment === "mainnet"
                      ? "bg-red-600 text-white"
                      : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                  }`}
                >
                  Mainnet
                </button>
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            {status && (
              <div className="flex items-center space-x-2">
                <div className={`w-3 h-3 rounded-full ${status.hyperliquid_connected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                <span className="text-sm">{status.hyperliquid_connected ? 'Connected' : 'Disconnected'}</span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex space-x-8">
            {["dashboard", "logs", "webhooks", "responses"].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-4 px-1 border-b-2 font-medium text-sm capitalize ${
                  activeTab === tab
                    ? "border-blue-500 text-blue-400"
                    : "border-transparent text-gray-400 hover:text-gray-300"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Error Message */}
      {error && (
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="bg-red-900 border border-red-700 text-red-200 px-4 py-3 rounded">
            {error}
          </div>
        </div>
      )}

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
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
                  ${status?.balance?.toFixed(2) || "0.00"}
                </div>
                <div className="text-sm text-gray-400 mt-2">
                  {currentEnvironment === "testnet" ? "Testnet Balance" : "Mainnet Balance"}
                </div>
              </div>
            </div>

            {/* Statistics */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Statistics</h3>
              {status && (
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Webhooks:</span>
                    <span className="text-white">{status.total_webhooks}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Successful:</span>
                    <span className="text-green-400">{status.successful_forwards}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Failed:</span>
                    <span className="text-red-400">{status.failed_forwards}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Success Rate:</span>
                    <span className="text-white">
                      {status.total_webhooks > 0 
                        ? ((status.successful_forwards / status.total_webhooks) * 100).toFixed(1) + '%'
                        : '0%'
                      }
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "logs" && (
          <div className="bg-gray-800 border border-gray-700 rounded-lg">
            <div className="px-6 py-4 border-b border-gray-700">
              <h3 className="text-lg font-semibold">Recent Logs</h3>
            </div>
            <div className="p-6">
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {logs.map((log, index) => (
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
                {logs.length === 0 && (
                  <div className="text-center text-gray-500 py-8">No logs available</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === "webhooks" && (
          <div className="bg-gray-800 border border-gray-700 rounded-lg">
            <div className="px-6 py-4 border-b border-gray-700">
              <h3 className="text-lg font-semibold">Recent Webhooks</h3>
            </div>
            <div className="p-6">
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {webhooks.map((webhook, index) => (
                  <div key={index} className="bg-gray-700 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
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
                    </div>
                    <pre className="text-sm text-gray-300 bg-gray-800 p-3 rounded overflow-x-auto">
                      {JSON.stringify(webhook.payload, null, 2)}
                    </pre>
                  </div>
                ))}
                {webhooks.length === 0 && (
                  <div className="text-center text-gray-500 py-8">No webhooks received</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === "responses" && (
          <div className="bg-gray-800 border border-gray-700 rounded-lg">
            <div className="px-6 py-4 border-b border-gray-700">
              <h3 className="text-lg font-semibold">Hyperliquid Responses</h3>
            </div>
            <div className="p-6">
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {responses.map((response, index) => (
                  <div key={index} className="bg-gray-700 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
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
                    </div>
                    <pre className="text-sm text-gray-300 bg-gray-800 p-3 rounded overflow-x-auto">
                      {JSON.stringify(response.response_data, null, 2)}
                    </pre>
                  </div>
                ))}
                {responses.length === 0 && (
                  <div className="text-center text-gray-500 py-8">No responses available</div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;