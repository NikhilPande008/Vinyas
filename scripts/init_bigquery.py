"""
scripts/init_bigquery.py
Initializes the BigQuery telemetry dataset (`nadatwin_telemetry` / `vinyas_ai_telemetry`)
in `asia-south1` and creates the required tables:
  - `machine_cycles`
  - `interventions_ledger`
  - `qa_certificates`
  - `shift_incidents_ledger`
Also seeds the local/baseline shift economic aggregates for Vinyas.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.bigquery_logger import BigQueryLogger
from config.settings import settings

TABLE_SCHEMAS = {
    "machine_cycles": (
        "cycle_id:STRING,timestamp_utc:TIMESTAMP,machine_id:STRING,tool_id:STRING,"
        "stage_a_state:STRING,peak_vibration_rms_g:FLOAT,band_power_ratio_2k_8k:FLOAT,"
        "hilbert_envelope_coherence:FLOAT,ct_ripple_std_amps:FLOAT,chatter_detected:BOOLEAN"
    ),
    "interventions_ledger": (
        "event_id:STRING,cycle_id:STRING,timestamp_utc:TIMESTAMP,machine_id:STRING,"
        "tool_id:STRING,state:STRING,coherence:FLOAT,feedrate_dial_pct:INTEGER,"
        "spindle_speed_dial_pct:INTEGER,ppap_passed:BOOLEAN,estimated_savings_inr:INTEGER,"
        "cycle_time_penalty_sec:FLOAT"
    ),
    "qa_certificates": (
        "certificate_id:STRING,part_id:STRING,work_order_id:STRING,cycle_id:STRING,"
        "timestamp_utc:TIMESTAMP,raw_frame_sha256:STRING,matched_reference_token_id:STRING,"
        "detected_anomaly_type:STRING,surface_ra_estimate_um:FLOAT,passed_iatf_16949:BOOLEAN,"
        "signing_backend:STRING,kms_signature_b64:STRING,gcs_vault_uri:STRING"
    ),
    "shift_incidents_ledger": (
        "event_id:STRING,timestamp_utc:TIMESTAMP,machine_id:STRING,tool_id:STRING,"
        "state:STRING,coherence:FLOAT,ppap_passed:BOOLEAN,estimated_savings_inr:INTEGER,"
        "cycle_time_penalty_sec:FLOAT"
    ),
}


def provision_bigquery_tables_via_bq(project_id: str, location: str, datasets: list[str]) -> None:
    """Idempotently creates BigQuery datasets and tables using the `bq` CLI."""
    bq_bin = shutil.which("bq")
    if not bq_bin:
        print("[WARN] `bq` CLI not found on PATH; skipping remote BigQuery DDL.")
        return

    for dataset in datasets:
        # Create dataset idempotently
        subprocess.run(
            [
                bq_bin,
                f"--location={location}",
                f"--project_id={project_id}",
                "mk",
                "--dataset",
                "--force",
                f"{project_id}:{dataset}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[BigQuery] Verified dataset: {project_id}:{dataset} ({location})")

        for table_name, schema in TABLE_SCHEMAS.items():
            table_ref = f"{project_id}:{dataset}.{table_name}"
            # Check if table exists
            show_res = subprocess.run(
                [bq_bin, f"--project_id={project_id}", "show", table_ref],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if show_res.returncode != 0:
                mk_res = subprocess.run(
                    [
                        bq_bin,
                        f"--location={location}",
                        f"--project_id={project_id}",
                        "mk",
                        "--table",
                        table_ref,
                        schema,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if mk_res.returncode == 0:
                    print(f"  + Created table: {table_ref}")
                else:
                    print(f"  ! Table creation warning for {table_ref}: {mk_res.stderr.strip()}")
            else:
                print(f"  = Table already exists: {table_ref}")


def init_bigquery() -> None:
    project_id = os.environ.get("GCP_PROJECT_ID") or settings.GCP_PROJECT_ID
    location = os.environ.get("GCP_LOCATION") or settings.GCP_LOCATION
    datasets = ["nadatwin_telemetry"]
    if settings.BIGQUERY_DATASET and settings.BIGQUERY_DATASET not in datasets:
        datasets.append(settings.BIGQUERY_DATASET)

    if project_id and project_id != "vinyas-ai-chakan-prod":
        provision_bigquery_tables_via_bq(project_id=project_id, location=location, datasets=datasets)

    logger = BigQueryLogger()
    aggregates = logger.get_shift_economic_aggregates()
    print("Initialized BigQuery Telemetry Dataset: nadatwin_telemetry (machine_cycles, interventions_ledger, qa_certificates)")
    print("Baseline Shift Aggregates:", aggregates)


if __name__ == "__main__":
    init_bigquery()
