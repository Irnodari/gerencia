#!/bin/bash

echo "--- Iniciando Coletor SNMP (Background) ---"
python -u coletor.py &

echo "--- Iniciando Dashboard Web ---"
python -u gerente.py