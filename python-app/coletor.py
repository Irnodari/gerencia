import time
import docker
from pysnmp.hlapi import *
from rdflib import Graph, Literal, Namespace, RDF, URIRef
import requests
import os

# --- CONFIGURAÇÕES ---
SNMP_TARGET = "device-node"
SNMP_PORT = 161
COMMUNITY = "public"
FUSEKI_UPDATE_URL = "http://jena-fuseki:3030/rede/update"
REDE = Namespace("http://rede#")

# Configuração de Alta Disponibilidade (HA)
GATEWAY_ALPHA = "172.25.0.101"
GATEWAY_BETA =  "172.25.0.102"
NO_ROUTE = "0.0.0.0"


try:
    client = docker.from_env()
    router_container = client.containers.get('device-node')
except:
    print("AVISO: Docker não conectado.")
    router_container = None

# --- OIDS ---
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_OPER  = "1.3.6.1.2.1.2.2.1.8"
OID_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_ROUTE_DEST = "1.3.6.1.2.1.4.21.1.1"
OID_ROUTE_NEXT_HOP = "1.3.6.1.2.1.4.21.1.7"
OID_ROUTE_IF_INDEX = "1.3.6.1.2.1.4.21.1.2"

def check_ping(host):
    response = os.system(f"ping -c 1 -W 1 {host} > /dev/null 2>&1")
    return response == 0

def perform_failover(dead_gw, backup_gw, affected_routes, if_names_map):
    """
    Executa o failover com comando ROBUSTO.
    Agora recebe if_names_map para saber qual 'veth' usar.
    """
#    if not router_container: return

    if dead_gw != "0.0.0.0":
        print(f"!!! ALERTA: Gateway {dead_gw} CAIU! Tentando mover {len(affected_routes)} rotas para {backup_gw}...")
    else:
        print(f"INFO: Tentando reativar {len(affected_routes)} rotas...")
    if not check_ping(backup_gw):
        print(f"!!! FALHA: Gateway {backup_gw} ESTÁ FORA! Sem rotas disponíveis, desligando inferfaces...")
        for route_dest, if_idx in affected_routes:
            if_name = if_names_map.get(if_idx, "")
            dev_cmd = f"dev {if_name}" if if_name else ""
            cmd = f"ip link set {if_name} down"
            code, out = router_container.exec_run(cmd)
            if code == 0:
                print(f"   [OK] Desativado adaptador {if_name}")
            else:
                print(f"    [ERRO] Falha ao desativar adaptador {if_name}")
        return
    if dead_gw == "0.0.0.0":
        for route_dest, if_idx in affected_routes:
            if_name = if_names_map.get(if_idx, "")
            dev_cmd = f"dev {if_name}" if if_name else ""
            cmd = f"ip link set {if_name} up"
            code, out = router_container.exec_run(cmd)
            if code == 0:
                print(f"   [OK] Reativando adaptador {if_name}")
            else:
                print(f"    [ERRO] Falha ao reativar adaptador {if_name}")
    
    for route_dest, if_idx in affected_routes:
        # Descobre o nome da interface (ex: veth0)
        if_name = if_names_map.get(if_idx, "")
        
        # Monta comando blindado: "ip route replace 50.0.0.0/24 via 172... dev veth0 onlink"
        # 'replace' é melhor que 'change' (cria se não existir)
        dev_cmd = f"dev {if_name}" if if_name else ""
        cmd = f"ip route replace {route_dest}/24 via {backup_gw} {dev_cmd} onlink"
        
        try:
            # exec_run retorna (exit_code, output_bytes)
            code, out = router_container.exec_run(cmd)
            
            if code == 0:
                print(f"   [OK] Rota {route_dest} ({if_name}) -> {backup_gw}")
            else:
                # Decodifica o erro para vermos no log
                err_msg = out.decode('utf-8').strip()
                print(f"   [ERRO] Falha ao mover {route_dest}: Código {code} - {err_msg}")
                
        except Exception as e:
            print(f"   [ERRO CRÍTICO] Docker falhou: {e}")

def snmp_walk(oid_base):
    data = {}
    for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
        SnmpEngine(),
        CommunityData(COMMUNITY),
        UdpTransportTarget((SNMP_TARGET, SNMP_PORT)),
        ContextData(),
        ObjectType(ObjectIdentity(oid_base)),
        lexicographicMode=False
    ):
        if errorIndication or errorStatus: continue
        for varBind in varBinds:
            oid_str = str(varBind[0])
            val = varBind[1]
            if oid_str.startswith(oid_base):
                index = oid_str[len(oid_base)+1:]
                try: data[index] = val.prettyPrint()
                except: data[index] = str(val)
    return data

