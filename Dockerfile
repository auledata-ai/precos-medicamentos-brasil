# Imagem propria em vez de _PIP_ADDITIONAL_REQUIREMENTS.
#
# Aquela variavel reinstala as dependencias a cada arranque de cada
# container, atrasa o boot e nao fixa versoes. A propria documentacao do
# Airflow a marca como recurso de desenvolvimento. Uma imagem construida
# resolve os tres problemas e torna o ambiente reproduzivel.
FROM apache/airflow:2.10.4-python3.12

COPY requisitos-airflow.txt /tmp/requisitos-airflow.txt

RUN pip install --no-cache-dir -r /tmp/requisitos-airflow.txt
