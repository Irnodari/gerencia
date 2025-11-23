FROM debian:bullseye-slim

# Instala snmpd, ferramentas de rede e ping
RUN sed -i 's/main/main contrib non-free/g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y snmp snmpd snmp-mibs-downloader iproute2 iputils-ping procps net-tools

# Script de inicialização que cria as interfaces
COPY entrypoint.sh /entrypoint.sh
COPY snmpd.conf /etc/snmp/snmpd.conf
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]