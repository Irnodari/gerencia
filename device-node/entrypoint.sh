#!/bin/bash

echo "--- Criando Interfaces e Rotas Reais ---"

GW_ALPHA="172.25.0.101"
GW_BETA="172.25.0.102"

for i in {0..9}
do
    # Cria par veth
    ip link add veth$i type veth peer name peer$i
    ip link set veth$i up
    ip link set peer$i up
    
    # IP Interno
    ip addr add 10.99.$i.1/24 dev veth$i
    
    # ROTAS (Balanceadas)
    if (( $i % 2 == 0 )); then
        ip route add 50.0.$i.0/24 via $GW_ALPHA dev veth$i onlink
    else
        ip route add 50.0.$i.0/24 via $GW_BETA dev veth$i onlink
    fi

    # Tráfego de fundo
    ping -f -i 0.1 10.99.$i.1 -I peer$i > /dev/null 2>&1 &
done

echo "--- Iniciando SNMPD (Modo Serviço) ---"
service snmpd start

# --- A MÁGICA: LOOP DE LIMPEZA DE CACHE ---
# Isso roda em background e força o SNMP a reler o Kernel a cada 3 segundos.
# É o que garante o "Real-Time" para a sua demonstração manual.
(
    echo "Iniciando Auto-Refresh do Cache SNMP..."
    while true; do
        sleep 3
        # O comando -HUP recarrega a config e limpa caches sem derrubar conexões
        pkill -HUP snmpd >/dev/null 2>&1
    done
) &

echo "--- Container Blindado Ativo ---"
tail -f /dev/null