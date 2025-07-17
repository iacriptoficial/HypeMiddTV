# Hyperliquid Trading Bot

Sistema completo de trading automatizado para a exchange Hyperliquid com integração TradingView via webhooks. O sistema executa ordens reais de mercado e limit, gerencia posições com reversão automática, e implementa stop loss e take profit em múltiplos níveis.

## 🚀 Funcionalidades

- **Execução de Ordens Reais**: Market e limit orders na Hyperliquid (testnet/mainnet)
- **Integração TradingView**: Recebe sinais via webhooks e executa automaticamente
- **Gerenciamento de Posições**: Reversão automática de posições (long ↔ short)
- **Stop Loss**: Ordens de stop loss automáticas com preços personalizados
- **Take Profit Multi-Nível**: Suporte para TP1, TP2, TP3, TP4 com tamanhos parciais
- **Timezone Brasileiro**: Todos os logs e timestamps em GMT-3
- **Interface Web**: Dashboard para monitoramento de ordens, logs e webhooks
- **Precisão Decimal**: Truncamento inteligente baseado no símbolo (não arredondamento)

## 📋 Requisitos

### Sistema
- **Python 3.8+**
- **Node.js 16+** 
- **MongoDB**
- **Supervisor** (para gerenciamento de processos)

### Dependências Python
```bash
fastapi
uvicorn
pymongo
hyperliquid-python-sdk
python-dotenv
pytz
pydantic
```

### Dependências Frontend
```bash
react
axios
```

## 🛠️ Instalação

### 1. Clone e Configure o Ambiente

```bash
# Clone o repositório
git clone <repository-url>
cd hyperliquid-trading-bot

# Instalar dependências do backend
cd backend
pip install -r requirements.txt

# Instalar dependências do frontend
cd ../frontend
yarn install  # IMPORTANTE: Use yarn, não npm
```

### 2. Configuração do MongoDB

```bash
# Instalar MongoDB (Ubuntu/Debian)
sudo apt update
sudo apt install mongodb

# Iniciar serviço
sudo systemctl start mongodb
sudo systemctl enable mongodb

# Verificar se está rodando
sudo systemctl status mongodb
```

### 3. Configuração das Variáveis de Ambiente

#### Backend (.env)
Crie `/app/backend/.env`:

```env
# MongoDB Configuration
MONGO_URL="mongodb://localhost:27017"
DB_NAME="hyperliquid_trading"

# Hyperliquid API Keys
HYPERLIQUID_TESTNET_KEY="0x..."  # Sua chave privada da Hyperliquid TESTNET
HYPERLIQUID_MAINNET_KEY=""       # Sua chave privada da Hyperliquid MAINNET (deixe vazio para testnet)

# Environment
ENVIRONMENT="testnet"  # ou "mainnet"
```

#### Frontend (.env)
Crie `/app/frontend/.env`:

```env
# Backend URL (NÃO MODIFIQUE)
REACT_APP_BACKEND_URL=https://your-domain.com
```

### 4. Obter Chave da Hyperliquid

