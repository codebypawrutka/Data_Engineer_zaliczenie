# Obraz Airflow + Java (dla Sparka) + biblioteki potoku
FROM apache/airflow:3.3.2-python3.12

USER root
# Java jest potrzebna PySparkowi (Spark działa w JVM)
RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jre-headless \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/default-java

USER airflow
COPY requirements.txt /requirements.txt
# przypięcie apache-airflow do wersji obrazu, żeby pip go nie podmienił
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt
