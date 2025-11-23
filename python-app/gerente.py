import json
import time
import os
from SPARQLWrapper import SPARQLWrapper, JSON, BASIC

# --- CONFIGURAÇÕES ---
FUSEKI_URL = "http://jena-fuseki:3030/rede/query"
JSON_FILE = "/app/public_html/dados.json" 
REFRESH_RATE = 0.5 # Modo Turbo

def fetch_data():
    sparql = SPARQLWrapper(FUSEKI_URL)
    sparql.setHTTPAuth(BASIC)
    sparql.setCredentials("admin", "admin")
    sparql.setReturnFormat(JSON)
    
    # --- QUERY SEMÂNTICA ---
    # Agora buscamos ?predLink (o nome da relação no banco)
    sparql.setQuery("""
        PREFIX : <http://rede#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT ?interface ?nome ?status ?gwUri ?gwIp ?predLink ?metricType ?metricVal ?metricUnit
        WHERE {
            ?interface a :InterfaceReal ;
                       :nome ?nome ;
                       :status ?status .
            
            # Descobre dinamicamente como a interface se conecta ao Gateway
            OPTIONAL { 
                ?interface ?predLink ?gwUri . 
                ?gwUri a :Gateway ; :ip ?gwIp .
            }
            
            OPTIONAL { 
                ?interface :temMetrica ?m . 
                ?m :tipo ?metricType ; :valor ?metricVal ; :unidade ?metricUnit . 
            }
        }
    """)
    try: return sparql.query().convert()["results"]["bindings"]
    except: return []

def format_metric(val, unit):
    try:
        val = float(val)
        power = 1000 if unit == 'bps' else 1024
        labels = {0:'', 1:'K', 2:'M', 3:'G'}
        n = 0
        while val > power: val /= power; n += 1
        return f"{val:.1f} {labels[n]}{unit}"
    except: return f"0 {unit}"

print("--- Gerente Semântico Iniciado ---")
os.makedirs("/app/public_html", exist_ok=True)

while True:
    data = fetch_data()
    nodes = []
    edges = []
    
    if data:
        interfaces = {}
        gateways = {}

        for item in data:
            uri = item['interface']['value'].split('#')[-1]
            
            # Pega o Gateway e o Predicado (Relação)
            gw_uri = item.get('gwUri', {}).get('value', '').split('#')[-1]
            gw_ip = item.get('gwIp', {}).get('value', '')
            
            # AQUI ESTÁ A MÁGICA: Pega o nome real da ontologia (ex: 'dependeDe')
            pred_link = item.get('predLink', {}).get('value', '').split('#')[-1]

            if gw_uri: gateways[gw_uri] = gw_ip
            
            if uri not in interfaces:
                interfaces[uri] = {
                    'nome': item['nome']['value'],
                    'status': item['status']['value'],
                    'gw': gw_uri,
                    'pred': pred_link, # Guarda o nome da relação
                    'metrics': {}
                }
            
            if 'metricType' in item:
                m_t = item['metricType']['value']
                m_v = item.get('metricVal', {}).get('value', '0')
                interfaces[uri]['metrics'][m_t] = format_metric(m_v, item.get('metricUnit',{}).get('value',''))

        # Nós Gateways
        for i, (g_uri, g_ip) in enumerate(gateways.items()):
            nodes.append({'id': g_uri, 'label': f"Gateway\n{g_ip}", 'group': 'gateway', 'level': 0})

        # Nós Interfaces
        for uri, info in interfaces.items():
            rx = info['metrics'].get('InOctets','-')
            tx = info['metrics'].get('OutOctets','-')
            
            nodes.append({
                'id': uri,
                'label': f"{info['nome']}\nRX: {rx}\nTX: {tx}",
                'color': '#55ff55' if (info['status'] == 'UP' and info['gw'] and info['gw'] in gateways) or 'peer' in info['nome'] else '#ff5555',
                'group': 'interface',
                'level': 1
            })
            
            # Cria aresta usando o NOME QUE VEIO DO BANCO
            if info['gw'] and info['gw'] in gateways:
                edges.append({
                    # --- CORREÇÃO DE DIREÇÃO SEMÂNTICA ---
                    'from': uri,          # Origem: A Interface
                    'to': info['gw'],     # Destino: O Gateway
                    
                    'label': info['pred'], # Rótulo: "dependeDe"
                    'arrows': 'to',        # Seta aponta para o destino (Gateway)
                    
                    # Estilização
                    'font': {'align': 'middle', 'size': 12, 'color': 'white', 'background': '#222'},
                    'color': {'color': '#aaaaaa'},
                    'dashes': True
                })

    with open(JSON_FILE, 'w') as f: json.dump({'nodes': nodes, 'edges': edges, 'timestamp': time.time()}, f)
    time.sleep(REFRESH_RATE)
