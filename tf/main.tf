provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable Required GCP Services
resource "google_project_service" "enable_services" {
  for_each = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "eventarc.googleapis.com"
  ])
  project = var.project_id
  service = each.key
}

# Create Artifact Registry for Cloud Run
resource "google_artifact_registry_repository" "cloud_run_repo" {
  provider      = google
  project       = var.project_id
  location      = var.region
  repository_id = "cloud-run-repo"
  format        = "DOCKER"
}
