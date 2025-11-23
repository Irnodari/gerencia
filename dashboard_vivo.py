from pyvis.network import Network
from SPARQLWrapper import SPARQLWrapper, JSON, BASIC
import time
import os

# --- Configurações ---
FUSEKI_URL = "http://localhost:3030/rede/query"
OUTPUT_FILE = "monitoramento.html"
REFRESH_RATE = 2

# --- IPs e URIs Fixos ---
GW_A_IP = "172.25.0.101"
GW_B_IP = "172.25.0.102"
GW_A_URI = f"Gateway_{GW_A_IP.replace('.', '_')}"
GW_B_URI = f"Gateway_{GW_B_IP.replace('.', '_')}"

# --- Layout (Pixels) ---
X_GW_LEFT = -500   # Gateway A
X_GW_RIGHT = 500   # Gateway B
X_CENTER = 0       # Interfaces
Y_SPACING = 100    # Altura entre interfaces

def fetch_data():
    sparql = SPARQLWrapper(FUSEKI_URL)
    sparql.setHTTPAuth(BASIC)
    sparql.setCredentials("admin", "admin")
    sparql.setReturnFormat(JSON)
    
    # Query Expandida
    sparql.setQuery("""
        PREFIX : <http://rede#>
        SELECT ?interface ?nome ?status ?gateway ?metricType ?metricVal ?metricUnit
        WHERE {
            GRAPH ?g {
                ?interface :tipo :InterfaceReal ;
                           :nome ?nome ;
                           :status ?status ;
                           :dependeDe ?gateway .
                
                OPTIONAL { 
                    ?interface :temMetrica ?m .
                    ?m :tipo ?metricType ; :valor ?metricVal ; :unidade ?metricUnit .
                }
            }
        }
    """)
    try: return sparql.query().convert()["results"]["bindings"]
    except: return []

def get_name(uri): return uri.split('#')[-1]

def format_metric(val, unit):
    """Formata bytes e bits de forma legível"""
    try:
        val = int(val)
        # Se for velocidade (bps), usa base 1000 (k, M, G)
        if unit == 'bps':
            power = 1000
            labels = {0 : '', 1: 'k', 2: 'M', 3: 'G'}
        else: # Bytes usa base 1024
            power = 1024
            labels = {0 : '', 1: 'K', 2: 'M', 3: 'G'}
            
        n = 0
        while val > power:
            val /= power
            n += 1
        return f"{val:.1f} {labels[n]}{unit}"
    except: return f"0 {unit}"

print(f"--- Dashboard Centralizado (Métricas Expandidas) ---")

while True:
    data = fetch_data()
    
    if data:
        net = Network(height='100vh', width='100%', bgcolor='#1a1a1a', font_color='white')
        net.toggle_physics(False) 

        # 1. Gateways Fixos
        net.add_node(GW_A_URI, label=f"Gateway Alpha\n{GW_A_IP}", color='#ffae00', 
                     size=50, shape='database', x=X_GW_LEFT, y=0, font={'size': 20})
        
        net.add_node(GW_B_URI, label=f"Gateway Beta\n{GW_B_IP}", color='#ffae00', 
                     size=50, shape='database', x=X_GW_RIGHT, y=0, font={'size': 20})

        # 2. Agrupa dados
        interfaces = {}
        for item in data:
            uri = get_name(item['interface']['value'])
            if uri not in interfaces:
                interfaces[uri] = {
                    'nome': item['nome']['value'],
                    'status': item['status']['value'],
                    'gw': get_name(item['gateway']['value']),
                    'metrics': {}
                }
            
            # Processa Métrica se existir (Com correção de chaves)
            if 'metricType' in item:
                m_type = get_name(item['metricType']['value']) # Ex: InOctets
                
                # CORREÇÃO: Usa .get() para segurança
                m_val = item.get('metricVal', {}).get('value', '0')
                m_unit = item.get('metricUnit', {}).get('value', '')
                
                interfaces[uri]['metrics'][m_type] = format_metric(m_val, m_unit)

        # Converte para lista e ordena
        node_list = []
        for uri, info in interfaces.items():
            name = info['nome']
            sort_key = int(name.replace('veth', '')) if 'veth' in name else 99
            
            # Monta o Label com as Métricas
            mets = info['metrics']
            rx = mets.get('InOctets', '-')
            tx = mets.get('OutOctets', '-')
            spd = mets.get('Speed', '-')
            
            # Label Multi-linha formatado
            label_final = f"{name}\nRX: {rx}\nTX: {tx}"

            node_list.append({
                'id': uri,
                'label': label_final,
                'status': info['status'],
                'gw_uri': info['gw'],
                'sort_key': sort_key
            })

        node_list.sort(key=lambda x: x['sort_key'])

        # 3. Desenha Interfaces
        total_h = len(node_list) * Y_SPACING
        current_y = -(total_h / 2)

        for item in node_list:
            color = '#00ff00' 
            if item['status'] in ['UNREACHABLE', 'DOWN']: color = '#ff0000'

            # Fonte monoespaçada ajuda a alinhar os números
            net.add_node(item['id'], label=item['label'], title=item['status'], 
                         color=color, size=30, shape='box', x=X_CENTER, y=current_y, 
                         font={'face': 'monospace', 'align': 'left'})
            
            net.add_edge(item['gw_uri'], item['id'], color='#666666', width=2)
            current_y += Y_SPACING

        # 4. Salva e Injeta Refresh
        net.save_graph(OUTPUT_FILE)
        
        with open(OUTPUT_FILE, "r") as f: html = f.read()
        script = f"<script>setTimeout(()=>window.location.reload(1), {REFRESH_RATE*1000});</script>"
        legend = """
        <div style='position:absolute;top:10px;left:10px;background:rgba(0,0,0,0.8);padding:10px;color:white;border-radius:5px;font-family:sans-serif'>
            <h3>Monitoramento Full-Stack</h3>
            <div style='font-size:12px;margin-bottom:5px'>Gateways & Hops Dinâmicos</div>
            <hr>
            <div><span style='color:#ffae00'>●</span> Gateway Físico</div>
            <div><span style='color:#00ff00'>■</span> Interface OK</div>
            <div><span style='color:#ff0000'>■</span> Interface Crítica</div>
            <div style='margin-top:5px;color:#aaa;font-size:10px'>RX/TX: Tráfego em Tempo Real</div>
        </div>
        """
        html = html.replace("</body>", f"{legend}{script}</body>")
        with open(OUTPUT_FILE, "w") as f: f.write(html)

        print(f"Atualizado: {len(node_list)} interfaces.")
    
    time.sleep(REFRESH_RATE)