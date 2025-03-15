
# Deploy Cloud Run Service
resource "google_cloud_run_service" "on_new_audio" {
  name     = "on-new-audio"
  location = var.region
  project  = var.project_id

  template {
    spec {
      containers {
        image = "europe-central2-docker.pkg.dev/${var.project_id}/cloud-run-repo/on-new-audio"

        env {
          name  = "OPENAI_API_KEY"
          value = var.openai_api_key
        }

        env {
          name  = "QDRANT_API_KEY"
          value = var.qdrant_api_key
        }

        env {
          name  = "AUDIO_FOLDER"
          value = var.audio_folder
        }

        env {
          name  = "TRANSCRIPT_FOLDER"
          value = var.transcript_folder
        }

        env {
          name  = "PROCESSED_FOLDER"
          value = var.processed_folder
        }
      }
    }
  }
}
