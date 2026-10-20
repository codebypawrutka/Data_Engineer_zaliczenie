-- Wykonywane raz, przy pierwszym starcie Postgresa (pusty wolumen).
-- Baza olist_dwh (hurtownia) powstaje z POSTGRES_DB; tu dodajemy bazę metadanych Airflow.
CREATE DATABASE airflow;
