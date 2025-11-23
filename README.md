# Gerência de Redes Autônoma com Grafos de Conhecimento

Este projeto implementa um sistema de **Gerência de Redes Baseada em Conhecimento** (Knowledge-Based Network Management). O sistema é capaz de descobrir a topologia da rede dinamicamente, monitorar o estado dos dispositivos via SNMP e realizar ações de **auto-recuperação (Self-Healing)** em caso de falhas de roteamento, utilizando uma ontologia RDF para tomada de decisão.

Projeto desenvolvido para a disciplina de **Gerência e Aplicações em Redes (UFRGS)**.

---

## 🚀 Funcionalidades Principais

### 1. Descoberta de Topologia Dinâmica (IP-FORWARD-MIB)
O sistema não possui um mapa estático da rede. Ele utiliza SNMP para ler a **Tabela de Roteamento** (`ipRouteTable`) do dispositivo central e descobre automaticamente:
* Quais interfaces existem.
* Para qual Gateway cada interface está apontando.
* O endereço IP dos Gateways vizinhos.
* *Destaque:* Se você alterar uma rota no Linux manualmente, o grafo se atualiza sozinho.

### 2. Gerência Ativa e Self-Healing (Failover)
O sistema atua como um controlador autônomo (Ciclo MAPE-K):
* **Monitora:** Verifica a disponibilidade dos Gateways (Alpha e Beta) via Ping/ICMP.
* **Analisa:** Se um Gateway cair, consulta o Grafo de Conhecimento para saber quais rotas dependem dele.
* **Executa:** Envia comandos ao roteador (`ip route replace`) para migrar o tráfego para o Gateway de backup.
* **Atualiza:** Limpa o cache SNMP e atualiza a ontologia para refletir a nova topologia.

### 3. Visualização Semântica em Tempo Real
* Dashboard Web interativo construído com **Vis.js**.
* Arquitetura Cliente-Servidor: Backend Python gera JSON, Frontend consome via AJAX.
* Exibe métricas de tráfego (RX/TX) e estado das interfaces (UP/DOWN).
* Visualiza a relação semântica `interface --[dependeDe]--> gateway`.

---

## 🛠️ Tecnologias Utilizadas

* **Docker & Docker Compose:** Orquestração do ambiente simulado (Roteador Debian + Gateways Alpine).
* **Python 3:** Scripts de Coleta (Manager) e Controle.
* **SNMP (Net-SNMP):** Protocolo de gerenciamento (agente rodando no `device-node`).
* **Apache Jena Fuseki:** Banco de dados RDF (Triplestore) para armazenar o Grafo de Conhecimento.
* **SPARQL:** Linguagem de consulta utilizada para inferir estados e dependências.
* **Vis.js:** Biblioteca Javascript para renderização do grafo no navegador.

---

## 📦 Estrutura do Projeto

```bash
.
├── device-node/        # Container do Roteador (Debian + SNMPD)
│   ├── entrypoint.sh   # Script que cria as veths e rotas iniciais
│   └── Dockerfile      # Instalação de ferramentas de rede (iproute2, snmp)
├── python-app/         # Container da Aplicação de Gerência
│   ├── coletor.py      # Coleta SNMP, Lógica de Failover e Update no Fuseki
│   ├── gerente.py      # Consulta SPARQL e gera JSON para o frontend
│   └── requirements.txt
├── public_html/        # Volume compartilhado com o Frontend
│   ├── index.html      # Dashboard (Vis.js)
│   └── dados.json      # Gerado automaticamente pelo Python
├── docker-compose.yml  # Definição dos serviços
└── README.md
````

-----

## ▶️ Como Rodar o Projeto

### 1\. Pré-requisitos

Certifique-se de ter o **Docker** e o **Docker Compose** instalados.

### 2\. Inicializar o Ambiente

Na raiz do projeto, execute:

```bash
docker-compose up -d --build
```

*Isso irá subir 4 containers: o roteador, dois gateways, o banco de dados Fuseki e a aplicação Python.*

### 3\. Iniciar o Servidor Frontend

Devido a políticas de segurança dos navegadores (CORS), o arquivo HTML precisa ser servido via HTTP para ler o JSON local.

Abra um novo terminal na pasta do projeto e execute:

```bash
cd public_html
python3 -m http.server 8000
```

*(Se estiver no Windows, pode ser `python -m http.server 8000`)*

### 4\. Acessar o Dashboard

Abra seu navegador em:
👉 **http://localhost:8000**

-----

## 🧪 Cenários de Teste (Demonstração)

### Cenário A: Descoberta Dinâmica de Rotas

Para provar que o grafo é gerado em tempo real a partir da `IP-FORWARD-MIB`:

1.  Observe uma interface (ex: `veth0`) conectada ao **Gateway Alpha** no grafo.
2.  No terminal, altere a rota manualmente dentro do roteador:
    ```bash
    docker exec device-node ip route replace 50.0.0.0/24 via 172.25.0.102 dev veth0 onlink
    ```
3.  **Resultado:** Em alguns segundos, a linha no grafo se soltará do Alpha e conectará ao **Gateway Beta** automaticamente.

### Cenário B: Auto-Recuperação (Failover Automático)

Para testar a resiliência do sistema:

1.  "Derrube" o Gateway Alpha:
    ```bash
    docker stop gateway-alpha
    ```
2.  **Resultado:**
      * O script Python detectará a falha no Ping.
      * Logs mostrarão: `!!! ALERTA: Gateway 172.25.0.101 CAIU! Movendo rotas...`
      * No Dashboard, **todas** as interfaces que dependiam do Alpha mudarão suas conexões para o **Gateway Beta** instantaneamente.

### Cenário C: Recuperação do Gateway

1.  Ligue o Gateway novamente:
    ```bash
    docker start gateway-alpha
    ```
2.  O sistema continuará operando no Beta (para evitar instabilidade), mas detectará que o Alpha está disponível para futuras operações.

### Cenário D: Desativação de interfaces

1.  Pare ambos os Gateways:
    ```bash
    docker stop gateway-alpha gateway-beta
    ```
2.  O sistema irá desativar as interfaces de rede e esperar o retorno de alguma das interfaces para seguir seu funcionamento normal.

3.  Reative um dos Gateways:
    ```bash
    docker start gateway-alpha
    ```

4.  O sistema irá reativar as interfaces e mudar o roteamento para usar o Gateway ativo

```