1. **Acesse**: [Hyperliquid Testnet](https://app.hyperliquid.xyz/testnet)
2. **Conecte sua carteira** MetaMask/WalletConnect
3. **Obtenha testnet USDC** via faucet
4. **Exporte a chave privada** da sua carteira
5. **Cole a chave** no arquivo `.env` (campo `HYPERLIQUID_TESTNET_KEY`)

⚠️ **IMPORTANTE**: Use apenas testnet para testes. Para mainnet, substitua a URL e use `HYPERLIQUID_MAINNET_KEY`.

### 5. Configuração do Supervisor

Crie `/etc/supervisor/conf.d/trading-bot.conf`:

```ini
[program:backend]
command=uvicorn server:app --host 0.0.0.0 --port 8001 --reload
directory=/app/backend
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/backend.err.log
stdout_logfile=/var/log/supervisor/backend.out.log

[program:frontend]
command=yarn start
directory=/app/frontend
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/frontend.err.log
stdout_logfile=/var/log/supervisor/frontend.out.log
environment=PORT=3000
```

### 6. Iniciar o Sistema

```bash
# Recarregar configuração do supervisor
sudo supervisorctl reread
sudo supervisorctl update

# Iniciar serviços
sudo supervisorctl start backend
sudo supervisorctl start frontend

# Verificar status
sudo supervisorctl status
```

## 🔧 Uso do Sistema

### 1. Acessar a Interface

Abra o navegador em: `http://localhost:3000` (desenvolvimento) ou sua URL de produção.

### 2. Configurar Webhook no TradingView

1. **Pine Script**: Configure seu indicador para enviar webhooks
2. **URL do Webhook**: `https://your-domain.com/api/webhook/tradingview`
3. **Formato do Payload**:

```json
{
  "symbol": "SOL",
  "side": "buy",
  "entry": "market",
  "quantity": "1.0",
  "price": "175.50",
  "stop": "170.00",
  "tp1_price": "180.00",
  "tp1_perc": "0.25",
  "tp2_price": "185.00", 
  "tp2_perc": "0.25",
  "tp3_price": "190.00",
  "tp3_perc": "0.25",
  "tp4_price": "195.00",
  "tp4_perc": "0.25"
}
```

### 3. Parâmetros do Webhook

#### Obrigatórios
- **symbol**: Símbolo do ativo (SOL, BTC, ETH, etc.)
- **side**: Direção ("buy" ou "sell")
- **entry**: Tipo de ordem ("market" ou "limit")
- **quantity**: Tamanho da posição

#### Opcionais
- **price**: Preço para ordens limit
- **stop**: Preço do stop loss
- **tp1_price, tp2_price, tp3_price, tp4_price**: Preços dos take profits
- **tp1_perc, tp2_perc, tp3_perc, tp4_perc**: Tamanhos dos take profits (não percentual, mas quantidade real)

### 4. Exemplos de Uso

#### Ordem Market Simples
```json
{
  "symbol": "SOL",
  "side": "buy", 
  "entry": "market",
  "quantity": "1.0"
}
```

#### Ordem Completa com Stop e TPs
```json
{
  "symbol": "SOL",
  "side": "sell",
  "entry": "market", 
  "quantity": "2.5",
  "stop": "170.00",
  "tp1_price": "160.00",
  "tp1_perc": "1.0",
  "tp2_price": "155.00",
  "tp2_perc": "1.0", 
  "tp3_price": "150.00",
  "tp3_perc": "0.5"
}
```

## 📚 API Endpoints

### Webhook
- **POST** `/api/webhook/tradingview` - Recebe sinais do TradingView
- **POST** `/api/webhook/re-execute` - Re-executa webhook existente

### Monitoring
- **GET** `/api/status` - Status do servidor e saldo da conta
- **GET** `/api/logs` - Logs do sistema
- **GET** `/api/webhooks` - Histórico de webhooks recebidos  
- **GET** `/api/responses` - Respostas da Hyperliquid

### Orders
- **GET** `/api/orders/history` - Histórico de ordens na exchange
- **GET** `/api/orders/open` - Ordens abertas na exchange

### Management
- **DELETE** `/api/logs` - Limpar logs do sistema
- **POST** `/api/restart` - Reiniciar servidor

## 🏗️ Estrutura do Projeto

```
/app/
├── backend/                 # FastAPI backend
│   ├── server.py           # Servidor principal
│   ├── requirements.txt    # Dependências Python
│   └── .env               # Variáveis de ambiente
├── frontend/               # React frontend  
│   ├── src/
│   │   ├── App.js         # Componente principal
│   │   └── index.css      # Estilos
│   ├── package.json       # Dependências Node.js
│   └── .env              # Variáveis de ambiente
└── README.md             # Este arquivo
```

## 🔧 Troubleshooting

### Problemas Comuns

#### 1. Backend não inicia
```bash
# Verificar logs
tail -f /var/log/supervisor/backend.err.log

# Problemas comuns:
# - Chave da Hyperliquid inválida
# - MongoDB não conectando
# - Porta 8001 já em uso
```

#### 2. Frontend não carrega
```bash
# Verificar logs
tail -f /var/log/supervisor/frontend.err.log

# Problemas comuns:
# - yarn não instalado (usar yarn, não npm)
# - Porta 3000 já em uso
# - REACT_APP_BACKEND_URL incorreta
```

#### 3. Ordens não executam
```bash
# Verificar no dashboard:
# - Saldo suficiente na conta Hyperliquid
# - Chave da API configurada corretamente
# - Symbol válido (SOL, BTC, ETH, etc.)
# - Formato do webhook correto
```

#### 4. Erro "float_to_wire causes rounding"
```bash
# Causa: Tamanho da ordem com muitas casas decimais
# Solução: O sistema trunca automaticamente
# Verificar szDecimals do símbolo
```

### Logs Importantes

```bash
# Backend logs
sudo tail -f /var/log/supervisor/backend.out.log

# Frontend logs  
sudo tail -f /var/log/supervisor/frontend.out.log

# MongoDB logs
sudo tail -f /var/log/mongodb/mongod.log
```

## 🔒 Segurança

### Chaves Privadas
- **NUNCA** compartilhe suas chaves privadas
- **Use testnet** para desenvolvimento  
- **Mantenha** as chaves em arquivos `.env` seguros
- **Configure** permissões adequadas nos arquivos

### Rede
- **Configure firewall** adequadamente
- **Use HTTPS** em produção
- **Limite acesso** aos endpoints sensíveis

## 📈 Monitoramento

### Dashboard Web
- **Status do servidor** e conectividade
- **Saldo da conta** Hyperliquid em tempo real
- **Histórico de webhooks** recebidos
- **Logs do sistema** com filtros
- **Respostas da Hyperliquid** para cada operação

### Funcionalidades do Dashboard
- **Clear Logs**: Limpar histórico de logs
- **Restart Server**: Reiniciar servidor backend
- **Execute**: Re-executar webhooks para testes
- **Copy Webhook URL**: Copiar URL para configurar no TradingView

## 📞 Suporte

Para questões sobre implementação:

1. **Verificar logs** primeiro
2. **Conferir configurações** (.env, supervisor, etc.)
3. **Testar conectividade** com Hyperliquid
4. **Validar formato** dos webhooks
5. **Consultar documentação** da Hyperliquid

## ⚠️ Avisos Importantes

- **Este é um sistema de trading real** - teste sempre em testnet primeiro
- **Gerencie riscos adequadamente** - defina stop loss apropriados  
- **Monitore posições** - o sistema é automatizado mas requer supervisão
- **Backup das configurações** - mantenha backups dos arquivos .env
- **Atualize dependências** - mantenha o sistema atualizado

## 🎯 Precisão e Formatação

O sistema implementa **truncamento inteligente**:

- **Tamanhos (_perc)**: Truncados para szDecimals do símbolo
- **Preços (_price)**: Formatados para tick size apropriado
- **Nunca arredonda**: Sempre trunca para não exceder valores originais
- **Compatibilidade**: Garante compatibilidade com regras da exchange

Exemplo:
- `"tp1_perc": "0.1146131805"` → `0.11` (SOL, szDecimals=2)
- `"tp1_price": "180.987654"` → `180.5` (SOL, tick size=0.5)
