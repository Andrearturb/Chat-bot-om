"""
Constantes de status utilizadas no sistema.

Estes valores são a fonte de verdade para os status possíveis de um serviço.
Devem ser mantidos em sincronia com os valores usados em `importer.py`
e com as constantes do frontend em `src/constants/status.js`.
"""

STATUS_BACKLOG = "BackLog"
STATUS_EM_ATENDIMENTO = "Em atendimento"
STATUS_AGENDADO = "Agendado"
STATUS_COMPLETA = "Completa"
STATUS_NAO_APROVADO = "Não aprovado"
