from pyvis.network import Network
import networkx as nx
from SPARQLWrapper import SPARQLWrapper, JSON, BASIC
import time
import os

# Configurações
FUSEKI_URL = "http://localhost:3030/rede/query"
OUTPUT_FILE = "monitoramento.html"

def get_data():
    sparql = SPARQLWrapper(FUSEKI_URL)
    sparql.setHTTPAuth(BASIC)
    sparql.setCredentials("admin", "admin")
    sparql.setReturnFormat(JSON)
    sparql.setQuery("""
        PREFIX : <http://rede#>
        SELECT ?interface ?nome ?status ?gateway
        WHERE {
            GRAPH ?g {
                ?interface :tipo :InterfaceReal ;
                           :nome ?nome ;
                           :status ?status ;
                           :dependeDe ?gateway .
            }
        }
    """)
    try:
        return sparql.query().convert()["results"]["bindings"]
    except:
        return []

print(f"--- Gerando Painel Web em {os.getcwd()}/{OUTPUT_FILE} ---")
print("Abra este arquivo no navegador e atualize (F5) para ver as mudanças.")

while True:
    data = get_data()
    if data:
        # Cria a rede PyVis
        net = Network(height='750px', width='100%', bgcolor='#222222', font_color='white')
        
        # Força o layout hierárquico (Gateways em cima)
        # net.force_atlas_2based() # Descomente para física solta
        
        for item in data:
            gw_name = item['gateway']['value'].split('#')[-1]
            iface_name = item['nome']['value']
            status = item['status']['value']

            # Cores
            color_iface = '#ff4444' if status == 'UNREACHABLE' else '#00ff00'
            color_gw = '#ffa500' # Laranja

            # Adiciona Nós
            net.add_node(gw_name, label=gw_name, color=color_gw, size=30, shape='dot')
            net.add_node(iface_name, label=f"{iface_name}\n({status})", color=color_iface, size=15, shape='dot')
            
            # Adiciona Aresta
            net.add_edge(gw_name, iface_name, color='#555555')

        # Opções de física para ficar estável
        net.set_options("""
        var options = {
          "physics": {
            "hierarchicalRepulsion": {
              "centralGravity": 0.0,
              "springLength": 100,
              "springConstant": 0.01,
              "nodeDistance": 120,
              "damping": 0.09
            },
            "solver": "hierarchicalRepulsion"
          }
        }
        """)
        
        net.save_graph(OUTPUT_FILE)
        print(f"Atualizado! Status: {len(data)} interfaces.")
    
    time.sleep(2)