def coletar_e_atualizar():
    print("--- Iniciando Ciclo de Gerência ---")
    g = Graph()
    g.bind("rede", REDE)

    # 1. Coleta
    descricoes = snmp_walk(OID_IF_DESCR) # Mapa: Index -> Nome (veth0)
    oper_status = snmp_walk(OID_IF_OPER)
    in_octets = snmp_walk(OID_IN_OCTETS)
    out_octets = snmp_walk(OID_OUT_OCTETS)
    rotas_next_hop = snmp_walk(OID_ROUTE_NEXT_HOP)
    rotas_if_index = snmp_walk(OID_ROUTE_IF_INDEX)

    # 2. Mapeamento de Rotas
    interface_gateway_map = {}
    routes_by_gw = {GATEWAY_ALPHA: [], GATEWAY_BETA: [], NO_ROUTE: []}
    registered_interfaces = []

    for route_dest, next_hop in rotas_next_hop.items():
        next_hop = next_hop.replace("'", "").strip()
        if_idx = rotas_if_index.get(route_dest)
        if if_idx and oper_status[str(if_idx)] == '1':
            interface_gateway_map[str(if_idx)] = next_hop
            # Agrupa para Failover
            if next_hop in routes_by_gw:
                routes_by_gw[next_hop].append((route_dest, if_idx))
        elif if_idx:
            routes_by_gw[NO_ROUTE].append((route_dest, if_idx))

    # 3. Lógica de Failover (Agora passando 'descricoes')
    if not check_ping(GATEWAY_ALPHA):
        if len(routes_by_gw[GATEWAY_ALPHA]) > 0:
            perform_failover(GATEWAY_ALPHA, GATEWAY_BETA, routes_by_gw[GATEWAY_ALPHA], descricoes)
            if router_container: router_container.exec_run("pkill -HUP snmpd")
    
    if not check_ping(GATEWAY_BETA):
        if len(routes_by_gw[GATEWAY_BETA]) > 0:
            perform_failover(GATEWAY_BETA, GATEWAY_ALPHA, routes_by_gw[GATEWAY_BETA], descricoes)
            if router_container: router_container.exec_run("pkill -HUP snmpd")
    if len(routes_by_gw[NO_ROUTE]) > 0:
        if check_ping(GATEWAY_ALPHA):
            perform_failover(NO_ROUTE, GATEWAY_ALPHA, routes_by_gw[NO_ROUTE], descricoes)
        elif check_ping(GATEWAY_BETA):
            perform_failover(NO_ROUTE, GATEWAY_BETA, routes_by_gw[NO_ROUTE], descricoes)


    # 4. Monta Grafo
    count_interfaces = 0
    for idx, nome_obj in descricoes.items():
        nome = str(nome_obj)
        if "lo" in nome: continue
        
        count_interfaces += 1
        uri_interface = URIRef(f"http://rede#Interface_{nome}")
        g.add((uri_interface, RDF.type, REDE.InterfaceReal))
        g.add((uri_interface, REDE.nome, Literal(nome)))
        g.add((uri_interface, REDE.status, Literal("UP" if oper_status.get(idx) == '1' else "DOWN")))

        # Métricas
        uri_rx = URIRef(f"http://rede#Metric_RX_{nome}")
        g.add((uri_interface, REDE.temMetrica, uri_rx))
        g.add((uri_rx, REDE.tipo, Literal("InOctets")))
        g.add((uri_rx, REDE.valor, Literal(in_octets.get(idx, '0'))))
        g.add((uri_rx, REDE.unidade, Literal("Bytes")))

        uri_tx = URIRef(f"http://rede#Metric_TX_{nome}")
        g.add((uri_interface, REDE.temMetrica, uri_tx))
        g.add((uri_tx, REDE.tipo, Literal("OutOctets")))
        g.add((uri_tx, REDE.valor, Literal(out_octets.get(idx, '0'))))
        g.add((uri_tx, REDE.unidade, Literal("Bytes")))

        if idx in interface_gateway_map:
            gw_ip = interface_gateway_map[idx]
            uri_gw = URIRef(f"http://rede#Gateway_{gw_ip.replace('.', '_')}")
            g.add((uri_interface, REDE.dependeDe, uri_gw))
            g.add((uri_gw, RDF.type, REDE.Gateway))
            g.add((uri_gw, REDE.ip, Literal(gw_ip)))

    # 5. Envia Fuseki
    if count_interfaces > 0:
        delete_query = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX : <http://rede#>
            DELETE { ?s ?p ?o } WHERE { ?s ?p ?o . ?s rdf:type :InterfaceReal . }
        """
        try: requests.post(FUSEKI_UPDATE_URL, data={'update': delete_query})
        except: pass
        
        insert_query = f"INSERT DATA {{ {g.serialize(format='nt')} }}"
        try: requests.post(FUSEKI_UPDATE_URL, data={'update': insert_query})
        except: pass
        print(f"Gerência Ativa: Monitorando {count_interfaces} interfaces.")

if __name__ == "__main__":
    print("Aguardando inicialização...")
    time.sleep(10)
    while True:
        try: coletar_e_atualizar()
        except Exception as e: print(f"Erro Ciclo: {e}")
        time.sleep(2)
