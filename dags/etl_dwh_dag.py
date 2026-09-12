"""
dags/etl_dwh_dag.py
=====================
Orchestre le pipeline ETL (Extract → Transform → Load) puis la validation
qualité de la couche staging/DWH avec Airflow.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "mexora_dwh",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _run_etl():
    from main import run_pipeline
    run_pipeline(use_postgres=True)


def _run_data_quality():
    from data_quality.validate_dwh import valider_dwh_postgres
    ok = valider_dwh_postgres()
    if not ok:
        raise RuntimeError("[DATA QUALITY] Validation du DWH échouée.")


with DAG(
    dag_id="mexora_etl_dwh_pipeline",
    default_args=default_args,
    description="Pipeline ETL Extract-Transform-Load vers le Data Warehouse Mexora",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["mexora", "dwh", "etl"],
) as dag:

    etl = PythonOperator(task_id="run_etl_pipeline", python_callable=_run_etl)
    data_quality = PythonOperator(task_id="data_quality_check", python_callable=_run_data_quality)

    etl >> data_quality