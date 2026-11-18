"""Camada de API (FastAPI) que serve a interface web em `web/`.

É deliberadamente FINA. O bot, os avaliadores das seis categorias e o runner
da bateria continuam sendo o mesmo código Python chamado pelos scripts de
terminal — aqui só existe transporte HTTP e o estado das conversas vivas.

A regra que não pode ser quebrada: `Instrumentador` continua sendo o ÚNICO
escritor do log JSONL. Todo o `eval/`, a bateria e os relatórios leem aquele
arquivo; uma API que gravasse turno por conta própria (ou deixasse de gravar)
faria a bateria continuar rodando e produzindo números errados, sem erro
nenhum. Ver `api/estado.py`.
"""
