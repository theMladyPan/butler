# GCP Project and Region
variable "project_id" {
  default = "butler-453810"
}

variable "region" {
  default = "europe-central2"
}

# Cloud Run Environment Variables
variable "openai_api_key" {}

variable "qdrant_api_key" {}
variable "qdrant_endpoint" {
    default = "https://49ee7ad7-6e9f-451f-8638-3ce96ed1a774.europe-west3-0.gcp.cloud.qdrant.io"
}

variable "audio_folder" {
  default = "audio"
}

variable "transcript_folder" {
  default = "transcript"
}

variable "processed_folder" {
  default = "processed"
}
