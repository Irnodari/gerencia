from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.smi import builder, instrum, exval
from pysnmp.proto.api import v2c
import asyncio

# --- CONFIGURAÇÃO DO SWITCH VIRTUAL ---
NUM_INTERFACES = 50
# MIB OIDs
OID_IF_NUMBER = "1.3.6.1.2.1.2.1.0"
OID_IF_TABLE_BASE = "1.3.6.1.2.1.2.2.1"
# Colunas da Tabela
COL_INDEX = 1
COL_DESCR = 2
COL_ADMIN_STATUS = 7  # 1=UP, 2=DOWN
COL_OPER_STATUS = 8
COL_IN_ERRORS = 14

# Estado em Memória do Switch
mib_data = {
    OID_IF_NUMBER: v2c.Integer(NUM_INTERFACES)
}

print(f"--- INICIANDO SWITCH VIRTUAL COM {NUM_INTERFACES} PORTAS ---")

# Gera as 50 interfaces dinamicamente
for i in range(1, NUM_INTERFACES + 1):
    idx = str(i)
    # Descrição: eth1, eth2...
    mib_data[f"{OID_IF_TABLE_BASE}.{COL_INDEX}.{i}"] = v2c.Integer(i)
    mib_data[f"{OID_IF_TABLE_BASE}.{COL_DESCR}.{i}"] = v2c.OctetString(f"GigabitEthernet1/0/{i}")
    # Status: Todos UP (1) inicialmente
    mib_data[f"{OID_IF_TABLE_BASE}.{COL_ADMIN_STATUS}.{i}"] = v2c.Integer(1)
    mib_data[f"{OID_IF_TABLE_BASE}.{COL_OPER_STATUS}.{i}"] = v2c.Integer(1)
    # Erros: 0
    mib_data[f"{OID_IF_TABLE_BASE}.{COL_IN_ERRORS}.{i}"] = v2c.Integer(0)

# Adicionamos OIDs de Controle para o Gateway (Simulação)
# Gateway A Status (1=UP, 2=DOWN) - Usamos um OID arbitrário da system
OID_GATEWAY_A = "1.3.6.1.2.1.1.9.1.0" 
mib_data[OID_GATEWAY_A] = v2c.Integer(1) 

class MibInstrumController(instrum.AbstractMibInstrumController):
    def readVars(self, varBinds, acInfo=(None, None)):
        return [(o, mib_data.get(str(o), v2c.NoSuchObject())) for o, v in varBinds]

    def readNextVars(self, varBinds, acInfo=(None, None)):
        # Lógica simples de WALK (Next)
        sorted_oids = sorted(mib_data.keys(), key=lambda x: tuple(map(int, x.split('.'))))
        result = []
        for oid, val in varBinds:
            oid_str = str(oid)
            next_oid = None
            for candidate in sorted_oids:
                # Compara OIDs convertendo para tuplas de inteiros
                cand_tup = tuple(map(int, candidate.split('.')))
                req_tup = tuple(map(int, oid_str.split('.'))) if oid_str else ()
                
                if cand_tup > req_tup:
                    next_oid = candidate
                    break
            
            if next_oid:
                result.append((next_oid, mib_data[next_oid]))
            else:
                result.append((oid, v2c.EndOfMibView()))
        return result

    def writeVars(self, varBinds, acInfo=(None, None)):
        # Permite alterar qualquer valor (Simulação de falha)
        for oid, val in varBinds:
            print(f"[Switch Virtual] SET Recebido: {oid} = {val}")
            mib_data[str(oid)] = val
        return [(o, v) for o, v in varBinds]

# Setup do Engine SNMP
snmpEngine = engine.SnmpEngine()
config.addTransport(
    snmpEngine,
    udp.domainName,
    udp.UdpTransport().openServerMode(('0.0.0.0', 161))
)
config.addV1System(snmpEngine, 'public', 'public')
config.addV1System(snmpEngine, 'private', 'private') # Escrita

# Registra nosso controlador customizado
snmpContext = context.SnmpContext(snmpEngine)
snmpContext.unregisterContextName(v2c.OctetString(''))
snmpContext.registerContextName(
    v2c.OctetString(''), 
    MibInstrumController() # Aqui entra nossa lógica Python
)

cmdrsp.GetCommandResponder(snmpEngine, snmpContext)
cmdrsp.SetCommandResponder(snmpEngine, snmpContext)
cmdrsp.NextCommandResponder(snmpEngine, snmpContext) # Permite WALK

print("Agente SNMP rodando... Aceitando requisições.")
snmpEngine.transportDispatcher.jobStarted(1)
try:
    snmpEngine.transportDispatcher.runDispatcher()
except:
    snmpEngine.transportDispatcher.closeDispatcher()